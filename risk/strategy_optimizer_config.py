"""
Strategy-Specific Profit Optimization Configuration

Different strategies have different characteristics and require different
profit optimization approaches:

1. Momentum strategies (simple_momentum, swing_momentum, ml_momentum):
   - Need room to run - wider profit targets
   - Trend-following requires patience
   - Tighter trailing stops once in profit

2. Mean reversion (pairs_trading):
   - Quick in and out
   - Tight profit targets
   - Fast exits if trade goes wrong

3. Factor composite:
   - Balanced approach
   - Medium-term holding period
   - Standard profit optimization

Academic References:
- Momentum: Jegadeesh & Titman (1993) - hold 3-12 months
- Mean Reversion: Gatev et al. (2006) - hold days to weeks
- Multi-factor: Asness et al. (2019) - monthly rebalancing
"""

from dataclasses import dataclass
from typing import Dict
import logging

logger = logging.getLogger(__name__)


@dataclass
class StrategyOptimizerParams:
    """Profit optimization parameters for a specific strategy."""

    # Trailing stops
    trailing_stop_pct: float
    trailing_stop_atr_multiple: float
    use_atr_trailing: bool

    # Profit taking
    first_target_pct: float  # First profit target
    first_target_size_pct: float  # Size to sell at first target
    second_target_pct: float  # Second profit target (if any)

    # Pyramiding
    max_scale_ins: int
    scale_in_profit_threshold: float
    scale_in_size_reduction: float

    # Loss management
    fast_exit_loss_pct: float

    # Time-based
    avoid_open_minutes: int
    reduce_size_friday_pct: float

    # Description
    description: str = ""


# Strategy-specific configurations optimized for each strategy's characteristics
STRATEGY_OPTIMIZER_CONFIGS: Dict[str, StrategyOptimizerParams] = {

    # MOMENTUM STRATEGIES - Need room to run, let winners ride
    'simple_momentum': StrategyOptimizerParams(
        trailing_stop_pct=0.04,  # 4% trailing (wider for momentum)
        trailing_stop_atr_multiple=3.5,  # 3.5x ATR (more room for volatility)
        use_atr_trailing=True,
        first_target_pct=0.08,  # Take 33% at +8% (let momentum develop)
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.15,  # Final exit at +15%
        max_scale_ins=2,
        scale_in_profit_threshold=0.03,  # Add at +3% (earlier to pyramid)
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.02,  # Exit at -2% (consistent with other strategies)
        avoid_open_minutes=5,  # Reduced from 10 (faster entries)
        reduce_size_friday_pct=0.90,
        description="Momentum needs room - wider stops, higher targets"
    ),

    'swing_momentum': StrategyOptimizerParams(
        trailing_stop_pct=0.045,  # 4.5% trailing (wider for swings)
        trailing_stop_atr_multiple=3.0,
        use_atr_trailing=True,
        first_target_pct=0.10,  # Take 50% at +10% (swing traders)
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.20,
        max_scale_ins=1,  # Less pyramiding for swing
        scale_in_profit_threshold=0.06,
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.03,  # -3% exit
        avoid_open_minutes=15,
        reduce_size_friday_pct=0.85,  # More reduction (avoid weekend gaps)
        description="Swing trading - wider stops, patience required"
    ),

    'ml_momentum': StrategyOptimizerParams(
        trailing_stop_pct=0.035,  # 3.5% trailing
        trailing_stop_atr_multiple=2.5,
        use_atr_trailing=True,
        first_target_pct=0.07,  # +7% first target
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.12,
        max_scale_ins=2,
        scale_in_profit_threshold=0.04,
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.02,
        avoid_open_minutes=5,
        reduce_size_friday_pct=0.90,
        description="ML-enhanced momentum - data-driven exits"
    ),

    # MEAN REVERSION - Quick in and out
    'pairs_trading': StrategyOptimizerParams(
        trailing_stop_pct=0.02,  # 2% trailing (tight)
        trailing_stop_atr_multiple=1.5,  # Tight ATR trailing
        use_atr_trailing=True,
        first_target_pct=0.03,  # Take 50% at +3% (quick profits)
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.05,  # Exit fully at +5%
        max_scale_ins=0,  # No pyramiding for mean reversion
        scale_in_profit_threshold=0.10,  # Effectively disabled
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.015,  # Very fast exit at -1.5%
        avoid_open_minutes=5,
        reduce_size_friday_pct=0.95,  # Minimal reduction (pairs are market-neutral)
        description="Mean reversion - quick in/out, tight stops"
    ),

    # FACTOR COMPOSITE - Balanced approach
    'factor_composite': StrategyOptimizerParams(
        trailing_stop_pct=0.04,  # 4% trailing (increased from 3% for less whipsaw)
        trailing_stop_atr_multiple=3.5,  # 3.5x ATR (more room)
        use_atr_trailing=True,
        first_target_pct=0.08,  # Take 33% at +8% (higher target for better R:R)
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.15,  # Raised from 12% to 15%
        max_scale_ins=2,
        scale_in_profit_threshold=0.03,  # Add at +3% (earlier pyramiding)
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.02,  # Standard -2% exit
        avoid_open_minutes=5,
        reduce_size_friday_pct=0.90,
        description="Multi-factor - balanced optimization"
    ),

    # VOLATILITY BREAKOUT - Aggressive pursuit
    'volatility_breakout': StrategyOptimizerParams(
        trailing_stop_pct=0.05,  # 5% trailing (wide for breakouts)
        trailing_stop_atr_multiple=3.5,  # Very wide for high vol
        use_atr_trailing=True,
        first_target_pct=0.10,  # +10% first target (big moves)
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.20,
        max_scale_ins=2,
        scale_in_profit_threshold=0.07,  # Add at +7% (strong breakout)
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.03,  # -3% exit (false breakout)
        avoid_open_minutes=0,  # Breakouts happen at open
        reduce_size_friday_pct=0.85,
        description="Breakout trading - wide stops, chase momentum"
    ),

    # DUAL MOMENTUM - Trend following
    'dual_momentum': StrategyOptimizerParams(
        trailing_stop_pct=0.04,  # 4% trailing
        trailing_stop_atr_multiple=3.0,
        use_atr_trailing=True,
        first_target_pct=0.08,  # +8% target
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.15,
        max_scale_ins=2,
        scale_in_profit_threshold=0.05,
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.025,
        avoid_open_minutes=10,
        reduce_size_friday_pct=0.90,
        description="Dual momentum - ride trends, wide stops"
    ),

    # DEFAULT - Conservative fallback
    'default': StrategyOptimizerParams(
        trailing_stop_pct=0.03,
        trailing_stop_atr_multiple=2.5,
        use_atr_trailing=True,
        first_target_pct=0.05,
        first_target_size_pct=0.33,  # Sell 33%, let 67% run
        second_target_pct=0.10,
        max_scale_ins=2,
        scale_in_profit_threshold=0.03,
        scale_in_size_reduction=0.5,
        fast_exit_loss_pct=0.02,
        avoid_open_minutes=5,
        reduce_size_friday_pct=0.90,
        description="Default conservative settings"
    ),
}


def get_optimizer_params_for_strategy(strategy_name: str) -> StrategyOptimizerParams:
    """
    Get profit optimizer parameters for a given strategy.

    Args:
        strategy_name: Name of the strategy

    Returns:
        StrategyOptimizerParams configured for this strategy
    """
    if strategy_name in STRATEGY_OPTIMIZER_CONFIGS:
        logger.debug(f"Using strategy-specific optimizer params for {strategy_name}")
        return STRATEGY_OPTIMIZER_CONFIGS[strategy_name]
    else:
        logger.warning(
            f"No strategy-specific params for '{strategy_name}', using defaults"
        )
        return STRATEGY_OPTIMIZER_CONFIGS['default']


def print_strategy_comparison():
    """Print comparison table of all strategy optimizer configs."""
    print("\n" + "=" * 120)
    print("STRATEGY-SPECIFIC PROFIT OPTIMIZATION COMPARISON")
    print("=" * 120)
    print()

    print(f"{'Strategy':<20} {'Trail%':<8} {'Target1%':<10} {'Target2%':<10} {'FastExit%':<11} {'ScaleIn':<8} {'Description':<40}")
    print("-" * 120)

    for strat_name, params in STRATEGY_OPTIMIZER_CONFIGS.items():
        if strat_name == 'default':
            continue

        print(
            f"{strat_name:<20} "
            f"{params.trailing_stop_pct*100:>6.1f}%  "
            f"{params.first_target_pct*100:>8.1f}%  "
            f"{params.second_target_pct*100:>8.1f}%  "
            f"{params.fast_exit_loss_pct*100:>9.2f}%  "
            f"{params.max_scale_ins:>6}  "
            f"{params.description:<40}"
        )

    print("=" * 120)
    print()


if __name__ == "__main__":
    # Run comparison when executed directly
    print_strategy_comparison()
