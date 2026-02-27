"""
Fast historical data backfill using Alpaca API.

Uses Alpaca's batch capability (100 symbols/request) at 200 calls/min
instead of Polygon (1 symbol/request at 5 calls/min).

Usage:
    python -m scripts.backfill_historical --years 10
    python -m scripts.backfill_historical --symbols SPY,QQQ --years 5
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from typing import List

from data.alpaca_data_client import AlpacaDataClient
from data.storage import TradingDatabase

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# All symbols needed for backtesting all strategies
ALL_SYMBOLS = [
    # Core ETFs (dual_momentum, simple_momentum)
    "SPY", "QQQ", "IWM", "TLT",
    # Sector ETFs
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY",
    # Thematic ETFs
    "ARKK", "SOXX", "GLD", "EFA", "EEM", "AGG", "VEA",
    # Leveraged ETFs
    "TQQQ", "SOXL", "UPRO",
    # Individual stocks (simple_momentum, factor_composite)
    "NVDA", "TSLA", "AAPL", "MSFT", "AMD", "AMZN", "GOOGL", "META", "JPM",
]


def backfill(symbols: List[str], years: int, force: bool = False):
    """Download full historical data using Alpaca API."""
    client = AlpacaDataClient()
    db = TradingDatabase()

    end_date = date.today()
    start_date = end_date - timedelta(days=years * 365)

    logger.info(f"Backfilling {len(symbols)} symbols from {start_date} to {end_date}")

    # Process in batches of 25 (conservative for reliability)
    batch_size = 25
    total_bars = 0

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        logger.info(f"Batch {i // batch_size + 1}: {', '.join(batch)}")

        try:
            # Fetch batch from Alpaca
            results = client.get_multiple_symbols(
                symbols=batch,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat()
            )

            # Store results (INSERT OR REPLACE handles duplicates)
            for symbol, bars in results.items():
                if bars:
                    db.insert_daily_bars(bars)
                    total_bars += len(bars)
                    date_range = f"{bars[0]['date']} to {bars[-1]['date']}" if bars else "N/A"
                    logger.info(f"  {symbol}: {len(bars)} bars ({date_range})")
                else:
                    logger.warning(f"  {symbol}: No data returned")

        except Exception as e:
            logger.error(f"Batch failed: {e}")
            # Fall back to individual downloads
            for symbol in batch:
                try:
                    bars = client.get_daily_bars(
                        symbol=symbol,
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat()
                    )
                    if bars:
                        db.insert_daily_bars(bars)
                        total_bars += len(bars)
                        logger.info(f"  {symbol}: {len(bars)} bars (individual)")
                except Exception as e2:
                    logger.error(f"  {symbol}: Failed - {e2}")

    logger.info(f"\nBackfill complete: {total_bars} total bars downloaded for {len(symbols)} symbols")

    # Validate
    logger.info("\nValidation:")
    for symbol in symbols:
        validation = db.validate_data(symbol)
        bar_count = validation.get('row_count', 0)
        issues = validation.get('issues', [])
        if issues:
            logger.warning(f"  {symbol}: {bar_count} bars - ISSUES: {issues}")
        else:
            logger.info(f"  {symbol}: {bar_count} bars - OK")


def main():
    parser = argparse.ArgumentParser(description="Fast historical data backfill using Alpaca API")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated symbols (default: all needed for strategies)")
    parser.add_argument("--years", type=int, default=10, help="Years of history (default: 10)")
    parser.add_argument("--force", action="store_true", help="Force re-download even if data exists")
    args = parser.parse_args()

    symbols = args.symbols.split(",") if args.symbols else ALL_SYMBOLS

    backfill(symbols, args.years, args.force)


if __name__ == "__main__":
    main()
