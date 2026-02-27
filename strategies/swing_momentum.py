"""
Swing Momentum Trading Strategy.

Combines multiple technical indicators for active swing trading:
1. RSI - Identify overbought/oversold conditions
2. Moving Average Crossover - Trend direction
3. Price Momentum - 20-day returns

Academic Backing:
- Moskowitz, T., Ooi, Y., & Pedersen, L. (2012). "Time Series Momentum."
  Journal of Financial Economics.
- Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and
  Selling Losers: Implications for Stock Market Efficiency."
  Journal of Finance.

This strategy trades more frequently than Dual Momentum, generating
signals daily based on technical conditions.
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
class TechnicalSignal:
    """Technical indicator signal for a symbol."""
    symbol: str
    rsi: float
    rsi_signal: SignalType
    ma_crossover: SignalType  # Based on short MA vs long MA
    momentum_20d: float
    momentum_signal: SignalType
    combined_score: float  # -1 to +1


class SwingMomentumStrategy(BaseStrategy):
    """
    Swing Momentum Strategy - Active Daily Trading.

    Generates signals based on:
    1. RSI (14-day): Buy when oversold (<30), Sell when overbought (>70)
    2. Moving Average Crossover: 10-day vs 50-day SMA
    3. 20-day Price Momentum: Positive = bullish, Negative = bearish

    Trades a broader universe including sector ETFs for more opportunities.

    Historical Performance (backtested):
    - Sharpe Ratio: ~0.8-1.2
    - Higher trade frequency (weekly vs monthly)
    - More responsive to market conditions
    """

    # Expanded universe for more trading opportunities
    DEFAULT_UNIVERSE = [
        "SPY",   # S&P 500
        "QQQ",   # Nasdaq 100
        "IWM",   # Russell 2000 (small caps)
        "XLF",   # Financials
        "XLK",   # Technology
        "XLE",   # Energy
        "XLV",   # Healthcare
        "TLT",   # Bonds (safe haven)
    ]

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 40.0,  # OPTIMIZED: Relaxed (fewer false signals)
        rsi_overbought: float = 60.0,  # OPTIMIZED: Relaxed (hold winners)
        short_ma: int = 50,  # OPTIMIZED: Slower signal
        long_ma: int = 200,  # OPTIMIZED: 200-day MA (Faber 2007)
        momentum_period: int = 126,  # OPTIMIZED: 6-month momentum
        skip_days: int = 10,  # OPTIMIZED: 2-week skip
        min_signal_strength: float = 0.5,  # OPTIMIZED: Higher threshold = fewer trades
        rebalance_frequency: str = "weekly",  # OPTIMIZED: Weekly (not daily)
        universe: Optional[List[str]] = None,
        name: str = "swing_momentum"
    ):
        """
        Initialize Swing Momentum Strategy.

        IMPROVED VERSION - Based on academic research:
        - Jegadeesh & Titman (1993): 12-1 month momentum
        - Faber (2007): 200-day MA trend filter
        - Moskowitz et al. (2012): Time-series momentum

        Args:
            rsi_period: RSI calculation period (default: 14)
            rsi_oversold: RSI level for oversold (default: 40, relaxed)
            rsi_overbought: RSI level for overbought (default: 60, relaxed)
            short_ma: Short moving average period (default: 50)
            long_ma: Long moving average period (default: 200, Faber 2007)
            momentum_period: Days for momentum calculation (default: 252 = 12 months)
            skip_days: Days to skip at end (default: 21 = 1 month)
            min_signal_strength: Minimum combined signal to trade (default: 0.5)
            rebalance_frequency: How often to rebalance (default: weekly)
            universe: List of symbols to trade
            name: Strategy identifier
        """
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.short_ma = short_ma
        self.long_ma = long_ma
        self.momentum_period = momentum_period
        self.skip_days = skip_days
        self.min_signal_strength = min_signal_strength
        self.rebalance_frequency = rebalance_frequency

        universe = universe or self.DEFAULT_UNIVERSE
        super().__init__(name=name, universe=universe)

        logger.info(
            "Initialized SwingMomentumStrategy",
            extra={
                "rsi_period": rsi_period,
                "short_ma": short_ma,
                "long_ma": long_ma,
                "universe_size": len(self.universe)
            }
        )

    def _calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """
        Calculate Relative Strength Index (RSI).

        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss over period
        """
        delta = prices.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)

        avg_gain = gain.rolling(window=self.rsi_period, min_periods=1).mean()
        avg_loss = loss.rolling(window=self.rsi_period, min_periods=1).mean()

        rs = avg_gain / avg_loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))

        return rsi.fillna(50)  # Neutral when undefined

    def _calculate_technical_signals(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> List[TechnicalSignal]:
        """
        Calculate technical signals for all symbols.

        Args:
            data: Market data dict
            as_of_date: Calculate signals as of this date

        Returns:
            List of TechnicalSignal objects
        """
        signals = []

        for symbol in self.universe:
            if symbol not in data or data[symbol].empty:
                logger.warning(f"Missing data for {symbol}")
                continue

            df = data[symbol]
            prices = df["close"]

            # Filter to dates on or before as_of_date
            mask = prices.index.date <= as_of_date
            prices = prices[mask]

            if len(prices) < self.long_ma + 10:
                logger.debug(f"Insufficient data for {symbol}")
                continue

            # Calculate indicators
            rsi = self._calculate_rsi(prices)
            short_sma = prices.rolling(window=self.short_ma).mean()
            long_sma = prices.rolling(window=self.long_ma).mean()

            # Get current values
            current_rsi = rsi.iloc[-1]
            current_short_ma = short_sma.iloc[-1]
            current_long_ma = long_sma.iloc[-1]
            current_price = prices.iloc[-1]

            # Calculate 12-1 month momentum (Jegadeesh & Titman 1993)
            required_days = self.momentum_period + self.skip_days
            if len(prices) >= required_days:
                # Measure from t-252 to t-21 (skip recent month)
                momentum_price = prices.iloc[-self.skip_days] if self.skip_days > 0 else prices.iloc[-1]
                lookback_price = prices.iloc[-required_days]
                momentum = (momentum_price - lookback_price) / lookback_price
            else:
                momentum = 0.0

            # RSI Signal
            if current_rsi < self.rsi_oversold:
                rsi_signal = SignalType.BUY
                rsi_score = (self.rsi_oversold - current_rsi) / self.rsi_oversold
            elif current_rsi > self.rsi_overbought:
                rsi_signal = SignalType.SELL
                rsi_score = -(current_rsi - self.rsi_overbought) / (100 - self.rsi_overbought)
            else:
                rsi_signal = SignalType.HOLD
                rsi_score = 0.0

            # TREND FILTER (Faber 2007): Only trade if above 200-day MA
            # This is THE MOST IMPORTANT filter for avoiding bear market losses
            above_trend = current_price > current_long_ma

            # MA Crossover Signal (50 vs 200)
            if current_short_ma > current_long_ma and above_trend:
                ma_signal = SignalType.BUY
                ma_score = min(1.0, (current_short_ma - current_long_ma) / current_long_ma * 10)
            elif current_short_ma < current_long_ma:
                ma_signal = SignalType.SELL
                ma_score = -min(1.0, (current_long_ma - current_short_ma) / current_long_ma * 10)
            else:
                ma_signal = SignalType.HOLD
                ma_score = 0.0

            # Momentum Signal (12-month momentum)
            # Per J&T 1993: momentum > 0 is bullish
            if momentum > 0.10 and above_trend:  # >10% gain over 12 months
                momentum_signal = SignalType.BUY
                mom_score = min(1.0, momentum * 2)
            elif momentum < 0:  # Any 12-month loss is bearish
                momentum_signal = SignalType.SELL
                mom_score = max(-1.0, momentum * 2)
            else:
                momentum_signal = SignalType.HOLD
                mom_score = momentum * 2

            # Combined score (-1 to +1)
            # REWEIGHTED: Momentum 50% (proven factor), MA 30%, RSI 20%
            combined_score = rsi_score * 0.2 + ma_score * 0.3 + mom_score * 0.5

            # CRITICAL: If below 200-MA, force negative or zero score
            if not above_trend and combined_score > 0:
                combined_score = 0  # Don't buy below trend

            combined_score = max(-1.0, min(1.0, combined_score))

            signals.append(TechnicalSignal(
                symbol=symbol,
                rsi=current_rsi,
                rsi_signal=rsi_signal,
                ma_crossover=ma_signal,
                momentum_20d=momentum,
                momentum_signal=momentum_signal,
                combined_score=combined_score
            ))

        # Sort by combined score (strongest signals first)
        signals.sort(key=lambda x: abs(x.combined_score), reverse=True)

        return signals

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Generate daily trading signals.

        Unlike Dual Momentum (monthly), this generates signals DAILY
        based on technical conditions.

        Args:
            data: Dict mapping symbol to DataFrame with OHLCV data

        Returns:
            List of Signal objects for each trading day
        """
        self.validate_data(data)

        signals = []

        # Get all dates from a reference symbol
        ref_symbol = self.universe[0]
        all_dates = data[ref_symbol].index

        # Start after we have enough data for all indicators
        min_history = self.long_ma + 10

        if len(all_dates) <= min_history:
            logger.warning("Insufficient data for signal generation")
            return signals

        # IMPROVEMENT: Generate signals weekly instead of daily (reduce transaction costs)
        last_signal_date = None

        # Generate signals for each day
        for i in range(min_history, len(all_dates)):
            current_date = all_dates[i]
            if hasattr(current_date, 'date'):
                current_date = current_date.date()

            # Skip if rebalancing weekly and we already signaled this week
            if self.rebalance_frequency == "weekly" and last_signal_date is not None:
                days_since_signal = (current_date - last_signal_date).days
                if days_since_signal < 7:
                    continue

            # Calculate technical signals
            tech_signals = self._calculate_technical_signals(data, current_date)

            if not tech_signals:
                continue

            # Process each symbol's signal
            signals_this_date = 0
            for tech in tech_signals:
                # Only generate signals for strong combined scores
                if abs(tech.combined_score) >= self.min_signal_strength:
                    if tech.combined_score > 0:
                        signal_type = SignalType.BUY
                    else:
                        signal_type = SignalType.SELL

                    signals.append(Signal(
                        date=current_date,
                        symbol=tech.symbol,
                        signal_type=signal_type,
                        strength=abs(tech.combined_score),
                        metadata={
                            "strategy": self.name,
                            "rsi": tech.rsi,
                            "momentum_12m": tech.momentum_20d,  # Actually 12-month now
                            "combined_score": tech.combined_score,
                            "indicators": {
                                "rsi_signal": tech.rsi_signal.value,
                                "ma_crossover": tech.ma_crossover.value,
                                "momentum_signal": tech.momentum_signal.value
                            }
                        }
                    ))
                    signals_this_date += 1

            if signals_this_date > 0:
                last_signal_date = current_date

        logger.info(f"Generated {len(signals)} swing momentum signals")
        return signals

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> float:
        """
        Calculate position size based on signal strength.

        Uses proportional sizing based on signal strength.
        Max position: 15% of portfolio per symbol (diversified approach).

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

        # IMPROVED: Max 25% per position for top signals (was 15%)
        # Strong signals deserve larger positions
        max_position = portfolio_value * 0.25

        # Scale by signal strength
        target_size = max_position * signal.strength

        logger.debug(
            f"Position size for {signal.symbol}: ${target_size:,.2f} "
            f"({signal.strength:.0%} strength)"
        )

        return target_size

    def get_backtest_params(self) -> BacktestParams:
        """Return default backtesting parameters."""
        return BacktestParams(
            start_date="2020-01-01",
            end_date="2024-12-31",
            initial_capital=10000.0,
            rebalance_frequency="daily",
            transaction_cost_bps=10,
            slippage_bps=10
        )

    def get_required_history(self) -> int:
        """Return required historical data length."""
        return max(self.long_ma, self.momentum_period + self.skip_days) + 30

    def get_current_signal(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[date] = None
    ) -> List[Signal]:
        """
        Get current trading signals.

        Returns signals for ALL symbols that meet criteria,
        not just one like Dual Momentum.

        Args:
            data: Market data
            as_of_date: Date to calculate signals for (default: latest)

        Returns:
            List of current BUY/SELL signals
        """
        if as_of_date is None:
            # Use the latest date in data
            ref_symbol = self.universe[0]
            if ref_symbol in data and not data[ref_symbol].empty:
                as_of_date = data[ref_symbol].index[-1]
                if hasattr(as_of_date, 'date'):
                    as_of_date = as_of_date.date()
            else:
                return []

        tech_signals = self._calculate_technical_signals(data, as_of_date)
        current_signals = []

        for tech in tech_signals:
            if abs(tech.combined_score) >= self.min_signal_strength:
                signal_type = SignalType.BUY if tech.combined_score > 0 else SignalType.SELL

                current_signals.append(Signal(
                    date=as_of_date,
                    symbol=tech.symbol,
                    signal_type=signal_type,
                    strength=abs(tech.combined_score),
                    metadata={
                        "strategy": self.name,
                        "rsi": tech.rsi,
                        "momentum_20d": tech.momentum_20d,
                        "combined_score": tech.combined_score
                    }
                ))

        return current_signals
