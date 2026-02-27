#!/usr/bin/env python3
"""
Download historical market data from Polygon.io.

Usage:
    python -m scripts.download_historical
    python -m scripts.download_historical --symbols SPY,QQQ,TLT --years 10
"""

import argparse
import logging
import sys
from datetime import date, timedelta
from typing import List

from data.polygon_client import RateLimitedPolygonClient, PolygonClientError
from data.storage import TradingDatabase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


DEFAULT_SYMBOLS = ["SPY", "QQQ", "TLT"]
DEFAULT_YEARS = 10


def download_historical_data(
    symbols: List[str],
    years: int,
    db_path: str = "data/quant.db"
) -> dict:
    """
    Download historical data for specified symbols.

    Args:
        symbols: List of ticker symbols
        years: Number of years of history to download
        db_path: Path to SQLite database

    Returns:
        Dict with download statistics
    """
    # Initialize clients
    polygon = RateLimitedPolygonClient()
    db = TradingDatabase(db_path)

    # Calculate date range
    end_date = date.today()
    start_date = end_date - timedelta(days=years * 365)

    stats = {
        "symbols": symbols,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "downloaded": {},
        "errors": []
    }

    logger.info(f"Downloading data for {symbols} from {start_date} to {end_date}")

    for symbol in symbols:
        logger.info(f"Downloading {symbol}...")

        try:
            # Check if we already have recent data
            latest_date = db.get_latest_date(symbol)
            if latest_date:
                # Only download from last date + 1
                actual_start = latest_date + timedelta(days=1)
                if actual_start >= end_date:
                    logger.info(f"{symbol}: Already up to date")
                    stats["downloaded"][symbol] = {"status": "up_to_date", "bars": 0}
                    continue
            else:
                actual_start = start_date

            # Download from Polygon
            bars = polygon.get_daily_bars(
                symbol=symbol,
                start_date=actual_start.isoformat(),
                end_date=end_date.isoformat()
            )

            if bars:
                # Store in database
                db.insert_daily_bars(bars)

                stats["downloaded"][symbol] = {
                    "status": "success",
                    "bars": len(bars),
                    "start": bars[0]["date"].isoformat() if bars else None,
                    "end": bars[-1]["date"].isoformat() if bars else None
                }

                logger.info(f"{symbol}: Downloaded {len(bars)} bars")
            else:
                stats["downloaded"][symbol] = {"status": "no_data", "bars": 0}
                logger.warning(f"{symbol}: No data returned")

        except PolygonClientError as e:
            logger.error(f"{symbol}: Download failed - {e}")
            stats["errors"].append({"symbol": symbol, "error": str(e)})
            stats["downloaded"][symbol] = {"status": "error", "bars": 0}

    # Validate downloaded data
    logger.info("\nValidating data...")
    for symbol in symbols:
        validation = db.validate_data(symbol)
        if validation.get("issues"):
            logger.warning(f"{symbol}: Validation issues - {validation['issues']}")
        else:
            logger.info(f"{symbol}: Validation passed ({validation.get('row_count', 0)} rows)")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Download historical market data from Polygon.io"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=",".join(DEFAULT_SYMBOLS),
        help=f"Comma-separated list of symbols (default: {','.join(DEFAULT_SYMBOLS)})"
    )
    parser.add_argument(
        "--years",
        type=int,
        default=DEFAULT_YEARS,
        help=f"Years of history to download (default: {DEFAULT_YEARS})"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/quant.db",
        help="Path to SQLite database"
    )

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    try:
        stats = download_historical_data(
            symbols=symbols,
            years=args.years,
            db_path=args.db
        )

        print("\n" + "=" * 50)
        print("Download Summary")
        print("=" * 50)
        print(f"Date range: {stats['start_date']} to {stats['end_date']}")
        print()

        for symbol, info in stats["downloaded"].items():
            status = info["status"]
            bars = info["bars"]
            if status == "success":
                print(f"  {symbol}: {bars:,} bars downloaded")
            elif status == "up_to_date":
                print(f"  {symbol}: Already up to date")
            else:
                print(f"  {symbol}: {status}")

        if stats["errors"]:
            print("\nErrors:")
            for err in stats["errors"]:
                print(f"  {err['symbol']}: {err['error']}")

        print("=" * 50)

    except Exception as e:
        logger.error(f"Download failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
