#!/usr/bin/env python3
"""
Fix Unknown Strategy Attributions

This script retroactively fixes positions that have "unknown" strategy attribution
by matching symbols to strategy universes.

Usage:
    python -m scripts.fix_unknown_strategies
    python -m scripts.fix_unknown_strategies --dry-run  # Preview changes only
"""

import argparse
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from data.storage import TradingDatabase
from strategies.dual_momentum import DualMomentumStrategy
from strategies.swing_momentum import SwingMomentumStrategy
from strategies.ml_momentum import MLMomentumStrategy
from strategies.pairs_trading import PairsTradingStrategy
from strategies.volatility_breakout import VolatilityBreakoutStrategy
from strategies.simple_momentum import SimpleMomentumStrategy
from strategies.factor_composite import FactorCompositeStrategy


def match_symbol_to_strategy(symbol: str, strategies: dict) -> str:
    """
    Match a symbol to its most likely strategy based on universe membership.

    Args:
        symbol: Symbol ticker
        strategies: Dict of strategy_name -> strategy instance

    Returns:
        Strategy name or "manual_review" if no match found
    """
    matching_strategies = []

    for strat_name, strategy in strategies.items():
        if symbol in strategy.universe:
            matching_strategies.append(strat_name)

    if len(matching_strategies) == 0:
        print(f"  WARNING: {symbol} not found in any strategy universe")
        return "manual_review"
    elif len(matching_strategies) == 1:
        return matching_strategies[0]
    else:
        # Multiple strategies - use priority order
        priority_order = [
            "factor_composite",
            "simple_momentum",
            "pairs_trading",
            "swing_momentum",
            "ml_momentum",
            "dual_momentum",
            "volatility_breakout"
        ]

        for priority_strat in priority_order:
            if priority_strat in matching_strategies:
                print(f"  INFO: {symbol} matches multiple strategies {matching_strategies}, using priority: {priority_strat}")
                return priority_strat

        return matching_strategies[0]


def main():
    parser = argparse.ArgumentParser(description="Fix unknown strategy attributions")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without updating database"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/quant.db",
        help="Path to database"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("FIX UNKNOWN STRATEGY ATTRIBUTIONS")
    print("=" * 70)
    print()

    # Initialize database
    db = TradingDatabase(args.db)

    # Load all strategies to get their universes
    print("Loading strategy universes...")
    strategies = {
        "factor_composite": FactorCompositeStrategy(),
        "simple_momentum": SimpleMomentumStrategy(),
        "pairs_trading": PairsTradingStrategy(),
        "swing_momentum": SwingMomentumStrategy(),
        "ml_momentum": MLMomentumStrategy(),
        "dual_momentum": DualMomentumStrategy(),
        "volatility_breakout": VolatilityBreakoutStrategy(),
    }

    print(f"Loaded {len(strategies)} strategies")
    print()

    # Load position tracker state
    print("Loading position tracker state from database...")
    positions = db.load_position_tracker_state()
    print(f"Found {len(positions)} positions in database")
    print()

    if not positions:
        print("No positions found. Nothing to fix.")
        return

    # Find positions with "unknown" strategy
    unknown_positions = {
        symbol: pos for symbol, pos in positions.items()
        if pos.get('strategy') == 'unknown' or pos.get('strategy') is None or pos.get('strategy') == ''
    }

    if not unknown_positions:
        print("No positions with 'unknown' strategy found. All good!")
        return

    print(f"Found {len(unknown_positions)} positions with 'unknown' strategy:")
    for symbol in unknown_positions.keys():
        print(f"  - {symbol}")
    print()

    # Match each symbol to a strategy
    print("Matching symbols to strategies...")
    print()

    fixes = {}
    for symbol, pos_data in unknown_positions.items():
        matched_strategy = match_symbol_to_strategy(symbol, strategies)
        fixes[symbol] = matched_strategy
        print(f"  {symbol:6s} -> {matched_strategy}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    for symbol, new_strategy in fixes.items():
        old_strategy = unknown_positions[symbol].get('strategy', 'unknown')
        print(f"  {symbol:6s}: '{old_strategy}' -> '{new_strategy}'")

    print()

    # Count manual review cases
    manual_review_count = sum(1 for s in fixes.values() if s == "manual_review")
    if manual_review_count > 0:
        print(f"WARNING: {manual_review_count} position(s) require manual review")
        print()

    if args.dry_run:
        print("DRY RUN: No changes made to database")
        print("Run without --dry-run to apply fixes")
    else:
        print("Applying fixes to database...")

        # Update database
        for symbol, new_strategy in fixes.items():
            # Update the strategy field
            positions[symbol]['strategy'] = new_strategy

        # Save back to database
        db.save_position_tracker_state(positions)

        print("✓ Database updated successfully")
        print()
        print("Next steps:")
        print("  1. Restart auto_trader to load updated positions")
        print("  2. Verify positions show correct strategy attribution")
        if manual_review_count > 0:
            print("  3. Manually review positions flagged as 'manual_review'")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
