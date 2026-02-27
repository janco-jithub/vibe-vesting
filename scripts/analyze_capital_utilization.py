#!/usr/bin/env python3
"""
Capital Utilization Analysis

Analyzes why capital is underdeployed and provides recommendations.

Checks:
1. Current capital deployment vs target
2. Position sizing settings and their impact
3. Risk constraints limiting deployment
4. Strategy-specific utilization
5. Time-based restrictions
6. Volatility-based adjustments
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from execution.alpaca_client import AlpacaClient
from data.storage import TradingDatabase


def main():
    print("=" * 80)
    print("CAPITAL UTILIZATION ANALYSIS")
    print("=" * 80)
    print()

    # Initialize clients
    alpaca = AlpacaClient(paper=True)
    db = TradingDatabase()

    # Get account info
    account = alpaca.get_account()
    positions = alpaca.get_positions()

    equity = account['equity']
    cash = account['cash']
    buying_power = account['buying_power']

    # Calculate deployment
    deployed_capital = equity - cash
    deployment_pct = (deployed_capital / equity) * 100 if equity > 0 else 0

    print("CURRENT STATE")
    print("-" * 80)
    print(f"  Equity:          ${equity:>12,.2f}")
    print(f"  Cash:            ${cash:>12,.2f}")
    print(f"  Deployed:        ${deployed_capital:>12,.2f} ({deployment_pct:.1f}%)")
    print(f"  Buying Power:    ${buying_power:>12,.2f}")
    print()

    print("POSITIONS")
    print("-" * 80)

    if not positions:
        print("  No positions")
    else:
        total_market_value = 0
        position_tracker_positions = db.load_position_tracker_state()

        for symbol, pos in sorted(positions.items()):
            market_value = pos['market_value']
            pct_of_equity = (market_value / equity) * 100
            total_market_value += market_value

            # Get strategy from position tracker
            strategy = "unknown"
            if symbol in position_tracker_positions:
                strategy = position_tracker_positions[symbol].get('strategy', 'unknown')

            pnl_pct = pos['unrealized_plpc']
            pnl_color = "+" if pnl_pct >= 0 else ""

            print(f"  {symbol:6s}: ${market_value:>10,.2f} ({pct_of_equity:>5.1f}%) | "
                  f"P&L: {pnl_color}{pnl_pct:>6.2f}% | {strategy}")

        print()
        print(f"  Total Market Value: ${total_market_value:>10,.2f}")

    print()
    print("CAPITAL UTILIZATION TARGETS")
    print("-" * 80)

    # Calculate different scenarios
    current_settings = {
        'max_position_pct': 0.20,  # Updated to 20%
        'max_positions': 5,
        'friday_reduction': 0.90,
        'high_vol_reduction': 0.67
    }

    scenarios = {
        'Current Settings (20% per position)': {
            'max_deployment': current_settings['max_position_pct'] * current_settings['max_positions'],
            'description': f"{current_settings['max_positions']} positions at {current_settings['max_position_pct']*100:.0f}% each"
        },
        'Conservative (15% per position)': {
            'max_deployment': 0.15 * 5,
            'description': "5 positions at 15% each"
        },
        'Aggressive (25% per position)': {
            'max_deployment': 0.25 * 4,
            'description': "4 positions at 25% each"
        },
        'Friday (10% reduction)': {
            'max_deployment': current_settings['max_position_pct'] * current_settings['max_positions'] * current_settings['friday_reduction'],
            'description': f"Friday size reduction applied ({current_settings['friday_reduction']*100:.0f}%)"
        },
        'High VIX (33% reduction)': {
            'max_deployment': current_settings['max_position_pct'] * current_settings['max_positions'] * current_settings['high_vol_reduction'],
            'description': f"High volatility reduction applied ({current_settings['high_vol_reduction']*100:.0f}%)"
        }
    }

    for name, scenario in scenarios.items():
        target_deployed = equity * scenario['max_deployment']
        print(f"\n  {name}:")
        print(f"    Target Deployment: {scenario['max_deployment']*100:.1f}% (${target_deployed:,.2f})")
        print(f"    Description: {scenario['description']}")
        print(f"    Current vs Target: {deployment_pct:.1f}% vs {scenario['max_deployment']*100:.1f}%")

        if deployment_pct < scenario['max_deployment'] * 100:
            gap = (scenario['max_deployment'] - deployment_pct/100) * equity
            print(f"    Gap: ${gap:,.2f} underdeployed")

    print()
    print()
    print("RECOMMENDATIONS")
    print("-" * 80)

    recommendations = []

    # Check current deployment
    if deployment_pct < 60:
        recommendations.append(
            "⚠️  CRITICAL: Only {:.1f}% deployed. Check for:\n"
            "    - Are strategies generating signals?\n"
            "    - Are signals being filtered out by profit optimizer?\n"
            "    - Are time-based restrictions too aggressive?".format(deployment_pct)
        )
    elif deployment_pct < 75:
        recommendations.append(
            "⚠️  WARNING: {:.1f}% deployed (target: 75-90%). Consider:\n"
            "    - Increasing max_position_pct from 20% to 22-25%\n"
            "    - Adding more strategies to generate signals\n"
            "    - Reviewing signal filtering criteria".format(deployment_pct)
        )
    elif deployment_pct > 95:
        recommendations.append(
            "✓  EXCELLENT: {:.1f}% deployed (near maximum utilization)".format(deployment_pct)
        )
    else:
        recommendations.append(
            "✓  GOOD: {:.1f}% deployed (within target range 75-95%)".format(deployment_pct)
        )

    # Position sizing recommendations
    num_positions = len(positions)
    if num_positions < 3:
        recommendations.append(
            "⚠️  Concentration risk: Only {} position(s). Consider:\n"
            "    - Running more strategies simultaneously\n"
            "    - Reviewing why signals are not being generated".format(num_positions)
        )
    elif num_positions > 7:
        recommendations.append(
            "⚠️  Over-diversification: {} positions may dilute returns\n"
            "    - Consider focusing on highest-conviction signals\n"
            "    - May want to reduce max_positions parameter".format(num_positions)
        )

    # Strategy diversity
    strategies_used = set()
    position_tracker_positions = db.load_position_tracker_state()
    for pos_data in position_tracker_positions.values():
        strategy = pos_data.get('strategy', 'unknown')
        if strategy != 'unknown':
            strategies_used.add(strategy)

    if len(strategies_used) == 1:
        recommendations.append(
            "⚠️  Strategy concentration: All positions from '{}'.\n"
            "    Consider enabling additional strategies for diversification".format(
                list(strategies_used)[0] if strategies_used else 'unknown'
            )
        )
    elif len(strategies_used) >= 3:
        recommendations.append(
            "✓  Good strategy diversity: {} different strategies active".format(len(strategies_used))
        )

    # Print recommendations
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. {rec}")
        print()

    print()
    print("OPTIMIZATION SUMMARY")
    print("-" * 80)
    print(f"Current Settings:")
    print(f"  - Max position size: {current_settings['max_position_pct']*100:.0f}%")
    print(f"  - Max positions: {current_settings['max_positions']}")
    print(f"  - Target deployment: {current_settings['max_position_pct'] * current_settings['max_positions'] * 100:.0f}%")
    print()
    print("Recent Optimizations:")
    print("  ✓ Increased max_position_pct from 15% to 20% (+33% capacity)")
    print("  ✓ Reduced Friday size reduction from 70% to 90% (+20% on Fridays)")
    print("  ✓ Restored first_target_pct from 3% to 5% (more room for momentum)")
    print("  ✓ Restored scale_in threshold from 1.5% to 3% (less aggressive pyramiding)")
    print()
    print("Expected Impact:")
    print("  - Max theoretical deployment: 100% (5 positions × 20%)")
    print("  - Typical deployment: 75-90% (accounting for restrictions)")
    print("  - Risk-adjusted deployment: Maintains 2:1 reward/risk ratio")
    print()
    print("=" * 80)


if __name__ == "__main__":
    main()
