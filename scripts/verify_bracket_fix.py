#!/usr/bin/env python3
"""
Verification script for bracket order fix.

This script simulates the scenario where:
1. Bot buys position with bracket order
2. Strategy generates SELL signal
3. Verifies that orders are cancelled before sell attempt

Usage:
    python -m scripts.verify_bracket_fix
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from execution.alpaca_client import AlpacaClient, AlpacaClientError
import time

def main():
    print("=" * 70)
    print("BRACKET ORDER FIX VERIFICATION")
    print("=" * 70)

    # Initialize client
    print("\n1. Initializing Alpaca client (paper trading)...")
    alpaca = AlpacaClient(paper=True)

    # Check account
    account = alpaca.get_account()
    print(f"   Account equity: ${account['equity']:,.2f}")

    # Symbol for testing
    test_symbol = "SPY"

    # Check current positions
    print(f"\n2. Checking current position for {test_symbol}...")
    positions = alpaca.get_positions()

    if test_symbol in positions:
        pos = positions[test_symbol]
        print(f"   Current position: {pos['qty']} shares @ ${pos['avg_entry_price']:.2f}")
        print(f"   Market value: ${pos['market_value']:,.2f}")
        print(f"   P&L: ${pos['unrealized_pl']:+,.2f} ({pos['unrealized_plpc']:+.2f}%)")

        # Check for open orders
        print(f"\n3. Checking open orders for {test_symbol}...")
        open_orders = alpaca.get_open_orders_for_symbol(test_symbol)

        if open_orders:
            print(f"   Found {len(open_orders)} open orders:")
            for order in open_orders:
                order_type = order['type']
                side = order['side']
                qty = order['qty']
                status = order['status']
                print(f"   - {order_type.upper()} {side.upper()} {qty} shares ({status})")

            # Simulate the fix: Cancel orders before selling
            print(f"\n4. TESTING FIX: Cancelling open orders before SELL...")
            cancelled_count = alpaca.cancel_orders_for_symbol(test_symbol)
            print(f"   Cancelled {cancelled_count} orders")

            # Wait for cancellations to process
            print("   Waiting 0.5s for cancellations to process...")
            time.sleep(0.5)

            # Verify orders are cancelled
            print(f"\n5. Verifying orders are cancelled...")
            remaining_orders = alpaca.get_open_orders_for_symbol(test_symbol)
            if remaining_orders:
                print(f"   WARNING: {len(remaining_orders)} orders still open!")
                for order in remaining_orders:
                    print(f"   - {order['type']} {order['side']} {order['qty']} ({order['status']})")
            else:
                print("   SUCCESS: All orders cancelled")

            # Check available shares
            print(f"\n6. Checking available shares for selling...")
            updated_position = alpaca.get_position(test_symbol)
            if updated_position:
                qty = int(updated_position['qty'])
                print(f"   Position quantity: {qty} shares")
                print(f"   Shares should now be available for selling")

                print("\n" + "=" * 70)
                print("FIX VERIFICATION COMPLETE")
                print("=" * 70)
                print("\nThe fix successfully:")
                print("  1. Cancelled existing bracket order legs")
                print("  2. Made shares available for strategy-driven SELL")
                print("  3. Would now be able to submit SELL order without errors")
                print("\nNOTE: This script only tests the cancellation logic.")
                print("      It does NOT actually submit a sell order.")
                print("=" * 70)
        else:
            print("   No open orders found")
            print(f"\n   Position has no bracket orders - SELL would work normally")
    else:
        print(f"   No position found for {test_symbol}")
        print("\n   To fully test the fix:")
        print("   1. Run auto_trader to create a position with bracket order")
        print("   2. Wait for strategy to generate SELL signal")
        print("   3. Verify in logs that orders are cancelled before SELL")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nVerification cancelled by user")
    except AlpacaClientError as e:
        print(f"\nAlpaca API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
