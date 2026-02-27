"""
Dual Momentum Strategy Implementation.

Based on Gary Antonacci's Global Equities Momentum (GEM) strategy:
- Antonacci, G. (2013). "Absolute momentum: A simple rule-based strategy
  and universal trend-following overlay." Journal of Portfolio Management.

The strategy combines:
1. Relative Momentum: Compare returns across assets, select the strongest
2. Absolute Momentum: Only invest if the selected asset has positive momentum

This implementation uses SPY, QQQ as risk assets and TLT as safe haven.
"""

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
import logging

import pandas as pd
import numpy as np

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams


logger = logging.getLogger(__name__)


@dataclass
class MomentumScore:
    """Momentum calculation result for a symbol."""
    symbol: str
    return_12m: float
    is_positive: bool
    rank: int


class DualMomentumStrategy(BaseStrategy):
    """
    Dual Momentum (GEM) Strategy.

    Logic:
    1. At end of each month, calculate 12-month returns for risk assets (SPY, QQQ)
    2. If both negative: Hold safe haven (TLT)
    3. If at least one positive: Hold the one with highest return

    Historical Performance (1974-2023):
    - Sharpe Ratio: ~1.0-1.4 (after costs)
    - Max Drawdown: ~20% (vs ~55% for buy-and-hold SPY)
    - CAGR: ~12-15%

    Attributes:
        lookback_days: Number of trading days for momentum calculation (default: 252)
        risk_assets: Symbols to compare for relative momentum
        safe_haven: Symbol to hold when momentum is negative
    """

    # Focus on high-momentum US assets for bull market capture
    DEFAULT_RISK_ASSETS = ["SPY", "QQQ", "IWM"]  # US Large/Tech/Small - higher beta
    DEFAULT_SAFE_HAVEN = "TLT"  # Long bonds for flight to safety
    DEFAULT_LOOKBACK = 252  # 12 months per Antonacci (2013) academic standard
    DEFAULT_SKIP_DAYS = 21  # 1 month skip per academic standard

    def __init__(
        self,
        lookback_days: int = DEFAULT_LOOKBACK,
        skip_days: int = DEFAULT_SKIP_DAYS,
        risk_assets: Optional[List[str]] = None,
        safe_haven: str = DEFAULT_SAFE_HAVEN,
        use_trend_filter: bool = True,
        trend_ma_days: int = 200,
        name: str = "dual_momentum"
    ):
        """
        Initialize Dual Momentum Strategy.

        Args:
            lookback_days: Days for momentum calculation (default: 252 = 12 months)
            skip_days: Days to skip at end (default: 21 = 1 month, per J&T 1993)
            risk_assets: List of risk assets to compare
            safe_haven: Safe haven asset (default: AGG)
            use_trend_filter: Apply 200-day MA filter (Faber 2007)
            trend_ma_days: Days for trend MA (default: 200)
            name: Strategy identifier
        """
        self.lookback_days = lookback_days
        self.skip_days = skip_days
        self.risk_assets = [s.upper() for s in (risk_assets or self.DEFAULT_RISK_ASSETS)]
        self.safe_haven = safe_haven.upper()
        self.use_trend_filter = use_trend_filter
        self.trend_ma_days = trend_ma_days

        # Universe includes both risk assets and safe haven
        universe = self.risk_assets + [self.safe_haven]
        super().__init__(name=name, universe=universe)

        logger.info(
            "Initialized DualMomentumStrategy with improvements",
            extra={
                "lookback_days": lookback_days,
                "skip_days": skip_days,
                "risk_assets": self.risk_assets,
                "safe_haven": self.safe_haven,
                "trend_filter": use_trend_filter
            }
        )

    def _calculate_momentum(
        self,
        prices: pd.Series,
        as_of_date: date
    ) -> Optional[float]:
        """
        Calculate momentum (return) over lookback period with skip.

        Implements Jegadeesh & Titman (1993) 12-1 month momentum:
        - Measure returns from t-12 to t-1 months
        - Skip most recent month to avoid short-term reversal

        Args:
            prices: Price series with DatetimeIndex
            as_of_date: Calculate momentum as of this date

        Returns:
            Return over lookback period, or None if insufficient data
        """
        # Filter to dates on or before as_of_date
        prices = prices[prices.index.date <= as_of_date]

        required_days = self.lookback_days + self.skip_days
        if len(prices) < required_days:
            logger.warning(
                f"Insufficient data for momentum calculation: "
                f"need {required_days}, have {len(prices)}"
            )
            return None

        # CRITICAL FIX: Skip most recent month (Jegadeesh & Titman 1993)
        # Measure momentum from t-252 to t-21, not t-252 to t
        # This avoids short-term reversal effects
        current_price = prices.iloc[-self.skip_days] if self.skip_days > 0 else prices.iloc[-1]
        lookback_price = prices.iloc[-(self.lookback_days + self.skip_days)]

        if lookback_price == 0:
            return None

        momentum = (current_price - lookback_price) / lookback_price
        return float(momentum)

    def _get_momentum_scores(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> List[MomentumScore]:
        """
        Calculate momentum scores for all risk assets.

        Args:
            data: Market data dict
            as_of_date: Calculate momentum as of this date

        Returns:
            List of MomentumScore sorted by return (descending)
        """
        scores = []

        for symbol in self.risk_assets:
            if symbol not in data or data[symbol].empty:
                logger.warning(f"Missing data for {symbol}")
                continue

            prices = data[symbol]["close"]
            momentum = self._calculate_momentum(prices, as_of_date)

            if momentum is not None:
                scores.append(MomentumScore(
                    symbol=symbol,
                    return_12m=momentum,
                    is_positive=momentum > 0,
                    rank=0  # Will be set after sorting
                ))

        # Sort by return descending and assign ranks
        scores.sort(key=lambda x: x.return_12m, reverse=True)
        for i, score in enumerate(scores):
            score.rank = i + 1

        return scores

    def _is_month_end(self, dt: date, data: Dict[str, pd.DataFrame]) -> bool:
        """
        Check if date is the last trading day of the month.

        Args:
            dt: Date to check
            data: Market data (used to get trading calendar)

        Returns:
            True if dt is last trading day of its month
        """
        # Get any symbol's dates as trading calendar
        sample_symbol = self.risk_assets[0]
        if sample_symbol not in data or data[sample_symbol].empty:
            return False

        trading_dates = data[sample_symbol].index
        trading_dates = trading_dates[trading_dates.date <= dt]

        if len(trading_dates) == 0:
            return False

        # Get the date and check if it's the last trading day of the month
        current_date = trading_dates[-1].date() if hasattr(trading_dates[-1], 'date') else trading_dates[-1]

        # Find next trading day
        future_dates = data[sample_symbol].index[data[sample_symbol].index.date > current_date]
        if len(future_dates) == 0:
            return True  # No future data, assume month end

        next_date = future_dates[0].date() if hasattr(future_dates[0], 'date') else future_dates[0]

        # If next trading day is in a different month, current is month end
        return current_date.month != next_date.month

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Generate monthly rebalancing signals.

        Args:
            data: Dict mapping symbol to DataFrame with OHLCV data

        Returns:
            List of Signal objects (one per month-end in the data)
        """
        self.validate_data(data)

        signals = []

        # Get all dates from a reference symbol
        ref_symbol = self.risk_assets[0]
        all_dates = data[ref_symbol].index

        # Skip first lookback_days to ensure we have enough history
        if len(all_dates) <= self.lookback_days:
            logger.warning("Insufficient data for signal generation")
            return signals

        # Iterate through dates starting after lookback period
        for i in range(self.lookback_days, len(all_dates)):
            current_date = all_dates[i]
            if hasattr(current_date, 'date'):
                current_date = current_date.date()

            # Only generate signals at month end
            if not self._is_month_end(current_date, data):
                continue

            # Calculate momentum scores
            scores = self._get_momentum_scores(data, current_date)

            if not scores:
                logger.warning(f"No momentum scores for {current_date}")
                continue

            # Decision logic with trend filter (Faber 2007)
            best_score = scores[0]  # Highest momentum

            # Apply 200-day MA trend filter (Faber 2007: only hold when price > 10-month SMA)
            trend_valid = True
            if self.use_trend_filter and best_score.is_positive:
                # Check if best asset is above its 200-day MA
                best_symbol = best_score.symbol
                if best_symbol in data and not data[best_symbol].empty:
                    prices = data[best_symbol]["close"]
                    prices = prices[prices.index.date <= current_date]

                    if len(prices) >= self.trend_ma_days:
                        current_price = prices.iloc[-1]
                        ma_200 = prices.rolling(self.trend_ma_days).mean().iloc[-1]
                        trend_valid = current_price > ma_200

                        if not trend_valid:
                            logger.debug(
                                f"{current_date}: {best_symbol} momentum positive but below 200-MA "
                                f"(${current_price:.2f} < ${ma_200:.2f}), going to safe haven"
                            )

            if best_score.is_positive and trend_valid:
                # Relative momentum: buy the best performing risk asset
                target_symbol = best_score.symbol
                signal_strength = min(1.0, abs(best_score.return_12m))

                logger.debug(
                    f"{current_date}: Positive momentum, selecting {target_symbol} "
                    f"(12m return: {best_score.return_12m:.2%})"
                )
            else:
                # Absolute momentum filter OR trend filter: go to safe haven
                target_symbol = self.safe_haven
                signal_strength = 1.0

                reason = "negative momentum" if not best_score.is_positive else "below trend"
                logger.debug(
                    f"{current_date}: {reason}, selecting safe haven {self.safe_haven}"
                )

            # Generate BUY signal for target
            signals.append(Signal(
                date=current_date,
                symbol=target_symbol,
                signal_type=SignalType.BUY,
                strength=signal_strength,
                metadata={
                    "strategy": self.name,
                    "momentum_scores": [
                        {"symbol": s.symbol, "return_12m": s.return_12m, "rank": s.rank}
                        for s in scores
                    ],
                    "absolute_momentum_triggered": not best_score.is_positive
                }
            ))

            # Generate SELL signals for other positions
            for symbol in self.universe:
                if symbol != target_symbol:
                    signals.append(Signal(
                        date=current_date,
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        strength=1.0,
                        metadata={"strategy": self.name, "reason": "not_selected"}
                    ))

        logger.info(f"Generated {len(signals)} signals")
        return signals

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> float:
        """
        Calculate position size for a signal.

        For Dual Momentum, we go 100% into the selected asset.
        This is appropriate because we're only ever in one position.

        Args:
            signal: The trading signal
            portfolio_value: Current total portfolio value
            current_positions: Current positions (symbol -> value)

        Returns:
            Target position size in dollars
        """
        if signal.signal_type == SignalType.SELL:
            return 0.0

        if signal.signal_type == SignalType.HOLD:
            return current_positions.get(signal.symbol, 0.0)

        # BUY: allocate full portfolio to the selected asset
        # Signal strength could be used to scale position in more complex strategies
        target_size = portfolio_value * signal.strength

        logger.debug(
            f"Position size for {signal.symbol}: ${target_size:,.2f} "
            f"({signal.strength:.0%} of ${portfolio_value:,.2f})"
        )

        return target_size

    def get_backtest_params(self) -> BacktestParams:
        """Return default backtesting parameters."""
        return BacktestParams(
            start_date="2014-01-01",
            end_date="2024-12-31",
            initial_capital=10000.0,
            rebalance_frequency="monthly",
            transaction_cost_bps=10,
            slippage_bps=10
        )

    def get_required_history(self) -> int:
        """Return required historical data length."""
        return max(self.lookback_days + self.skip_days, self.trend_ma_days) + 30

    def get_current_signal(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[date] = None
    ) -> Optional[Signal]:
        """
        Get the current (most recent) signal.

        Convenience method for live trading.

        Args:
            data: Market data
            as_of_date: Date to calculate signal for (default: latest in data)

        Returns:
            Most recent BUY signal, or None
        """
        signals = self.generate_signals(data)
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]

        if not buy_signals:
            return None

        if as_of_date:
            # Find most recent signal on or before as_of_date
            valid_signals = [s for s in buy_signals if s.date <= as_of_date]
            return valid_signals[-1] if valid_signals else None

        return buy_signals[-1]
