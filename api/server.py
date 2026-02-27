"""
FastAPI backend for the trading dashboard.

Provides REST endpoints for:
- Account status and positions
- Portfolio history and equity curves
- Backtest results and metrics
- Strategy signals
- Trade history

Optimized for long-running operation with:
- Data caching with TTL to prevent memory leaks
- Periodic cache cleanup
- Resource management
"""

import os
import sys
import logging
import asyncio
import gc
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal
from functools import lru_cache
from dataclasses import dataclass, field
import json
import time
import threading

from fastapi import FastAPI, HTTPException, Query

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd


# ==================== Caching Infrastructure ====================

@dataclass
class CachedData:
    """Container for cached data with TTL."""
    data: Any
    timestamp: float
    ttl: float = 300.0  # 5 minutes default

    def is_expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl


class DataCache:
    """
    Thread-safe cache with TTL and automatic cleanup.

    Prevents memory leaks during long-running operation by:
    - Expiring stale data
    - Periodic cleanup of expired entries
    - Maximum size limits
    """

    def __init__(self, max_size: int = 100, cleanup_interval: float = 300.0):
        self._cache: Dict[str, CachedData] = {}
        self._lock = threading.Lock()
        self._max_size = max_size
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        self._maybe_cleanup()
        with self._lock:
            if key in self._cache:
                cached = self._cache[key]
                if not cached.is_expired():
                    return cached.data
                else:
                    del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: float = 300.0) -> None:
        """Set cached value with TTL."""
        self._maybe_cleanup()
        with self._lock:
            # Enforce max size
            if len(self._cache) >= self._max_size:
                self._evict_oldest()
            self._cache[key] = CachedData(data=value, timestamp=time.time(), ttl=ttl)

    def _evict_oldest(self) -> None:
        """Evict oldest cache entries (must hold lock)."""
        if not self._cache:
            return
        # Find and remove oldest
        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
        del self._cache[oldest_key]

    def _maybe_cleanup(self) -> None:
        """Periodically clean up expired entries."""
        if time.time() - self._last_cleanup < self._cleanup_interval:
            return
        with self._lock:
            expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
            for key in expired_keys:
                del self._cache[key]
            self._last_cleanup = time.time()
            if expired_keys:
                logger.debug(f"Cache cleanup: removed {len(expired_keys)} expired entries")

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()
        gc.collect()


# Global cache instance
_data_cache = DataCache(max_size=50, cleanup_interval=300.0)
_signal_cache = DataCache(max_size=20, cleanup_interval=60.0)  # Shorter TTL for signals

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from data.storage import TradingDatabase
from data.polygon_client import RateLimitedPolygonClient, PolygonClientError
from strategies.dual_momentum import DualMomentumStrategy
from strategies.swing_momentum import SwingMomentumStrategy
from strategies.ml_momentum import MLMomentumStrategy
from strategies.pairs_trading import PairsTradingStrategy
from strategies.volatility_breakout import VolatilityBreakoutStrategy
from backtest.engine import BacktestEngine
from backtest.metrics import print_metrics
from execution.alpaca_client import AlpacaClient, AlpacaClientError
from risk.circuit_breakers import CircuitBreaker
from risk.position_sizing import PositionSizer

# Initialize FastAPI
app = FastAPI(
    title="Quant Trading Dashboard API",
    description="Backend API for the quantitative trading dashboard",
    version="1.0.0"
)

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components (lazy loading)
_db: Optional[TradingDatabase] = None
_alpaca: Optional[AlpacaClient] = None
_polygon: Optional[RateLimitedPolygonClient] = None
_dual_momentum: Optional[DualMomentumStrategy] = None
_swing_momentum: Optional[SwingMomentumStrategy] = None
_ml_momentum: Optional[MLMomentumStrategy] = None
_pairs_trading: Optional[PairsTradingStrategy] = None
_volatility_breakout: Optional[VolatilityBreakoutStrategy] = None


def get_db() -> TradingDatabase:
    global _db
    if _db is None:
        _db = TradingDatabase()
    return _db


def get_alpaca() -> AlpacaClient:
    global _alpaca
    if _alpaca is None:
        _alpaca = AlpacaClient(paper=True)
    return _alpaca


def get_polygon() -> RateLimitedPolygonClient:
    global _polygon
    if _polygon is None:
        _polygon = RateLimitedPolygonClient()
    return _polygon


def get_dual_momentum() -> DualMomentumStrategy:
    global _dual_momentum
    if _dual_momentum is None:
        _dual_momentum = DualMomentumStrategy()
    return _dual_momentum


def get_swing_momentum() -> SwingMomentumStrategy:
    global _swing_momentum
    if _swing_momentum is None:
        _swing_momentum = SwingMomentumStrategy()
    return _swing_momentum


def get_ml_momentum() -> MLMomentumStrategy:
    global _ml_momentum
    if _ml_momentum is None:
        _ml_momentum = MLMomentumStrategy()
    return _ml_momentum


def get_pairs_trading() -> PairsTradingStrategy:
    global _pairs_trading
    if _pairs_trading is None:
        _pairs_trading = PairsTradingStrategy()
    return _pairs_trading


def get_volatility_breakout() -> VolatilityBreakoutStrategy:
    global _volatility_breakout
    if _volatility_breakout is None:
        _volatility_breakout = VolatilityBreakoutStrategy()
    return _volatility_breakout


def get_strategy(name: str = "dual_momentum"):
    """Get strategy by name."""
    if name == "swing_momentum":
        return get_swing_momentum()
    elif name == "ml_momentum":
        return get_ml_momentum()
    elif name == "pairs_trading":
        return get_pairs_trading()
    elif name == "volatility_breakout":
        return get_volatility_breakout()
    return get_dual_momentum()


def get_cached_market_data(symbols: List[str], cache_key: str = "default") -> Dict[str, pd.DataFrame]:
    """
    Get market data with caching to prevent repeated database loads.

    Only loads last 120 trading days to limit memory usage.
    Cache expires after 5 minutes.
    """
    full_key = f"market_data_{cache_key}_{','.join(sorted(symbols))}"

    cached = _data_cache.get(full_key)
    if cached is not None:
        return cached

    # Load fresh data (limited to last 120 days for memory efficiency)
    db = get_db()
    start_date = date.today() - timedelta(days=180)  # ~120 trading days
    data = db.get_multiple_symbols(symbols, start_date=start_date)

    # Cache for 5 minutes
    _data_cache.set(full_key, data, ttl=300.0)

    return data


def clear_caches() -> None:
    """Clear all caches - useful for memory management."""
    global _data_cache, _signal_cache
    _data_cache.clear()
    _signal_cache.clear()
    gc.collect()
    logger.info("Caches cleared")


# ==================== Response Models ====================

class AccountStatus(BaseModel):
    equity: float
    cash: float
    buying_power: float
    portfolio_value: float
    daily_pnl: float
    daily_return: float
    total_return: float
    status: str
    # New fields for cash management
    available_cash: Optional[float] = None
    locked_cash: Optional[float] = None
    pending_buy_orders: Optional[int] = None


class Position(BaseModel):
    symbol: str
    quantity: int
    market_value: float
    cost_basis: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    current_price: float
    avg_entry_price: float


class Signal(BaseModel):
    date: str
    symbol: str
    signal_type: str
    strength: float
    momentum_scores: Optional[List[Dict]] = None


class Trade(BaseModel):
    id: int
    timestamp: str
    symbol: str
    action: str
    quantity: float
    price: float
    value: float


class BacktestResult(BaseModel):
    strategy: str
    start_date: str
    end_date: str
    initial_capital: float
    final_equity: float
    total_return: float
    cagr: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    win_rate: float
    trade_count: int
    equity_curve: List[Dict[str, Any]]


class RiskStatus(BaseModel):
    can_trade: bool
    halt_reason: Optional[str]
    daily_return: str
    daily_limit: str
    weekly_return: str
    weekly_limit: str
    drawdown: str
    drawdown_limit: str


# ==================== Endpoints ====================

@app.get("/")
async def root():
    return {"message": "Quant Trading Dashboard API", "version": "1.0.0"}


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/account", response_model=AccountStatus)
async def get_account_status():
    """Get current account status from Alpaca."""
    try:
        alpaca = get_alpaca()
        account = alpaca.get_account()

        # Calculate daily P&L (simplified - from positions)
        positions = alpaca.get_positions()
        daily_pnl = sum(p.get("unrealized_pl", 0) for p in positions.values())

        equity = account["equity"]
        initial_capital = 100000  # Assumed starting capital
        total_return = (equity - initial_capital) / initial_capital
        daily_return = daily_pnl / equity if equity > 0 else 0

        # Get cash availability status
        from execution.cash_manager import CashManager
        cash_mgr = CashManager(alpaca)
        cash_status = cash_mgr.get_cash_status()

        return AccountStatus(
            equity=equity,
            cash=account["cash"],
            buying_power=account["buying_power"],
            portfolio_value=account["portfolio_value"],
            daily_pnl=daily_pnl,
            daily_return=daily_return,
            total_return=total_return,
            status=str(account["status"]),
            available_cash=cash_status.get('available_cash'),
            locked_cash=cash_status.get('locked_cash'),
            pending_buy_orders=cash_status.get('pending_buy_orders')
        )
    except AlpacaClientError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/positions", response_model=List[Position])
async def get_positions():
    """Get current positions from Alpaca."""
    try:
        alpaca = get_alpaca()
        positions = alpaca.get_positions()

        return [
            Position(
                symbol=p["symbol"],
                quantity=p["qty"],
                market_value=p["market_value"],
                cost_basis=p["cost_basis"],
                unrealized_pnl=p["unrealized_pl"],
                unrealized_pnl_pct=p["unrealized_plpc"],
                current_price=p["current_price"],
                avg_entry_price=p["avg_entry_price"]
            )
            for p in positions.values()
        ]
    except AlpacaClientError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/signal")
async def get_current_signal(strategy: str = Query("dual_momentum")):
    """Get current trading signal from a strategy."""
    try:
        strat = get_strategy(strategy)

        # Load data with caching - get all symbols for both strategies
        all_symbols = list(set(get_dual_momentum().universe + get_swing_momentum().universe))
        data = get_cached_market_data(all_symbols, cache_key="signals")

        # Check if we have data
        if not data or all(df.empty for df in data.values()):
            return {"signal": None, "message": "No market data available"}

        # Get current signal
        if strategy == "swing_momentum":
            signals = strat.get_current_signal(data)
            if signals and len(signals) > 0:
                signal = signals[0]  # Return strongest signal
                return Signal(
                    date=signal.date.isoformat(),
                    symbol=signal.symbol,
                    signal_type=signal.signal_type.value,
                    strength=signal.strength,
                    momentum_scores=None
                )
        else:
            signal = strat.get_current_signal(data)
            if signal:
                return Signal(
                    date=signal.date.isoformat(),
                    symbol=signal.symbol,
                    signal_type=signal.signal_type.value,
                    strength=signal.strength,
                    momentum_scores=signal.metadata.get("momentum_scores") if signal.metadata else None
                )

        return {"signal": None, "message": "No signal generated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/signals/all")
async def get_all_signals():
    """Get current trading signals from ALL strategies."""
    try:
        # Check signal cache first (1 minute TTL)
        cache_key = "all_signals"
        cached_result = _signal_cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        # Get all symbols for all strategies
        all_symbols = list(set(
            get_dual_momentum().universe +
            get_swing_momentum().universe +
            get_pairs_trading().universe +
            get_volatility_breakout().universe
        ))
        data = get_cached_market_data(all_symbols, cache_key="all_signals")

        if not data or all(df.empty for df in data.values()):
            return {"signals": [], "message": "No market data available"}

        all_signals = []

        # Dual Momentum signals
        dm_strat = get_dual_momentum()
        dm_signal = dm_strat.get_current_signal(data)
        if dm_signal:
            all_signals.append({
                "strategy": "Dual Momentum",
                "date": dm_signal.date.isoformat(),
                "symbol": dm_signal.symbol,
                "signal_type": dm_signal.signal_type.value,
                "strength": dm_signal.strength,
                "description": "Monthly rebalancing based on 12-month momentum",
                "metadata": dm_signal.metadata
            })

        # Swing Momentum signals
        sm_strat = get_swing_momentum()
        sm_signals = sm_strat.get_current_signal(data)
        for signal in sm_signals[:5]:  # Top 5 signals
            all_signals.append({
                "strategy": "Swing Momentum",
                "date": signal.date.isoformat(),
                "symbol": signal.symbol,
                "signal_type": signal.signal_type.value,
                "strength": signal.strength,
                "description": f"RSI: {signal.metadata.get('rsi', 0):.1f}, Momentum: {signal.metadata.get('momentum_20d', 0)*100:.1f}%",
                "metadata": signal.metadata
            })

        # ML Momentum signals
        try:
            ml_strat = get_ml_momentum()
            ml_signals = ml_strat.get_current_signal(data)
            for signal in ml_signals[:5]:  # Top 5 signals
                pred_ret = signal.metadata.get('predicted_return', 0) if signal.metadata else 0
                confidence = signal.metadata.get('confidence', 0) if signal.metadata else 0
                all_signals.append({
                    "strategy": "ML Momentum",
                    "date": signal.date.isoformat(),
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type.value,
                    "strength": signal.strength,
                    "description": f"Predicted: {pred_ret*100:.2f}%, Confidence: {confidence:.0%}",
                    "metadata": signal.metadata
                })
        except Exception as e:
            logger.warning(f"ML strategy signals failed: {e}")

        # Pairs Trading signals
        try:
            pt_strat = get_pairs_trading()
            pt_signals = pt_strat.get_current_signal(data)
            for signal in pt_signals[:10]:  # Top 10 signals (pairs generate 2 signals each)
                z_score = signal.metadata.get('z_score', 0) if signal.metadata else 0
                pair_symbol = signal.metadata.get('pair_symbol', '') if signal.metadata else ''
                correlation = signal.metadata.get('correlation', 0) if signal.metadata else 0
                position = signal.metadata.get('position', '') if signal.metadata else ''
                all_signals.append({
                    "strategy": "Pairs Trading",
                    "date": signal.date.isoformat(),
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type.value,
                    "strength": signal.strength,
                    "description": f"Pair: {signal.symbol}/{pair_symbol}, Z-score: {z_score:.2f}, {position.upper()}",
                    "metadata": signal.metadata
                })
        except Exception as e:
            logger.warning(f"Pairs trading signals failed: {e}")

        # Volatility Breakout signals
        try:
            vb_strat = get_volatility_breakout()
            vb_signals = vb_strat.get_current_signal(data)
            for signal in vb_signals[:5]:  # Top 5 signals
                volatility = signal.metadata.get('volatility', 0) if signal.metadata else 0
                momentum = signal.metadata.get('momentum_50d', 0) if signal.metadata else 0
                all_signals.append({
                    "strategy": "Volatility Breakout",
                    "date": signal.date.isoformat(),
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type.value,
                    "strength": signal.strength,
                    "description": f"Vol: {volatility*100:.1f}%, Momentum: {momentum*100:.1f}%, Donchian breakout",
                    "metadata": signal.metadata
                })
        except Exception as e:
            logger.warning(f"Volatility breakout signals failed: {e}")

        result = {"signals": all_signals, "count": len(all_signals)}

        # Cache result for 1 minute
        _signal_cache.set(cache_key, result, ttl=60.0)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trades", response_model=List[Trade])
async def get_trades(
    limit: int = Query(50, ge=1, le=500),
    symbol: Optional[str] = None
):
    """Get trade history from database."""
    try:
        db = get_db()

        # Query directly from SQLite to avoid pandas timestamp parsing issues
        import sqlite3
        conn = sqlite3.connect(db.db_path)

        if symbol:
            query = "SELECT id, timestamp, symbol, action, quantity, price FROM trades WHERE symbol = ? ORDER BY id DESC LIMIT ?"
            cursor = conn.execute(query, (symbol, limit))
        else:
            query = "SELECT id, timestamp, symbol, action, quantity, price FROM trades ORDER BY id DESC LIMIT ?"
            cursor = conn.execute(query, (limit,))

        trades = []
        for row in cursor:
            trade_id, ts, sym, action, qty, price = row

            # Convert timestamp to ISO format for JavaScript compatibility
            if ts and ts != 'None' and ts != 'NaT':
                # Replace space with T for ISO format, handle timezone
                ts_iso = ts.replace(' ', 'T')
                # If no timezone, assume UTC
                if '+' not in ts_iso and 'Z' not in ts_iso:
                    ts_iso = ts_iso + 'Z'
            else:
                # Fallback for invalid timestamps
                ts_iso = datetime.now().isoformat() + 'Z'

            trades.append(Trade(
                id=int(trade_id),
                timestamp=ts_iso,
                symbol=sym,
                action=action,
                quantity=float(qty),
                price=float(price),
                value=float(qty * price)
            ))

        conn.close()
        return trades
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/equity-curve")
async def get_equity_curve():
    """Get portfolio equity curve from database."""
    try:
        db = get_db()
        history = db.get_portfolio_history()

        if history.empty:
            # If no portfolio history, return empty with message
            return {"data": [], "message": "No portfolio history available yet"}

        # Convert to list of dicts
        data = []
        for idx, row in history.iterrows():
            data.append({
                "date": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                "equity": float(row["equity"]),
                "cash": float(row["cash"]),
                "daily_return": float(row["daily_return"]) if pd.notna(row.get("daily_return")) else 0,
                "drawdown": float(row["drawdown"]) if pd.notna(row.get("drawdown")) else 0
            })

        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market-data/{symbol}")
async def get_market_data(
    symbol: str,
    days: int = Query(30, ge=1, le=365)
):
    """Get historical market data for a symbol."""
    try:
        db = get_db()
        start_date = date.today() - timedelta(days=days)

        df = db.get_daily_bars(symbol.upper(), start_date=start_date)

        if df.empty:
            return {"data": [], "message": f"No data for {symbol}"}

        data = []
        for idx, row in df.iterrows():
            data.append({
                "date": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": int(row["volume"])
            })

        return {"symbol": symbol.upper(), "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/backtest", response_model=BacktestResult)
async def run_backtest(
    start_date: str = Query("2023-01-01"),
    end_date: str = Query("2025-12-31"),
    initial_capital: float = Query(10000)
):
    """Run a backtest and return results."""
    try:
        db = get_db()
        strategy = get_strategy()

        # Load data
        data = db.get_multiple_symbols(strategy.universe)

        if not data or all(df.empty for df in data.values()):
            raise HTTPException(status_code=400, detail="No market data available for backtest")

        # Set up backtest params
        params = strategy.get_backtest_params()
        params.start_date = start_date
        params.end_date = end_date
        params.initial_capital = initial_capital

        # Run backtest
        engine = BacktestEngine(strategy, data, params)
        result = engine.run()

        # Build equity curve data
        equity_curve = [
            {"date": idx.isoformat() if hasattr(idx, 'isoformat') else str(idx), "equity": float(val)}
            for idx, val in result.equity_curve.items()
        ]

        return BacktestResult(
            strategy=result.strategy_name,
            start_date=str(result.start_date),
            end_date=str(result.end_date),
            initial_capital=result.initial_capital,
            final_equity=result.final_equity,
            total_return=result.metrics.total_return,
            cagr=result.metrics.cagr,
            sharpe_ratio=result.metrics.sharpe_ratio,
            sortino_ratio=result.metrics.sortino_ratio,
            max_drawdown=result.metrics.max_drawdown,
            win_rate=result.metrics.win_rate,
            trade_count=result.trade_count,
            equity_curve=equity_curve
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/risk-status", response_model=RiskStatus)
async def get_risk_status():
    """Get current risk status."""
    try:
        alpaca = get_alpaca()
        account = alpaca.get_account()

        # Create circuit breaker with current equity
        circuit_breaker = CircuitBreaker(initial_equity=account["equity"])
        circuit_breaker.update(account["equity"])

        summary = circuit_breaker.get_risk_summary()

        return RiskStatus(
            can_trade=summary["can_trade"],
            halt_reason=summary["halt_reason"],
            daily_return=summary["daily_return"],
            daily_limit=summary["daily_limit"],
            weekly_return=summary["weekly_return"],
            weekly_limit=summary["weekly_limit"],
            drawdown=summary["drawdown"],
            drawdown_limit=summary["drawdown_limit"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cash-status")
async def get_cash_status():
    """Get detailed cash availability status."""
    try:
        from execution.cash_manager import CashManager

        alpaca = get_alpaca()
        cash_mgr = CashManager(alpaca)

        status = cash_mgr.get_cash_status()

        # Add cash utilization percentage
        if status['total_cash'] > 0:
            status['cash_utilization_pct'] = (
                status['locked_cash'] / status['total_cash'] * 100
            )
        else:
            status['cash_utilization_pct'] = 0.0

        return {
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/strategy-performance")
async def get_strategy_performance():
    """Get performance comparison data for strategies."""
    try:
        # Check cache (5 minute TTL for performance data)
        cache_key = "strategy_performance"
        cached_result = _data_cache.get(cache_key)
        if cached_result is not None:
            return cached_result

        # Get all symbols for all strategies
        all_symbols = list(set(
            get_dual_momentum().universe +
            get_swing_momentum().universe +
            get_pairs_trading().universe +
            get_volatility_breakout().universe
        ))
        data = get_cached_market_data(all_symbols, cache_key="performance")

        if not data or all(df.empty for df in data.values()):
            return {"strategies": [], "message": "No data available"}

        strategies_results = []

        # Run backtest for dual momentum
        try:
            dm_strat = get_dual_momentum()
            dm_params = dm_strat.get_backtest_params()
            dm_engine = BacktestEngine(dm_strat, data, dm_params)
            dm_result = dm_engine.run()

            strategies_results.append({
                "name": "Dual Momentum",
                "description": "Monthly rebalancing - picks strongest of SPY/QQQ or moves to bonds",
                "total_return": dm_result.metrics.total_return,
                "sharpe_ratio": dm_result.metrics.sharpe_ratio,
                "max_drawdown": dm_result.metrics.max_drawdown,
                "win_rate": dm_result.metrics.win_rate,
                "trade_count": dm_result.trade_count,
                "rebalance_frequency": "Monthly",
                "status": "active"
            })
        except Exception as e:
            logger.error(f"Dual Momentum backtest failed: {e}")

        # Run backtest for swing momentum
        try:
            sm_strat = get_swing_momentum()
            sm_params = sm_strat.get_backtest_params()
            sm_engine = BacktestEngine(sm_strat, data, sm_params)
            sm_result = sm_engine.run()

            strategies_results.append({
                "name": "Swing Momentum",
                "description": "Daily signals using RSI, moving averages, and momentum",
                "total_return": sm_result.metrics.total_return,
                "sharpe_ratio": sm_result.metrics.sharpe_ratio,
                "max_drawdown": sm_result.metrics.max_drawdown,
                "win_rate": sm_result.metrics.win_rate,
                "trade_count": sm_result.trade_count,
                "rebalance_frequency": "Daily",
                "status": "active"
            })
        except Exception as e:
            logger.error(f"Swing Momentum backtest failed: {e}")

        # Get benchmark (SPY buy-and-hold) performance
        spy_data = data.get("SPY")
        if spy_data is not None and not spy_data.empty:
            spy_return = (spy_data["close"].iloc[-1] - spy_data["close"].iloc[0]) / spy_data["close"].iloc[0]
            spy_returns = spy_data["close"].pct_change().dropna()
            spy_sharpe = (spy_returns.mean() * 252) / (spy_returns.std() * (252 ** 0.5)) if spy_returns.std() > 0 else 0

            # Calculate max drawdown
            cumulative = (1 + spy_returns).cumprod()
            running_max = cumulative.cummax()
            drawdown = (cumulative - running_max) / running_max
            spy_max_dd = drawdown.min()
        else:
            spy_return = 0
            spy_sharpe = 0
            spy_max_dd = 0

        strategies_results.append({
            "name": "S&P 500 (Benchmark)",
            "description": "Buy and hold SPY - this is what we're trying to beat!",
            "total_return": spy_return,
            "sharpe_ratio": spy_sharpe,
            "max_drawdown": spy_max_dd,
            "win_rate": 0,
            "trade_count": 1,
            "rebalance_frequency": "Never",
            "status": "benchmark"
        })

        result = {"strategies": strategies_results}

        # Cache for 5 minutes
        _data_cache.set(cache_key, result, ttl=300.0)

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/market-status")
async def get_market_status():
    """Get current market status."""
    try:
        alpaca = get_alpaca()
        market = alpaca.get_market_hours()

        return {
            "is_open": market["is_open"],
            "next_open": market["next_open"],
            "next_close": market["next_close"]
        }
    except AlpacaClientError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cache/clear")
async def clear_cache():
    """Clear all caches - useful for memory management."""
    clear_caches()
    return {"status": "ok", "message": "All caches cleared"}


@app.get("/api/pairs-status")
async def get_pairs_status():
    """Get status of all trading pairs."""
    try:
        pt_strat = get_pairs_trading()

        # Get all symbols with caching
        all_symbols = pt_strat.universe
        data = get_cached_market_data(all_symbols, cache_key="pairs")

        if not data or all(df.empty for df in data.values()):
            return {"pairs": [], "message": "No market data available"}

        # Get pair statuses
        pair_statuses = pt_strat.get_pair_status(data)

        return {
            "pairs": pair_statuses,
            "count": len(pair_statuses),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bot-insights")
async def get_bot_insights():
    """
    Get comprehensive bot insights including:
    - Current positions with strategy attribution
    - Pending actions (trailing stops, scale out, pyramiding)
    - Active signals the bot is considering
    - Market phase and volatility regime
    """
    try:
        from strategies.simple_momentum import SimpleMomentumStrategy
        from strategies.pairs_trading import PairsTradingStrategy
        from strategies.base import SignalType

        # Get current positions from Alpaca
        alpaca = get_alpaca()
        positions = alpaca.get_positions()
        account = alpaca.get_account()

        # Get market data
        all_symbols = list(set(
            get_dual_momentum().universe +
            get_swing_momentum().universe +
            get_pairs_trading().universe
        ))

        # Add simple momentum symbols
        simple_symbols = ["QQQ", "SPY", "XLK", "SOXX", "IWM", "XLF", "XLE", "ARKK"]
        all_symbols = list(set(all_symbols + simple_symbols))

        data = get_cached_market_data(all_symbols, cache_key="bot_insights")

        # Get signals from Simple Momentum (most active strategy)
        simple_strat = SimpleMomentumStrategy()
        simple_signals = []
        if data:
            valid_data = {s: df for s, df in data.items() if not df.empty}
            try:
                sigs = simple_strat.get_current_signal(valid_data)
                # Get only today's signals (most recent)
                today_signals = {}
                for sig in sigs:
                    key = (sig.symbol, sig.signal_type.value)
                    if key not in today_signals or sig.strength > today_signals[key]['strength']:
                        today_signals[key] = {
                            "symbol": sig.symbol,
                            "action": sig.signal_type.value,
                            "strength": round(sig.strength, 2),
                            "momentum": round(sig.metadata.get('momentum', 0), 1),
                            "in_position": sig.symbol in positions,
                            "strategy": "Simple Momentum"
                        }
                simple_signals = list(today_signals.values())
                # Sort by strength
                simple_signals.sort(key=lambda x: x['strength'], reverse=True)
            except Exception as e:
                logger.warning(f"Error getting simple momentum signals: {e}")

        # Get pairs trading signals
        pairs_signals = []
        try:
            pairs_strat = get_pairs_trading()
            pairs_sigs = pairs_strat.get_current_signal(data)
            for sig in pairs_sigs[:5]:
                pairs_signals.append({
                    "symbol": sig.symbol,
                    "action": sig.signal_type.value,
                    "strength": round(sig.strength, 2),
                    "in_position": sig.symbol in positions,
                    "strategy": "Pairs Trading"
                })
        except Exception as e:
            logger.warning(f"Error getting pairs signals: {e}")

        # Calculate pending actions for each position
        pending_actions = []
        position_details = []

        for symbol, pos in positions.items():
            pnl_pct = pos['unrealized_plpc'] * 100
            entry = pos['avg_entry_price']
            current = pos['current_price']
            qty = pos['qty']

            # Determine strategy based on signals
            strategy = "Unknown"
            for sig in simple_signals:
                if sig['symbol'] == symbol:
                    strategy = sig['strategy']
                    break
            for sig in pairs_signals:
                if sig['symbol'] == symbol:
                    strategy = sig['strategy']
                    break

            # Get stop loss and highest price from database
            stop_loss = entry * 0.96  # Default 4% stop
            highest_price = current
            try:
                import sqlite3
                conn = sqlite3.connect('data/quant.db')
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT stop_loss, highest_price, strategy FROM position_tracker WHERE symbol = ?',
                    (symbol,)
                )
                row = cursor.fetchone()
                if row:
                    stop_loss = row[0] or stop_loss
                    highest_price = row[1] or current
                    if row[2] and row[2] != 'unknown':
                        strategy = row[2].replace('_', ' ').title()
                # Fallback: check trades table for most recent trade
                if strategy == "Unknown":
                    cursor.execute(
                        'SELECT strategy FROM trades WHERE symbol = ? ORDER BY timestamp DESC LIMIT 1',
                        (symbol,)
                    )
                    trade_row = cursor.fetchone()
                    if trade_row and trade_row[0]:
                        strategy = trade_row[0].replace('_', ' ').title()
                conn.close()
            except Exception:
                pass

            stop_distance_pct = (current - stop_loss) / current if current > 0 else 0

            # Position details
            position_details.append({
                "symbol": symbol,
                "quantity": qty,
                "entry_price": round(entry, 2),
                "current_price": round(current, 2),
                "pnl_pct": round(pnl_pct, 2),
                "pnl_dollars": round(pos['unrealized_pl'], 2),
                "market_value": round(pos['market_value'], 2),
                "strategy": strategy,
                "stop_loss": round(stop_loss, 2),
                "highest_price": round(highest_price, 2),
                "stop_distance_pct": round(stop_distance_pct, 4)
            })

            # Determine pending actions
            actions = []

            # Scale out at +5%
            if pnl_pct >= 5:
                actions.append({
                    "action": "SCALE_OUT",
                    "description": f"Take 50% profit at +{pnl_pct:.1f}%",
                    "priority": "high",
                    "target_qty": int(qty / 2)
                })

            # Pyramiding opportunity at +3%
            elif 3 <= pnl_pct < 5:
                actions.append({
                    "action": "PYRAMID",
                    "description": f"Consider adding to winner (+{pnl_pct:.1f}%)",
                    "priority": "medium"
                })

            # Fast exit at -2%
            if pnl_pct <= -2:
                actions.append({
                    "action": "FAST_EXIT",
                    "description": f"Cut loss at {pnl_pct:.1f}% (before -4% stop)",
                    "priority": "high"
                })

            # Trailing stop update
            if pnl_pct > 0:
                new_stop = round(current * 0.97, 2)  # 3% trailing
                actions.append({
                    "action": "TRAILING_STOP",
                    "description": f"Raise stop to ${new_stop}",
                    "priority": "low",
                    "new_stop": new_stop
                })

            # Check for SELL signal on position
            for sig in simple_signals:
                if sig['symbol'] == symbol and sig['action'] == 'SELL':
                    actions.append({
                        "action": "SELL_SIGNAL",
                        "description": f"Strategy says SELL (momentum: {sig['momentum']}%)",
                        "priority": "high"
                    })
                    break

            if actions:
                pending_actions.append({
                    "symbol": symbol,
                    "actions": actions
                })

        # Signals the bot is considering for NEW positions
        new_position_candidates = []
        for sig in simple_signals[:10]:
            if sig['action'] == 'BUY' and not sig['in_position']:
                new_position_candidates.append({
                    "symbol": sig['symbol'],
                    "strategy": sig['strategy'],
                    "strength": sig['strength'],
                    "momentum": sig['momentum'],
                    "reason": f"Strong momentum ({sig['momentum']}%)"
                })

        # Market phase (using US Eastern time)
        import pytz
        us_eastern = pytz.timezone('US/Eastern')
        now_et = datetime.now(us_eastern)
        hour = now_et.hour
        minute = now_et.minute

        if hour < 9 or (hour == 9 and minute < 30):
            market_phase = "pre_market"
        elif hour == 9 and minute < 45:
            market_phase = "opening_volatility"
        elif hour < 11 or (hour == 11 and minute < 30):
            market_phase = "morning_session"
        elif hour < 14:
            market_phase = "midday_lull"
        elif hour < 15 or (hour == 15 and minute < 30):
            market_phase = "afternoon_session"
        elif hour < 16:
            market_phase = "closing_action"
        else:
            market_phase = "after_hours"

        return {
            "timestamp": datetime.now().isoformat(),
            "account": {
                "equity": round(account['equity'], 2),
                "cash": round(account['cash'], 2),
                "buying_power": round(account['buying_power'], 2),
                "position_count": len(positions)
            },
            "market_phase": market_phase,
            "positions": position_details,
            "pending_actions": pending_actions,
            "new_position_candidates": new_position_candidates[:5],
            "active_signals": {
                "simple_momentum": simple_signals[:10],
                "pairs_trading": pairs_signals[:5]
            },
            "summary": {
                "total_positions": len(positions),
                "profitable_positions": len([p for p in position_details if p['pnl_pct'] > 0]),
                "losing_positions": len([p for p in position_details if p['pnl_pct'] < 0]),
                "pending_action_count": sum(len(pa['actions']) for pa in pending_actions),
                "new_candidates": len(new_position_candidates)
            }
        }

    except Exception as e:
        logger.error(f"Error getting bot insights: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Daily Journal ====================

class DailyJournalEntry(BaseModel):
    id: Optional[int] = None
    date: str
    starting_equity: float
    ending_equity: float
    daily_pnl: float
    daily_pnl_pct: float
    notes: Optional[str] = None


class DailyJournalCreate(BaseModel):
    date: str
    starting_equity: float
    ending_equity: float
    notes: Optional[str] = None


@app.get("/api/journal", response_model=List[DailyJournalEntry])
async def get_journal(
    limit: int = Query(30, ge=1, le=365),
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
):
    """Get daily journal entries."""
    try:
        db = get_db()

        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None

        journal_df = db.get_daily_journal(start_date=start, end_date=end, limit=limit)

        if journal_df.empty:
            return []

        return [
            DailyJournalEntry(
                id=int(row["id"]),
                date=str(row["date"]),
                starting_equity=float(row["starting_equity"]),
                ending_equity=float(row["ending_equity"]),
                daily_pnl=float(row["daily_pnl"]),
                daily_pnl_pct=float(row["daily_pnl_pct"]),
                notes=row["notes"] if row["notes"] else None
            )
            for _, row in journal_df.iterrows()
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/journal", response_model=DailyJournalEntry)
async def create_journal_entry(entry: DailyJournalCreate):
    """Create or update a daily journal entry."""
    try:
        db = get_db()

        journal_date = date.fromisoformat(entry.date)
        entry_id = db.save_daily_journal(
            journal_date=journal_date,
            starting_equity=entry.starting_equity,
            ending_equity=entry.ending_equity,
            notes=entry.notes
        )

        daily_pnl = entry.ending_equity - entry.starting_equity
        daily_pnl_pct = (daily_pnl / entry.starting_equity * 100) if entry.starting_equity > 0 else 0

        return DailyJournalEntry(
            id=entry_id,
            date=entry.date,
            starting_equity=entry.starting_equity,
            ending_equity=entry.ending_equity,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            notes=entry.notes
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/journal/{journal_date}")
async def delete_journal_entry(journal_date: str):
    """Delete a daily journal entry."""
    try:
        db = get_db()
        deleted = db.delete_daily_journal(date.fromisoformat(journal_date))

        if not deleted:
            raise HTTPException(status_code=404, detail="Journal entry not found")

        return {"status": "deleted", "date": journal_date}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/journal/summary")
async def get_journal_summary():
    """Get summary statistics for the journal."""
    try:
        db = get_db()
        journal_df = db.get_daily_journal(limit=365)

        if journal_df.empty:
            return {
                "total_entries": 0,
                "total_pnl": 0,
                "total_pnl_pct": 0,
                "winning_days": 0,
                "losing_days": 0,
                "best_day": None,
                "worst_day": None,
                "average_daily_pnl": 0,
                "current_streak": 0
            }

        total_pnl = journal_df["daily_pnl"].sum()
        winning_days = len(journal_df[journal_df["daily_pnl"] > 0])
        losing_days = len(journal_df[journal_df["daily_pnl"] < 0])

        best_idx = journal_df["daily_pnl"].idxmax()
        worst_idx = journal_df["daily_pnl"].idxmin()

        # Calculate current streak
        streak = 0
        for _, row in journal_df.iterrows():
            if row["daily_pnl"] > 0:
                if streak >= 0:
                    streak += 1
                else:
                    break
            elif row["daily_pnl"] < 0:
                if streak <= 0:
                    streak -= 1
                else:
                    break
            else:
                break

        return {
            "total_entries": len(journal_df),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(journal_df["daily_pnl_pct"].sum(), 2),
            "winning_days": winning_days,
            "losing_days": losing_days,
            "win_rate": round(winning_days / len(journal_df) * 100, 1) if len(journal_df) > 0 else 0,
            "best_day": {
                "date": str(journal_df.loc[best_idx, "date"]),
                "pnl": round(journal_df.loc[best_idx, "daily_pnl"], 2),
                "pct": round(journal_df.loc[best_idx, "daily_pnl_pct"], 2)
            },
            "worst_day": {
                "date": str(journal_df.loc[worst_idx, "date"]),
                "pnl": round(journal_df.loc[worst_idx, "daily_pnl"], 2),
                "pct": round(journal_df.loc[worst_idx, "daily_pnl_pct"], 2)
            },
            "average_daily_pnl": round(journal_df["daily_pnl"].mean(), 2),
            "average_daily_pct": round(journal_df["daily_pnl_pct"].mean(), 2),
            "current_streak": streak
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Lifecycle Events ====================

_cleanup_task: Optional[asyncio.Task] = None


async def periodic_cleanup():
    """
    Background task for periodic memory cleanup.

    Runs every 30 minutes to:
    - Clear expired cache entries
    - Run garbage collection
    - Log memory usage
    """
    while True:
        try:
            await asyncio.sleep(1800)  # 30 minutes

            # Clear caches
            _data_cache._maybe_cleanup()
            _signal_cache._maybe_cleanup()

            # Force garbage collection
            collected = gc.collect()

            logger.info(
                "Periodic cleanup completed",
                extra={"gc_collected": collected}
            )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Periodic cleanup failed: {e}")


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    global _cleanup_task
    logger.info("API server starting up")

    # Start periodic cleanup task
    _cleanup_task = asyncio.create_task(periodic_cleanup())


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown."""
    global _cleanup_task, _db, _alpaca, _polygon
    global _dual_momentum, _swing_momentum, _ml_momentum, _pairs_trading, _volatility_breakout

    logger.info("API server shutting down")

    # Cancel cleanup task
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    # Clear caches
    clear_caches()

    # Close database connection
    if _db is not None:
        _db.close()
        _db = None

    # Clear strategy references
    _dual_momentum = None
    _swing_momentum = None
    _ml_momentum = None
    _pairs_trading = None
    _volatility_breakout = None

    # Final garbage collection
    gc.collect()

    logger.info("API server shutdown complete")


# Run with: uvicorn api.server:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
