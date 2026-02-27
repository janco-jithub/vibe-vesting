"""
Adaptive Trailing Stop System

Implements intelligent stop loss management that adapts to:
1. Profit level (tighter stops for larger gains - lock in profits)
2. Volatility regime (wider stops in high vol to avoid whipsaws)
3. Time in position (exit stale positions)
4. Volatility-adjusted ATR multiples

Academic References:
- Kaufman (2013): "Trading Systems and Methods" - adaptive stops
- Wilder (1978): "New Concepts in Technical Trading Systems" - ATR
- Chande & Kroll (1994): "The New Technical Trader" - volatility stops
- Pring (2002): "Technical Analysis Explained" - trailing stop techniques
"""

import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import numpy as np

logger = logging.getLogger(__name__)


class StopType(Enum):
    """Types of stop losses."""
    INITIAL = "initial"          # Initial hard stop
    TRAILING = "trailing"        # Trailing stop
    PROFIT_LOCK = "profit_lock"  # Locking in profits
    TIME_BASED = "time_based"    # Time-based exit
    VOLATILITY = "volatility"    # Volatility-based stop


@dataclass
class StopLossParams:
    """Parameters for stop loss calculation."""
    symbol: str
    current_price: float
    entry_price: float
    entry_time: datetime
    current_stop: float
    atr: Optional[float]

    # Calculated values
    unrealized_pnl_pct: float
    days_held: int
    current_volatility_regime: str

    # Recommended stop
    recommended_stop: float
    stop_type: StopType
    stop_distance_pct: float
    reasoning: str


class AdaptiveStopManager:
    """
    Adaptive stop loss management system.

    Dynamically adjusts stops based on:
    - Profit level (lock in gains)
    - Volatility (avoid whipsaws)
    - Time (exit stale positions)
    - Market regime
    """

    def __init__(
        self,
        # Initial stop parameters
        initial_stop_pct: float = 0.04,           # 4% initial stop
        initial_stop_atr_multiple: float = 2.0,   # Or 2x ATR

        # Trailing stop parameters
        trailing_stop_pct: float = 0.03,          # 3% trailing stop
        trailing_stop_atr_multiple: float = 2.5,  # Or 2.5x ATR

        # Profit-based tightening
        profit_tighten_breakpoints: Dict[float, float] = None,  # profit% -> stop%

        # Volatility adjustments
        vix_low_threshold: float = 15.0,
        vix_high_threshold: float = 25.0,
        low_vol_multiplier: float = 0.8,          # Tighter stops in low vol
        high_vol_multiplier: float = 1.5,         # Wider stops in high vol

        # Time-based exits
        max_hold_days: int = 60,                  # Exit after 60 days
        stale_position_days: int = 30,            # Tighten after 30 days with no progress

        # Use ATR or percentage
        use_atr: bool = True,
    ):
        """
        Initialize adaptive stop manager.

        Args:
            initial_stop_pct: Initial stop loss percentage
            initial_stop_atr_multiple: Initial stop as ATR multiple
            trailing_stop_pct: Trailing stop percentage
            trailing_stop_atr_multiple: Trailing stop as ATR multiple
            profit_tighten_breakpoints: Dict of profit% -> stop% for profit locking
            vix_low_threshold: VIX level for low volatility
            vix_high_threshold: VIX level for high volatility
            low_vol_multiplier: Stop multiplier in low vol
            high_vol_multiplier: Stop multiplier in high vol
            max_hold_days: Maximum days to hold position
            stale_position_days: Days before considering position stale
            use_atr: Use ATR-based stops (vs percentage)
        """
        self.initial_stop_pct = initial_stop_pct
        self.initial_stop_atr_multiple = initial_stop_atr_multiple

        self.trailing_stop_pct = trailing_stop_pct
        self.trailing_stop_atr_multiple = trailing_stop_atr_multiple

        # Default profit tightening schedule
        if profit_tighten_breakpoints is None:
            self.profit_tighten_breakpoints = {
                0.05: 0.025,   # At +5% profit, use 2.5% stop
                0.10: 0.02,    # At +10% profit, use 2% stop
                0.15: 0.015,   # At +15% profit, use 1.5% stop
                0.20: 0.01,    # At +20% profit, use 1% stop
            }
        else:
            self.profit_tighten_breakpoints = profit_tighten_breakpoints

        self.vix_low_threshold = vix_low_threshold
        self.vix_high_threshold = vix_high_threshold
        self.low_vol_multiplier = low_vol_multiplier
        self.high_vol_multiplier = high_vol_multiplier

        self.max_hold_days = max_hold_days
        self.stale_position_days = stale_position_days

        self.use_atr = use_atr

        logger.info(
            "AdaptiveStopManager initialized",
            extra={
                "initial_stop": initial_stop_pct,
                "trailing_stop": trailing_stop_pct,
                "use_atr": use_atr,
                "max_hold_days": max_hold_days
            }
        )

    def get_volatility_regime(self, vix: float) -> str:
        """Classify volatility regime."""
        if vix < self.vix_low_threshold:
            return "low"
        elif vix < self.vix_high_threshold:
            return "normal"
        else:
            return "high"

    def get_volatility_multiplier(self, vix: float) -> float:
        """Get stop multiplier based on VIX."""
        regime = self.get_volatility_regime(vix)

        if regime == "low":
            return self.low_vol_multiplier
        elif regime == "high":
            return self.high_vol_multiplier
        else:
            return 1.0

    def get_profit_based_stop_pct(self, unrealized_pnl_pct: float) -> Optional[float]:
        """
        Get tighter stop percentage based on profit level.

        As positions become more profitable, we tighten stops to lock in gains.

        Args:
            unrealized_pnl_pct: Current unrealized P&L percentage

        Returns:
            Stop percentage if profit thresholds met, None otherwise
        """
        # Find the highest breakpoint we've passed
        applicable_stop = None

        for profit_threshold in sorted(self.profit_tighten_breakpoints.keys(), reverse=True):
            if unrealized_pnl_pct >= profit_threshold:
                applicable_stop = self.profit_tighten_breakpoints[profit_threshold]
                break

        return applicable_stop

    def calculate_stop_loss(
        self,
        symbol: str,
        current_price: float,
        entry_price: float,
        entry_time: datetime,
        current_stop: float,
        highest_price_since_entry: float,
        atr: Optional[float] = None,
        vix: float = 20.0
    ) -> StopLossParams:
        """
        Calculate adaptive stop loss.

        Args:
            symbol: Symbol
            current_price: Current price
            entry_price: Entry price
            entry_time: Entry timestamp
            current_stop: Current stop loss price
            highest_price_since_entry: Highest price reached
            atr: Average True Range
            vix: Current VIX level

        Returns:
            StopLossParams with recommended stop
        """
        # Calculate current metrics
        unrealized_pnl_pct = (current_price - entry_price) / entry_price
        days_held = (datetime.now() - entry_time).days
        vol_regime = self.get_volatility_regime(vix)
        vol_multiplier = self.get_volatility_multiplier(vix)

        reasoning_parts = []

        # Start with current stop (never lower it)
        recommended_stop = current_stop
        stop_type = StopType.TRAILING

        # 1. Check for time-based exit
        if days_held >= self.max_hold_days:
            # Time to exit - use current price as stop
            recommended_stop = current_price * 0.99  # Exit at market
            stop_type = StopType.TIME_BASED
            reasoning_parts.append(
                f"Position held {days_held} days (max: {self.max_hold_days})"
            )

        # 2. Check for stale position (no progress)
        elif days_held >= self.stale_position_days and unrealized_pnl_pct < 0.03:
            # Stale position - tighten stop
            stale_stop_pct = 0.02  # 2% stop for stale positions
            if self.use_atr and atr:
                stale_stop = current_price - (atr * 1.5 * vol_multiplier)
            else:
                stale_stop = current_price * (1 - stale_stop_pct * vol_multiplier)

            recommended_stop = max(recommended_stop, stale_stop)
            stop_type = StopType.TIME_BASED
            reasoning_parts.append(
                f"Stale position ({days_held} days, +{unrealized_pnl_pct:.1%})"
            )

        # 3. Profit-based stop tightening
        elif unrealized_pnl_pct > 0:
            profit_stop_pct = self.get_profit_based_stop_pct(unrealized_pnl_pct)

            if profit_stop_pct:
                # Lock in profits with tighter stop
                if self.use_atr and atr:
                    # Use tighter ATR multiple for profit locking
                    profit_atr_multiple = self.trailing_stop_atr_multiple * 0.7
                    profit_stop = highest_price_since_entry - (
                        atr * profit_atr_multiple * vol_multiplier
                    )
                else:
                    profit_stop = highest_price_since_entry * (
                        1 - profit_stop_pct * vol_multiplier
                    )

                if profit_stop > recommended_stop:
                    recommended_stop = profit_stop
                    stop_type = StopType.PROFIT_LOCK
                    reasoning_parts.append(
                        f"Profit lock: +{unrealized_pnl_pct:.1%} -> {profit_stop_pct:.1%} stop"
                    )

            # Standard trailing stop for profits
            else:
                if self.use_atr and atr:
                    trail_stop = highest_price_since_entry - (
                        atr * self.trailing_stop_atr_multiple * vol_multiplier
                    )
                else:
                    trail_stop = highest_price_since_entry * (
                        1 - self.trailing_stop_pct * vol_multiplier
                    )

                if trail_stop > recommended_stop:
                    recommended_stop = trail_stop
                    stop_type = StopType.TRAILING
                    reasoning_parts.append(
                        f"Trailing stop from high ${highest_price_since_entry:.2f}"
                    )

        # 4. Initial stop (no profit yet)
        else:
            # Use initial stop parameters
            if self.use_atr and atr:
                initial_stop = entry_price - (
                    atr * self.initial_stop_atr_multiple * vol_multiplier
                )
            else:
                initial_stop = entry_price * (
                    1 - self.initial_stop_pct * vol_multiplier
                )

            # Only raise the stop if better than current
            if initial_stop > recommended_stop:
                recommended_stop = initial_stop
                stop_type = StopType.INITIAL

            reasoning_parts.append(
                f"Initial stop: {self.initial_stop_pct:.1%} "
                f"* {vol_multiplier:.2f}x (VIX={vix:.1f})"
            )

        # Add volatility context
        reasoning_parts.append(f"Vol regime: {vol_regime} ({vol_multiplier:.2f}x)")

        # Never lower the stop
        recommended_stop = max(recommended_stop, current_stop)

        # Calculate stop distance
        stop_distance_pct = abs(current_price - recommended_stop) / current_price

        params = StopLossParams(
            symbol=symbol,
            current_price=current_price,
            entry_price=entry_price,
            entry_time=entry_time,
            current_stop=current_stop,
            atr=atr,
            unrealized_pnl_pct=unrealized_pnl_pct,
            days_held=days_held,
            current_volatility_regime=vol_regime,
            recommended_stop=round(recommended_stop, 2),
            stop_type=stop_type,
            stop_distance_pct=stop_distance_pct,
            reasoning=" | ".join(reasoning_parts)
        )

        if recommended_stop > current_stop:
            logger.info(
                f"Stop raised for {symbol}: ${current_stop:.2f} -> ${recommended_stop:.2f} "
                f"({stop_type.value}) - {params.reasoning}"
            )

        return params

    def should_exit_time_based(
        self,
        entry_time: datetime,
        unrealized_pnl_pct: float
    ) -> Tuple[bool, str]:
        """
        Check if position should exit based on time.

        Args:
            entry_time: Entry timestamp
            unrealized_pnl_pct: Current P&L percentage

        Returns:
            (should_exit, reason)
        """
        days_held = (datetime.now() - entry_time).days

        # Force exit after max hold days
        if days_held >= self.max_hold_days:
            return True, f"Max hold period reached ({days_held} days)"

        # Exit stale positions
        if days_held >= self.stale_position_days and unrealized_pnl_pct < 0.03:
            return True, f"Stale position ({days_held} days with minimal gain)"

        return False, ""

    def calculate_batch_stops(
        self,
        positions: Dict[str, Dict],
        vix: float = 20.0
    ) -> Dict[str, StopLossParams]:
        """
        Calculate adaptive stops for multiple positions.

        Args:
            positions: Dict of symbol -> position data (must have entry_price,
                      entry_time, current_price, stop_loss, highest_price)
            vix: Current VIX level

        Returns:
            Dict of symbol -> StopLossParams
        """
        results = {}

        for symbol, pos in positions.items():
            try:
                params = self.calculate_stop_loss(
                    symbol=symbol,
                    current_price=pos['current_price'],
                    entry_price=pos['entry_price'],
                    entry_time=pos['entry_time'],
                    current_stop=pos['stop_loss'],
                    highest_price_since_entry=pos.get('highest_price', pos['current_price']),
                    atr=pos.get('atr'),
                    vix=vix
                )
                results[symbol] = params

            except Exception as e:
                logger.error(f"Error calculating stop for {symbol}: {e}")

        return results

    def print_stop_summary(self, stops: Dict[str, StopLossParams]) -> None:
        """Print formatted summary of stops."""
        print("\n" + "=" * 80)
        print("ADAPTIVE STOP LOSS SUMMARY")
        print("=" * 80)

        for symbol, params in sorted(stops.items()):
            print(f"\n{symbol}:")
            print(f"  Price: ${params.current_price:.2f} | Entry: ${params.entry_price:.2f} | "
                  f"P&L: {params.unrealized_pnl_pct:+.1%}")
            print(f"  Current Stop: ${params.current_stop:.2f}")
            print(f"  Recommended:  ${params.recommended_stop:.2f} ({params.stop_type.value})")
            print(f"  Distance: {params.stop_distance_pct:.1%} | Days Held: {params.days_held}")
            print(f"  {params.reasoning}")

            if params.recommended_stop > params.current_stop:
                print(f"  → ACTION: RAISE STOP TO ${params.recommended_stop:.2f}")

        print("\n" + "=" * 80)
