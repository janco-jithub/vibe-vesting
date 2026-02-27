"""
Advanced Profit Optimization System

Implements institutional-grade profit maximization techniques:
1. Trailing stop losses - Lock in profits as price moves up
2. Dynamic take profits - Scale out at multiple levels
3. Position scaling (pyramiding) - Add to winners, cut losers fast
4. Time-based rules - Market open/close behavior
5. Volatility adaptation - Adjust risk based on market conditions
6. Strategy-specific optimization - Different rules for different strategy types

Academic References:
- Kaufman (2013): "Trading Systems and Methods" - trailing stops, position sizing
- Tharp (2006): "Trade Your Way to Financial Freedom" - R-multiples, scaling
- Schwager (1989): "Market Wizards" - pyramiding, risk management
- Appel (2005): "Technical Analysis: Power Tools for Active Investors"
"""

import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import numpy as np
import pytz

logger = logging.getLogger(__name__)

# US Eastern timezone for market hours
US_EASTERN = pytz.timezone('US/Eastern')

def get_et_now() -> datetime:
    """Get current time in US Eastern timezone."""
    return datetime.now(US_EASTERN)


class MarketPhase(Enum):
    """Market phases with different trading characteristics."""
    PRE_MARKET = "pre_market"
    OPEN_VOLATILITY = "open_volatility"  # First 30 min
    MORNING_SESSION = "morning_session"  # 10:00-11:30
    MIDDAY_LULL = "midday_lull"  # 11:30-14:00
    AFTERNOON_SESSION = "afternoon_session"  # 14:00-15:30
    CLOSE_RUSH = "close_rush"  # Last 30 min
    AFTER_HOURS = "after_hours"


class VolatilityRegime(Enum):
    """Volatility regime classification."""
    LOW = "low"  # VIX < 15
    NORMAL = "normal"  # VIX 15-25
    ELEVATED = "elevated"  # VIX 25-35
    HIGH = "high"  # VIX > 35


@dataclass
class PositionState:
    """Track state of an open position for optimization."""
    symbol: str
    entry_price: float
    entry_time: datetime
    quantity: int
    side: str  # 'long' or 'short'

    # Current state
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float

    # Risk management
    stop_loss: float
    take_profit: Optional[float]
    trailing_stop: Optional[float]

    # Scaling state
    scale_in_count: int = 0  # Number of times we've added to position
    scale_out_count: int = 0  # Number of times we've taken partial profits

    # Strategy metadata
    strategy: str = ""
    signal_strength: float = 0.0

    # ATR for volatility-based stops
    atr: Optional[float] = None


@dataclass
class TradeAction:
    """Recommended action from the profit optimizer."""
    symbol: str
    action: str  # 'scale_in', 'scale_out', 'close', 'update_stop', 'update_tp'
    quantity: Optional[int] = None
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""


class ProfitOptimizer:
    """
    Advanced profit optimization system for active trading.

    Implements professional techniques to maximize risk-adjusted returns:
    - Trailing stops that lock in profits
    - Partial profit taking at multiple levels
    - Position pyramiding on strong trends
    - Time-of-day and volatility-based adjustments
    """

    def __init__(
        self,
        # Trailing stop parameters - OPTIMIZED per Moskowitz et al. (2012)
        trailing_stop_pct: float = 0.04,  # 4% trailing stop (was 3% - too tight)
        trailing_stop_atr_multiple: float = 3.5,  # 3.5x ATR (was 2.5x - caused whipsaws)
        use_atr_trailing: bool = True,

        # Scale-out parameters - OPTIMIZED for trend capture
        first_target_pct: float = 0.08,  # Take 33% profit at +8% (was +5%)
        first_target_size_pct: float = 0.33,  # Sell 33% of position (was 50%)
        second_target_pct: float = 0.15,  # Take another 33% at +15% (was +10%)
        second_target_size_pct: float = 0.50,  # Sell 50% of remaining at second target
        third_target_pct: float = 0.25,  # Tier 3: Take 50% at +25% (let big winners run)
        third_target_size_pct: float = 0.50,  # Sell 50% of remaining at third target

        # Breakeven stop protection - NEW
        breakeven_trigger_pct: float = 0.02,  # Move to breakeven at +2% profit
        profit_lock_pct: float = 0.005,  # Lock in +0.5% profit (small cushion above breakeven)

        # Scale-in (pyramiding) parameters
        max_scale_ins: int = 2,  # Max 2 additional entries
        scale_in_profit_threshold: float = 0.03,  # Add at +3% profit
        scale_in_size_reduction: float = 0.5,  # Each add is 50% of original

        # Fast exit for losers
        fast_exit_loss_pct: float = 0.02,  # Exit at -2% instead of waiting for -4%

        # Time-based rules
        avoid_open_minutes: int = 15,  # Avoid first 15 min
        reduce_size_friday_pct: float = 0.5,  # 50% smaller positions on Friday
        close_intraday_before_close: bool = False,  # Close day trades before market close

        # Volatility adaptation
        vix_high_threshold: float = 25.0,  # VIX > 25 = elevated volatility
        vix_low_threshold: float = 15.0,  # VIX < 15 = low volatility
        high_vol_stop_multiplier: float = 1.5,  # 1.5x wider stops in high vol
        high_vol_size_reduction: float = 0.67,  # 33% smaller positions in high vol
    ):
        """
        Initialize profit optimizer.

        Args:
            trailing_stop_pct: Percentage-based trailing stop
            trailing_stop_atr_multiple: ATR multiple for trailing stops
            use_atr_trailing: Use ATR-based trailing vs percentage
            first_target_pct: First profit target as % gain
            first_target_size_pct: Portion of position to sell at first target
            second_target_pct: Second profit target as % gain
            second_target_size_pct: Portion of position to sell at second target
            third_target_pct: Third profit target as % gain (let big winners run)
            third_target_size_pct: Portion of position to sell at third target
            breakeven_trigger_pct: Profit % at which to move stop to breakeven
            profit_lock_pct: Small profit cushion above breakeven (e.g., +0.5%)
            max_scale_ins: Maximum number of scale-in entries
            scale_in_profit_threshold: Minimum profit % before scaling in
            scale_in_size_reduction: Size multiplier for each scale-in
            fast_exit_loss_pct: Quick exit threshold for losing trades
            avoid_open_minutes: Minutes to avoid after market open
            reduce_size_friday_pct: Position size reduction on Fridays
            close_intraday_before_close: Close all positions before market close
            vix_high_threshold: VIX level defining high volatility
            vix_low_threshold: VIX level defining low volatility
            high_vol_stop_multiplier: Stop distance multiplier in high vol
            high_vol_size_reduction: Position size reduction in high vol
        """
        self.trailing_stop_pct = trailing_stop_pct
        self.trailing_stop_atr_multiple = trailing_stop_atr_multiple
        self.use_atr_trailing = use_atr_trailing

        self.first_target_pct = first_target_pct
        self.first_target_size_pct = first_target_size_pct
        self.second_target_pct = second_target_pct
        self.second_target_size_pct = second_target_size_pct
        self.third_target_pct = third_target_pct
        self.third_target_size_pct = third_target_size_pct

        self.breakeven_trigger_pct = breakeven_trigger_pct
        self.profit_lock_pct = profit_lock_pct

        self.max_scale_ins = max_scale_ins
        self.scale_in_profit_threshold = scale_in_profit_threshold
        self.scale_in_size_reduction = scale_in_size_reduction

        self.fast_exit_loss_pct = fast_exit_loss_pct

        self.avoid_open_minutes = avoid_open_minutes
        self.reduce_size_friday_pct = reduce_size_friday_pct
        self.close_intraday_before_close = close_intraday_before_close

        self.vix_high_threshold = vix_high_threshold
        self.vix_low_threshold = vix_low_threshold
        self.high_vol_stop_multiplier = high_vol_stop_multiplier
        self.high_vol_size_reduction = high_vol_size_reduction

        logger.info("ProfitOptimizer initialized with advanced techniques")

    def get_market_phase(self, current_time: datetime = None) -> MarketPhase:
        """
        Determine current market phase based on time of day.

        Market phases have different characteristics:
        - Open volatility: High volatility, wider stops
        - Morning session: Best liquidity, ideal for entries
        - Midday lull: Low volume, avoid entries
        - Afternoon session: Good for exits and rebalancing
        - Close rush: High volatility, close day trades

        Args:
            current_time: Current datetime (defaults to now)

        Returns:
            MarketPhase enum
        """
        if current_time is None:
            current_time = get_et_now()  # Use US Eastern time

        market_time = current_time.time()

        # Market hours: 9:30 AM - 4:00 PM ET (using Eastern time)
        if market_time < time(9, 30):
            return MarketPhase.PRE_MARKET
        elif market_time < time(10, 0):
            return MarketPhase.OPEN_VOLATILITY
        elif market_time < time(11, 30):
            return MarketPhase.MORNING_SESSION
        elif market_time < time(14, 0):
            return MarketPhase.MIDDAY_LULL
        elif market_time < time(15, 30):
            return MarketPhase.AFTERNOON_SESSION
        elif market_time < time(16, 0):
            return MarketPhase.CLOSE_RUSH
        else:
            return MarketPhase.AFTER_HOURS

    def get_volatility_regime(self, vix: float) -> VolatilityRegime:
        """
        Classify current volatility regime.

        Args:
            vix: Current VIX level

        Returns:
            VolatilityRegime enum
        """
        if vix < self.vix_low_threshold:
            return VolatilityRegime.LOW
        elif vix < self.vix_high_threshold:
            return VolatilityRegime.NORMAL
        elif vix < 35.0:
            return VolatilityRegime.ELEVATED
        else:
            return VolatilityRegime.HIGH

    def calculate_trailing_stop(
        self,
        position: PositionState,
        highest_price: float
    ) -> float:
        """
        Calculate trailing stop loss that follows price higher.

        Uses either percentage-based or ATR-based trailing, whichever is more
        conservative (allows more room).

        Args:
            position: Current position state
            highest_price: Highest price since entry

        Returns:
            New trailing stop price
        """
        if position.side != 'long':
            # For short positions, trail from lowest price
            logger.warning("Trailing stops for short positions not yet implemented")
            return position.stop_loss

        # Calculate percentage-based trail
        pct_trail = highest_price * (1 - self.trailing_stop_pct)

        # Calculate ATR-based trail if available
        if self.use_atr_trailing and position.atr:
            atr_trail = highest_price - (position.atr * self.trailing_stop_atr_multiple)
            # Use the TIGHTER (higher) stop to ensure proper trailing
            # Previously used min() which caused stops to barely move on high-ATR stocks
            # The tighter stop ensures we lock in profits while still respecting volatility
            new_stop = max(pct_trail, atr_trail)
        else:
            new_stop = pct_trail

        # Never lower the stop - only raise it
        new_stop = max(new_stop, position.stop_loss)

        return round(new_stop, 2)

    def should_scale_out(self, position: PositionState) -> Optional[TradeAction]:
        """
        Check if we should take partial profits.

        Implements tiered scaled exits:
        1. Tier 1: Take 33-50% at first target (e.g., +3%)
        2. Tier 2: Take 50% of remaining at second target (e.g., +6%)
        3. Tier 3: Take 50% of remaining at third target (e.g., +25%)
        4. Let final runner run with trailing stop

        Args:
            position: Current position state

        Returns:
            TradeAction if we should scale out, None otherwise
        """
        # Already scaled out three times (Tier 1, Tier 2, and Tier 3)?
        if position.scale_out_count >= 3:
            logger.debug(
                f"{position.symbol}: Already scaled out {position.scale_out_count} time(s), "
                f"no additional scale-out"
            )
            return None

        profit_pct = position.unrealized_pnl_pct * 100

        # Check Tier 2 (second target) if we've already done Tier 1
        if position.scale_out_count == 1 and position.unrealized_pnl_pct >= self.second_target_pct:
            target_pct = self.second_target_pct * 100

            logger.debug(
                f"{position.symbol}: Tier 2 check: P&L={profit_pct:+.2f}%, "
                f"target={target_pct:.1f}%, scale_outs={position.scale_out_count}"
            )

            # Calculate quantity to sell (50% of current position)
            raw_quantity = position.quantity * self.second_target_size_pct
            quantity_to_sell = int(raw_quantity)

            # For small positions, ensure at least 1 share if possible
            if quantity_to_sell == 0 and position.quantity > 1:
                quantity_to_sell = 1
                logger.info(
                    f"{position.symbol}: Small position ({position.quantity} shares), "
                    f"selling minimum 1 share for Tier 2 instead of {raw_quantity:.2f}"
                )

            if quantity_to_sell > 0:
                logger.info(
                    f"{position.symbol}: TIER 2 SCALE OUT TRIGGERED! "
                    f"P&L={profit_pct:.2f}% >= {target_pct:.1f}% target, "
                    f"selling {quantity_to_sell} shares ({self.second_target_size_pct*100:.0f}% of remaining)"
                )
                return TradeAction(
                    symbol=position.symbol,
                    action='scale_out',
                    quantity=quantity_to_sell,
                    price=position.current_price,
                    reason=f"Tier 2: Taking {self.second_target_size_pct*100:.0f}% profit at "
                           f"{position.unrealized_pnl_pct*100:.1f}% gain"
                )

        # Check Tier 3 (third target) if we've already done Tier 1 and Tier 2
        if position.scale_out_count == 2 and position.unrealized_pnl_pct >= self.third_target_pct:
            target_pct = self.third_target_pct * 100

            logger.debug(
                f"{position.symbol}: Tier 3 check: P&L={profit_pct:+.2f}%, "
                f"target={target_pct:.1f}%, scale_outs={position.scale_out_count}"
            )

            # Calculate quantity to sell (50% of current position)
            raw_quantity = position.quantity * self.third_target_size_pct
            quantity_to_sell = int(raw_quantity)

            # For small positions, ensure at least 1 share if possible
            if quantity_to_sell == 0 and position.quantity > 1:
                quantity_to_sell = 1
                logger.info(
                    f"{position.symbol}: Small position ({position.quantity} shares), "
                    f"selling minimum 1 share for Tier 3 instead of {raw_quantity:.2f}"
                )

            if quantity_to_sell > 0:
                logger.info(
                    f"{position.symbol}: TIER 3 SCALE OUT TRIGGERED! "
                    f"P&L={profit_pct:.2f}% >= {target_pct:.1f}% target, "
                    f"selling {quantity_to_sell} shares ({self.third_target_size_pct*100:.0f}% of remaining)"
                )
                return TradeAction(
                    symbol=position.symbol,
                    action='scale_out',
                    quantity=quantity_to_sell,
                    price=position.current_price,
                    reason=f"Tier 3: Taking {self.third_target_size_pct*100:.0f}% profit at "
                           f"{position.unrealized_pnl_pct*100:.1f}% gain (big winner!)"
                )

        # Check Tier 1 (first target) if we haven't scaled out yet
        if position.scale_out_count == 0 and position.unrealized_pnl_pct >= self.first_target_pct:
            target_pct = self.first_target_pct * 100

            logger.debug(
                f"{position.symbol}: Tier 1 check: P&L={profit_pct:+.2f}%, "
                f"target={target_pct:.1f}%, scale_outs={position.scale_out_count}"
            )

            # Calculate quantity to sell
            raw_quantity = position.quantity * self.first_target_size_pct
            quantity_to_sell = int(raw_quantity)

            # For small positions, ensure at least 1 share if possible
            if quantity_to_sell == 0 and position.quantity > 1:
                quantity_to_sell = 1
                logger.info(
                    f"{position.symbol}: Small position ({position.quantity} shares), "
                    f"selling minimum 1 share for Tier 1 instead of {raw_quantity:.2f}"
                )

            if quantity_to_sell > 0:
                logger.info(
                    f"{position.symbol}: TIER 1 SCALE OUT TRIGGERED! "
                    f"P&L={profit_pct:.2f}% >= {target_pct:.1f}% target, "
                    f"selling {quantity_to_sell} shares ({self.first_target_size_pct*100:.0f}%)"
                )
                return TradeAction(
                    symbol=position.symbol,
                    action='scale_out',
                    quantity=quantity_to_sell,
                    price=position.current_price,
                    reason=f"Tier 1: Taking {self.first_target_size_pct*100:.0f}% profit at "
                           f"{position.unrealized_pnl_pct*100:.1f}% gain"
                )
            else:
                logger.debug(
                    f"{position.symbol}: Scale out triggered but position too small to split "
                    f"(quantity={position.quantity})"
                )

        return None

    def should_scale_in(
        self,
        position: PositionState,
        signal_strength: float = 0.0
    ) -> Optional[TradeAction]:
        """
        Check if we should add to a winning position (pyramiding).

        Only adds to positions that are:
        1. In profit above threshold
        2. Haven't exceeded max scale-ins
        3. Still showing strong signal

        Args:
            position: Current position state
            signal_strength: Current signal strength (0-1)

        Returns:
            TradeAction if we should scale in, None otherwise
        """
        # Already scaled in too many times?
        if position.scale_in_count >= self.max_scale_ins:
            return None

        # Position not profitable enough?
        if position.unrealized_pnl_pct < self.scale_in_profit_threshold:
            return None

        # Signal not strong enough?
        if signal_strength < 0.6:
            return None

        # Calculate scaled-in quantity (each add is smaller)
        scale_factor = self.scale_in_size_reduction ** (position.scale_in_count + 1)
        original_quantity = position.quantity / (1 + sum(
            self.scale_in_size_reduction ** i for i in range(1, position.scale_in_count + 1)
        ))
        quantity_to_add = int(original_quantity * scale_factor)

        if quantity_to_add > 0:
            return TradeAction(
                symbol=position.symbol,
                action='scale_in',
                quantity=quantity_to_add,
                price=position.current_price,
                reason=f"Pyramiding into winner at {position.unrealized_pnl_pct*100:.1f}% profit"
            )

        return None

    def should_fast_exit(self, position: PositionState) -> Optional[TradeAction]:
        """
        Check if we should quickly exit a losing position.

        "Cut your losers quickly" - exit at smaller loss instead of waiting
        for full stop loss to hit.

        Args:
            position: Current position state

        Returns:
            TradeAction if we should fast exit, None otherwise
        """
        # Is this a losing position above the fast exit threshold?
        loss_pct = position.unrealized_pnl_pct * 100
        threshold_pct = self.fast_exit_loss_pct * 100

        logger.debug(
            f"{position.symbol}: Fast exit check: "
            f"P&L={loss_pct:+.2f}%, threshold=-{threshold_pct:.1f}%"
        )

        if position.unrealized_pnl_pct <= -self.fast_exit_loss_pct:
            logger.warning(
                f"{position.symbol}: FAST EXIT TRIGGERED! "
                f"Loss={loss_pct:.2f}% >= -{threshold_pct:.1f}% threshold"
            )
            return TradeAction(
                symbol=position.symbol,
                action='close',
                quantity=position.quantity,
                price=position.current_price,
                reason=f"Fast exit on loss: {position.unrealized_pnl_pct*100:.1f}%"
            )

        return None

    def adjust_for_volatility(
        self,
        base_stop_distance: float,
        base_position_size: float,
        vix: float
    ) -> Tuple[float, float]:
        """
        Adjust stop distance and position size based on volatility regime.

        High volatility:
        - Wider stops to avoid getting shaken out
        - Smaller position sizes to maintain same dollar risk

        Low volatility:
        - Tighter stops
        - Can use larger positions

        Args:
            base_stop_distance: Base stop distance (e.g., 4%)
            base_position_size: Base position size in shares
            vix: Current VIX level

        Returns:
            Tuple of (adjusted_stop_distance, adjusted_position_size)
        """
        regime = self.get_volatility_regime(vix)

        if regime == VolatilityRegime.HIGH or regime == VolatilityRegime.ELEVATED:
            # High volatility: wider stops, smaller size
            stop_multiplier = self.high_vol_stop_multiplier
            size_multiplier = self.high_vol_size_reduction

            logger.info(
                f"High volatility regime (VIX={vix:.1f}): "
                f"stops {stop_multiplier}x wider, size {size_multiplier}x smaller"
            )
        elif regime == VolatilityRegime.LOW:
            # Low volatility: tighter stops, can use normal or slightly larger size
            stop_multiplier = 0.8
            size_multiplier = 1.0

            logger.info(f"Low volatility regime (VIX={vix:.1f}): tighter stops")
        else:
            # Normal volatility: no adjustment
            stop_multiplier = 1.0
            size_multiplier = 1.0

        adjusted_stop = base_stop_distance * stop_multiplier
        adjusted_size = int(base_position_size * size_multiplier)

        return adjusted_stop, adjusted_size

    def adjust_for_time_of_day(
        self,
        base_position_size: float,
        current_time: datetime = None
    ) -> Tuple[float, bool]:
        """
        Adjust trading behavior based on time of day.

        Risk-aware time management:
        - Block entries during open volatility (first 30 min)
        - Block entries during close rush (last 30 min) - avoid overnight risk on new positions
        - Reduce size on Fridays (weekend gap risk)
        - Reduce size during midday lull (lower liquidity)

        Args:
            base_position_size: Base position size
            current_time: Current time (defaults to now)

        Returns:
            Tuple of (adjusted_position_size, should_trade)
        """
        if current_time is None:
            current_time = get_et_now()  # Use US Eastern time

        phase = self.get_market_phase(current_time)

        # Avoid trading in first 30 minutes after open (too volatile/unpredictable)
        if phase == MarketPhase.OPEN_VOLATILITY:
            logger.info("Open volatility phase (9:30-10:00 ET) - blocking new entries")
            return base_position_size, False

        # Avoid NEW entries in last 30 minutes (don't want overnight risk on fresh positions)
        if phase == MarketPhase.CLOSE_RUSH:
            logger.info("Close rush phase (3:30-4:00 ET) - blocking new entries to avoid immediate overnight risk")
            return base_position_size, False

        # Avoid entries in pre-market and after-hours
        if phase in (MarketPhase.PRE_MARKET, MarketPhase.AFTER_HOURS):
            logger.info(f"{phase.value} - market closed, blocking entries")
            return base_position_size, False

        # Reduce size on Fridays (weekend gap risk) - 30% reduction
        if current_time.weekday() == 4:  # Friday
            adjusted_size = int(base_position_size * self.reduce_size_friday_pct)
            logger.info(
                f"Friday trading - reducing position size by "
                f"{(1-self.reduce_size_friday_pct)*100:.0f}% for weekend gap risk"
            )
            return adjusted_size, True

        # Midday lull - lower priority for entries (lower liquidity)
        if phase == MarketPhase.MIDDAY_LULL:
            logger.debug("Midday lull (11:30-14:00 ET) - 20% smaller positions due to lower liquidity")
            return base_position_size * 0.8, True

        return base_position_size, True

    def get_strategy_params(self, strategy_name: str) -> Dict:
        """
        Get strategy-specific optimization parameters.

        Loads from strategy_optimizer_config module if available,
        otherwise uses default parameters.

        Args:
            strategy_name: Name of the strategy

        Returns:
            Dict of parameter overrides for this strategy
        """
        try:
            from risk.strategy_optimizer_config import get_optimizer_params_for_strategy
            params = get_optimizer_params_for_strategy(strategy_name)

            return {
                'trailing_stop_pct': params.trailing_stop_pct,
                'trailing_stop_atr_multiple': params.trailing_stop_atr_multiple,
                'first_target_pct': params.first_target_pct,
                'first_target_size_pct': params.first_target_size_pct,
                'max_scale_ins': params.max_scale_ins,
                'scale_in_profit_threshold': params.scale_in_profit_threshold,
                'fast_exit_loss_pct': params.fast_exit_loss_pct,
                'avoid_open_minutes': params.avoid_open_minutes,
                'reduce_size_friday_pct': params.reduce_size_friday_pct,
            }
        except ImportError:
            logger.warning("strategy_optimizer_config not available, using defaults")
            return {}

    def optimize_position(
        self,
        position: PositionState,
        vix: float = 20.0,
        signal_strength: float = 0.0,
        highest_price_since_entry: Optional[float] = None,
        use_strategy_specific_params: bool = True
    ) -> List[TradeAction]:
        """
        Analyze position and return recommended optimization actions.

        This is the main entry point - call this periodically for each position.

        Args:
            position: Current position state
            vix: Current VIX level
            signal_strength: Current signal strength (0-1)
            highest_price_since_entry: Highest price since entry (for trailing stop)
            use_strategy_specific_params: Use strategy-specific parameters if available

        Returns:
            List of recommended TradeActions
        """
        # Load strategy-specific parameters if enabled
        original_params = {}
        if use_strategy_specific_params and position.strategy:
            strategy_params = self.get_strategy_params(position.strategy)
            if strategy_params:
                # Save original params
                original_params = {
                    'trailing_stop_pct': self.trailing_stop_pct,
                    'first_target_pct': self.first_target_pct,
                    'max_scale_ins': self.max_scale_ins,
                    'scale_in_profit_threshold': self.scale_in_profit_threshold,
                    'fast_exit_loss_pct': self.fast_exit_loss_pct,
                }

                # Apply strategy-specific overrides
                for param_name, param_value in strategy_params.items():
                    setattr(self, param_name, param_value)

                logger.debug(
                    f"Using strategy-specific params for {position.strategy} on {position.symbol}"
                )

        try:
            actions = []

            # 1. Check for fast exit on losers
            fast_exit = self.should_fast_exit(position)
            if fast_exit:
                actions.append(fast_exit)
                return actions  # Exit immediately, don't check other rules

            # 2. Move stop to breakeven once position reaches profit threshold
            # This protects against giving back all gains on reversals
            if position.unrealized_pnl_pct >= self.breakeven_trigger_pct:
                # Calculate breakeven stop (entry + small profit cushion)
                breakeven_stop = position.entry_price * (1 + self.profit_lock_pct)

                # Only move to breakeven if current stop is below it
                # (don't lower stops that have already been raised higher)
                if position.stop_loss < breakeven_stop:
                    logger.info(
                        f"{position.symbol}: BREAKEVEN STOP TRIGGERED! "
                        f"P&L={position.unrealized_pnl_pct*100:+.2f}% >= "
                        f"{self.breakeven_trigger_pct*100:.1f}% trigger, "
                        f"moving stop ${position.stop_loss:.2f} -> ${breakeven_stop:.2f} "
                        f"(locking {self.profit_lock_pct*100:.1f}% profit)"
                    )
                    actions.append(TradeAction(
                        symbol=position.symbol,
                        action='update_stop',
                        stop_loss=breakeven_stop,
                        reason=f"Breakeven protection: locking {self.profit_lock_pct*100:.1f}% profit"
                    ))

            # 3. Check for partial profit taking
            scale_out = self.should_scale_out(position)
            if scale_out:
                actions.append(scale_out)

            # 4. Update trailing stop if in profit
            if position.unrealized_pnl_pct > 0 and highest_price_since_entry:
                new_stop = self.calculate_trailing_stop(position, highest_price_since_entry)

                logger.debug(
                    f"{position.symbol}: Trailing stop analysis: "
                    f"highest=${highest_price_since_entry:.2f}, "
                    f"current=${position.current_price:.2f}, "
                    f"trail%={self.trailing_stop_pct*100:.1f}%, "
                    f"new_stop=${new_stop:.2f}, "
                    f"current_stop=${position.stop_loss:.2f}"
                )

                if new_stop > position.stop_loss:
                    logger.info(
                        f"{position.symbol}: TRAILING STOP RAISED! "
                        f"${position.stop_loss:.2f} -> ${new_stop:.2f} "
                        f"(P&L={position.unrealized_pnl_pct*100:+.2f}%)"
                    )
                    # Check if we already have a breakeven stop action
                    existing_stop_action = next(
                        (a for a in actions if a.action == 'update_stop'), None
                    )
                    if existing_stop_action:
                        # Use the higher of the two stops
                        if new_stop > existing_stop_action.stop_loss:
                            existing_stop_action.stop_loss = new_stop
                            existing_stop_action.reason = (
                                f"Trailing stop raised to ${new_stop:.2f} "
                                f"(locking in profit, strategy={position.strategy})"
                            )
                    else:
                        actions.append(TradeAction(
                            symbol=position.symbol,
                            action='update_stop',
                            stop_loss=new_stop,
                            reason=f"Trailing stop raised to ${new_stop:.2f} "
                                   f"(locking in profit, strategy={position.strategy})"
                        ))
                else:
                    logger.debug(
                        f"{position.symbol}: Trailing stop unchanged at ${position.stop_loss:.2f}"
                    )

            # 5. Tighten stops during CLOSE_RUSH to lock in more profit before overnight
            phase = self.get_market_phase()
            if phase == MarketPhase.CLOSE_RUSH and position.unrealized_pnl_pct > 0.01:
                # In last 30 min, use tighter trailing stop (2% instead of 4%) to lock in profits
                close_rush_trail_pct = 0.02  # 2% trailing stop before close
                tighter_stop = position.current_price * (1 - close_rush_trail_pct)

                if tighter_stop > position.stop_loss:
                    logger.info(
                        f"{position.symbol}: CLOSE RUSH - tightening stop from "
                        f"${position.stop_loss:.2f} to ${tighter_stop:.2f} "
                        f"(locking in profit before overnight)"
                    )
                    # Check if we already have an update_stop action, update it
                    existing_stop_action = next(
                        (a for a in actions if a.action == 'update_stop'), None
                    )
                    if existing_stop_action:
                        # Use the tighter of the two stops
                        if tighter_stop > existing_stop_action.stop_loss:
                            existing_stop_action.stop_loss = tighter_stop
                            existing_stop_action.reason = (
                                f"Close rush - tightened stop to ${tighter_stop:.2f} "
                                f"(protecting overnight)"
                            )
                    else:
                        actions.append(TradeAction(
                            symbol=position.symbol,
                            action='update_stop',
                            stop_loss=tighter_stop,
                            reason=f"Close rush - tightened stop to ${tighter_stop:.2f} "
                                   f"(protecting overnight)"
                        ))

            # 6. Check if we should add to winner (pyramiding)
            # Only if we haven't just scaled out and not in close rush
            if not scale_out and phase != MarketPhase.CLOSE_RUSH:
                scale_in = self.should_scale_in(position, signal_strength)
                if scale_in:
                    actions.append(scale_in)

            # 7. Check time-based rules (e.g., close before market close)
            if self.close_intraday_before_close:
                phase = self.get_market_phase()
                if phase == MarketPhase.CLOSE_RUSH:
                    # Close intraday positions in last 30 min
                    entry_today = position.entry_time.date() == datetime.now().date()
                    if entry_today:
                        actions.append(TradeAction(
                            symbol=position.symbol,
                            action='close',
                            quantity=position.quantity,
                            reason="Closing intraday position before market close"
                        ))

            return actions

        finally:
            # Restore original parameters
            if original_params:
                for param_name, param_value in original_params.items():
                    setattr(self, param_name, param_value)

    def calculate_optimal_entry(
        self,
        symbol: str,
        base_price: float,
        base_quantity: int,
        base_stop_pct: float,
        vix: float = 20.0,
        atr: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate optimal entry parameters considering volatility and time.

        Args:
            symbol: Symbol to trade
            base_price: Target entry price
            base_quantity: Base position size
            base_stop_pct: Base stop loss percentage
            vix: Current VIX level
            atr: Average True Range for the symbol

        Returns:
            Dict with optimized entry parameters
        """
        # Adjust for volatility
        adjusted_stop_pct, adjusted_quantity = self.adjust_for_volatility(
            base_stop_pct,
            base_quantity,
            vix
        )

        # Adjust for time of day
        time_adjusted_quantity, should_trade = self.adjust_for_time_of_day(
            adjusted_quantity
        )

        if not should_trade:
            return {
                'should_trade': False,
                'reason': 'Time-based restriction'
            }

        # Calculate prices
        stop_loss_price = round(base_price * (1 - adjusted_stop_pct), 2)
        take_profit_price = round(base_price * (1 + self.first_target_pct), 2)

        return {
            'should_trade': True,
            'symbol': symbol,
            'quantity': int(time_adjusted_quantity),
            'entry_price': base_price,
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price,
            'stop_pct': adjusted_stop_pct,
            'reason': f'Optimized entry (VIX={vix:.1f}, qty={int(time_adjusted_quantity)})'
        }
