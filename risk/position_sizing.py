"""
Position sizing module for risk-controlled trading.

Implements various position sizing methods including:
- Fixed fractional
- Kelly Criterion (with safety fraction)
- Volatility-adjusted

All methods respect hard limits defined in config.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Hard limits (from .copilot.md)
MAX_SINGLE_POSITION_PCT = 0.05  # 5% of portfolio
MAX_SECTOR_EXPOSURE_PCT = 0.25  # 25% of portfolio


@dataclass
class PositionSizeResult:
    """Result of position size calculation."""
    symbol: str
    target_value: float
    target_shares: int
    current_value: float
    change_value: float
    change_shares: int
    method: str
    limited_by: Optional[str] = None  # Which limit was hit, if any


class PositionSizer:
    """
    Calculate position sizes with risk limits.

    Supports multiple sizing methods while enforcing hard limits:
    - Maximum single position: 5% of portfolio
    - Maximum sector exposure: 25% of portfolio

    Attributes:
        max_position_pct: Maximum single position as fraction of portfolio
        max_sector_pct: Maximum sector exposure as fraction of portfolio
        method: Sizing method ('fixed', 'kelly', 'volatility')
        kelly_fraction: Fraction of Kelly to use (default: 0.25)
    """

    def __init__(
        self,
        max_position_pct: float = MAX_SINGLE_POSITION_PCT,
        max_sector_pct: float = MAX_SECTOR_EXPOSURE_PCT,
        method: str = "fixed",
        kelly_fraction: float = 0.25
    ):
        """
        Initialize position sizer.

        Args:
            max_position_pct: Max single position (0-1)
            max_sector_pct: Max sector exposure (0-1)
            method: 'fixed', 'kelly', or 'volatility'
            kelly_fraction: Use this fraction of Kelly (0.25 = quarter Kelly)
        """
        self.max_position_pct = max_position_pct
        self.max_sector_pct = max_sector_pct
        self.method = method
        self.kelly_fraction = kelly_fraction

        logger.info(
            "PositionSizer initialized",
            extra={
                "method": method,
                "max_position_pct": max_position_pct,
                "max_sector_pct": max_sector_pct
            }
        )

    def calculate_fixed_size(
        self,
        target_pct: float,
        portfolio_value: float
    ) -> float:
        """
        Calculate position size using fixed percentage.

        Args:
            target_pct: Target allocation (0-1)
            portfolio_value: Total portfolio value

        Returns:
            Position value in dollars
        """
        size = portfolio_value * min(target_pct, self.max_position_pct)
        return float(size)

    def calculate_kelly_size(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        portfolio_value: float
    ) -> float:
        """
        Calculate position size using Kelly Criterion.

        Kelly formula: f* = (bp - q) / b
        where:
            b = odds (avg_win / avg_loss)
            p = probability of winning
            q = probability of losing (1 - p)

        We use a fraction of Kelly (default 25%) to reduce variance.

        Args:
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade return
            avg_loss: Average losing trade return (positive number)
            portfolio_value: Total portfolio value

        Returns:
            Position value in dollars
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            logger.warning("Invalid Kelly inputs, using fixed sizing")
            return self.calculate_fixed_size(self.max_position_pct, portfolio_value)

        b = avg_win / avg_loss  # Odds
        p = win_rate
        q = 1 - p

        kelly_fraction_full = (b * p - q) / b

        if kelly_fraction_full <= 0:
            logger.info("Kelly suggests no position (negative edge)")
            return 0.0

        # Use fractional Kelly
        kelly_adjusted = kelly_fraction_full * self.kelly_fraction

        # Apply maximum limit
        final_pct = min(kelly_adjusted, self.max_position_pct)

        logger.debug(
            f"Kelly calculation: full={kelly_fraction_full:.2%}, "
            f"adjusted={kelly_adjusted:.2%}, final={final_pct:.2%}"
        )

        return portfolio_value * final_pct

    def calculate_volatility_adjusted_size(
        self,
        returns: pd.Series,
        target_volatility: float,
        portfolio_value: float
    ) -> float:
        """
        Calculate position size targeting a specific volatility.

        Args:
            returns: Historical returns series
            target_volatility: Target annualized volatility (e.g., 0.15 for 15%)
            portfolio_value: Total portfolio value

        Returns:
            Position value in dollars
        """
        if len(returns) < 20:
            logger.warning("Insufficient data for volatility calculation")
            return self.calculate_fixed_size(self.max_position_pct, portfolio_value)

        # Calculate annualized volatility
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)

        if annual_vol == 0:
            logger.warning("Zero volatility, using max position")
            return self.calculate_fixed_size(self.max_position_pct, portfolio_value)

        # Scale position to achieve target volatility
        vol_scalar = target_volatility / annual_vol
        target_pct = min(vol_scalar, self.max_position_pct)

        logger.debug(
            f"Volatility sizing: annual_vol={annual_vol:.2%}, "
            f"scalar={vol_scalar:.2f}, target_pct={target_pct:.2%}"
        )

        return portfolio_value * target_pct

    def calculate_position_size(
        self,
        symbol: str,
        portfolio_value: float,
        current_price: float,
        current_positions: Dict[str, float],
        sector_map: Optional[Dict[str, str]] = None,
        target_pct: Optional[float] = None,
        **kwargs
    ) -> PositionSizeResult:
        """
        Calculate position size with all risk checks.

        Args:
            symbol: Target symbol
            portfolio_value: Total portfolio value
            current_price: Current price per share
            current_positions: Dict of symbol -> position value
            sector_map: Optional dict of symbol -> sector
            target_pct: Target allocation (for fixed method)
            **kwargs: Additional args for specific methods (win_rate, returns, etc.)

        Returns:
            PositionSizeResult with sizing details
        """
        current_value = current_positions.get(symbol, 0.0)
        limited_by = None

        # Calculate raw target based on method
        if self.method == "fixed":
            pct = target_pct if target_pct is not None else self.max_position_pct
            target_value = self.calculate_fixed_size(pct, portfolio_value)

        elif self.method == "kelly":
            win_rate = kwargs.get("win_rate", 0.55)
            avg_win = kwargs.get("avg_win", 0.02)
            avg_loss = kwargs.get("avg_loss", 0.01)
            target_value = self.calculate_kelly_size(
                win_rate, avg_win, avg_loss, portfolio_value
            )

        elif self.method == "volatility":
            returns = kwargs.get("returns")
            target_vol = kwargs.get("target_volatility", 0.15)
            if returns is None:
                logger.warning("No returns provided for volatility method, using fixed")
                target_value = self.calculate_fixed_size(self.max_position_pct, portfolio_value)
            else:
                target_value = self.calculate_volatility_adjusted_size(
                    returns, target_vol, portfolio_value
                )

        else:
            raise ValueError(f"Unknown sizing method: {self.method}")

        # Apply position limit
        max_position_value = portfolio_value * self.max_position_pct
        if target_value > max_position_value:
            target_value = max_position_value
            limited_by = "max_position"

        # Check sector exposure if sector map provided
        if sector_map and symbol in sector_map:
            sector = sector_map[symbol]
            sector_exposure = sum(
                v for s, v in current_positions.items()
                if sector_map.get(s) == sector and s != symbol
            )
            max_sector_value = portfolio_value * self.max_sector_pct
            available_sector = max_sector_value - sector_exposure

            if target_value > available_sector:
                target_value = max(0, available_sector)
                limited_by = "max_sector"

        # Calculate shares
        if current_price > 0:
            target_shares = int(target_value / current_price)
            current_shares = int(current_value / current_price) if current_value > 0 else 0
        else:
            target_shares = 0
            current_shares = 0

        result = PositionSizeResult(
            symbol=symbol,
            target_value=target_value,
            target_shares=target_shares,
            current_value=current_value,
            change_value=target_value - current_value,
            change_shares=target_shares - current_shares,
            method=self.method,
            limited_by=limited_by
        )

        logger.info(
            "Position size calculated",
            extra={
                "symbol": symbol,
                "target_value": target_value,
                "target_shares": target_shares,
                "limited_by": limited_by
            }
        )

        return result

    def validate_order(
        self,
        symbol: str,
        order_value: float,
        portfolio_value: float,
        current_positions: Dict[str, float],
        sector_map: Optional[Dict[str, str]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate if an order respects risk limits.

        Args:
            symbol: Symbol to trade
            order_value: Proposed order value
            portfolio_value: Total portfolio value
            current_positions: Current positions
            sector_map: Optional sector mapping

        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        current_position = current_positions.get(symbol, 0.0)
        new_position = current_position + order_value

        # Check position limit
        max_position = portfolio_value * self.max_position_pct
        if new_position > max_position:
            return False, f"Exceeds max position size ({self.max_position_pct:.0%})"

        # Check sector limit
        if sector_map and symbol in sector_map:
            sector = sector_map[symbol]
            sector_exposure = sum(
                v for s, v in current_positions.items()
                if sector_map.get(s) == sector
            ) + order_value

            max_sector = portfolio_value * self.max_sector_pct
            if sector_exposure > max_sector:
                return False, f"Exceeds max sector exposure ({self.max_sector_pct:.0%})"

        return True, None
