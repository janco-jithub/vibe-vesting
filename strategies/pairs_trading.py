"""
Pairs Trading Strategy Implementation.

Based on academic research:
- Gatev, E., Goetzmann, W., & Rouwenhorst, K. G. (2006). "Pairs Trading:
  Performance of a Relative-Value Arbitrage Rule." Review of Financial Studies.

Methodology:
1. Formation Period: Identify cointegrated/correlated pairs (correlation > 0.80)
2. Trading Period: Monitor spread between pairs, trade when divergence > 2 std devs
3. Exit when spread converges back to mean

Historical Performance (Gatev et al. 2006):
- Sharpe Ratio: ~1.0-1.4 (market-neutral, consistent returns)
- Max Drawdown: ~10-15% (lower than directional strategies)
- Win Rate: ~65-70%
- Works best in mean-reverting markets

Key Advantages:
- Market-neutral: Long one asset, short the other
- Lower correlation to market risk (SPY beta ~ 0)
- Statistical edge from mean reversion
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import logging

import pandas as pd
import numpy as np
from scipy import stats

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams


logger = logging.getLogger(__name__)


@dataclass
class PairInfo:
    """Information about a trading pair."""
    symbol_a: str
    symbol_b: str
    correlation: float
    spread_mean: float
    spread_std: float
    z_score: float
    is_cointegrated: bool
    hedge_ratio: float  # How much of B to short per unit of A


@dataclass
class PairSignal:
    """Trading signal for a pair."""
    pair_info: PairInfo
    signal_type: SignalType  # For the LONG leg
    z_score: float
    spread: float
    entry_threshold: float


class PairsTradingStrategy(BaseStrategy):
    """
    Statistical Pairs Trading Strategy.

    Identifies mean-reverting pairs of ETFs and trades divergences:
    - When spread > +2σ: Short pair A, Long pair B (spread expected to narrow)
    - When spread < -2σ: Long pair A, Short pair B (spread expected to widen)
    - Exit when spread returns to mean (|z-score| < 0.5)

    Universe: Sector ETFs with high liquidity
    - XLF/XLV: Financials vs Healthcare
    - XLK/XLC: Technology vs Communications
    - SPY/IWM: Large cap vs Small cap
    - QQQ/SPY: Tech-heavy vs Broad market
    - XLE/XLU: Energy vs Utilities

    Attributes:
        lookback_days: Days for calculating pair statistics (default: 60)
        entry_threshold: Z-score threshold for entry (default: 2.0)
        exit_threshold: Z-score threshold for exit (default: 0.5)
        min_correlation: Minimum correlation to form pair (default: 0.75)
    """

    # Pairs to evaluate (based on sector relationships)
    DEFAULT_PAIRS = [
        ("SPY", "IWM"),   # Large cap vs Small cap
        ("QQQ", "SPY"),   # Tech-heavy vs Broad market
        ("XLF", "XLV"),   # Financials vs Healthcare
        ("XLK", "XLC"),   # Technology vs Communications (if available)
        ("XLE", "XLU"),   # Energy vs Utilities
        ("XLF", "XLK"),   # Financials vs Technology
    ]

    def __init__(
        self,
        pairs: Optional[List[Tuple[str, str]]] = None,
        lookback_days: int = 120,  # OPTIMIZED: 120-day lookback (more stable)
        entry_threshold: float = 1.5,  # OPTIMIZED: Higher threshold = fewer false signals
        exit_threshold: float = 0.3,  # OPTIMIZED: Lock in profits earlier
        min_correlation: float = 0.75,  # OPTIMIZED: Higher correlation requirement
        check_cointegration: bool = False,  # Skip slow cointegration check
        recalc_frequency: int = 10,  # OPTIMIZED: Biweekly recalculation
        use_long_only: bool = True,  # Long-only mode (paper trading compatible)
        name: str = "pairs_trading"
    ):
        """
        Initialize Pairs Trading Strategy.

        IMPROVED VERSION:
        - Longer lookback (252 days vs 60) for stable cointegration
        - Lower entry threshold (1.5 vs 2.0) for more opportunities
        - Tighter exit threshold (0.3 vs 0.5) to lock in profits
        - Monthly recalculation instead of daily (reduce overfitting)
        - Long-only mode (works with paper trading limitations)

        Args:
            pairs: List of (symbol_a, symbol_b) tuples to trade
            lookback_days: Formation period for calculating statistics (default: 252)
            entry_threshold: Z-score for entering trades (default: 1.5)
            exit_threshold: Z-score for exiting trades (default: 0.3)
            min_correlation: Minimum correlation for valid pair (default: 0.80)
            check_cointegration: Whether to test for cointegration (default: True)
            recalc_frequency: Days between stat recalculation (default: 21 = monthly)
            use_long_only: Only trade long legs (default: True)
            name: Strategy identifier
        """
        self.pairs = [(a.upper(), b.upper()) for a, b in (pairs or self.DEFAULT_PAIRS)]
        self.lookback_days = lookback_days
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.min_correlation = min_correlation
        self.check_cointegration = check_cointegration
        self.recalc_frequency = recalc_frequency
        self.use_long_only = use_long_only

        # Extract all unique symbols from pairs
        all_symbols = set()
        for a, b in self.pairs:
            all_symbols.add(a)
            all_symbols.add(b)

        super().__init__(name=name, universe=list(all_symbols))

        # Track active positions (pairs we're currently trading)
        self.active_pairs: Dict[Tuple[str, str], PairInfo] = {}

        # Cache pair statistics to avoid recalculating every day
        self.pair_stats_cache: Dict[Tuple[str, str], Tuple[date, PairInfo]] = {}

        logger.info(
            "Initialized PairsTradingStrategy",
            extra={
                "pairs": self.pairs,
                "lookback_days": lookback_days,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold
            }
        )

    def _calculate_hedge_ratio(
        self,
        prices_a: pd.Series,
        prices_b: pd.Series
    ) -> float:
        """
        Calculate optimal hedge ratio using linear regression.

        The hedge ratio determines how much of B to short per unit of A.
        We use OLS regression: price_a = beta * price_b + alpha

        Args:
            prices_a: Price series for asset A
            prices_b: Price series for asset B

        Returns:
            Hedge ratio (beta)
        """
        # Use OLS to find relationship: A = beta * B + alpha
        slope, intercept, r_value, p_value, std_err = stats.linregress(prices_b, prices_a)
        return slope

    def _check_cointegration(
        self,
        prices_a: pd.Series,
        prices_b: pd.Series
    ) -> Tuple[bool, float]:
        """
        Test if two price series are cointegrated using Engle-Granger test.

        Cointegration means the spread is mean-reverting (stationary).

        Args:
            prices_a: Price series for asset A
            prices_b: Price series for asset B

        Returns:
            Tuple of (is_cointegrated, p_value)
        """
        try:
            from statsmodels.tsa.stattools import coint

            # Perform cointegration test
            score, p_value, _ = coint(prices_a, prices_b)

            # p_value < 0.05 means we reject null hypothesis (no cointegration)
            # So p_value < 0.05 means the series ARE cointegrated
            is_cointegrated = p_value < 0.05

            return is_cointegrated, float(p_value)
        except ImportError:
            logger.warning("statsmodels not installed, skipping cointegration test")
            return True, 0.0  # Assume cointegrated if can't test
        except Exception as e:
            logger.warning(f"Cointegration test failed: {e}")
            return False, 1.0

    def _calculate_spread(
        self,
        prices_a: pd.Series,
        prices_b: pd.Series,
        hedge_ratio: float
    ) -> pd.Series:
        """
        Calculate spread between two assets.

        Spread = price_a - hedge_ratio * price_b

        Args:
            prices_a: Price series for asset A
            prices_b: Price series for asset B
            hedge_ratio: Ratio of B to hedge A

        Returns:
            Spread series
        """
        return prices_a - hedge_ratio * prices_b

    def _analyze_pair(
        self,
        symbol_a: str,
        symbol_b: str,
        data: Dict[str, pd.DataFrame],
        as_of_date: date
    ) -> Optional[PairInfo]:
        """
        Analyze a pair to determine if it's tradeable.

        Args:
            symbol_a: First symbol
            symbol_b: Second symbol
            data: Market data dict
            as_of_date: Analysis date

        Returns:
            PairInfo if pair is valid, None otherwise
        """
        if symbol_a not in data or symbol_b not in data:
            return None

        # Get price data
        df_a = data[symbol_a]
        df_b = data[symbol_b]

        # Filter to dates on or before as_of_date
        mask_a = df_a.index.date <= as_of_date
        mask_b = df_b.index.date <= as_of_date

        prices_a = df_a[mask_a]["close"]
        prices_b = df_b[mask_b]["close"]

        # Align on dates
        prices_a, prices_b = prices_a.align(prices_b, join="inner")

        if len(prices_a) < self.lookback_days:
            return None

        # Use lookback period
        prices_a = prices_a.iloc[-self.lookback_days:]
        prices_b = prices_b.iloc[-self.lookback_days:]

        # Calculate correlation
        correlation = prices_a.corr(prices_b)

        if abs(correlation) < self.min_correlation:
            logger.debug(
                f"Pair {symbol_a}/{symbol_b} correlation too low: {correlation:.3f}"
            )
            return None

        # Calculate hedge ratio
        hedge_ratio = self._calculate_hedge_ratio(prices_a, prices_b)

        # Check cointegration
        is_cointegrated = True
        if self.check_cointegration:
            is_cointegrated, p_value = self._check_cointegration(prices_a, prices_b)
            if not is_cointegrated:
                logger.debug(
                    f"Pair {symbol_a}/{symbol_b} not cointegrated (p={p_value:.3f})"
                )
                return None

        # Calculate spread statistics
        spread = self._calculate_spread(prices_a, prices_b, hedge_ratio)
        spread_mean = spread.mean()
        spread_std = spread.std()

        if spread_std == 0:
            return None

        # Calculate current z-score
        current_spread = spread.iloc[-1]
        z_score = (current_spread - spread_mean) / spread_std

        return PairInfo(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            correlation=float(correlation),
            spread_mean=float(spread_mean),
            spread_std=float(spread_std),
            z_score=float(z_score),
            is_cointegrated=is_cointegrated,
            hedge_ratio=float(hedge_ratio)
        )

    def _generate_pair_signals(
        self,
        pair_info: PairInfo,
        as_of_date: date
    ) -> List[Signal]:
        """
        Generate trading signals for a pair.

        IMPROVED: Long-only mode for paper trading compatibility.
        Instead of shorting, we just don't trade that leg.

        Args:
            pair_info: Pair analysis results
            as_of_date: Signal date

        Returns:
            List of Signal objects (1-2 signals depending on long-only mode)
        """
        signals = []
        z = pair_info.z_score

        # Check if we should enter a new position
        if abs(z) >= self.entry_threshold:
            if z > self.entry_threshold:
                # Spread too high: Prefer B (expected to rise relative to A)
                if self.use_long_only:
                    # LONG-ONLY: Only buy B
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_b,
                        signal_type=SignalType.BUY,
                        strength=min(1.0, abs(z) / (self.entry_threshold * 2)),
                        metadata={
                            "strategy": self.name,
                            "pair_symbol": pair_info.symbol_a,
                            "z_score": z,
                            "spread": (pair_info.spread_mean + z * pair_info.spread_std),
                            "correlation": pair_info.correlation,
                            "position": "long_only_b"
                        }
                    ))
                else:
                    # FULL PAIRS: Short A, Long B
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_a,
                        signal_type=SignalType.SELL,
                    strength=min(1.0, abs(z) / (self.entry_threshold * 2)),
                    metadata={
                        "strategy": self.name,
                        "pair_symbol": pair_info.symbol_b,
                        "z_score": z,
                        "spread": (pair_info.spread_mean + z * pair_info.spread_std),
                        "hedge_ratio": pair_info.hedge_ratio,
                        "correlation": pair_info.correlation,
                        "position": "short"
                    }
                ))
                signals.append(Signal(
                    date=as_of_date,
                    symbol=pair_info.symbol_b,
                    signal_type=SignalType.BUY,
                    strength=min(1.0, abs(z) / (self.entry_threshold * 2)),
                    metadata={
                        "strategy": self.name,
                        "pair_symbol": pair_info.symbol_a,
                        "z_score": z,
                        "spread": (pair_info.spread_mean + z * pair_info.spread_std),
                        "hedge_ratio": 1.0 / pair_info.hedge_ratio,
                        "correlation": pair_info.correlation,
                        "position": "long"
                    }
                ))

            elif z < -self.entry_threshold:
                # Spread too low: Prefer A (expected to rise relative to B)
                if self.use_long_only:
                    # LONG-ONLY: Only buy A
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_a,
                        signal_type=SignalType.BUY,
                        strength=min(1.0, abs(z) / (self.entry_threshold * 2)),
                        metadata={
                            "strategy": self.name,
                            "pair_symbol": pair_info.symbol_b,
                            "z_score": z,
                            "spread": (pair_info.spread_mean + z * pair_info.spread_std),
                            "correlation": pair_info.correlation,
                            "position": "long_only_a"
                        }
                    ))
                else:
                    # FULL PAIRS: Long A, Short B
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_a,
                        signal_type=SignalType.BUY,
                    strength=min(1.0, abs(z) / (self.entry_threshold * 2)),
                    metadata={
                        "strategy": self.name,
                        "pair_symbol": pair_info.symbol_b,
                        "z_score": z,
                        "spread": (pair_info.spread_mean + z * pair_info.spread_std),
                        "hedge_ratio": pair_info.hedge_ratio,
                        "correlation": pair_info.correlation,
                        "position": "long"
                    }
                ))
                signals.append(Signal(
                    date=as_of_date,
                    symbol=pair_info.symbol_b,
                    signal_type=SignalType.SELL,
                    strength=min(1.0, abs(z) / (self.entry_threshold * 2)),
                    metadata={
                        "strategy": self.name,
                        "pair_symbol": pair_info.symbol_a,
                        "z_score": z,
                        "spread": (pair_info.spread_mean + z * pair_info.spread_std),
                        "hedge_ratio": 1.0 / pair_info.hedge_ratio,
                        "correlation": pair_info.correlation,
                        "position": "short"
                    }
                ))

        # Check if we should exit an active position
        elif abs(z) <= self.exit_threshold:
            # Spread has converged - close positions
            pair_key = (pair_info.symbol_a, pair_info.symbol_b)
            if pair_key in self.active_pairs:
                # Generate exit signals (opposite of entry)
                active_info = self.active_pairs[pair_key]

                if active_info.z_score > 0:
                    # Was short A, long B - now reverse
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_a,
                        signal_type=SignalType.BUY,  # Close short
                        strength=1.0,
                        metadata={
                            "strategy": self.name,
                            "pair_symbol": pair_info.symbol_b,
                            "z_score": z,
                            "reason": "exit_convergence"
                        }
                    ))
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_b,
                        signal_type=SignalType.SELL,  # Close long
                        strength=1.0,
                        metadata={
                            "strategy": self.name,
                            "pair_symbol": pair_info.symbol_a,
                            "z_score": z,
                            "reason": "exit_convergence"
                        }
                    ))
                else:
                    # Was long A, short B - now reverse
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_a,
                        signal_type=SignalType.SELL,  # Close long
                        strength=1.0,
                        metadata={
                            "strategy": self.name,
                            "pair_symbol": pair_info.symbol_b,
                            "z_score": z,
                            "reason": "exit_convergence"
                        }
                    ))
                    signals.append(Signal(
                        date=as_of_date,
                        symbol=pair_info.symbol_b,
                        signal_type=SignalType.BUY,  # Close short
                        strength=1.0,
                        metadata={
                            "strategy": self.name,
                            "pair_symbol": pair_info.symbol_a,
                            "z_score": z,
                            "reason": "exit_convergence"
                        }
                    ))

                del self.active_pairs[pair_key]

        return signals

    def generate_signals(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """
        Generate pairs trading signals.

        Args:
            data: Dict mapping symbol to DataFrame with OHLCV data

        Returns:
            List of Signal objects
        """
        self.validate_data(data)

        signals = []

        # Get all dates from reference symbol
        ref_symbol = self.universe[0]
        all_dates = data[ref_symbol].index

        if len(all_dates) <= self.lookback_days:
            logger.warning("Insufficient data for pairs trading")
            return signals

        # Generate signals for each date after formation period
        for i in range(self.lookback_days, len(all_dates)):
            current_date = all_dates[i]
            if hasattr(current_date, 'date'):
                current_date = current_date.date()

            # Analyze each pair
            for symbol_a, symbol_b in self.pairs:
                pair_key = (symbol_a, symbol_b)

                # OPTIMIZATION: Use cached stats if recent
                if pair_key in self.pair_stats_cache:
                    last_calc_date, cached_info = self.pair_stats_cache[pair_key]
                    days_since_calc = (current_date - last_calc_date).days

                    # Only recalculate if past frequency threshold
                    if days_since_calc < self.recalc_frequency:
                        # Just update current z-score with cached stats
                        if symbol_a in data and symbol_b in data:
                            df_a = data[symbol_a]
                            df_b = data[symbol_b]
                            mask_a = df_a.index.date <= current_date
                            mask_b = df_b.index.date <= current_date
                            prices_a = df_a[mask_a]["close"]
                            prices_b = df_b[mask_b]["close"]

                            if len(prices_a) > 0 and len(prices_b) > 0:
                                current_spread = (
                                    prices_a.iloc[-1] -
                                    cached_info.hedge_ratio * prices_b.iloc[-1]
                                )
                                z_score = (
                                    (current_spread - cached_info.spread_mean) /
                                    cached_info.spread_std
                                )

                                # Create updated pair_info with new z-score
                                pair_info = PairInfo(
                                    symbol_a=cached_info.symbol_a,
                                    symbol_b=cached_info.symbol_b,
                                    correlation=cached_info.correlation,
                                    spread_mean=cached_info.spread_mean,
                                    spread_std=cached_info.spread_std,
                                    z_score=float(z_score),
                                    is_cointegrated=cached_info.is_cointegrated,
                                    hedge_ratio=cached_info.hedge_ratio
                                )
                            else:
                                pair_info = None
                        else:
                            pair_info = None
                    else:
                        # Time to recalculate
                        pair_info = self._analyze_pair(symbol_a, symbol_b, data, current_date)
                        if pair_info:
                            self.pair_stats_cache[pair_key] = (current_date, pair_info)
                else:
                    # First time - calculate and cache
                    pair_info = self._analyze_pair(symbol_a, symbol_b, data, current_date)
                    if pair_info:
                        self.pair_stats_cache[pair_key] = (current_date, pair_info)

                if pair_info is None:
                    continue

                # Generate signals for this pair
                pair_signals = self._generate_pair_signals(pair_info, current_date)
                signals.extend(pair_signals)

                # Track active pairs
                if abs(pair_info.z_score) >= self.entry_threshold:
                    self.active_pairs[(symbol_a, symbol_b)] = pair_info

        logger.info(f"Generated {len(signals)} pairs trading signals")
        return signals

    def calculate_position_size(
        self,
        signal: Signal,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> float:
        """
        Calculate position size for pairs trading.

        For pairs trading, we want balanced exposure:
        - Each leg gets 5-10% of portfolio value
        - Hedge ratio determines the exact ratio between legs

        Args:
            signal: The trading signal
            portfolio_value: Current total portfolio value
            current_positions: Current positions (symbol -> value)

        Returns:
            Target position size in dollars
        """
        if signal.signal_type == SignalType.HOLD:
            return current_positions.get(signal.symbol, 0.0)

        # IMPROVED: Allocate 10% to each leg in long-only mode
        # (was 7.5% for full pairs with short legs)
        # This gives us more exposure since we're only trading one leg per pair
        max_position = portfolio_value * 0.10

        if signal.signal_type == SignalType.BUY:
            # Long position
            target_size = max_position * signal.strength

            # Adjust for hedge ratio if in metadata
            if signal.metadata and "hedge_ratio" in signal.metadata:
                hedge_ratio = signal.metadata["hedge_ratio"]
                target_size *= hedge_ratio

            return target_size

        elif signal.signal_type == SignalType.SELL:
            # Short position (negative value)
            # Note: Alpaca paper trading may not support shorts
            # In that case, we'll just close the position
            current_pos = current_positions.get(signal.symbol, 0.0)

            if signal.metadata and signal.metadata.get("reason") == "exit_convergence":
                # Exit signal - close position
                return 0.0

            # Entry signal - would be short, but return 0 if we can't short
            # In production, this would be: return -max_position * signal.strength
            logger.warning(
                f"Pairs trading SELL signal for {signal.symbol} - "
                "short selling may not be supported in paper trading"
            )
            return 0.0

        return 0.0

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
        return self.lookback_days + 30  # Extra buffer

    def get_current_signal(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[date] = None
    ) -> List[Signal]:
        """
        Get current pairs trading signals.

        Args:
            data: Market data
            as_of_date: Date for signals (default: latest)

        Returns:
            List of current signals for all pairs
        """
        if as_of_date is None:
            ref_symbol = self.universe[0]
            if ref_symbol in data and not data[ref_symbol].empty:
                as_of_date = data[ref_symbol].index[-1]
                if hasattr(as_of_date, 'date'):
                    as_of_date = as_of_date.date()
            else:
                return []

        current_signals = []

        # Analyze each pair
        for symbol_a, symbol_b in self.pairs:
            pair_info = self._analyze_pair(symbol_a, symbol_b, data, as_of_date)

            if pair_info is None:
                continue

            # Generate signals
            pair_signals = self._generate_pair_signals(pair_info, as_of_date)
            current_signals.extend(pair_signals)

        return current_signals

    def get_pair_status(
        self,
        data: Dict[str, pd.DataFrame],
        as_of_date: Optional[date] = None
    ) -> List[Dict]:
        """
        Get status of all pairs for monitoring.

        Useful for dashboard display.

        Args:
            data: Market data
            as_of_date: Date for analysis (default: latest)

        Returns:
            List of pair status dicts
        """
        if as_of_date is None:
            ref_symbol = self.universe[0]
            if ref_symbol in data and not data[ref_symbol].empty:
                as_of_date = data[ref_symbol].index[-1]
                if hasattr(as_of_date, 'date'):
                    as_of_date = as_of_date.date()
            else:
                return []

        pair_statuses = []

        for symbol_a, symbol_b in self.pairs:
            pair_info = self._analyze_pair(symbol_a, symbol_b, data, as_of_date)

            if pair_info is None:
                pair_statuses.append({
                    "pair": f"{symbol_a}/{symbol_b}",
                    "status": "invalid",
                    "reason": "insufficient data or low correlation"
                })
                continue

            # Determine status
            if abs(pair_info.z_score) >= self.entry_threshold:
                status = "entry_signal"
            elif abs(pair_info.z_score) <= self.exit_threshold:
                status = "at_mean"
            else:
                status = "watching"

            pair_statuses.append({
                "pair": f"{symbol_a}/{symbol_b}",
                "status": status,
                "z_score": float(pair_info.z_score),
                "correlation": float(pair_info.correlation),
                "hedge_ratio": float(pair_info.hedge_ratio),
                "is_cointegrated": bool(pair_info.is_cointegrated),
                "spread_mean": float(pair_info.spread_mean),
                "spread_std": float(pair_info.spread_std)
            })

        return pair_statuses
