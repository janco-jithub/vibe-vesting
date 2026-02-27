#!/usr/bin/env python3
"""
Automated Trading Service - Runs continuously and executes trades.

This service:
1. Runs multiple strategies simultaneously
2. Checks for signals at regular intervals
3. Executes trades automatically
4. Logs all activity to the database and files

Optimized for long-running operation (days/weeks) with:
- Operation timeouts to prevent hangs
- Periodic memory cleanup
- Circuit breakers for external APIs
- Graceful error recovery

Usage:
    python -m scripts.auto_trader
    python -m scripts.auto_trader --interval 300  # Check every 5 minutes

The service runs until interrupted (Ctrl+C).
"""

import argparse
import logging
import sys
import os
import time
import signal
import threading
import gc
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import math

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from data.storage import TradingDatabase
from data.alpaca_data_client import AlpacaDataClient, AlpacaDataClientError
from strategies.dual_momentum import DualMomentumStrategy
from strategies.swing_momentum import SwingMomentumStrategy
from strategies.ml_momentum import MLMomentumStrategy
from strategies.pairs_trading import PairsTradingStrategy
from strategies.volatility_breakout import VolatilityBreakoutStrategy
from strategies.simple_momentum import SimpleMomentumStrategy
from strategies.factor_composite import FactorCompositeStrategy
from strategies.regime_detector import RegimeDetector, VIXRegimeDetector, MarketRegime
from strategies.base import Signal, SignalType
from risk.position_sizing import PositionSizer
from risk.circuit_breakers import CircuitBreaker
from risk.profit_optimizer import ProfitOptimizer
from risk.kelly_sizing import KellyPositionSizer, DEFAULT_STRATEGY_STATS
from risk.var_calculator import VaRCalculator, RiskMonitor
from risk.correlation_manager import CorrelationManager
from execution.alpaca_client import AlpacaClient, AlpacaClientError, TimeoutHTTPAdapter
from execution.order_manager import OrderManager, RiskLimitExceeded
from execution.position_tracker import PositionTracker
from execution.cash_manager import CashManager

# Ensure logs directory exists
Path("logs").mkdir(exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/auto_trader.log")
    ]
)
logger = logging.getLogger(__name__)


class AutoTrader:
    """
    Automated trading service that runs multiple strategies.

    Features:
    - Runs continuously, checking for signals at regular intervals
    - Supports multiple strategies simultaneously
    - Respects risk limits and circuit breakers
    - Logs all trades and decisions
    - Graceful shutdown handling
    """

    def __init__(
        self,
        strategies: List[str] = None,
        check_interval: int = 300,  # 5 minutes
        db_path: str = "data/quant.db"
    ):
        """
        Initialize auto trader.

        Args:
            strategies: List of strategy names to run
            check_interval: Seconds between signal checks
            db_path: Path to trading database
        """
        self.check_interval = check_interval
        self.running = False
        self._shutdown_event = threading.Event()

        # Timeout settings for operations
        self.operation_timeout = 120  # 2 minutes max per operation
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="trader")

        # Cleanup tracking
        self._last_cleanup = datetime.now()
        self._cleanup_interval = timedelta(hours=1)
        self._cycle_count = 0

        # Heartbeat file for health monitoring
        self._heartbeat_file = Path("logs/auto_trader_heartbeat.json")
        self._trades_last_hour: List[datetime] = []
        self._errors_last_hour: List[datetime] = []

        # Initialize database and data client
        self.db = TradingDatabase(db_path)
        # Use Alpaca for market data - 40x faster than Polygon (200 vs 5 calls/min)
        self.data_client = AlpacaDataClient()

        # Initialize Alpaca (paper trading)
        self.alpaca = AlpacaClient(paper=True)

        # Get initial account info
        account = self.alpaca.get_account()
        self.initial_equity = account["equity"]

        # Initialize strategies - factor_composite and simple_momentum for best performance
        strategies = strategies or ["factor_composite", "simple_momentum", "pairs_trading"]
        self.strategies = {}
        self.all_symbols: Set[str] = set()

        for strat_name in strategies:
            if strat_name == "dual_momentum":
                strat = DualMomentumStrategy()
            elif strat_name == "swing_momentum":
                strat = SwingMomentumStrategy()
            elif strat_name == "ml_momentum":
                strat = MLMomentumStrategy()
            elif strat_name == "pairs_trading":
                strat = PairsTradingStrategy()
            elif strat_name == "volatility_breakout":
                strat = VolatilityBreakoutStrategy()
            elif strat_name == "simple_momentum":
                strat = SimpleMomentumStrategy()
            elif strat_name == "factor_composite":
                strat = FactorCompositeStrategy()
            else:
                logger.warning(f"Unknown strategy: {strat_name}")
                continue

            self.strategies[strat_name] = strat
            self.all_symbols.update(strat.universe)

        # Initialize risk components
        # OPTIMIZED: Increased from 15% to 20% for better capital utilization
        # With 5 positions, this allows 100% deployment vs 75% previously
        self.position_sizer = PositionSizer(
            max_position_pct=0.20,  # 20% max per position (balanced risk/return)
            method="fixed"
        )
        self.circuit_breaker = CircuitBreaker(initial_equity=self.initial_equity)

        # Initialize order manager
        self.order_manager = OrderManager(
            alpaca_client=self.alpaca,
            position_sizer=self.position_sizer,
            circuit_breaker=self.circuit_breaker,
            database=self.db
        )

        # Initialize cash manager for cash validation
        self.cash_manager = CashManager(alpaca_client=self.alpaca)

        # Initialize correlation manager to prevent concentrated risk
        self.correlation_manager = CorrelationManager(
            database=self.db,
            max_correlation=0.70,  # Reject positions with >70% correlation
            lookback_days=60  # 60-day correlation window
        )

        # Initialize VIX regime detector for crisis mode protection
        self.vix_regime_detector = VIXRegimeDetector(
            vix_low=15.0,   # VIX < 15: Bull market (full exposure)
            vix_normal=25.0,  # VIX 15-25: Normal (80% exposure)
            vix_high=35.0   # VIX > 35: Crisis mode (25% exposure)
        )

        # Track recent trades to avoid over-trading
        self.recent_trades: Dict[str, datetime] = {}
        self.min_trade_interval = timedelta(minutes=15)  # Reduced to 15 min for more active trading

        # Risk management settings for bracket orders
        self.take_profit_pct = 0.08  # 8% take profit target
        self.stop_loss_pct = 0.04    # 4% stop loss (2% was suicide for TSLA/SOXL/TQQQ)
        self.use_bracket_orders = True  # Always use bracket orders for risk management

        # Profit optimization - let winners run, cut losers at the stop
        # Previous settings were WAY too tight: 3% target, 2% stop = 1.5:1 R:R
        # New: 8% target, 4% stop = 2:1 R:R minimum
        self.profit_optimizer = ProfitOptimizer(
            trailing_stop_pct=0.035,  # 3.5% trailing stop (2% cut winners on normal pullbacks)
            trailing_stop_atr_multiple=3.0,  # 3x ATR for volatility-adjusted trailing
            use_atr_trailing=True,
            first_target_pct=0.08,  # Tier 1: Take profit at +8% (3% was cutting winners way too early)
            first_target_size_pct=0.33,  # Tier 1: Sell 33% (50% was giving away too much upside)
            second_target_pct=0.15,  # Tier 2: Take profit at +15%
            second_target_size_pct=0.50,  # Tier 2: Sell 50% of remaining
            third_target_pct=0.25,  # Tier 3: Take profit at +25% (big winners)
            third_target_size_pct=0.50,  # Tier 3: Sell 50% of remaining
            breakeven_trigger_pct=0.03,  # Move stop to breakeven at +3% (was 2%, too tight)
            profit_lock_pct=0.005,  # Lock +0.5% profit at breakeven
            max_scale_ins=2,  # Allow pyramiding up to 2 times
            scale_in_profit_threshold=0.03,  # Add at +3%
            fast_exit_loss_pct=0.04,  # Align with stop loss (1.5% was tighter than the actual stop!)
            avoid_open_minutes=5,  # 5 minutes after open
            reduce_size_friday_pct=0.85,  # 15% reduction on Fridays (30% was excessive with stops)
            vix_high_threshold=25.0,
            high_vol_stop_multiplier=1.5,
            high_vol_size_reduction=0.75  # 25% smaller in high vol (was 33%)
        )
        self.position_tracker = PositionTracker(
            profit_optimizer=self.profit_optimizer,
            database=self.db,
            auto_persist=True
        )

        # Load previous position state (if any) after restart
        loaded_count = self.position_tracker.load_state_from_database()
        if loaded_count > 0:
            logger.info(f"Restored {loaded_count} positions from previous session")

        # Migrate existing bracket orders to profit optimizer exits (Option B)
        self._migrate_to_profit_optimizer_exits()

        # VIX tracking for volatility regime
        self.current_vix = 20.0  # Default, will update from market data

        # Advanced components for world-class performance
        # Regime detection for dynamic strategy allocation
        self.regime_detector = RegimeDetector()
        self.current_regime = MarketRegime.UNKNOWN

        # Kelly position sizing for optimal bet sizing
        # OPTIMIZED: Aligned max_position_pct with PositionSizer
        self.kelly_sizer = KellyPositionSizer(
            kelly_fraction=0.25,  # Quarter Kelly for safety (balance growth vs drawdown)
            max_position_pct=0.20,  # INCREASED: Aligned with PositionSizer (was 0.15)
            min_position_pct=0.02
        )
        # Initialize with default strategy stats
        for strat_name, stats in DEFAULT_STRATEGY_STATS.items():
            self.kelly_sizer._strategy_stats[strat_name] = stats

        # VaR calculator for risk monitoring
        self.var_calculator = VaRCalculator()
        self._portfolio_returns: List[float] = []

        logger.info(
            "AutoTrader initialized",
            extra={
                "strategies": list(self.strategies.keys()),
                "symbols": list(self.all_symbols),
                "initial_equity": self.initial_equity,
                "check_interval": check_interval
            }
        )

    def _migrate_to_profit_optimizer_exits(self) -> None:
        """
        Migrate existing bracket orders to profit optimizer exit strategy (Option B).

        For positions with bracket orders (TP + SL), this cancels all orders and
        re-adds just stop-loss protection. The profit optimizer will handle exits
        via scale-outs and trailing stops instead of fixed take-profit orders.
        """
        try:
            positions = self.alpaca.get_positions()
            if not positions:
                logger.info("No positions to migrate")
                return

            migrated = 0
            for symbol, pos_data in positions.items():
                # Check for open orders on this symbol
                try:
                    open_orders = self.alpaca.get_open_orders_for_symbol(symbol)

                    # Look for bracket order legs (TP or parent bracket)
                    has_bracket = any(
                        o.get('order_class') in ['bracket', 'oto'] or
                        o.get('order_type') == 'limit' and o.get('side') == 'sell'  # Potential TP leg
                        for o in open_orders
                    )

                    if has_bracket and len(open_orders) > 0:
                        logger.info(f"Migrating {symbol}: canceling bracket orders, adding stop-loss only")

                        # Get position info before canceling
                        qty = pos_data['qty']
                        current_price = pos_data['current_price']
                        entry_price = pos_data['avg_entry_price']

                        # Calculate stop loss (use tracked stop if available, else default)
                        if symbol in self.position_tracker.positions:
                            stop_price = self.position_tracker.positions[symbol].stop_loss
                        else:
                            stop_price = entry_price * (1 - self.stop_loss_pct)

                        # Cancel all existing orders
                        cancelled = self.alpaca.cancel_orders_for_symbol(symbol)
                        if cancelled > 0:
                            # Wait for cancellations to complete
                            time.sleep(1.0)

                            # Re-add just stop-loss protection
                            self.alpaca.submit_stop_order(
                                symbol=symbol,
                                qty=qty,
                                side='sell',
                                stop_price=stop_price,
                                time_in_force='gtc'
                            )

                            logger.info(
                                f"Migrated {symbol}: {cancelled} orders cancelled, "
                                f"new stop @ ${stop_price:.2f} (profit optimizer handles exits)"
                            )
                            migrated += 1

                except Exception as e:
                    logger.warning(f"Failed to migrate {symbol}: {e}")
                    continue

            if migrated > 0:
                logger.info(f"Migration complete: {migrated} positions converted to profit optimizer exits")
            else:
                logger.info("No bracket orders found to migrate")

        except Exception as e:
            logger.error(f"Migration failed: {e}")

    def _run_with_timeout(self, func, timeout: int = None, description: str = "operation"):
        """
        Run a function with a timeout to prevent hangs.

        Uses a fresh ThreadPoolExecutor for each call to prevent thread exhaustion
        when operations hang. The executor is shut down after timeout regardless
        of whether the operation completed.

        Args:
            func: Callable to execute
            timeout: Timeout in seconds (default: self.operation_timeout)
            description: Description for logging

        Returns:
            Result of the function, or None on timeout/error
        """
        timeout = timeout or self.operation_timeout
        result = None
        executor = None

        try:
            # Use a fresh executor for each operation to prevent thread exhaustion
            executor = ThreadPoolExecutor(max_workers=1)
            future = executor.submit(func)
            result = future.result(timeout=timeout)
        except FuturesTimeoutError:
            logger.error(f"Timeout ({timeout}s) during {description} - operation may still be running")
            # Cancel the future if possible
            future.cancel()
        except Exception as e:
            logger.error(f"Error during {description}: {e}")
        finally:
            # Always shut down the executor to clean up threads
            if executor:
                executor.shutdown(wait=False, cancel_futures=True)

        return result

    def _maybe_cleanup(self) -> None:
        """Periodic cleanup to prevent memory leaks during long runs."""
        if datetime.now() - self._last_cleanup < self._cleanup_interval:
            return

        logger.info("Running periodic cleanup...")

        # Force garbage collection
        collected = gc.collect()
        logger.info(f"Garbage collection freed {collected} objects")

        # Close ALL database connections to prevent connection leaks
        try:
            db_path = self.db.db_path
            self.db.close_all_connections()
            self.db = TradingDatabase(db_path)
            logger.info("All database connections refreshed")
        except Exception as e:
            logger.error(f"Failed to refresh database connections: {e}")

        self._last_cleanup = datetime.now()

    def _write_heartbeat(self, cycle_result: dict) -> None:
        """
        Write heartbeat file for health monitoring daemon.

        The health monitor reads this to detect stuck/failing states.
        """
        try:
            # Prune old entries from tracking lists (keep last hour)
            cutoff = datetime.now() - timedelta(hours=1)
            self._trades_last_hour = [t for t in self._trades_last_hour if t > cutoff]
            self._errors_last_hour = [e for e in self._errors_last_hour if e > cutoff]

            # Count trades and errors from this cycle
            trades_this_cycle = len(cycle_result.get("trades_executed", []))
            errors_this_cycle = len(cycle_result.get("errors", []))

            # Update tracking lists
            now = datetime.now()
            self._trades_last_hour.extend([now] * trades_this_cycle)
            self._errors_last_hour.extend([now] * errors_this_cycle)

            heartbeat = {
                "timestamp": now.isoformat(),
                "cycle_number": self._cycle_count,
                "trades_last_hour": len(self._trades_last_hour),
                "errors_last_hour": len(self._errors_last_hour),
                "strategies_active": len(self.strategies),
                "positions_tracked": self.position_tracker.get_position_count(),
                "market_status": cycle_result.get("market_status", "unknown"),
                "last_cycle_duration": cycle_result.get("duration_seconds", 0),
                "signals_generated": cycle_result.get("signals_generated", 0),
                "vix": self.current_vix
            }

            self._heartbeat_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._heartbeat_file, 'w') as f:
                json.dump(heartbeat, f, indent=2)

            logger.debug(f"Heartbeat written: cycle {self._cycle_count}")

        except Exception as e:
            logger.error(f"Failed to write heartbeat: {e}")

    def update_market_data(self) -> bool:
        """
        Download latest market data for all symbols.

        Uses Alpaca's batch API - much faster than Polygon!
        Can fetch all symbols in a single API call.

        Returns:
            True if data was updated successfully
        """
        logger.info("Updating market data...")

        end_date = date.today()
        start_date = end_date - timedelta(days=90)  # 90 days for indicators

        # Use batch fetching - single API call for all symbols (40x faster!)
        symbols_list = list(self.all_symbols)
        success_count = 0

        try:
            # Alpaca allows up to 100 symbols per batch call
            batch_size = 100
            for i in range(0, len(symbols_list), batch_size):
                batch = symbols_list[i:i + batch_size]
                logger.info(f"Fetching batch {i//batch_size + 1}: {len(batch)} symbols")

                bars_dict = self.data_client.get_multiple_symbols(
                    symbols=batch,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat()
                )

                for symbol, bars in bars_dict.items():
                    if bars:
                        self.db.insert_daily_bars(bars)
                        success_count += 1

        except AlpacaDataClientError as e:
            logger.error(f"Failed to fetch market data: {e}")

        # Update VIX proxy using SPY realized volatility
        # VIXY proxy was inaccurate (showed VIX=40 when actual VIX=21)
        # SPY 20-day realized vol * sqrt(252) gives VIX-like reading
        try:
            spy_bars = self.data_client.get_daily_bars(
                symbol="SPY",
                start_date=(end_date - timedelta(days=40)).isoformat(),
                end_date=end_date.isoformat()
            )
            if spy_bars and len(spy_bars) >= 20:
                closes = [b['close'] for b in spy_bars]
                # Daily log returns
                returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
                # 20-day realized volatility, annualized
                recent_returns = returns[-20:]
                mean_ret = sum(recent_returns) / len(recent_returns)
                variance = sum((r - mean_ret) ** 2 for r in recent_returns) / (len(recent_returns) - 1)
                realized_vol = math.sqrt(variance) * math.sqrt(252) * 100
                # VIX typically trades at ~1.5x realized vol (implied vol risk premium)
                vix_estimate = realized_vol * 1.5
                self.current_vix = max(10, min(80, vix_estimate))
                logger.info(f"VIX proxy updated: {self.current_vix:.2f} "
                           f"(SPY 20d realized vol: {realized_vol:.1f}%)")
            else:
                logger.warning("Insufficient SPY data for VIX estimation")
        except Exception as e:
            logger.warning(f"Failed to update VIX: {e}")

        logger.info(f"Updated {success_count}/{len(self.all_symbols)} symbols")
        return success_count > 0

    def get_current_state(self) -> dict:
        """Get current portfolio state."""
        account = self.alpaca.get_account()
        positions = self.alpaca.get_positions()

        return {
            "equity": account["equity"],
            "cash": account["cash"],
            "buying_power": account["buying_power"],
            "positions": positions
        }

    def log_cash_status(self) -> None:
        """Log current cash status for debugging and monitoring."""
        try:
            cash_status = self.cash_manager.get_cash_status()
            logger.info(
                "Cash Status",
                extra={
                    "total_cash": f"${cash_status['total_cash']:,.2f}",
                    "locked_cash": f"${cash_status['locked_cash']:,.2f}",
                    "available_cash": f"${cash_status['available_cash']:,.2f}",
                    "pending_buy_orders": cash_status['pending_buy_orders'],
                    "minimum_reserve": f"${cash_status['minimum_reserve']:,.2f}"
                }
            )
        except Exception as e:
            logger.error(f"Failed to log cash status: {e}")

    def can_trade_symbol(self, symbol: str) -> bool:
        """Check if we can trade this symbol (not recently traded)."""
        if symbol in self.recent_trades:
            time_since_trade = datetime.now() - self.recent_trades[symbol]
            if time_since_trade < self.min_trade_interval:
                logger.debug(f"Skipping {symbol} - traded {time_since_trade} ago")
                return False
        return True

    def match_symbol_to_strategy(self, symbol: str) -> str:
        """
        Match a symbol to its most likely strategy based on universe membership.

        Args:
            symbol: Symbol ticker

        Returns:
            Strategy name or "manual_review" if no match found
        """
        # Check which strategies have this symbol in their universe
        matching_strategies = []

        for strat_name, strategy in self.strategies.items():
            if symbol in strategy.universe:
                matching_strategies.append(strat_name)

        if len(matching_strategies) == 0:
            logger.warning(
                f"Symbol {symbol} not found in any strategy universe. "
                f"Flagging for manual review."
            )
            return "manual_review"
        elif len(matching_strategies) == 1:
            logger.info(f"Matched {symbol} to strategy: {matching_strategies[0]}")
            return matching_strategies[0]
        else:
            # Multiple strategies trade this symbol - use priority order
            # Priority: factor_composite > simple_momentum > pairs_trading > others
            priority_order = [
                "factor_composite",
                "simple_momentum",
                "pairs_trading",
                "swing_momentum",
                "ml_momentum",
                "dual_momentum",
                "volatility_breakout"
            ]

            for priority_strat in priority_order:
                if priority_strat in matching_strategies:
                    logger.info(
                        f"Matched {symbol} to strategy {priority_strat} "
                        f"(multiple matches: {matching_strategies}, using priority)"
                    )
                    return priority_strat

            # Fallback to first match if not in priority list
            logger.info(
                f"Matched {symbol} to strategy {matching_strategies[0]} "
                f"(first of multiple matches: {matching_strategies})"
            )
            return matching_strategies[0]

    def _log_trade_to_db(
        self,
        symbol: str,
        action: str,
        quantity: float,
        price: float,
        order_id: str = None,
        strategy: str = None,
        notes: str = None
    ) -> None:
        """
        Log a trade execution to the database.

        This ensures all trades (including scale-outs, scale-ins, trailing stops)
        are recorded for the Recent Trades display and audit trail.
        """
        try:
            self.db.insert_trade(
                timestamp=datetime.now(),
                symbol=symbol,
                action=action,
                quantity=quantity,
                price=price,
                commission=0.0,  # Alpaca is commission-free
                order_id=order_id,
                strategy=strategy or self.match_symbol_to_strategy(symbol),
                notes=notes
            )
            logger.info(f"Trade logged: {action} {quantity} {symbol} @ ${price:.2f}")
        except Exception as e:
            logger.error(f"Failed to log trade to database: {e}")

    def sync_positions_with_broker(self) -> None:
        """
        Sync position tracker with actual broker positions.

        Updates current prices and adds any positions not being tracked.
        IMPORTANT: Strategy attribution uses universe matching, never "unknown".
        """
        try:
            broker_positions = self.alpaca.get_positions()

            # Update existing tracked positions
            for symbol in list(self.position_tracker.positions.keys()):
                if symbol in broker_positions:
                    broker_pos = broker_positions[symbol]
                    self.position_tracker.update_position(
                        symbol=symbol,
                        current_price=broker_pos['current_price'],
                        quantity=broker_pos['qty']
                    )
                else:
                    # Check if there are pending orders for this symbol
                    # (limit order may not have filled yet - don't remove)
                    try:
                        pending = self.alpaca.get_open_orders_for_symbol(symbol)
                        if pending:
                            logger.info(
                                f"Keeping {symbol} in tracker - "
                                f"{len(pending)} pending orders (awaiting fill)"
                            )
                            continue
                    except Exception:
                        pass
                    # Position truly closed at broker
                    self.position_tracker.remove_position(
                        symbol=symbol,
                        reason="Position closed at broker"
                    )

            # Add any positions from broker not being tracked
            for symbol, broker_pos in broker_positions.items():
                if symbol not in self.position_tracker.positions:
                    # Determine strategy by matching symbol to strategy universes
                    strategy_name = self.match_symbol_to_strategy(symbol)

                    # Try to get ATR from recent data
                    atr = None
                    try:
                        start_date = date.today() - timedelta(days=30)
                        df = self.db.get_daily_bars(symbol, start_date)
                        if not df.empty and len(df) >= 14:
                            # Simple ATR calculation
                            df['tr'] = df[['high', 'low', 'close']].apply(
                                lambda x: max(
                                    x['high'] - x['low'],
                                    abs(x['high'] - x['close']),
                                    abs(x['low'] - x['close'])
                                ),
                                axis=1
                            )
                            atr = df['tr'].rolling(14).mean().iloc[-1]
                    except Exception as e:
                        logger.debug(f"Could not calculate ATR for {symbol}: {e}")

                    self.position_tracker.add_position(
                        symbol=symbol,
                        entry_price=broker_pos['avg_entry_price'],
                        quantity=broker_pos['qty'],
                        side='long' if broker_pos['side'] == 'long' else 'short',
                        stop_loss=broker_pos['avg_entry_price'] * 0.96,  # Default 4% stop
                        take_profit=None,
                        strategy=strategy_name,
                        atr=atr
                    )

                    if strategy_name == "manual_review":
                        logger.warning(
                            f"MANUAL REVIEW REQUIRED: Position {symbol} could not be "
                            f"matched to any strategy. Please verify and update strategy field."
                        )
                    else:
                        logger.info(
                            f"Added untracked position to tracker: {symbol} -> {strategy_name}"
                        )

        except Exception as e:
            logger.error(f"Failed to sync positions with broker: {e}")

    def optimize_positions(self) -> List[dict]:
        """
        Apply profit optimization to all open positions.

        Checks for:
        - Trailing stop updates
        - Partial profit taking
        - Position scaling opportunities
        - Fast exits on losers

        Returns:
            List of actions taken
        """
        actions_taken = []

        try:
            # Sync with broker first
            self.sync_positions_with_broker()

            # Log current position status before optimization
            if self.position_tracker.get_position_count() > 0:
                logger.info("=" * 70)
                logger.info("PROFIT OPTIMIZER: Analyzing positions")
                logger.info("=" * 70)
                summary = self.position_tracker.get_position_summary()
                for _, row in summary.iterrows():
                    logger.info(
                        f"{row['symbol']:6s}: Entry=${row['entry_price']:>7.2f} "
                        f"Current=${row['current_price']:>7.2f} "
                        f"P&L={row['unrealized_pnl_pct']:>+6.1f}% "
                        f"Stop=${row['stop_loss']:>7.2f} "
                        f"ScaleOuts={row['scale_outs']}"
                    )
                logger.info("=" * 70)

            # Get signal strengths for current positions (optional enhancement)
            signal_strengths = {}
            # TODO: Could re-calculate signals for existing positions

            # Get optimization actions
            trade_actions = self.position_tracker.get_all_optimization_actions(
                vix=self.current_vix,
                signal_strengths=signal_strengths
            )

            # Log what actions were recommended
            if trade_actions:
                logger.info(f"PROFIT OPTIMIZER: Generated {len(trade_actions)} recommended actions:")
                for action in trade_actions:
                    logger.info(
                        f"  - {action.action.upper()}: {action.symbol} - {action.reason}"
                    )
            else:
                logger.info("PROFIT OPTIMIZER: No optimization actions recommended at this time")

            # Execute actions
            logger.info("=" * 70)
            logger.info(f"PROFIT OPTIMIZER: Executing {len(trade_actions)} actions...")
            logger.info("=" * 70)

            for action in trade_actions:
                try:
                    logger.info(f"EXECUTING: {action.action.upper()} for {action.symbol}")

                    if action.action == 'scale_out':
                        # Partial profit taking
                        # Cancel existing orders first (bracket orders lock shares)
                        try:
                            cancelled = self.alpaca.cancel_orders_for_symbol(action.symbol)
                            if cancelled > 0:
                                logger.info(f"Cancelled {cancelled} orders for {action.symbol} before scale-out")
                                # Wait and verify cancellations completed (10s per plan recommendations)
                                max_wait = 10.0
                                elapsed = 0.0
                                retries = 0
                                max_retries = 3

                                while elapsed < max_wait and retries < max_retries:
                                    time.sleep(0.5)
                                    elapsed += 0.5
                                    open_orders = self.alpaca.get_open_orders_for_symbol(action.symbol)
                                    if len(open_orders) == 0:
                                        logger.info(f"All orders successfully cancelled for {action.symbol}")
                                        break
                                    retries += 1

                                # If orders still pending, abort scale-out to prevent error
                                if len(open_orders) > 0:
                                    logger.error(
                                        f"ABORT SCALE-OUT: {action.symbol} still has {len(open_orders)} pending orders after {max_wait}s wait. "
                                        f"Cannot scale out safely (would cause error 40310000)"
                                    )
                                    continue  # Skip this action
                        except Exception as e:
                            logger.warning(f"Failed to cancel orders for {action.symbol}: {e}")
                            # Continue with scale-out attempt anyway (might fail, but user should know)

                        order = self.alpaca.submit_limit_order(
                            symbol=action.symbol,
                            qty=action.quantity,
                            side='sell',
                            limit_price=action.price,
                            time_in_force='day'
                        )

                        self.position_tracker.scale_out(
                            symbol=action.symbol,
                            reduce_quantity=action.quantity,
                            exit_price=action.price
                        )

                        # Log the trade to database for Recent Trades display
                        self._log_trade_to_db(
                            symbol=action.symbol,
                            action='SELL',
                            quantity=action.quantity,
                            price=action.price,
                            order_id=order['id'],
                            notes=f"Scale-out: {action.reason}"
                        )

                        actions_taken.append({
                            'symbol': action.symbol,
                            'action': 'scale_out',
                            'quantity': action.quantity,
                            'price': action.price,
                            'reason': action.reason,
                            'order_id': order['id']
                        })

                        logger.info(
                            f"SCALE OUT: {action.symbol} -{action.quantity} @ ${action.price:.2f} "
                            f"({action.reason})"
                        )

                        # Re-protect remaining position with trailing stop
                        remaining_qty = self.position_tracker.positions[action.symbol].quantity
                        if remaining_qty > 0:
                            try:
                                stop_order = self.alpaca.submit_trailing_stop_order(
                                    symbol=action.symbol,
                                    qty=remaining_qty,
                                    side='sell',
                                    trail_percent=self.profit_optimizer.trailing_stop_pct * 100,
                                    time_in_force='gtc'
                                )
                                logger.info(f"Re-protected {action.symbol} with trailing stop for {remaining_qty} shares")
                            except Exception as e:
                                logger.warning(f"Failed to re-protect {action.symbol}: {e}")

                    elif action.action == 'scale_in':
                        # Add to winning position
                        order = self.alpaca.submit_limit_order(
                            symbol=action.symbol,
                            qty=action.quantity,
                            side='buy',
                            limit_price=action.price,
                            time_in_force='day'
                        )

                        self.position_tracker.scale_in(
                            symbol=action.symbol,
                            add_quantity=action.quantity,
                            add_price=action.price
                        )

                        # Log the trade to database for Recent Trades display
                        self._log_trade_to_db(
                            symbol=action.symbol,
                            action='BUY',
                            quantity=action.quantity,
                            price=action.price,
                            order_id=order['id'],
                            notes=f"Scale-in: {action.reason}"
                        )

                        actions_taken.append({
                            'symbol': action.symbol,
                            'action': 'scale_in',
                            'quantity': action.quantity,
                            'price': action.price,
                            'reason': action.reason,
                            'order_id': order['id']
                        })

                        logger.info(
                            f"SCALE IN: {action.symbol} +{action.quantity} @ ${action.price:.2f} "
                            f"({action.reason})"
                        )

                    elif action.action == 'update_stop':
                        # Update trailing stop - but don't cancel/replace if we already
                        # have a trailing stop at the correct percentage (resetting it
                        # loses the high-water mark that Alpaca tracks)
                        position = self.position_tracker.positions.get(action.symbol)
                        if not position:
                            continue

                        # Check if there's already an active trailing stop for this symbol
                        open_orders = self.alpaca.get_open_orders_for_symbol(action.symbol)
                        has_trailing_stop = any(
                            o.get('type') == 'trailing_stop' for o in open_orders
                        )

                        if has_trailing_stop:
                            # Don't replace - Alpaca's trailing stop is already tracking
                            # the high-water mark. Replacing resets it and gives back gains.
                            self.position_tracker.update_stop_loss(
                                symbol=action.symbol,
                                new_stop=action.stop_loss
                            )
                            logger.debug(
                                f"TRAILING STOP: {action.symbol} tracker updated to "
                                f"${action.stop_loss:.2f} (Alpaca trailing stop preserved)"
                            )
                            continue

                        # No trailing stop exists - create one
                        # Cancel any other stop orders first
                        cancelled = self.alpaca.cancel_orders_for_symbol(action.symbol)
                        if cancelled > 0:
                            max_wait = 10.0
                            elapsed = 0.0
                            while elapsed < max_wait:
                                time.sleep(0.5)
                                elapsed += 0.5
                                remaining = self.alpaca.get_open_orders_for_symbol(action.symbol)
                                if len(remaining) == 0:
                                    break

                        # Submit new trailing stop order
                        order = self.alpaca.submit_trailing_stop_order(
                            symbol=action.symbol,
                            qty=position.quantity,
                            side='sell',
                            trail_percent=self.profit_optimizer.trailing_stop_pct * 100,
                            time_in_force='gtc'
                        )

                        self.position_tracker.update_stop_loss(
                            symbol=action.symbol,
                            new_stop=action.stop_loss
                        )

                        actions_taken.append({
                            'symbol': action.symbol,
                            'action': 'update_stop',
                            'new_stop': action.stop_loss,
                            'reason': action.reason,
                            'order_id': order['id']
                        })

                        logger.info(
                            f"TRAILING STOP: {action.symbol} set at ${action.stop_loss:.2f} "
                            f"({action.reason})"
                        )

                    elif action.action == 'close':
                        # Get position info before closing
                        position = self.position_tracker.positions.get(action.symbol)
                        close_qty = position.quantity if position else action.quantity
                        close_price = position.current_price if position else action.price

                        # CRITICAL: Cancel existing orders first (bracket orders lock shares)
                        # This prevents error 40310000 "insufficient qty available"
                        try:
                            cancelled = self.alpaca.cancel_orders_for_symbol(action.symbol)
                            if cancelled > 0:
                                logger.info(f"Cancelled {cancelled} orders for {action.symbol} before closing position")
                                # Wait and verify cancellations completed (10s per plan recommendations)
                                max_wait = 10.0
                                elapsed = 0.0
                                retries = 0
                                max_retries = 3

                                while elapsed < max_wait and retries < max_retries:
                                    time.sleep(0.5)
                                    elapsed += 0.5
                                    open_orders = self.alpaca.get_open_orders_for_symbol(action.symbol)
                                    if len(open_orders) == 0:
                                        logger.info(f"All orders successfully cancelled for {action.symbol}")
                                        break
                                    retries += 1

                                # If orders still pending, abort close to prevent error
                                if len(open_orders) > 0:
                                    logger.error(
                                        f"ABORT CLOSE: {action.symbol} still has {len(open_orders)} pending orders after {max_wait}s wait. "
                                        f"Cannot close position safely (would cause error 40310000)"
                                    )
                                    continue  # Skip this action
                        except Exception as e:
                            logger.warning(f"Failed to cancel orders for {action.symbol}: {e}")
                            # Continue with close attempt anyway (might fail, but user should know)

                        # Close position
                        order = self.alpaca.close_position(action.symbol)

                        # Log the trade to database for Recent Trades display
                        if close_qty and close_price:
                            self._log_trade_to_db(
                                symbol=action.symbol,
                                action='SELL',
                                quantity=close_qty,
                                price=close_price,
                                order_id=order['id'],
                                notes=f"Position closed: {action.reason}"
                            )

                        self.position_tracker.remove_position(
                            symbol=action.symbol,
                            reason=action.reason
                        )

                        actions_taken.append({
                            'symbol': action.symbol,
                            'action': 'close',
                            'reason': action.reason,
                            'order_id': order['id']
                        })

                        logger.info(
                            f"CLOSE POSITION: {action.symbol} ({action.reason})"
                        )

                except AlpacaClientError as e:
                    logger.error(f"Failed to execute action {action.action} for {action.symbol}: {e}")

        except Exception as e:
            logger.error(f"Error during position optimization: {e}")

        return actions_taken

    def process_signals(self, signals: List[Signal], strategy_name: str) -> List[dict]:
        """
        Process trading signals and execute trades.

        Args:
            signals: List of signals to process
            strategy_name: Name of the strategy that generated signals

        Returns:
            List of executed trade info
        """
        executed = []
        state = self.get_current_state()
        equity = state["equity"]
        positions = state["positions"]

        # Track signal conversion metrics
        total_signals = len(signals)
        buy_signals = sum(1 for s in signals if s.signal_type == SignalType.BUY)
        sell_signals = sum(1 for s in signals if s.signal_type == SignalType.SELL)
        skipped_recent_trade = 0
        skipped_existing_position = 0
        skipped_no_shares = 0
        skipped_optimizer = 0
        skipped_insufficient_cash = 0
        skipped_pending_conflict = 0
        skipped_correlation = 0
        skipped_regime = 0

        # VIX REGIME DETECTION: Adjust exposure based on market volatility
        vix_regime, position_multiplier = self.vix_regime_detector.detect_regime(self.current_vix)

        # Push VIX regime multiplier into strategy for position sizing
        strategy = self.strategies.get(strategy_name)
        if strategy and hasattr(strategy, 'regime_multiplier'):
            strategy.regime_multiplier = position_multiplier

        logger.info(
            f"VIX Regime: {vix_regime.value.upper()} (VIX={self.current_vix:.1f}, "
            f"Position Multiplier={position_multiplier:.2f}x)"
        )

        # In CRISIS mode (VIX > 35), skip aggressive momentum strategies
        if vix_regime == MarketRegime.BEAR and position_multiplier < 0.5:
            if strategy_name == "simple_momentum":
                logger.warning(
                    f"CRISIS MODE: Skipping {strategy_name} strategy entirely "
                    f"(VIX {self.current_vix:.1f} > 35, too risky for momentum)"
                )
                return executed  # Skip all signals from aggressive momentum

        # Update circuit breaker
        self.circuit_breaker.update(equity)

        # Check if trading is allowed
        can_trade, halt_reason = self.circuit_breaker.can_trade()
        if not can_trade:
            logger.warning(f"Trading halted: {halt_reason}")
            logger.info(
                f"Signal conversion tracking [{strategy_name}]: "
                f"{total_signals} signals (BUY: {buy_signals}, SELL: {sell_signals}), "
                f"0 executed (circuit breaker halted)"
            )
            return executed

        # Separate BUY and SELL signals and process independently.
        # Previously, mixing them in a single sorted list meant SELL signals for
        # unheld stocks and BUY signals for already-held stocks consumed all 5
        # processing slots, preventing any NEW positions from being opened.
        buy_signals_list = sorted(
            [s for s in signals if s.signal_type == SignalType.BUY],
            key=lambda s: s.strength, reverse=True
        )
        sell_signals_list = sorted(
            [s for s in signals if s.signal_type == SignalType.SELL],
            key=lambda s: s.strength, reverse=True
        )

        # Prioritize NEW positions: move signals for unheld stocks to the front
        new_position_signals = [
            s for s in buy_signals_list
            if positions.get(s.symbol, {}).get("market_value", 0.0) <= 0
        ]
        existing_position_signals = [
            s for s in buy_signals_list
            if positions.get(s.symbol, {}).get("market_value", 0.0) > 0
        ]
        # New positions first, then pyramiding candidates
        ordered_buy_signals = new_position_signals + existing_position_signals

        # Process: up to 5 SELL exits, then up to 5 BUY entries
        prioritized_signals = sell_signals_list[:5] + ordered_buy_signals[:10]

        max_new_buys = 5
        buys_executed = 0

        logger.info(
            f"Signal processing [{strategy_name}]: "
            f"{len(new_position_signals)} NEW buy candidates, "
            f"{len(existing_position_signals)} existing position buys, "
            f"{len(sell_signals_list)} sell signals"
        )

        for signal in prioritized_signals:
            symbol = signal.symbol

            # Skip if recently traded
            if not self.can_trade_symbol(symbol):
                skipped_recent_trade += 1
                continue

            try:
                current_position = positions.get(symbol, {}).get("market_value", 0.0)

                if signal.signal_type == SignalType.BUY:
                    # Cap total new BUY executions per cycle
                    if buys_executed >= max_new_buys:
                        break

                    # Check if we already have a position - allow pyramiding if profitable
                    if current_position > 0:
                        # Get position details for pyramiding check
                        position_data = positions.get(symbol, {})
                        avg_entry = position_data.get("avg_entry_price", 0)
                        current_price = position_data.get("current_price", 0)
                        unrealized_pnl_pct = position_data.get("unrealized_plpc", 0)

                        # Check if position is tracked for scale-in history
                        can_pyramid = False
                        if symbol in self.position_tracker.positions:
                            tracked_pos = self.position_tracker.positions[symbol]
                            # Allow pyramiding if:
                            # 1. Position is profitable (>3%)
                            # 2. Haven't scaled in too many times (max 2 scale-ins)
                            if unrealized_pnl_pct >= 0.03 and tracked_pos.scale_in_count < 2:
                                can_pyramid = True
                                logger.info(
                                    f"Pyramiding opportunity for {symbol}: "
                                    f"P&L={unrealized_pnl_pct*100:.1f}%, scale_ins={tracked_pos.scale_in_count}/2"
                                )

                        if not can_pyramid:
                            logger.debug(
                                f"Skipping {symbol} - existing position, "
                                f"P&L={unrealized_pnl_pct:.1f}%, not eligible for pyramiding"
                            )
                            skipped_existing_position += 1
                            continue
                        else:
                            # Continue with pyramiding logic below
                            logger.info(f"Pyramiding into {symbol} at +{unrealized_pnl_pct:.1f}%")

                    # Calculate target position
                    strategy = self.strategies[strategy_name]
                    target_value = strategy.calculate_position_size(
                        signal=signal,
                        portfolio_value=equity,
                        current_positions={s: p["market_value"] for s, p in positions.items()}
                    )

                    # VIX regime multiplier is already applied inside strategy.calculate_position_size()
                    # via strategy.regime_multiplier (set on line 1097). Do NOT apply again here.
                    if position_multiplier < 1.0:
                        logger.info(
                            f"{symbol}: VIX regime applied via strategy sizing "
                            f"({position_multiplier:.2f}x, VIX={self.current_vix:.1f})"
                        )

                    # Get current price
                    price = self.alpaca.get_latest_price(symbol)
                    shares = int(target_value / price)

                    if shares < 1:
                        skipped_no_shares += 1
                        continue

                    # CASH VALIDATION: Check if we have sufficient cash for this order
                    order_cost = shares * price
                    available_cash = self.cash_manager.get_available_cash()

                    if order_cost > available_cash:
                        logger.warning(
                            f"Skipping {symbol} - insufficient cash: "
                            f"need ${order_cost:,.2f}, have ${available_cash:,.2f}"
                        )
                        skipped_insufficient_cash += 1
                        continue

                    # Check for pending order conflicts
                    has_conflicts, conflict_reason = self.order_manager.check_pending_order_conflicts(
                        symbol, "buy"
                    )
                    if not has_conflicts:
                        logger.warning(f"Skipping {symbol} - {conflict_reason}")
                        skipped_pending_conflict += 1
                        continue

                    # CORRELATION CHECK: Prevent concentrated risk
                    # Get list of current position symbols
                    existing_symbols = list(positions.keys())
                    is_valid_corr, corr_reason, corr_details = self.correlation_manager.check_position_correlation(
                        new_symbol=symbol,
                        existing_symbols=existing_symbols,
                        return_details=True
                    )
                    if not is_valid_corr:
                        logger.warning(
                            f"Skipping {symbol} - {corr_reason}",
                            extra=corr_details
                        )
                        skipped_correlation += 1
                        continue

                    # Get ATR for volatility-based stops
                    atr = None
                    try:
                        start_date = date.today() - timedelta(days=30)
                        df = self.db.get_daily_bars(symbol, start_date)
                        if not df.empty and len(df) >= 14:
                            df['tr'] = df[['high', 'low', 'close']].apply(
                                lambda x: max(
                                    x['high'] - x['low'],
                                    abs(x['high'] - x['close']),
                                    abs(x['low'] - x['close'])
                                ),
                                axis=1
                            )
                            atr = df['tr'].rolling(14).mean().iloc[-1]
                    except Exception as e:
                        logger.debug(f"Could not calculate ATR for {symbol}: {e}")

                    # Use profit optimizer to calculate optimal entry
                    entry_params = self.profit_optimizer.calculate_optimal_entry(
                        symbol=symbol,
                        base_price=price,
                        base_quantity=shares,
                        base_stop_pct=self.stop_loss_pct,
                        vix=self.current_vix,
                        atr=atr
                    )

                    if not entry_params['should_trade']:
                        logger.info(f"Skipping {symbol}: {entry_params['reason']}")
                        skipped_optimizer += 1
                        continue

                    # Use optimized parameters
                    shares = entry_params['quantity']
                    stop_loss_price = entry_params['stop_loss']
                    take_profit_price = entry_params['take_profit']
                    limit_price = round(price * 1.001, 2)  # Slightly above market for fill

                    # Submit OTO order with stop loss only (no take profit)
                    # Option B: Profit optimizer handles all exits (scale-outs, trailing stops)
                    if self.use_bracket_orders:
                        try:
                            order_result = self.alpaca.submit_limit_oto_order(
                                symbol=symbol,
                                qty=shares,
                                side="buy",
                                limit_price=limit_price,
                                stop_loss_price=stop_loss_price,
                                time_in_force="gtc"
                            )
                            order_id = order_result["id"]

                            # Log the trade to database for Recent Trades display
                            self._log_trade_to_db(
                                symbol=symbol,
                                action='BUY',
                                quantity=shares,
                                price=limit_price,
                                order_id=order_id,
                                strategy=strategy_name,
                                notes=f"OTO order: SL=${stop_loss_price:.2f} (profit optimizer handles exits)"
                            )

                            # Add to position tracker or scale in
                            if symbol in self.position_tracker.positions:
                                # Pyramiding - scale into existing position
                                self.position_tracker.scale_in(
                                    symbol=symbol,
                                    add_quantity=shares,
                                    add_price=limit_price
                                )
                                logger.info(
                                    f"PYRAMID (SCALE IN): BUY {shares} {symbol} @ ${limit_price:.2f}, "
                                    f"SL: ${stop_loss_price:.2f}, "
                                    f"Scale-ins: {self.position_tracker.positions[symbol].scale_in_count}/2"
                                )
                            else:
                                # New position - profit optimizer handles take profits via scale-outs
                                self.position_tracker.add_position(
                                    symbol=symbol,
                                    entry_price=limit_price,
                                    quantity=shares,
                                    side='long',
                                    stop_loss=stop_loss_price,
                                    take_profit=take_profit_price,  # Track for reference, not enforced by broker
                                    strategy=strategy_name,
                                    signal_strength=signal.strength,
                                    atr=atr
                                )
                                logger.info(
                                    f"OTO ORDER: BUY {shares} {symbol} @ ${limit_price:.2f}, "
                                    f"SL: ${stop_loss_price:.2f} (-{self.stop_loss_pct*100:.0f}%), "
                                    f"Exits: Profit Optimizer (scale-outs @ +8%, trailing stops), "
                                    f"VIX: {self.current_vix:.1f}"
                                )
                        except Exception as e:
                            logger.warning(f"OTO order failed, using simple limit: {e}")
                            # Fallback to simple limit order
                            order = self.order_manager.create_order(
                                symbol=symbol,
                                side="buy",
                                quantity=shares,
                                order_type="limit",
                                strategy=strategy_name
                            )
                            self.order_manager.submit_order(order)
                            order_id = order.id
                    else:
                        # Simple limit order (no risk management)
                        order = self.order_manager.create_order(
                            symbol=symbol,
                            side="buy",
                            quantity=shares,
                            order_type="limit",
                            strategy=strategy_name
                        )
                        self.order_manager.submit_order(order)
                        order_id = order.id

                    executed.append({
                        "symbol": symbol,
                        "action": "BUY",
                        "shares": shares,
                        "price": price,
                        "take_profit": take_profit_price,
                        "stop_loss": stop_loss_price,
                        "strategy": strategy_name,
                        "strength": signal.strength,
                        "order_id": order_id
                    })
                    buys_executed += 1

                    self.recent_trades[symbol] = datetime.now()

                    logger.info(
                        f"BUY {shares} shares of {symbol} @ ${price:.2f}",
                        extra={
                            "strategy": strategy_name,
                            "strength": signal.strength,
                            "take_profit": take_profit_price,
                            "stop_loss": stop_loss_price,
                            "order_id": order_id
                        }
                    )

                elif signal.signal_type == SignalType.SELL:
                    # Only sell if we have a position
                    if current_position <= 0:
                        continue

                    position_data = positions[symbol]
                    shares = int(position_data["qty"])

                    # CRITICAL FIX: Cancel any existing orders (bracket legs, stops) before selling
                    # This prevents "insufficient qty available" errors from locked shares
                    cancelled_count = 0
                    try:
                        # Check for pending orders first
                        open_orders = self.alpaca.get_open_orders_for_symbol(symbol)

                        if len(open_orders) > 0:
                            logger.info(
                                f"Found {len(open_orders)} pending orders for {symbol}, canceling before SELL"
                            )

                            cancelled_count = self.alpaca.cancel_orders_for_symbol(symbol)

                            if cancelled_count > 0:
                                # EXTENDED VERIFICATION: Wait up to 10 seconds (was 5)
                                max_wait = 10.0
                                wait_interval = 0.5
                                elapsed = 0.0
                                retry_count = 0
                                max_retries = 3

                                while elapsed < max_wait and retry_count < max_retries:
                                    time.sleep(wait_interval)
                                    elapsed += wait_interval

                                    # Verify cancellations completed
                                    remaining_orders = self.alpaca.get_open_orders_for_symbol(symbol)

                                    if len(remaining_orders) == 0:
                                        logger.info(
                                            f"Verified: all orders cancelled for {symbol} after {elapsed:.1f}s"
                                        )
                                        break
                                    else:
                                        retry_count += 1
                                        logger.debug(
                                            f"Cancellation retry {retry_count}/{max_retries}: "
                                            f"{len(remaining_orders)} orders still pending"
                                        )
                                else:
                                    # Timeout - check final state
                                    remaining_orders = self.alpaca.get_open_orders_for_symbol(symbol)
                                    if len(remaining_orders) > 0:
                                        logger.error(
                                            f"TIMEOUT: {len(remaining_orders)} orders still pending after {max_wait}s. "
                                            f"ABORTING SELL to avoid error 40310000"
                                        )
                                        # CRITICAL: Skip this sell to prevent "insufficient qty" error
                                        continue

                    except AlpacaClientError as e:
                        logger.warning(f"Failed to cancel/verify orders for {symbol}: {e}")
                        # If we can't verify, it's safer to skip the sell
                        continue

                    # Create and submit sell order
                    order = self.order_manager.create_order(
                        symbol=symbol,
                        side="sell",
                        quantity=shares,
                        order_type="limit",
                        strategy=strategy_name
                    )

                    try:
                        self.order_manager.submit_order(order)

                        # Remove from position tracker since we're exiting
                        if symbol in self.position_tracker.positions:
                            self.position_tracker.remove_position(
                                symbol=symbol,
                                reason=f"Strategy SELL signal (strength: {signal.strength:.2f})"
                            )

                        executed.append({
                            "symbol": symbol,
                            "action": "SELL",
                            "shares": shares,
                            "strategy": strategy_name,
                            "strength": signal.strength,
                            "order_id": order.id
                        })

                        self.recent_trades[symbol] = datetime.now()

                        logger.info(
                            f"SELL {shares} shares of {symbol}",
                            extra={
                                "strategy": strategy_name,
                                "strength": signal.strength,
                                "order_id": order.id
                            }
                        )

                    except (RiskLimitExceeded, AlpacaClientError) as e:
                        # Sell failed - re-protect the position if we cancelled stops
                        logger.error(f"SELL order failed for {symbol}: {e}")

                        if cancelled_count > 0:
                            logger.warning(
                                f"Re-adding stop protection for {symbol} since SELL failed"
                            )
                            try:
                                # Re-add basic stop loss protection
                                current_price = position_data["current_price"]
                                stop_price = current_price * (1 - self.stop_loss_pct)

                                self.alpaca.submit_stop_order(
                                    symbol=symbol,
                                    qty=shares,
                                    side="sell",
                                    stop_price=stop_price,
                                    time_in_force="gtc"
                                )
                                logger.info(f"Re-added stop loss for {symbol} @ ${stop_price:.2f}")
                            except AlpacaClientError as stop_error:
                                logger.error(
                                    f"Failed to re-add stop protection for {symbol}: {stop_error}"
                                )

                        # Don't add to executed list since order failed
                        continue

            except RiskLimitExceeded as e:
                logger.warning(f"Order rejected for {symbol}: {e}")
            except AlpacaClientError as e:
                logger.error(f"Order failed for {symbol}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing {symbol}: {e}")

        # Log signal conversion metrics
        conversion_rate = (len(executed) / total_signals * 100) if total_signals > 0 else 0
        logger.info(
            f"Signal conversion tracking [{strategy_name}]: "
            f"{total_signals} signals (BUY: {buy_signals}, SELL: {sell_signals}) -> "
            f"{len(executed)} executed ({conversion_rate:.1f}% conversion). "
            f"Skipped: recent_trade={skipped_recent_trade}, "
            f"existing_position={skipped_existing_position}, "
            f"no_shares={skipped_no_shares}, "
            f"optimizer_rejected={skipped_optimizer}, "
            f"insufficient_cash={skipped_insufficient_cash}, "
            f"pending_conflict={skipped_pending_conflict}, "
            f"correlation={skipped_correlation}, "
            f"regime={skipped_regime}"
        )

        return executed

    def run_cycle(self) -> dict:
        """
        Run one trading cycle.

        Returns:
            Cycle result with actions taken
        """
        self._cycle_count += 1
        cycle_start = datetime.now()
        result = {
            "timestamp": cycle_start.isoformat(),
            "cycle_number": self._cycle_count,
            "strategies_checked": 0,
            "signals_generated": 0,
            "trades_executed": [],
            "optimizations": [],
            "errors": []
        }

        # Run periodic cleanup
        self._maybe_cleanup()

        # Log cash status at cycle start
        self.log_cash_status()

        try:
            # Check market hours (with timeout protection)
            market = self._run_with_timeout(
                self.alpaca.get_market_hours,
                timeout=30,
                description="get market hours"
            )
            if market is None:
                result["errors"].append("Failed to get market hours")
                return result

            if not market["is_open"]:
                logger.info(f"Market closed. Next open: {market['next_open']}")
                result["market_status"] = "closed"
                return result
            else:
                result["market_status"] = "open"

            # Update market data
            self.update_market_data()

            # Detect market regime using SPY data
            try:
                spy_data = self.db.get_daily_bars("SPY", date.today() - timedelta(days=90))
                if not spy_data.empty:
                    regime_state = self.regime_detector.detect_regime(spy_data)
                    self.current_regime = regime_state.regime

                    # Also use VIX for additional regime signals
                    vix_regime, vix_mult = self.vix_regime_detector.detect_regime(self.current_vix)

                    result["regime"] = {
                        "regime": regime_state.regime.value,
                        "confidence": regime_state.confidence,
                        "vix_regime": vix_regime.value,
                        "vix_position_mult": vix_mult
                    }

                    logger.info(
                        f"Market regime: {regime_state.regime.value} "
                        f"(confidence: {regime_state.confidence:.1%}), "
                        f"VIX: {self.current_vix:.1f} ({vix_regime.value})"
                    )
            except Exception as e:
                logger.warning(f"Failed to detect regime: {e}")

            # Load data for all strategies
            start_date = date.today() - timedelta(days=400)  # 400 calendar days = ~280 trading days for 200-day SMA
            data = self.db.get_multiple_symbols(
                symbols=list(self.all_symbols),
                start_date=start_date
            )

            if not data or all(df.empty for df in data.values()):
                logger.warning("No market data available")
                result["errors"].append("No market data")
                return result

            # Get regime-based position multiplier
            regime_multiplier = 1.0
            if self.current_regime == MarketRegime.BEAR:
                regime_multiplier = 0.5  # Reduce exposure in bear markets
            elif self.current_regime == MarketRegime.SIDEWAYS:
                regime_multiplier = 0.75

            result["regime_multiplier"] = regime_multiplier

            # Run each strategy
            for strat_name, strategy in self.strategies.items():
                try:
                    # Get current signals
                    if strat_name in ["swing_momentum", "ml_momentum", "pairs_trading", "volatility_breakout", "simple_momentum", "factor_composite"]:
                        signals = strategy.get_current_signal(data)
                    else:
                        signal = strategy.get_current_signal(data)
                        signals = [signal] if signal else []

                    result["strategies_checked"] += 1
                    result["signals_generated"] += len(signals)

                    if signals:
                        # Process signals
                        trades = self.process_signals(signals, strat_name)
                        result["trades_executed"].extend(trades)

                        logger.info(
                            f"{strat_name}: {len(signals)} signals, {len(trades)} trades"
                        )

                except Exception as e:
                    logger.error(f"Error running {strat_name}: {e}")
                    result["errors"].append(f"{strat_name}: {str(e)}")

            # Optimize existing positions (trailing stops, profit taking, etc.)
            try:
                optimization_actions = self.optimize_positions()
                result["optimizations"] = optimization_actions

                if optimization_actions:
                    logger.info(f"Position optimizations: {len(optimization_actions)} actions")
            except Exception as e:
                logger.error(f"Error optimizing positions: {e}")
                result["errors"].append(f"optimization: {str(e)}")

            # Sync order states
            self.order_manager.sync_with_broker()

            # Track portfolio returns for VaR calculation
            try:
                account = self.alpaca.get_account()
                current_equity = account["equity"]
                if hasattr(self, '_last_equity') and self._last_equity > 0:
                    daily_return = (current_equity - self._last_equity) / self._last_equity
                    self._portfolio_returns.append(daily_return)
                    # Keep only last 252 returns (1 year)
                    if len(self._portfolio_returns) > 252:
                        self._portfolio_returns = self._portfolio_returns[-252:]
                self._last_equity = current_equity

                # Calculate VaR if we have enough data
                if len(self._portfolio_returns) >= 30:
                    import pandas as pd
                    returns_series = pd.Series(self._portfolio_returns)
                    risk_metrics = self.var_calculator.calculate_all_metrics(returns_series)
                    result["risk_metrics"] = {
                        "var_95": risk_metrics.var_95,
                        "cvar_95": risk_metrics.cvar_95,
                        "max_drawdown": risk_metrics.max_drawdown
                    }

                    # Check risk limits
                    within_limits, violations = self.var_calculator.check_risk_limits(risk_metrics)
                    if not within_limits:
                        logger.warning(f"RISK LIMIT BREACH: {violations}")
                        result["risk_violations"] = violations
            except Exception as e:
                logger.debug(f"VaR calculation skipped: {e}")

        except Exception as e:
            logger.error(f"Cycle error: {e}")
            result["errors"].append(str(e))

        cycle_duration = (datetime.now() - cycle_start).total_seconds()
        result["duration_seconds"] = cycle_duration

        # Write heartbeat for health monitoring daemon
        self._write_heartbeat(result)

        return result

    def print_status(self) -> None:
        """Print current status."""
        state = self.get_current_state()

        print("\n" + "=" * 70)
        print("AUTO TRADER STATUS - PROFIT OPTIMIZER EXIT STRATEGY (Option B)")
        print("=" * 70)

        print(f"\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Running: {self.running}")
        print(f"Check Interval: {self.check_interval}s")
        print(f"VIX: {self.current_vix:.2f} ({self.profit_optimizer.get_volatility_regime(self.current_vix).value})")
        print(f"Market Regime: {self.current_regime.value.upper()}")
        print(f"Market Phase: {self.profit_optimizer.get_market_phase().value}")

        print("\nAccount:")
        print(f"  Equity:       ${state['equity']:>12,.2f}")
        print(f"  Cash:         ${state['cash']:>12,.2f}")
        print(f"  Buying Power: ${state['buying_power']:>12,.2f}")

        pnl = state['equity'] - self.initial_equity
        pnl_pct = (pnl / self.initial_equity) * 100
        print(f"\n  Total P&L:    ${pnl:>+12,.2f} ({pnl_pct:+.2f}%)")

        print("\nPositions (Tracked):")
        if self.position_tracker.get_position_count() > 0:
            summary = self.position_tracker.get_position_summary()
            for _, row in summary.iterrows():
                scale_info = ""
                if row['scale_ins'] > 0 or row['scale_outs'] > 0:
                    scale_info = f" [+{row['scale_ins']}/-{row['scale_outs']}]"

                print(
                    f"  {row['symbol']:6s}: {row['quantity']:>6.0f} @ ${row['entry_price']:>8.2f} -> "
                    f"${row['current_price']:>8.2f} | P&L: {row['unrealized_pnl_pct']:>+6.1f}% | "
                    f"Stop: ${row['stop_loss']:>7.2f}{scale_info}"
                )

            winning = len(self.position_tracker.get_winning_positions())
            losing = len(self.position_tracker.get_losing_positions())
            total_pnl = self.position_tracker.get_total_unrealized_pnl()
            print(f"\n  Summary: {winning}W/{losing}L, Total P&L: ${total_pnl:+,.2f}")
        else:
            print("  No positions")

        print("\nStrategies:")
        for name in self.strategies:
            print(f"  - {name}")

        print("\nExit Strategy (Profit Optimizer - Option B):")
        print(f"  Entry Protection: OTO orders with -{self.stop_loss_pct*100:.0f}% stop loss")
        print(f"  Scale Out: Sell {self.profit_optimizer.first_target_size_pct*100:.0f}% @ +{self.profit_optimizer.first_target_pct*100:.1f}% profit")
        print(f"  Trailing Stop: {self.profit_optimizer.trailing_stop_pct*100:.1f}% / {self.profit_optimizer.trailing_stop_atr_multiple:.1f}x ATR (whichever tighter)")
        print(f"  Fast Exit: -{self.profit_optimizer.fast_exit_loss_pct*100:.1f}% (cut losers quickly)")
        print(f"  Pyramiding: Up to {self.profit_optimizer.max_scale_ins} scale-ins @ +{self.profit_optimizer.scale_in_profit_threshold*100:.1f}%")

        print("\nRecent Trades (last 4 hours):")
        if self.recent_trades:
            for symbol, trade_time in sorted(self.recent_trades.items(), key=lambda x: x[1], reverse=True):
                age = datetime.now() - trade_time
                print(f"  {symbol}: {age.total_seconds()/60:.0f} minutes ago")
        else:
            print("  None")

        print("=" * 70 + "\n")

    def start(self) -> None:
        """Start the auto trader."""
        self.running = True
        logger.info("Auto trader starting...")

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        self.print_status()

        cycle_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 10  # Only stop after 10 consecutive failed cycles

        while self.running and not self._shutdown_event.is_set():
            cycle_count += 1
            logger.info(f"=== Cycle {cycle_count} ===")

            try:
                result = self.run_cycle()
                consecutive_failures = 0  # Reset on success

                logger.info(
                    f"Cycle complete",
                    extra={
                        "strategies": result["strategies_checked"],
                        "signals": result["signals_generated"],
                        "trades": len(result["trades_executed"]),
                        "optimizations": len(result.get("optimizations", [])),
                        "duration": result.get("duration_seconds", 0)
                    }
                )

                if result["trades_executed"]:
                    print("\nTrades Executed:")
                    for trade in result["trades_executed"]:
                        print(f"  {trade['action']} {trade['shares']} {trade['symbol']} "
                              f"({trade['strategy']}, strength: {trade['strength']:.2f})")

                if result.get("optimizations"):
                    print("\nPosition Optimizations:")
                    for opt in result["optimizations"]:
                        action_str = opt['action'].upper()
                        if opt['action'] == 'scale_out':
                            print(f"  {action_str}: {opt['symbol']} -{opt['quantity']} @ ${opt['price']:.2f}")
                        elif opt['action'] == 'scale_in':
                            print(f"  {action_str}: {opt['symbol']} +{opt['quantity']} @ ${opt['price']:.2f}")
                        elif opt['action'] == 'update_stop':
                            print(f"  {action_str}: {opt['symbol']} stop -> ${opt['new_stop']:.2f}")
                        elif opt['action'] == 'close':
                            print(f"  {action_str}: {opt['symbol']} ({opt['reason']})")
                        print(f"    Reason: {opt['reason']}")

            except Exception as e:
                consecutive_failures += 1
                logger.error(
                    f"Cycle {cycle_count} failed ({consecutive_failures}/{max_consecutive_failures}): {e}"
                )

                if consecutive_failures >= max_consecutive_failures:
                    logger.critical(
                        f"FATAL: {max_consecutive_failures} consecutive cycle failures. Stopping."
                    )
                    break

                # Reset circuit breaker and reconnect after failure
                self._recover_from_failure()

                # Back off: wait longer after failures (30s * failure_count, max 5 min)
                backoff = min(30 * consecutive_failures, 300)
                logger.info(f"Backing off {backoff}s before retry...")
                self._shutdown_event.wait(backoff)
                continue

            # Print status every 5 cycles
            if cycle_count % 5 == 0:
                self.print_status()

            # Wait for next cycle
            logger.info(f"Waiting {self.check_interval}s until next check...")
            self._shutdown_event.wait(self.check_interval)

        logger.info("Auto trader stopped.")

    def _recover_from_failure(self) -> None:
        """Reset connections and circuit breakers after a failure (e.g., laptop wake)."""
        logger.info("Attempting recovery: resetting connections and circuit breakers...")

        # Reset Alpaca client circuit breaker
        try:
            with self.alpaca._lock:
                self.alpaca._consecutive_failures = 0
                self.alpaca._circuit_open_until = 0.0
            logger.info("Alpaca circuit breaker reset")
        except Exception as e:
            logger.warning(f"Failed to reset Alpaca circuit breaker: {e}")

        # Recreate HTTP sessions with fresh connections
        try:
            from requests.adapters import HTTPAdapter
            timeout_adapter = TimeoutHTTPAdapter(timeout=30)
            for client in [self.alpaca.trading_client, self.alpaca.data_client,
                           self.alpaca.crypto_data_client]:
                if hasattr(client, '_session'):
                    client._session.close()
                    # Session will be recreated on next use, but mount adapters
                    client._session.mount('https://', timeout_adapter)
                    client._session.mount('http://', timeout_adapter)
            logger.info("HTTP sessions refreshed with timeout adapters")
        except Exception as e:
            logger.warning(f"Failed to refresh HTTP sessions: {e}")

        # Reset data client circuit breaker too
        try:
            with self.data_client._lock:
                self.data_client._consecutive_failures = 0
                self.data_client._circuit_open_until = 0.0
            logger.info("Data client circuit breaker reset")
        except Exception as e:
            logger.warning(f"Failed to reset data client circuit breaker: {e}")

        # Invalidate cash manager cache (stale after sleep)
        try:
            self.cash_manager.invalidate_cache()
        except Exception:
            pass

        logger.info("Recovery complete - ready to retry")

    def stop(self) -> None:
        """Stop the auto trader and clean up resources."""
        logger.info("Stopping auto trader...")
        self.running = False
        self._shutdown_event.set()

        # Shut down executor
        try:
            self._executor.shutdown(wait=True, cancel_futures=True)
        except Exception as e:
            logger.error(f"Error shutting down executor: {e}")

        # Close database connection
        try:
            self.db.close()
        except Exception as e:
            logger.error(f"Error closing database: {e}")

        # Final garbage collection
        gc.collect()
        logger.info("Cleanup complete")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()


def main():
    parser = argparse.ArgumentParser(description="Automated trading service")
    parser.add_argument(
        "--strategies",
        nargs="+",
        default=["factor_composite", "simple_momentum", "pairs_trading"],
        help="Strategies to run (default: factor_composite, simple_momentum, pairs_trading)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between signal checks (default: 300)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/quant.db",
        help="Path to database"
    )
    parser.add_argument(
        "--status-only",
        action="store_true",
        help="Print status and exit"
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run one cycle and exit"
    )

    args = parser.parse_args()

    try:
        trader = AutoTrader(
            strategies=args.strategies,
            check_interval=args.interval,
            db_path=args.db
        )

        if args.status_only:
            trader.print_status()
        elif args.run_once:
            result = trader.run_cycle()
            trader.print_status()
            print(f"\nCycle result: {result}")
        else:
            # Run continuously
            print("\n" + "=" * 60)
            print("STARTING AUTOMATED TRADING")
            print("=" * 60)
            print(f"\nStrategies: {args.strategies}")
            print(f"Check Interval: {args.interval} seconds")
            print("\nPress Ctrl+C to stop\n")

            trader.start()

    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        logger.error(f"Auto trader failed: {e}")
        raise


if __name__ == "__main__":
    main()
