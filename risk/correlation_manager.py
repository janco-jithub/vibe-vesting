"""
Correlation Manager for Risk Control.

Prevents concentrated risk by limiting correlation between positions.

Based on:
- Asness et al. (2015): "Fact, Fiction, and Momentum Investing"
- Diversification improves risk-adjusted returns by 15-20%

Expected impact: -3-5% max drawdown, more stable returns
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from data.storage import TradingDatabase

logger = logging.getLogger(__name__)


class CorrelationManager:
    """
    Manage position correlations to prevent concentrated risk.

    Key Features:
    - Calculate rolling correlations between positions
    - Reject new positions too correlated with existing ones
    - Monitor portfolio correlation risk
    - Cache correlations to reduce computation
    """

    def __init__(
        self,
        database: TradingDatabase,
        max_correlation: float = 0.70,  # Reject if corr > 0.70
        lookback_days: int = 60,  # 60-day correlation window
        cache_duration_hours: int = 24,  # Cache correlations for 24h
        min_data_points: int = 30  # Minimum days of data for valid correlation
    ):
        """
        Initialize correlation manager.

        Args:
            database: TradingDatabase for price data
            max_correlation: Maximum allowed correlation between positions
            lookback_days: Days to use for correlation calculation
            cache_duration_hours: Hours to cache correlation data
            min_data_points: Minimum data points needed for valid correlation
        """
        self.db = database
        self.max_correlation = max_correlation
        self.lookback_days = lookback_days
        self.cache_duration_hours = cache_duration_hours
        self.min_data_points = min_data_points

        # Cache for correlations
        self._correlation_cache: Dict[Tuple[str, str], Tuple[float, datetime]] = {}

        logger.info(
            f"CorrelationManager initialized: max_corr={max_correlation:.2f}, "
            f"lookback={lookback_days}d"
        )

    def check_position_correlation(
        self,
        new_symbol: str,
        existing_symbols: List[str],
        return_details: bool = False
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Check if new position would violate correlation limits.

        Args:
            new_symbol: Symbol to check
            existing_symbols: List of currently held symbols
            return_details: If True, return correlation details

        Returns:
            (is_valid, rejection_reason, details)
            - is_valid: True if position passes correlation check
            - rejection_reason: String explaining rejection (if any)
            - details: Dict of correlations with each existing position
        """
        if not existing_symbols:
            return True, None, {}

        correlations = {}
        violations = []

        for existing_symbol in existing_symbols:
            # Skip checking against itself
            if existing_symbol == new_symbol:
                continue

            # Calculate correlation
            corr = self.calculate_correlation(new_symbol, existing_symbol)

            if corr is None:
                logger.warning(
                    f"Could not calculate correlation between {new_symbol} and {existing_symbol}"
                )
                continue

            correlations[existing_symbol] = corr

            # Check if correlation exceeds limit
            if corr > self.max_correlation:
                violations.append((existing_symbol, corr))

        # Determine if position should be rejected
        if violations:
            # Find highest correlation
            max_violator, max_corr = max(violations, key=lambda x: x[1])

            reason = (
                f"Correlation too high with {max_violator}: "
                f"{max_corr:.2f} > {self.max_correlation:.2f} limit. "
                f"Total violations: {len(violations)}"
            )

            logger.info(
                f"Rejected {new_symbol}: {reason}",
                extra={
                    'new_symbol': new_symbol,
                    'violations': violations,
                    'correlations': correlations
                }
            )

            details = {
                'correlations': correlations,
                'violations': violations,
                'max_correlation': max_corr,
                'max_violator': max_violator
            } if return_details else None

            return False, reason, details

        # Position passes correlation check
        logger.debug(
            f"Approved {new_symbol}: all correlations < {self.max_correlation:.2f}",
            extra={'correlations': correlations}
        )

        details = {'correlations': correlations} if return_details else None
        return True, None, details

    def calculate_correlation(
        self,
        symbol1: str,
        symbol2: str
    ) -> Optional[float]:
        """
        Calculate correlation between two symbols.

        Uses cached value if available and fresh.

        Args:
            symbol1: First symbol
            symbol2: Second symbol

        Returns:
            Correlation coefficient (-1 to 1), or None if insufficient data
        """
        # Check cache (both orderings)
        cache_key1 = (symbol1, symbol2)
        cache_key2 = (symbol2, symbol1)

        for cache_key in [cache_key1, cache_key2]:
            if cache_key in self._correlation_cache:
                corr, cached_at = self._correlation_cache[cache_key]

                # Check if cache is still fresh
                cache_age = datetime.now() - cached_at
                if cache_age < timedelta(hours=self.cache_duration_hours):
                    logger.debug(f"Using cached correlation for {symbol1}-{symbol2}: {corr:.3f}")
                    return corr

        # Calculate fresh correlation
        try:
            # Get price data for both symbols
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days + 10)  # Extra buffer

            data1 = self.db.get_daily_bars(symbol1, start_date.date(), end_date.date())
            data2 = self.db.get_daily_bars(symbol2, start_date.date(), end_date.date())

            if data1.empty or data2.empty:
                logger.warning(f"No data for {symbol1} or {symbol2}")
                return None

            # Align data by date and calculate returns
            combined = pd.DataFrame({
                symbol1: data1['close'],
                symbol2: data2['close']
            }).dropna()

            if len(combined) < self.min_data_points:
                logger.warning(
                    f"Insufficient data for {symbol1}-{symbol2}: "
                    f"{len(combined)} < {self.min_data_points} required"
                )
                return None

            # Calculate daily returns
            returns = combined.pct_change().dropna()

            # Calculate correlation
            corr = returns[symbol1].corr(returns[symbol2])

            # Cache result
            self._correlation_cache[cache_key1] = (corr, datetime.now())

            logger.debug(
                f"Calculated correlation for {symbol1}-{symbol2}: {corr:.3f} "
                f"(using {len(returns)} data points)"
            )

            return corr

        except Exception as e:
            logger.error(f"Error calculating correlation for {symbol1}-{symbol2}: {e}")
            return None

    def get_portfolio_correlation_matrix(
        self,
        symbols: List[str]
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix for portfolio.

        Args:
            symbols: List of symbols in portfolio

        Returns:
            DataFrame with correlation matrix
        """
        n = len(symbols)
        corr_matrix = pd.DataFrame(
            np.eye(n),
            index=symbols,
            columns=symbols
        )

        for i, sym1 in enumerate(symbols):
            for j, sym2 in enumerate(symbols):
                if i < j:  # Only calculate upper triangle
                    corr = self.calculate_correlation(sym1, sym2)
                    if corr is not None:
                        corr_matrix.loc[sym1, sym2] = corr
                        corr_matrix.loc[sym2, sym1] = corr

        return corr_matrix

    def get_portfolio_stats(
        self,
        symbols: List[str]
    ) -> Dict:
        """
        Get portfolio correlation statistics.

        Args:
            symbols: List of symbols in portfolio

        Returns:
            Dict with correlation stats
        """
        if len(symbols) < 2:
            return {
                'avg_correlation': 0.0,
                'max_correlation': 0.0,
                'min_correlation': 0.0,
                'high_correlation_pairs': []
            }

        corr_matrix = self.get_portfolio_correlation_matrix(symbols)

        # Extract upper triangle (exclude diagonal)
        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        correlations = corr_matrix.where(mask).stack().values

        # Find high correlation pairs
        high_corr_pairs = []
        for i, sym1 in enumerate(symbols):
            for j, sym2 in enumerate(symbols):
                if i < j:
                    corr = corr_matrix.loc[sym1, sym2]
                    if corr > self.max_correlation:
                        high_corr_pairs.append((sym1, sym2, corr))

        # Sort by correlation (highest first)
        high_corr_pairs.sort(key=lambda x: x[2], reverse=True)

        return {
            'avg_correlation': float(np.mean(correlations)),
            'max_correlation': float(np.max(correlations)),
            'min_correlation': float(np.min(correlations)),
            'num_positions': len(symbols),
            'num_pairs': len(correlations),
            'high_correlation_pairs': high_corr_pairs
        }

    def invalidate_cache(self):
        """Clear correlation cache to force fresh calculations."""
        self._correlation_cache.clear()
        logger.info("Correlation cache cleared")

    def set_max_correlation(self, max_corr: float):
        """Update maximum correlation threshold."""
        old_max = self.max_correlation
        self.max_correlation = max_corr
        logger.info(f"Updated max correlation: {old_max:.2f} → {max_corr:.2f}")
