"""
Institutional-Grade Momentum Strategy

Based on proven academic research with STRICT signal discipline:
- Jegadeesh & Titman (1993): 12-1 month momentum
- Faber (2007): 10-month SMA trend filter
- Asness et al. (2013): Cross-sectional momentum

KEY IMPROVEMENTS over simple_momentum.py:
1. Monthly rebalancing ONLY (not daily whipsawing)
2. 200-day MA trend filter (Faber 2007)
3. Top 20% momentum ranking (cross-sectional)
4. NO SELL signals unless monthly rebalance
5. Position sizing by signal strength (Kelly-inspired)

TARGET METRICS:
- Sharpe Ratio > 1.5
- Max Drawdown < 15%
- Win Rate > 55%
- Turnover < 50% per year
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
import logging

import pandas as pd
import numpy as np

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams

logger = logging.getLogger(__name__)


class InstitutionalMomentumStrategy(BaseStrategy):
    """
    Monthly-rebalanced momentum strategy with strict trend filtering.

    Rules (CRITICAL - these create the edge):
    1. Calculate 12-month momentum (252 trading days back)
    2. Skip most recent month (21 days) to avoid reversal
    3. ONLY hold stocks above 200-day MA (Faber's trend filter)
    4. Rank all stocks by momentum, take top 20%
    5. Rebalance ONLY once per month (last trading day)
    6. Equal-weight top positions

    NO intraday signals. NO daily signals. Monthly discipline ONLY.
    """

    DEFAULT_UNIVERSE = [
        # Diversified ETF universe for momentum
        "SPY",   # S&P 500
        "QQQ",   # Nasdaq
        "IWM",   # Small caps
        "EFA",   # International developed
        "EEM",   # Emerging markets
        # Sector ETFs
        "XLF",   # Financials
        "XLK",   # Technology
        "XLE",   # Energy
        "XLV",   # Healthcare
        "XLI",   # Industrials
        "XLP",   # Consumer staples
        "XLY",   # Consumer discretionary
        # Safe haven
        "TLT",   # Long-term treasuries
        "GLD",   # Gold
    ]

    def __init__(
        self,
        momentum_lookback: int = 252,  # 12 months
        momentum_skip: int = 21,  # Skip recent month
        trend_filter_days: int = 200,  # 10-month SMA
        max_positions: int = 5,  # Diversified
        position_size_pct: float = 0.20,  # 20% per position
        min_momentum_pct: float = 0.05,  # Minimum 5% momentum
        universe: Optional[List[str]] = None,
        name: str = "institutional_momentum"
    ):
        """
        Initialize institutional momentum strategy.

        Args:
            momentum_lookback: Days for momentum formation (default: 252 = 12 months)
            momentum_skip: Days to skip at end (default: 21 = 1 month)
            trend_filter_days: Days for trend MA (default: 200 = 10 months)
            max_positions: Maximum positions (default: 5)
            position_size_pct: Target allocation per position (default: 20%)
            min_momentum_pct: Minimum momentum to consider (default: 5%)
            universe: Trading universe
            name: Strategy name
        """
        self.momentum_lookback = momentum_lookback
        self.momentum_skip = momentum_skip
        self.trend_filter_days = trend_filter_days
        self.max_positions = max_positions
        self.position_size_pct = position_size_pct
        self.min_momentum_pct = min_momentum_pct

        universe = universe or self.DEFAULT_UNIVERSE
        super().__init__(name=name, universe=universe)

        logger.info(
            f"InstitutionalMomentumStrategy initialized: "
            f"{momentum_lookback}-{momentum_skip} day momentum, "
            f"{trend_filter_days}-day MA filter, "
            f"max {max_positions} positions"
        )

    def _is_month_end(self, dt: date, all_dates: pd.DatetimeIndex) -> bool:
        """Check if date is last trading day of month."""
        current_month = dt.month

        # Find next trading day after this date
        future_dates = [d for d in all_dates if d.date() > dt]
        if not future_dates:
            return True  # Last day in data

        next_date = future_dates[0].date()
        return next_date.month != current_month

    def _calculate_momentum(self, prices: pd.Series, as_of_idx: int) -> Optional[float]:
        """
        Calculate 12-1 month momentum (Jegadeesh & Titman 1993).

        Returns percent change from t-252 to t-21 (skip recent month).
        """
        required = self.momentum_lookback + self.momentum_skip

        if as_of_idx < required:
            return None

        # Price 21 days ago (skip recent month to avoid reversal)
        recent_price = prices.iloc[as_of_idx - self.momentum_skip]

        # Price 252 days before that
        past_price = prices.iloc[as_of_idx - required]

        if past_price == 0 or pd.isna(past_price) or pd.isna(recent_price):
            return None

        return (recent_price - past_price) / past_price

    def _is_above_trend(self, prices: pd.Series, as_of_idx: int) -> bool:
        """Check if price is above long-term trend (Faber 2007)."""
        if as_of_idx < self.trend_filter_days:
            return False

        current_price = prices.iloc[as_of_idx]
        ma_200 = prices.iloc[as_of_idx - self.trend_filter_days + 1:as_of_idx + 1].mean()

        return current_price > ma_200

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Generate MONTHLY rebalancing signals.

        This is the KEY difference - we ONLY trade once per month.
        NO daily whipsawing.
        """
        self.validate_data(data)

        signals = []

        # Get reference dates
        ref_symbol = self.universe[0]
        if ref_symbol not in data:
            return signals

        all_dates = data[ref_symbol].index

        # Generate signals only at month-end
        for i in range(len(all_dates)):
            current_date = all_dates[i]
            current_date_obj = current_date.date() if hasattr(current_date, 'date') else current_date

            # CRITICAL: Only generate signals at month-end
            if not self._is_month_end(current_date_obj, all_dates):
                continue

            # Calculate momentum for all symbols
            momentum_scores = []

            for symbol in self.universe:
                if symbol not in data or data[symbol].empty:
                    continue

                df = data[symbol]

                # Find index for this date
                symbol_dates = df.index
                idx = None
                for j, dt in enumerate(symbol_dates):
                    if dt <= current_date:
                        idx = j

                if idx is None or idx < self.momentum_lookback + self.momentum_skip:
                    continue

                prices = df['close']

                # Calculate momentum
                mom = self._calculate_momentum(prices, idx)
                if mom is None or mom < self.min_momentum_pct:
                    continue

                # Apply trend filter
                if not self._is_above_trend(prices, idx):
                    continue

                momentum_scores.append({
                    'symbol': symbol,
                    'momentum': mom,
                    'date': current_date_obj
                })

            # Rank and select top N
            momentum_scores.sort(key=lambda x: x['momentum'], reverse=True)
            selected = momentum_scores[:self.max_positions]

            # Generate BUY signals for selected
            for item in selected:
                strength = min(1.0, item['momentum'] / 0.50)  # Normalize to [0, 1]

                signals.append(Signal(
                    date=item['date'],
                    symbol=item['symbol'],
                    signal_type=SignalType.BUY,
                    strength=strength,
                    metadata={
                        'strategy': self.name,
                        'momentum': item['momentum'],
                        'rank': selected.index(item) + 1
                    }
                ))

            # Generate SELL signals for others (if we're rebalancing)
            selected_symbols = {item['symbol'] for item in selected}
            for symbol in self.universe:
                if symbol not in selected_symbols:
                    signals.append(Signal(
                        date=current_date_obj,
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        strength=1.0,
                        metadata={
                            'strategy': self.name,
                            'reason': 'monthly_rebalance'
                        }
                    ))

        logger.info(f"Generated {len(signals)} signals ({len([s for s in signals if s.signal_type == SignalType.BUY])} BUY)")
        return signals

    def get_current_signal(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """Get current month's signals."""
        # Just use latest signals from generate_signals
        all_signals = self.generate_signals(data)

        if not all_signals:
            return []

        # Get most recent date
        latest_date = max(s.date for s in all_signals)

        # Return signals from latest month-end
        current_signals = [s for s in all_signals if s.date == latest_date]

        logger.info(f"Current signals: {len(current_signals)} ({latest_date})")
        return current_signals

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> float:
        """
        Calculate position size with Kelly-inspired scaling.

        Stronger momentum = larger position (up to max).
        """
        if signal.signal_type == SignalType.SELL:
            return 0.0

        # Base size
        base_size = portfolio_value * self.position_size_pct

        # Scale by signal strength (momentum)
        target_size = base_size * signal.strength

        # Cap at maximum
        max_size = portfolio_value * 0.25  # Never more than 25% in one position
        target_size = min(target_size, max_size)

        return target_size

    def get_backtest_params(self) -> BacktestParams:
        """Get backtest parameters."""
        return BacktestParams(
            start_date="2024-01-01",
            end_date="2026-02-01",
            initial_capital=100000.0,
            transaction_cost_bps=10,
            slippage_bps=5
        )
