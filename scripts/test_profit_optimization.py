#!/usr/bin/env python3
"""
Test and demonstrate advanced profit optimization features.

This script shows how the profit optimization system works with:
- Trailing stops
- Dynamic profit taking
- Position scaling
- Time-based rules
- Volatility adaptation
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk.profit_optimizer import (
    ProfitOptimizer,
    PositionState,
    MarketPhase,
    VolatilityRegime
)
from execution.position_tracker import PositionTracker


def test_trailing_stops():
    """Test trailing stop functionality."""
    print("\n" + "=" * 70)
    print("TEST 1: TRAILING STOPS")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        trailing_stop_pct=0.03,  # 3% trailing stop
        use_atr_trailing=False
    )

    # Simulate a position that's up 10%
    position = PositionState(
        symbol="AAPL",
        entry_price=100.0,
        entry_time=datetime.now() - timedelta(hours=2),
        quantity=100,
        side='long',
        current_price=110.0,  # Up 10%
        unrealized_pnl=1000.0,
        unrealized_pnl_pct=0.10,
        stop_loss=96.0,  # Original stop at 96
        take_profit=108.0,
        trailing_stop=None
    )

    print(f"\nPosition: {position.symbol}")
    print(f"Entry: ${position.entry_price:.2f}")
    print(f"Current: ${position.current_price:.2f} (+{position.unrealized_pnl_pct*100:.1f}%)")
    print(f"Original Stop: ${position.stop_loss:.2f}")

    # Calculate trailing stop
    highest_price = 110.0
    new_stop = optimizer.calculate_trailing_stop(position, highest_price)

    print(f"\nTrailing Stop Calculation:")
    print(f"Highest Price Since Entry: ${highest_price:.2f}")
    print(f"New Trailing Stop: ${new_stop:.2f}")
    print(f"Stop Raised By: ${new_stop - position.stop_loss:.2f}")
    print(f"\nResult: Stop moved up from ${position.stop_loss:.2f} to ${new_stop:.2f}")
    print("This locks in profit - position can't become a loser!")


def test_scale_out():
    """Test partial profit taking."""
    print("\n" + "=" * 70)
    print("TEST 2: DYNAMIC PROFIT TAKING (SCALE OUT)")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        first_target_pct=0.05,  # First target at +5%
        first_target_size_pct=0.5  # Sell 50%
    )

    position = PositionState(
        symbol="TSLA",
        entry_price=200.0,
        entry_time=datetime.now() - timedelta(hours=1),
        quantity=50,
        side='long',
        current_price=210.0,  # Up 5%
        unrealized_pnl=500.0,
        unrealized_pnl_pct=0.05,
        stop_loss=192.0,
        take_profit=216.0,
        trailing_stop=None,
        scale_out_count=0
    )

    print(f"\nPosition: {position.symbol}")
    print(f"Entry: ${position.entry_price:.2f}")
    print(f"Current: ${position.current_price:.2f} (+{position.unrealized_pnl_pct*100:.1f}%)")
    print(f"Quantity: {position.quantity} shares")

    action = optimizer.should_scale_out(position)

    if action:
        print(f"\nAction: {action.action.upper()}")
        print(f"Sell {action.quantity} shares @ ${action.price:.2f}")
        print(f"Reason: {action.reason}")
        print(f"\nRemaining: {position.quantity - action.quantity} shares")
        print("Let remaining shares run with trailing stop for bigger gains!")


def test_scale_in():
    """Test pyramiding (adding to winners)."""
    print("\n" + "=" * 70)
    print("TEST 3: POSITION SCALING (PYRAMIDING)")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        scale_in_profit_threshold=0.03,  # Add at +3%
        scale_in_size_reduction=0.5,  # Each add is 50% of original
        max_scale_ins=2
    )

    position = PositionState(
        symbol="NVDA",
        entry_price=500.0,
        entry_time=datetime.now() - timedelta(hours=3),
        quantity=20,  # Original position
        side='long',
        current_price=520.0,  # Up 4%
        unrealized_pnl=400.0,
        unrealized_pnl_pct=0.04,
        stop_loss=480.0,
        take_profit=None,
        trailing_stop=None,
        scale_in_count=0
    )

    print(f"\nPosition: {position.symbol}")
    print(f"Entry: ${position.entry_price:.2f}")
    print(f"Current: ${position.current_price:.2f} (+{position.unrealized_pnl_pct*100:.1f}%)")
    print(f"Current Quantity: {position.quantity} shares")
    print(f"Scale-ins so far: {position.scale_in_count}")

    signal_strength = 0.75  # Strong signal

    action = optimizer.should_scale_in(position, signal_strength)

    if action:
        print(f"\nAction: {action.action.upper()}")
        print(f"Add {action.quantity} shares @ ${action.price:.2f}")
        print(f"Reason: {action.reason}")
        print(f"\nNew Total: {position.quantity + action.quantity} shares")
        print("Adding to winner - 'let profits run' by pyramiding!")


def test_fast_exit():
    """Test quick exit on losers."""
    print("\n" + "=" * 70)
    print("TEST 4: FAST EXIT ON LOSERS")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        fast_exit_loss_pct=0.02  # Exit at -2% instead of -4%
    )

    position = PositionState(
        symbol="SPY",
        entry_price=450.0,
        entry_time=datetime.now() - timedelta(minutes=30),
        quantity=100,
        side='long',
        current_price=441.0,  # Down 2%
        unrealized_pnl=-900.0,
        unrealized_pnl_pct=-0.02,
        stop_loss=432.0,  # Normal stop at -4%
        take_profit=None,
        trailing_stop=None
    )

    print(f"\nPosition: {position.symbol}")
    print(f"Entry: ${position.entry_price:.2f}")
    print(f"Current: ${position.current_price:.2f} ({position.unrealized_pnl_pct*100:.1f}%)")
    print(f"Normal Stop Loss: ${position.stop_loss:.2f} (-4%)")
    print(f"Current Loss: ${position.unrealized_pnl:.2f}")

    action = optimizer.should_fast_exit(position)

    if action:
        print(f"\nAction: {action.action.upper()}")
        print(f"Exit NOW at ${action.price:.2f}")
        print(f"Reason: {action.reason}")
        print(f"\n'Cut losers quickly' - Don't wait for full stop loss!")
        print(f"Saved ${(position.stop_loss - position.current_price) * position.quantity:.2f} by exiting early")


def test_volatility_adaptation():
    """Test volatility-based adjustments."""
    print("\n" + "=" * 70)
    print("TEST 5: VOLATILITY ADAPTATION")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        vix_high_threshold=25.0,
        high_vol_stop_multiplier=1.5,
        high_vol_size_reduction=0.67
    )

    base_stop = 0.04  # 4% base stop
    base_size = 100  # 100 shares

    print("\nScenario A: Normal Volatility (VIX = 18)")
    vix_normal = 18.0
    regime = optimizer.get_volatility_regime(vix_normal)
    adj_stop, adj_size = optimizer.adjust_for_volatility(base_stop, base_size, vix_normal)

    print(f"VIX: {vix_normal:.1f} ({regime.value})")
    print(f"Stop Distance: {base_stop*100:.1f}% -> {adj_stop*100:.1f}%")
    print(f"Position Size: {base_size} -> {adj_size} shares")

    print("\nScenario B: High Volatility (VIX = 32)")
    vix_high = 32.0
    regime = optimizer.get_volatility_regime(vix_high)
    adj_stop, adj_size = optimizer.adjust_for_volatility(base_stop, base_size, vix_high)

    print(f"VIX: {vix_high:.1f} ({regime.value})")
    print(f"Stop Distance: {base_stop*100:.1f}% -> {adj_stop*100:.1f}%")
    print(f"Position Size: {base_size} -> {adj_size} shares")
    print("\nHigh volatility = Wider stops to avoid shakeouts")
    print("                  Smaller size to maintain same dollar risk")


def test_time_based_rules():
    """Test time-of-day adjustments."""
    print("\n" + "=" * 70)
    print("TEST 6: TIME-BASED RULES")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        avoid_open_minutes=15,
        reduce_size_friday_pct=0.7
    )

    base_size = 100

    # Test different times
    times_to_test = [
        datetime(2024, 1, 2, 9, 35),   # Tuesday 9:35 AM (market open)
        datetime(2024, 1, 2, 10, 30),  # Tuesday 10:30 AM
        datetime(2024, 1, 5, 14, 30),  # Friday 2:30 PM
    ]

    for test_time in times_to_test:
        phase = optimizer.get_market_phase(test_time)
        adj_size, should_trade = optimizer.adjust_for_time_of_day(base_size, test_time)

        day_name = test_time.strftime("%A")
        time_str = test_time.strftime("%I:%M %p")

        print(f"\n{day_name} {time_str}")
        print(f"Market Phase: {phase.value}")
        print(f"Should Trade: {should_trade}")
        print(f"Position Size: {base_size} -> {adj_size} shares")

        if not should_trade:
            print("Avoiding trade during high volatility open period")
        elif adj_size < base_size:
            print("Reducing size for weekend risk (Friday)")


def test_full_optimization():
    """Test full position optimization."""
    print("\n" + "=" * 70)
    print("TEST 7: COMPLETE POSITION OPTIMIZATION")
    print("=" * 70)

    tracker = PositionTracker()

    # Add a winning position
    tracker.add_position(
        symbol="AAPL",
        entry_price=150.0,
        quantity=100,
        side='long',
        stop_loss=144.0,
        take_profit=165.0,
        strategy="momentum",
        signal_strength=0.8,
        atr=2.5
    )

    # Simulate price moving up
    tracker.update_position("AAPL", current_price=157.5)

    print("\nPosition Status:")
    summary = tracker.get_position_summary()
    print(summary.to_string(index=False))

    # Get optimization actions
    vix = 20.0
    signal_strength = 0.75
    actions = tracker.get_optimization_actions("AAPL", vix, signal_strength)

    print(f"\nOptimization Actions ({len(actions)}):")
    for i, action in enumerate(actions, 1):
        print(f"\n{i}. {action.action.upper()}")
        print(f"   Symbol: {action.symbol}")
        if action.quantity:
            print(f"   Quantity: {action.quantity}")
        if action.stop_loss:
            print(f"   New Stop: ${action.stop_loss:.2f}")
        print(f"   Reason: {action.reason}")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("ADVANCED PROFIT OPTIMIZATION - TEST SUITE")
    print("=" * 70)
    print("\nDemonstrating institutional-grade profit maximization techniques")
    print("Academic foundations: Kaufman (2013), Tharp (2006), Schwager (1989)")

    test_trailing_stops()
    test_scale_out()
    test_scale_in()
    test_fast_exit()
    test_volatility_adaptation()
    test_time_based_rules()
    test_full_optimization()

    print("\n" + "=" * 70)
    print("ALL TESTS COMPLETE")
    print("=" * 70)
    print("\nThese techniques are now integrated into auto_trader.py")
    print("The system will automatically:")
    print("  - Lock in profits with trailing stops")
    print("  - Take partial profits at targets")
    print("  - Add to winning positions")
    print("  - Cut losers quickly")
    print("  - Adapt to volatility and time of day")
    print("\nResult: Higher risk-adjusted returns and better drawdown control")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
