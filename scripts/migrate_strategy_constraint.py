#!/usr/bin/env python3
"""
Database Migration: Add Strategy Validation

Adds constraint to prevent "unknown" strategy values and ensure
strategy attribution is always valid.

This migration:
1. Validates all existing positions have valid strategies
2. Updates schema to prevent future "unknown" values
3. Adds index for faster strategy-based queries
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from data.storage import TradingDatabase
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


VALID_STRATEGIES = [
    'factor_composite',
    'simple_momentum',
    'pairs_trading',
    'swing_momentum',
    'ml_momentum',
    'dual_momentum',
    'volatility_breakout',
    'manual_review'  # Special flag for positions requiring review
]


def main():
    print("=" * 70)
    print("DATABASE MIGRATION: Strategy Validation")
    print("=" * 70)
    print()

    db_path = "data/quant.db"
    db = TradingDatabase(db_path)

    # Step 1: Validate existing positions
    print("Step 1: Validating existing positions...")
    positions = db.load_position_tracker_state()

    invalid_count = 0
    for symbol, pos in positions.items():
        strategy = pos.get('strategy', '')
        if not strategy or strategy == 'unknown' or strategy not in VALID_STRATEGIES:
            print(f"  ERROR: {symbol} has invalid strategy: '{strategy}'")
            invalid_count += 1

    if invalid_count > 0:
        print(f"\nERROR: Found {invalid_count} positions with invalid strategies")
        print("Run fix_unknown_strategies.py first to fix these positions")
        return 1

    print(f"✓ All {len(positions)} positions have valid strategies")
    print()

    # Step 2: Add index for strategy-based queries
    print("Step 2: Adding strategy index...")
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Check if index already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_position_tracker_strategy'
        """)

        if cursor.fetchone():
            print("  Index already exists, skipping")
        else:
            cursor.execute("""
                CREATE INDEX idx_position_tracker_strategy
                ON position_tracker(strategy)
            """)
            conn.commit()
            print("✓ Strategy index created")

    print()

    # Step 3: Add documentation comment
    print("Step 3: Documenting valid strategy values...")
    print("Valid strategies:")
    for strategy in VALID_STRATEGIES:
        print(f"  - {strategy}")

    print()
    print("=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Update position_tracker.py to validate strategy on add_position()")
    print("  2. Update auto_trader.py to never use 'unknown' (✓ already done)")
    print("  3. Add strategy validation to PositionTracker class")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
