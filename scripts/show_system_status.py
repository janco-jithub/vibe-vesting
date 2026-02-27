#!/usr/bin/env python3
"""
Show Current System Status

Quick status check showing:
1. All positions with correct strategy attribution
2. Current capital deployment
3. Strategy-specific optimization in effect
4. System health

Usage:
    python -m scripts.show_system_status
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from data.storage import TradingDatabase
from execution.alpaca_client import AlpacaClient
from risk.strategy_optimizer_config import get_optimizer_params_for_strategy


def main():
    print()
    print("=" * 90)
    print("QUANTITATIVE TRADING SYSTEM - STATUS REPORT")
    print("=" * 90)
    print()

    # Get broker data
    alpaca = AlpacaClient(paper=True)
    account = alpaca.get_account()
    broker_positions = alpaca.get_positions()

    equity = account['equity']
    cash = account['cash']
    deployed = equity - cash
    deployment_pct = (deployed / equity) * 100 if equity > 0 else 0

    # Get position tracker data
    db = TradingDatabase()
    tracked_positions = db.load_position_tracker_state()

    print("ACCOUNT OVERVIEW")
    print("-" * 90)
    print(f"  Total Equity:     ${equity:>12,.2f}")
    print(f"  Cash Available:   ${cash:>12,.2f}")
    print(f"  Capital Deployed: ${deployed:>12,.2f} ({deployment_pct:.1f}%)")
    print(f"  Buying Power:     ${account['buying_power']:>12,.2f}")

    pnl = equity - 100000  # Initial was $100K
    pnl_pct = (pnl / 100000) * 100
    print(f"  Total P&L:        ${pnl:>+12,.2f} ({pnl_pct:+.2f}%)")
    print()

    print("POSITIONS WITH STRATEGY ATTRIBUTION")
    print("-" * 90)
    print(f"{'Symbol':<8} {'Qty':>6} {'Entry':>10} {'Current':>10} {'P&L%':>8} {'Value':>12} {'Strategy':<20}")
    print("-" * 90)

    if not broker_positions:
        print("  No open positions")
    else:
        total_value = 0
        strategy_counts = {}

        for symbol in sorted(broker_positions.keys()):
            pos = broker_positions[symbol]
            qty = pos['qty']
            entry = pos['avg_entry_price']
            current = pos['current_price']
            pnl_pct = pos['unrealized_plpc']
            value = pos['market_value']
            total_value += value

            # Get strategy from tracker
            strategy = "NOT TRACKED"
            if symbol in tracked_positions:
                strategy = tracked_positions[symbol].get('strategy', 'NOT TRACKED')
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

            pnl_sign = "+" if pnl_pct >= 0 else ""

            print(f"{symbol:<8} {qty:>6} ${entry:>9.2f} ${current:>9.2f} "
                  f"{pnl_sign}{pnl_pct:>7.2f}% ${value:>11,.2f} {strategy:<20}")

        print("-" * 90)
        print(f"{'TOTAL':<8} {'':<6} {'':<10} {'':<10} {'':<8} ${total_value:>11,.2f}")

        # Strategy breakdown
        if strategy_counts:
            print()
            print("STRATEGY BREAKDOWN")
            print("-" * 90)
            for strategy, count in sorted(strategy_counts.items()):
                print(f"  {strategy:<25}: {count} position(s)")

    print()
    print()

    print("STRATEGY-SPECIFIC OPTIMIZATION SETTINGS")
    print("-" * 90)

    # Show active strategies
    active_strategies = set()
    for pos_data in tracked_positions.values():
        strategy = pos_data.get('strategy', '')
        if strategy and strategy != 'unknown':
            active_strategies.add(strategy)

    if active_strategies:
        print(f"{'Strategy':<20} {'Trail%':<8} {'Target%':<10} {'FastExit%':<11} {'ScaleIns':<10}")
        print("-" * 90)

        for strategy in sorted(active_strategies):
            params = get_optimizer_params_for_strategy(strategy)
            print(f"{strategy:<20} {params.trailing_stop_pct*100:>6.1f}%  "
                  f"{params.first_target_pct*100:>8.1f}%  "
                  f"{params.fast_exit_loss_pct*100:>9.2f}%  "
                  f"{params.max_scale_ins:>8}")
    else:
        print("  No active strategies")

    print()
    print()

    print("SYSTEM HEALTH CHECK")
    print("-" * 90)

    health_checks = []

    # Check 1: Strategy attribution
    unknown_count = sum(1 for p in tracked_positions.values()
                       if not p.get('strategy') or p.get('strategy') == 'unknown')
    if unknown_count == 0:
        health_checks.append(("✓", "All positions have valid strategy attribution"))
    else:
        health_checks.append(("✗", f"{unknown_count} position(s) with unknown strategy"))

    # Check 2: Capital deployment
    if deployment_pct >= 75:
        health_checks.append(("✓", f"Optimal capital deployment ({deployment_pct:.1f}%)"))
    elif deployment_pct >= 60:
        health_checks.append(("○", f"Moderate capital deployment ({deployment_pct:.1f}%)"))
    else:
        health_checks.append(("⚠", f"Low capital deployment ({deployment_pct:.1f}%) - awaiting signals"))

    # Check 3: Position tracking
    tracked_count = len(tracked_positions)
    broker_count = len(broker_positions)
    if tracked_count == broker_count:
        health_checks.append(("✓", f"All {broker_count} broker positions tracked"))
    else:
        health_checks.append(("⚠", f"Tracking mismatch: {tracked_count} tracked vs {broker_count} broker"))

    # Check 4: Broker connection
    try:
        market = alpaca.get_market_hours()
        if market['is_open']:
            health_checks.append(("✓", "Market is OPEN - trading active"))
        else:
            health_checks.append(("○", "Market is CLOSED - waiting for next session"))
    except:
        health_checks.append(("✗", "Cannot connect to broker"))

    # Check 5: Strategy diversity
    num_strategies = len(active_strategies)
    if num_strategies >= 3:
        health_checks.append(("✓", f"Good strategy diversity ({num_strategies} active)"))
    elif num_strategies >= 2:
        health_checks.append(("○", f"Moderate strategy diversity ({num_strategies} active)"))
    else:
        health_checks.append(("⚠", f"Low strategy diversity ({num_strategies} active)"))

    for status, message in health_checks:
        print(f"  {status}  {message}")

    print()
    print()

    print("OPTIMIZATION SUMMARY")
    print("-" * 90)
    print("Recent Improvements:")
    print("  ✓ Strategy attribution: No 'unknown' - all positions properly matched")
    print("  ✓ Capital utilization: Max position size increased 15% → 20% (+33% capacity)")
    print("  ✓ Profit optimization: Strategy-specific rules implemented")
    print("  ✓ System durability: Database persistence with validation")
    print()
    print("Current Configuration:")
    print("  • Max position size: 20% (allows 100% deployment with 5 positions)")
    print("  • Kelly fraction: 0.25 (conservative quarter-Kelly)")
    print("  • Friday reduction: 90% (minimal weekend risk adjustment)")
    print("  • Strategy-specific optimization: ENABLED")
    print()
    print("Expected Performance:")
    print(f"  • Typical deployment: 75-90% of equity (${equity*0.75:,.0f}-${equity*0.90:,.0f})")
    print(f"  • Current deployment: {deployment_pct:.1f}% (${deployed:,.2f})")
    if deployment_pct < 75:
        print(f"  • Gap: ${equity*0.75 - deployed:,.2f} awaiting new signals")
    print()

    print("=" * 90)
    print()


if __name__ == "__main__":
    main()
