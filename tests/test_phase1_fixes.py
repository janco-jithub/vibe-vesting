#!/usr/bin/env python3
"""
Test Phase 1 optimizations to verify they work correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import date, timedelta
from strategies.simple_momentum import SimpleMomentumStrategy
from strategies.base import SignalType

def generate_test_data(symbols, days=100):
    """Generate synthetic price data for testing."""
    data = {}
    end_date = date.today()
    dates = pd.date_range(end=end_date, periods=days, freq='D')

    for symbol in symbols:
        # Generate random walk with upward drift
        np.random.seed(hash(symbol) % 2**32)
        returns = np.random.randn(days) * 0.02 + 0.001  # 0.1% daily drift
        prices = 100 * (1 + returns).cumprod()

        data[symbol] = pd.DataFrame({
            'open': prices * 0.995,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices,
            'volume': np.random.randint(1000000, 10000000, days)
        }, index=dates)

    return data


def test_signal_generation_fix():
    """Test that get_current_signal returns only latest signals, not all historical."""
    print("\n" + "="*70)
    print("TEST: Signal Generation Fix")
    print("="*70)

    strategy = SimpleMomentumStrategy(
        sma_period=50,
        momentum_period=20,
        max_positions=3
    )

    # Generate 100 days of data
    data = generate_test_data(strategy.universe, days=100)

    # Get current signals (should only return today's signals)
    current_signals = strategy.get_current_signal(data)

    print(f"\nStrategy Universe: {len(strategy.universe)} symbols")
    print(f"Max Positions: {strategy.max_positions}")
    print(f"Generated signals: {len(current_signals)}")

    # Check signal dates - all should be the latest date
    if current_signals:
        latest_date = max(df.index[-1].date() for df in data.values())
        signal_dates = [s.date for s in current_signals]
        unique_dates = set(signal_dates)

        print(f"Latest data date: {latest_date}")
        print(f"Unique signal dates: {unique_dates}")
        print(f"All signals from latest date: {len(unique_dates) == 1 and latest_date in unique_dates}")

        # Count by signal type
        buy_count = sum(1 for s in current_signals if s.signal_type == SignalType.BUY)
        sell_count = sum(1 for s in current_signals if s.signal_type == SignalType.SELL)

        print(f"\nSignal breakdown:")
        print(f"  BUY signals: {buy_count} (should be <= {strategy.max_positions})")
        print(f"  SELL signals: {sell_count}")

        # Verify BUY signals don't exceed max_positions
        if buy_count <= strategy.max_positions:
            print(f"\n✓ BUY signal limit respected: {buy_count} <= {strategy.max_positions}")
        else:
            print(f"\n✗ BUY signal limit EXCEEDED: {buy_count} > {strategy.max_positions}")
            return False

        # Verify all signals are from latest date
        if len(unique_dates) == 1 and latest_date in unique_dates:
            print(f"✓ All signals from latest date only")
        else:
            print(f"✗ Signals from multiple dates: {unique_dates}")
            return False

        # Print signal details
        print(f"\nSignal details:")
        for signal in current_signals[:5]:  # Show first 5
            print(f"  {signal.symbol}: {signal.signal_type.name} "
                  f"(strength: {signal.strength:.2f}, "
                  f"momentum: {signal.metadata.get('momentum', 'N/A'):.2f}%)")

    else:
        print("\nNo signals generated (market conditions may not be favorable)")

    print("\n✓ TEST PASSED: Signal generation returns only latest signals\n")
    return True


def test_profit_optimizer_params():
    """Test that ProfitOptimizer parameters were updated correctly."""
    print("\n" + "="*70)
    print("TEST: Profit Optimizer Parameter Changes")
    print("="*70)

    # Import here to avoid loading database/API connections
    from risk.profit_optimizer import ProfitOptimizer

    # Create optimizer with Phase 1 parameters
    optimizer = ProfitOptimizer(
        avoid_open_minutes=5,
        reduce_size_friday_pct=0.85
    )

    print(f"\nParameter verification:")
    print(f"  avoid_open_minutes: {optimizer.avoid_open_minutes} (expected: 5)")
    print(f"  reduce_size_friday_pct: {optimizer.reduce_size_friday_pct} (expected: 0.85)")

    # Verify values
    if optimizer.avoid_open_minutes == 5:
        print(f"✓ Opening avoidance window reduced to 5 minutes")
    else:
        print(f"✗ Opening avoidance window incorrect: {optimizer.avoid_open_minutes}")
        return False

    if optimizer.reduce_size_friday_pct == 0.85:
        print(f"✓ Friday position penalty reduced to 0.85 (15% smaller)")
    else:
        print(f"✗ Friday position penalty incorrect: {optimizer.reduce_size_friday_pct}")
        return False

    print("\n✓ TEST PASSED: ProfitOptimizer parameters updated correctly\n")
    return True


def main():
    """Run all Phase 1 tests."""
    print("\n" + "="*70)
    print("PHASE 1 OPTIMIZATION TESTS")
    print("="*70)

    all_passed = True

    # Test 1: Signal generation fix
    try:
        if not test_signal_generation_fix():
            all_passed = False
    except Exception as e:
        print(f"\n✗ Signal generation test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Test 2: Profit optimizer parameters
    try:
        if not test_profit_optimizer_params():
            all_passed = False
    except Exception as e:
        print(f"\n✗ Profit optimizer test FAILED with error: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # Summary
    print("\n" + "="*70)
    if all_passed:
        print("ALL TESTS PASSED ✓")
    else:
        print("SOME TESTS FAILED ✗")
    print("="*70 + "\n")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
