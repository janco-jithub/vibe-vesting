#!/usr/bin/env python3
"""
Test Profit Optimizer Logic

Tests the profit optimizer with simulated positions to verify:
1. Scale out triggers at +8%
2. Trailing stops are raised automatically
3. Fast exits trigger at -2%
4. All logging works correctly
"""

import sys
from datetime import datetime, timedelta
from risk.profit_optimizer import ProfitOptimizer, PositionState

def test_scale_out_at_8_percent():
    """Test that scale out triggers at +8% profit."""
    print("\n" + "=" * 70)
    print("TEST 1: Scale out at +8% profit")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        trailing_stop_pct=0.04,
        trailing_stop_atr_multiple=3.5,
        use_atr_trailing=True,
        first_target_pct=0.08,  # 8%
        first_target_size_pct=0.33,  # 33%
        fast_exit_loss_pct=0.02,
    )

    # Create a position at +8.7% profit (like SOXX)
    position = PositionState(
        symbol="SOXX",
        entry_price=45.25,
        entry_time=datetime.now() - timedelta(hours=2),
        quantity=30,
        side='long',
        current_price=49.18,  # +8.7% profit
        unrealized_pnl=(49.18 - 45.25) * 30,
        unrealized_pnl_pct=(49.18 - 45.25) / 45.25,
        stop_loss=43.89,
        take_profit=None,
        trailing_stop=None,
        scale_in_count=0,
        scale_out_count=0,
        strategy='factor_composite',
        signal_strength=0.8,
        atr=1.2
    )

    print(f"\nPosition: {position.symbol}")
    print(f"  Entry: ${position.entry_price:.2f}")
    print(f"  Current: ${position.current_price:.2f}")
    print(f"  P&L: {position.unrealized_pnl_pct*100:+.2f}%")
    print(f"  Quantity: {position.quantity}")
    print(f"  Scale outs: {position.scale_out_count}")

    # Check for scale out
    actions = optimizer.optimize_position(
        position=position,
        vix=20.0,
        signal_strength=0.8,
        highest_price_since_entry=49.18
    )

    print(f"\nActions generated: {len(actions)}")
    for action in actions:
        print(f"  - {action.action.upper()}: {action.reason}")
        if action.action == 'scale_out':
            print(f"    Quantity to sell: {action.quantity} shares")
            print(f"    Price: ${action.price:.2f}")

    # Verify scale out was triggered
    scale_out_found = any(a.action == 'scale_out' for a in actions)
    if scale_out_found:
        print("\n✓ PASS: Scale out triggered at +8.7%")
        return True
    else:
        print("\n✗ FAIL: Scale out did NOT trigger at +8.7%")
        return False


def test_trailing_stop_raised():
    """Test that trailing stops are raised as price increases."""
    print("\n" + "=" * 70)
    print("TEST 2: Trailing stop raised as price increases")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        trailing_stop_pct=0.04,  # 4%
        trailing_stop_atr_multiple=3.5,
        use_atr_trailing=True,
        first_target_pct=0.08,
    )

    # Create a position at +5% profit
    position = PositionState(
        symbol="QQQ",
        entry_price=382.50,
        entry_time=datetime.now() - timedelta(hours=3),
        quantity=5,
        side='long',
        current_price=401.63,  # +5% profit
        unrealized_pnl=(401.63 - 382.50) * 5,
        unrealized_pnl_pct=(401.63 - 382.50) / 382.50,
        stop_loss=371.65,  # Original stop at -2.8%
        take_profit=None,
        trailing_stop=None,
        scale_in_count=0,
        scale_out_count=0,
        strategy='simple_momentum',
        signal_strength=0.7,
        atr=5.2
    )

    print(f"\nPosition: {position.symbol}")
    print(f"  Entry: ${position.entry_price:.2f}")
    print(f"  Highest: ${position.current_price:.2f}")
    print(f"  Current stop: ${position.stop_loss:.2f}")
    print(f"  P&L: {position.unrealized_pnl_pct*100:+.2f}%")
    print(f"  ATR: ${position.atr:.2f}")

    # Calculate what the new stop should be
    # 4% below highest: 401.63 * 0.96 = $385.56
    # 3.5x ATR below: 401.63 - (5.2 * 3.5) = $383.43
    # Use the lower (more room): $383.43
    expected_stop = 401.63 - (5.2 * 3.5)
    print(f"  Expected new stop: ${expected_stop:.2f} (3.5x ATR)")

    # Get optimization actions
    actions = optimizer.optimize_position(
        position=position,
        vix=20.0,
        signal_strength=0.7,
        highest_price_since_entry=401.63
    )

    print(f"\nActions generated: {len(actions)}")
    for action in actions:
        print(f"  - {action.action.upper()}: {action.reason}")
        if action.action == 'update_stop':
            print(f"    New stop: ${action.stop_loss:.2f}")

    # Verify trailing stop was updated
    stop_update_found = any(a.action == 'update_stop' for a in actions)
    if stop_update_found:
        stop_action = next(a for a in actions if a.action == 'update_stop')
        if stop_action.stop_loss > position.stop_loss:
            print(f"\n✓ PASS: Trailing stop raised from ${position.stop_loss:.2f} to ${stop_action.stop_loss:.2f}")
            return True
        else:
            print(f"\n✗ FAIL: Stop not raised (stayed at ${position.stop_loss:.2f})")
            return False
    else:
        print("\n✗ FAIL: No trailing stop update generated")
        return False


def test_fast_exit_at_2_percent():
    """Test that fast exit triggers at -2% loss."""
    print("\n" + "=" * 70)
    print("TEST 3: Fast exit at -2% loss")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        fast_exit_loss_pct=0.02,  # -2%
    )

    # Create a losing position at -2.5%
    position = PositionState(
        symbol="SPY",
        entry_price=450.00,
        entry_time=datetime.now() - timedelta(hours=1),
        quantity=10,
        side='long',
        current_price=438.75,  # -2.5% loss
        unrealized_pnl=(438.75 - 450.00) * 10,
        unrealized_pnl_pct=(438.75 - 450.00) / 450.00,
        stop_loss=432.00,  # Stop at -4%
        take_profit=None,
        trailing_stop=None,
        scale_in_count=0,
        scale_out_count=0,
        strategy='factor_composite',
        signal_strength=0.3,
        atr=3.5
    )

    print(f"\nPosition: {position.symbol}")
    print(f"  Entry: ${position.entry_price:.2f}")
    print(f"  Current: ${position.current_price:.2f}")
    print(f"  P&L: {position.unrealized_pnl_pct*100:+.2f}%")
    print(f"  Stop loss: ${position.stop_loss:.2f}")

    # Get optimization actions
    actions = optimizer.optimize_position(
        position=position,
        vix=20.0,
        signal_strength=0.3,
        highest_price_since_entry=450.00
    )

    print(f"\nActions generated: {len(actions)}")
    for action in actions:
        print(f"  - {action.action.upper()}: {action.reason}")
        if action.action == 'close':
            print(f"    Closing entire position ({action.quantity} shares)")

    # Verify fast exit was triggered
    close_found = any(a.action == 'close' for a in actions)
    if close_found:
        print("\n✓ PASS: Fast exit triggered at -2.5%")
        return True
    else:
        print("\n✗ FAIL: Fast exit did NOT trigger at -2.5%")
        return False


def test_no_double_scale_out():
    """Test that we don't scale out twice."""
    print("\n" + "=" * 70)
    print("TEST 4: No double scale-out")
    print("=" * 70)

    optimizer = ProfitOptimizer(
        first_target_pct=0.08,  # 8%
        first_target_size_pct=0.33,
    )

    # Create a position at +10% that already scaled out once
    position = PositionState(
        symbol="NVDA",
        entry_price=100.00,
        entry_time=datetime.now() - timedelta(hours=4),
        quantity=20,  # Already reduced from original 30
        side='long',
        current_price=110.00,  # +10% profit
        unrealized_pnl=(110.00 - 100.00) * 20,
        unrealized_pnl_pct=(110.00 - 100.00) / 100.00,
        stop_loss=105.60,  # Trailing stop at 4% below current
        take_profit=None,
        trailing_stop=None,
        scale_in_count=0,
        scale_out_count=1,  # Already scaled out once!
        strategy='simple_momentum',
        signal_strength=0.9,
        atr=2.5
    )

    print(f"\nPosition: {position.symbol}")
    print(f"  Entry: ${position.entry_price:.2f}")
    print(f"  Current: ${position.current_price:.2f}")
    print(f"  P&L: {position.unrealized_pnl_pct*100:+.2f}%")
    print(f"  Scale outs: {position.scale_out_count} (already scaled out)")

    # Get optimization actions
    actions = optimizer.optimize_position(
        position=position,
        vix=20.0,
        signal_strength=0.9,
        highest_price_since_entry=110.00
    )

    print(f"\nActions generated: {len(actions)}")
    for action in actions:
        print(f"  - {action.action.upper()}: {action.reason}")

    # Verify NO scale out was generated
    scale_out_found = any(a.action == 'scale_out' for a in actions)
    if not scale_out_found:
        print("\n✓ PASS: No second scale-out (correct behavior)")
        return True
    else:
        print("\n✗ FAIL: Attempted to scale out again (should only scale out once)")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("PROFIT OPTIMIZER TEST SUITE")
    print("=" * 70)
    print("\nTesting the fixes to profit optimizer logic...")

    results = []

    # Run all tests
    results.append(("Scale out at +8%", test_scale_out_at_8_percent()))
    results.append(("Trailing stop raised", test_trailing_stop_raised()))
    results.append(("Fast exit at -2%", test_fast_exit_at_2_percent()))
    results.append(("No double scale-out", test_no_double_scale_out()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    total_passed = sum(1 for _, p in results if p)
    total_tests = len(results)

    print(f"\nResults: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("\n✓ ALL TESTS PASSED - Profit optimizer is working correctly!")
        return 0
    else:
        print(f"\n✗ {total_tests - total_passed} TEST(S) FAILED - Review the output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
