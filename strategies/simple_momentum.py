"""
Simple Aggressive Momentum Strategy.

This strategy is designed to:
1. Generate more frequent trading signals
2. Capture bull market momentum
3. Use simple, proven rules

Based on the 10-month SMA timing model (Faber 2007):
- BUY when price > 50-day SMA (bullish)
- SELL when price < 50-day SMA (bearish)
- Use 20-day momentum for ranking

Simple rules = fewer false signals, more robust performance.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
import logging

import pandas as pd
import numpy as np

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams
from risk.kelly_sizing import KellyPositionSizer, DEFAULT_STRATEGY_STATS


logger = logging.getLogger(__name__)


class SimpleMomentumStrategy(BaseStrategy):
    """
    Simple momentum strategy optimized for bull markets.

    Rules:
    1. Price must be above 50-day SMA (trend filter)
    2. 20-day momentum must be positive
    3. Buy the top 3 momentum stocks
    4. Sell when price crosses below 50-day SMA

    This generates more signals than complex strategies.
    """

    # High-momentum, liquid ETFs and stocks - expanded for more opportunities
    DEFAULT_UNIVERSE = [
        # Original ETFs
        "QQQ",   # Nasdaq - tech heavy, high momentum
        "SPY",   # S&P 500 - broad market
        "XLK",   # Technology sector
        "SOXX",  # Semiconductors - very high momentum
        "IWM",   # Small caps
        "XLF",   # Financials
        "XLE",   # Energy
        "ARKK",  # Innovation ETF
        # Tech Stocks - high liquidity and momentum
        "NVDA",  # NVIDIA - AI/GPU leader
        "TSLA",  # Tesla - high beta EV
        "AMD",   # AMD - semiconductors
        "META",  # Meta - social media
        "GOOGL", # Alphabet - search/cloud
        "AMZN",  # Amazon - ecommerce/cloud
        "MSFT",  # Microsoft - enterprise/cloud
        "AAPL",  # Apple - consumer tech
        # High-Beta Leveraged ETFs
        "TQQQ",  # 3x Nasdaq Bull
        "SOXL",  # 3x Semiconductors Bull
        "UPRO",  # 3x S&P 500 Bull
        # Additional Sector ETFs
        "XLY",   # Consumer Discretionary
        "XLP",   # Consumer Staples
        "XLB",   # Materials
        "XLC",   # Communication Services
    ]

    def __init__(
        self,
        sma_period: int = 100,  # 100-day SMA (200 was too slow, missed 30% of rallies)
        momentum_period: int = 63,  # 3-month momentum (6-month was glacial for active trading)
        max_positions: int = 10,  # Diversified across 10 positions
        position_size_pct: float = 0.15,  # 15% per position (12% left too much cash idle)
        universe: Optional[List[str]] = None,
        name: str = "simple_momentum"
    ):
        """
        Initialize simple momentum strategy.

        Args:
            sma_period: Days for trend filter SMA (default: 50)
            momentum_period: Days for momentum calculation (default: 20)
            max_positions: Maximum concurrent positions (default: 3)
            position_size_pct: Position size as % of portfolio (default: 15%)
            universe: List of symbols to trade
            name: Strategy identifier
        """
        self.sma_period = sma_period
        self.momentum_period = momentum_period
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct

        # VIX regime multiplier - updated by auto_trader each cycle
        self.regime_multiplier = 1.0

        # Initialize Kelly position sizer for optimal position sizing
        self.kelly_sizer = KellyPositionSizer(
            kelly_fraction=0.25,  # Quarter Kelly (conservative)
            max_position_pct=self.position_size_pct,  # Use strategy max as ceiling
            min_position_pct=0.02  # Minimum 2% position
        )
        # Load default stats for simple_momentum
        if 'simple_momentum' in DEFAULT_STRATEGY_STATS:
            stats = DEFAULT_STRATEGY_STATS['simple_momentum']
            self.kelly_sizer.update_stats_from_signals(
                strategy_name=name,
                win_rate=stats.win_rate,
                avg_win=stats.avg_win,
                avg_loss=stats.avg_loss,
                num_trades=stats.num_trades,
                sharpe=stats.sharpe,
                max_drawdown=stats.max_drawdown
            )

        universe = universe or self.DEFAULT_UNIVERSE
        super().__init__(name=name, universe=universe)

        logger.info(
            f"SimpleMomentumStrategy initialized",
            extra={
                "sma_period": sma_period,
                "momentum_period": momentum_period,
                "max_positions": max_positions,
                "universe": self.universe
            }
        )

    def _calculate_signals(self, data: Dict[str, pd.DataFrame]) -> List[dict]:
        """Calculate momentum and trend signals for all symbols."""
        signals = []

        for symbol in self.universe:
            if symbol not in data or data[symbol].empty:
                continue

            df = data[symbol]
            if len(df) < self.sma_period + 5:
                continue

            # Calculate indicators
            close = df['close']
            sma = close.rolling(self.sma_period).mean()

            # 20-day momentum (percent change)
            momentum = (close / close.shift(self.momentum_period) - 1) * 100

            # Get latest values
            latest_close = close.iloc[-1]
            latest_sma = sma.iloc[-1]
            latest_momentum = momentum.iloc[-1]

            # Trend filter: price above SMA
            above_trend = latest_close > latest_sma

            # Calculate signal strength (0-1)
            # Based on how far above SMA and momentum strength
            if above_trend and latest_momentum > 0:
                pct_above_sma = (latest_close - latest_sma) / latest_sma
                strength = min(1.0, (pct_above_sma * 10 + latest_momentum / 10) / 2)
                strength = max(0.3, strength)  # Minimum 0.3 strength

                signals.append({
                    "symbol": symbol,
                    "signal": "BUY",
                    "strength": strength,
                    "momentum": latest_momentum,
                    "pct_above_sma": pct_above_sma * 100,
                    "price": latest_close
                })
            elif not above_trend:
                # Sell signal if below SMA
                signals.append({
                    "symbol": symbol,
                    "signal": "SELL",
                    "strength": 0.8,
                    "momentum": latest_momentum,
                    "pct_above_sma": ((latest_close - latest_sma) / latest_sma) * 100,
                    "price": latest_close
                })

        return signals

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Generate trading signals from market data for backtesting.

        OPTIMIZED: Generate signals WEEKLY (not daily) to reduce whipsawing.
        This dramatically reduces transaction costs.

        Args:
            data: Dict mapping symbol to OHLCV DataFrame

        Returns:
            List of Signal objects
        """
        all_signals = []

        # Get all trading dates from the first symbol
        ref_symbol = list(data.keys())[0]
        all_dates = data[ref_symbol].index[self.sma_period + 5:]  # Skip warmup period

        last_signal_date = None

        for signal_date in all_dates:
            # CRITICAL OPTIMIZATION: Only generate signals weekly (every 5 trading days)
            if last_signal_date is not None:
                days_diff = (signal_date.date() - last_signal_date if hasattr(signal_date, 'date')
                            else signal_date - last_signal_date).days
                if days_diff < 5:  # Skip if less than 5 days since last signal
                    continue
            # Slice data up to this date
            data_slice = {}
            for symbol, df in data.items():
                mask = df.index <= signal_date
                data_slice[symbol] = df[mask]

            # Calculate signals for this date
            day_signals = []
            for symbol in self.universe:
                if symbol not in data_slice or data_slice[symbol].empty:
                    continue

                df = data_slice[symbol]
                if len(df) < self.sma_period + 5:
                    continue

                close = df['close']
                sma = close.rolling(self.sma_period).mean()
                momentum = (close / close.shift(self.momentum_period) - 1) * 100

                latest_close = close.iloc[-1]
                latest_sma = sma.iloc[-1]
                latest_momentum = momentum.iloc[-1]

                if pd.isna(latest_sma) or pd.isna(latest_momentum):
                    continue

                above_trend = latest_close > latest_sma

                if above_trend and latest_momentum > 0:
                    pct_above_sma = (latest_close - latest_sma) / latest_sma
                    strength = min(1.0, max(0.3, (pct_above_sma * 10 + latest_momentum / 10) / 2))

                    day_signals.append({
                        "symbol": symbol,
                        "signal": "BUY",
                        "strength": strength,
                        "momentum": latest_momentum,
                        "date": signal_date.date() if hasattr(signal_date, 'date') else signal_date
                    })
                elif not above_trend:
                    day_signals.append({
                        "symbol": symbol,
                        "signal": "SELL",
                        "strength": 0.8,
                        "momentum": latest_momentum,
                        "date": signal_date.date() if hasattr(signal_date, 'date') else signal_date
                    })

            # Sort buy signals by momentum and take top N
            buy_signals = sorted(
                [s for s in day_signals if s["signal"] == "BUY"],
                key=lambda x: x["momentum"],
                reverse=True
            )[:self.max_positions]

            sell_signals = [s for s in day_signals if s["signal"] == "SELL"]

            # Convert to Signal objects
            for s in buy_signals:
                all_signals.append(Signal(
                    date=s["date"],
                    symbol=s["symbol"],
                    signal_type=SignalType.BUY,
                    strength=s["strength"],
                    metadata={"momentum": s["momentum"], "strategy": self.name}
                ))

            for s in sell_signals:
                all_signals.append(Signal(
                    date=s["date"],
                    symbol=s["symbol"],
                    signal_type=SignalType.SELL,
                    strength=s["strength"],
                    metadata={"momentum": s["momentum"], "strategy": self.name}
                ))

            # Update last signal date
            last_signal_date = signal_date.date() if hasattr(signal_date, 'date') else signal_date

        logger.info(f"Generated {len(all_signals)} total signals for backtesting")
        return all_signals

    def get_current_signal(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Get current trading signals (for live trading).

        Returns only the latest date's actionable signals, sorted by momentum.
        """
        # Calculate signals for the latest data
        raw_signals = self._calculate_signals(data)

        if not raw_signals:
            logger.debug("No signals generated for current data")
            return []

        # Filter to BUY signals only for new position consideration
        buy_signals = [s for s in raw_signals if s["signal"] == "BUY"]
        sell_signals = [s for s in raw_signals if s["signal"] == "SELL"]

        # Sort buy signals by momentum (strongest first) and take top N
        buy_signals_sorted = sorted(
            buy_signals,
            key=lambda x: x["momentum"],
            reverse=True
        )[:self.max_positions]

        # Get latest date from data
        ref_symbol = list(data.keys())[0]
        latest_date = data[ref_symbol].index[-1]
        signal_date = latest_date.date() if hasattr(latest_date, 'date') else latest_date

        # Convert to Signal objects
        result_signals = []

        for s in buy_signals_sorted:
            result_signals.append(Signal(
                date=signal_date,
                symbol=s["symbol"],
                signal_type=SignalType.BUY,
                strength=s["strength"],
                metadata={
                    "momentum": s["momentum"],
                    "pct_above_sma": s["pct_above_sma"],
                    "strategy": self.name
                }
            ))

        for s in sell_signals:
            result_signals.append(Signal(
                date=signal_date,
                symbol=s["symbol"],
                signal_type=SignalType.SELL,
                strength=s["strength"],
                metadata={
                    "momentum": s["momentum"],
                    "strategy": self.name
                }
            ))

        logger.info(
            f"Generated {len(result_signals)} current signals "
            f"({len(buy_signals_sorted)} BUY, {len(sell_signals)} SELL) "
            f"from {len(raw_signals)} total signals"
        )

        return result_signals

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> float:
        """
        Calculate position size for a signal.

        Uses Kelly Criterion for optimal position sizing based on:
        - Historical win rate and avg win/loss
        - Signal strength (confidence)
        - Portfolio value

        Fractional Kelly (1/4) is used for conservative sizing.

        Args:
            signal: Trading signal
            portfolio_value: Total portfolio value
            current_positions: Dict of symbol -> position value

        Returns:
            Target position value in dollars
        """
        # Use Kelly sizing with signal strength and VIX regime adjustment
        target_size = self.kelly_sizer.calculate_position_size(
            strategy_name=self.name,
            portfolio_value=portfolio_value,
            signal_strength=signal.strength,
            current_regime_multiplier=self.regime_multiplier
        )

        # Fallback to fixed sizing if Kelly returns 0 (e.g., no stats yet)
        if target_size == 0:
            target_size = portfolio_value * self.position_size_pct * signal.strength * self.regime_multiplier

        return target_size

    def get_backtest_params(self) -> BacktestParams:
        """Get default backtest parameters."""
        return BacktestParams(
            start_date="2024-01-01",
            end_date="2026-02-01",
            initial_capital=100000.0,
            transaction_cost_bps=10,
            slippage_bps=5
        )
