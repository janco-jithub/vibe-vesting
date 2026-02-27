#!/usr/bin/env python3
"""
Comprehensive Backtest Runner

Runs backtests on all available strategies with:
- Full performance metrics
- Strategy validation
- Regime analysis
- Parameter sensitivity
- Capital allocation recommendations

Usage:
    python scripts/run_comprehensive_backtest.py [--start-date YYYY-MM-DD] [--end-date YYYY-MM-DD]
"""

import sys
import os
from pathlib import Path
import argparse
import logging
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np

from data.storage import TradingDatabase
from data.alpaca_data_client import AlpacaDataClient
from backtest.runner import BacktestRunner
from strategies.simple_momentum import SimpleMomentumStrategy
from strategies.long_short_momentum import LongShortMomentumStrategy
from strategies.dual_momentum import DualMomentumStrategy
from strategies.swing_momentum import SwingMomentumStrategy
from strategies.institutional_momentum import InstitutionalMomentumStrategy
from strategies.volatility_breakout import VolatilityBreakoutStrategy
# from strategies.pairs_trading import PairsTradingStrategy
# from strategies.ml_momentum import MLMomentumStrategy
# from strategies.factor_composite import FactorCompositeStrategy

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)


def ensure_data_available(
    db: TradingDatabase,
    alpaca_client: AlpacaDataClient,
    symbols: list,
    start_date: str,
    end_date: str
):
    """
    Ensure all required data is available in database.

    Args:
        db: Database instance
        alpaca_client: Data client
        symbols: List of symbols needed
        start_date: Start date string
        end_date: End date string
    """
    logger.info("Checking data availability...")

    missing_symbols = []
    insufficient_symbols = []

    for symbol in symbols:
        df = db.get_daily_bars(symbol, start_date, end_date)

        if df is None or len(df) == 0:
            missing_symbols.append(symbol)
        elif len(df) < 250:  # Need at least ~1 year
            insufficient_symbols.append((symbol, len(df)))

    if missing_symbols or insufficient_symbols:
        logger.warning(
            f"Missing data for {len(missing_symbols)} symbols, "
            f"insufficient data for {len(insufficient_symbols)} symbols"
        )

        # Fetch missing data
        if missing_symbols:
            logger.info(f"Fetching data for {len(missing_symbols)} symbols from Alpaca...")
            for symbol in missing_symbols:
                try:
                    logger.info(f"Fetching {symbol}...")
                    alpaca_client.fetch_and_store_daily_bars(
                        symbol=symbol,
                        start_date=start_date,
                        end_date=end_date
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch {symbol}: {e}")

        # Try to fetch more data for insufficient symbols
        if insufficient_symbols:
            logger.info(f"Fetching more historical data for {len(insufficient_symbols)} symbols...")
            for symbol, current_bars in insufficient_symbols:
                try:
                    # Fetch from earlier date
                    earlier_start = (
                        datetime.strptime(start_date, '%Y-%m-%d') - timedelta(days=730)
                    ).strftime('%Y-%m-%d')

                    logger.info(f"Fetching {symbol} from {earlier_start}...")
                    alpaca_client.fetch_and_store_daily_bars(
                        symbol=symbol,
                        start_date=earlier_start,
                        end_date=end_date
                    )
                except Exception as e:
                    logger.error(f"Failed to fetch more data for {symbol}: {e}")

    logger.info("Data availability check complete")


def initialize_strategies():
    """
    Initialize all available strategies for testing.

    Returns:
        List of strategy instances
    """
    strategies = []

    # 1. Simple Momentum (current live strategy)
    logger.info("Initializing SimpleMomentumStrategy...")
    strategies.append(SimpleMomentumStrategy(
        sma_period=100,
        momentum_period=63,
        max_positions=3,
        position_size_pct=0.20,
        name="simple_momentum"
    ))

    # 2. Long/Short Momentum
    logger.info("Initializing LongShortMomentumStrategy...")
    ls_universe = [
        'QQQ', 'SPY', 'IWM', 'XLK', 'XLF', 'XLE', 'XLY', 'XLP',
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'JPM'
    ]
    strategies.append(LongShortMomentumStrategy(
        universe=ls_universe,
        lookback_months=12,
        skip_month=True,
        enable_shorting=False,  # Disable shorting for basic backtest
        long_positions=10,
        short_positions=0
    ))

    # 3. Dual Momentum
    logger.info("Initializing DualMomentumStrategy...")
    strategies.append(DualMomentumStrategy(
        lookback_days=126,
        skip_days=10,
        name="dual_momentum"
    ))

    # 4. Swing Momentum
    logger.info("Initializing SwingMomentumStrategy...")
    strategies.append(SwingMomentumStrategy(
        rsi_period=14,
        short_ma=50,
        long_ma=200,
        momentum_period=126,
        name="swing_momentum"
    ))

    # 5. Institutional Momentum
    logger.info("Initializing InstitutionalMomentumStrategy...")
    strategies.append(InstitutionalMomentumStrategy(
        momentum_lookback=252,
        trend_filter_days=200,
        max_positions=5,
        name="institutional_momentum"
    ))

    # 6. Volatility Breakout
    logger.info("Initializing VolatilityBreakoutStrategy...")
    strategies.append(VolatilityBreakoutStrategy(
        entry_lookback=20,
        exit_lookback=10,
        atr_period=14,
        max_positions=3,
        use_etfs_only=True,
        name="volatility_breakout"
    ))

    # 7. Factor Composite - SKIPPED (complex requirements)
    # 8. ML Momentum - SKIPPED (requires training)
    # 9. Pairs Trading - SKIPPED (requires pair selection)

    logger.info(f"Initialized {len(strategies)} strategies")
    return strategies


def main():
    parser = argparse.ArgumentParser(description='Run comprehensive backtests')
    parser.add_argument(
        '--start-date',
        default='2024-01-01',
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        default=datetime.now().strftime('%Y-%m-%d'),
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--no-validation',
        action='store_true',
        help='Skip strategy validation (faster)'
    )
    parser.add_argument(
        '--no-fetch',
        action='store_true',
        help='Skip data fetching (use existing data only)'
    )
    parser.add_argument(
        '--capital',
        type=float,
        default=100000.0,
        help='Total capital for allocation recommendation'
    )

    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("COMPREHENSIVE BACKTEST RUNNER")
    print("=" * 80)
    print(f"Period: {args.start_date} to {args.end_date}")
    print(f"Validation: {'Disabled' if args.no_validation else 'Enabled'}")
    print(f"Capital: ${args.capital:,.0f}")
    print("=" * 80 + "\n")

    # Initialize components
    logger.info("Initializing components...")
    db = TradingDatabase()
    alpaca_client = AlpacaDataClient()
    runner = BacktestRunner(db=db, output_dir="backtest_results")

    # Initialize strategies
    strategies = initialize_strategies()

    # Collect all symbols needed
    all_symbols = set(['SPY'])  # Always need SPY as benchmark
    for strategy in strategies:
        all_symbols.update(strategy.universe)

    logger.info(f"Total symbols needed: {len(all_symbols)}")

    # Ensure data is available
    if not args.no_fetch:
        ensure_data_available(
            db=db,
            alpaca_client=alpaca_client,
            symbols=list(all_symbols),
            start_date=args.start_date,
            end_date=args.end_date
        )
    else:
        logger.info("Skipping data fetch (--no-fetch)")

    # Load all data once
    logger.info("Loading historical data...")
    try:
        data = runner.load_data_for_strategies(
            strategies=strategies,
            start_date=args.start_date,
            end_date=args.end_date
        )
        logger.info(f"Loaded data for {len(data)} symbols")
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        return 1

    # Run backtests
    logger.info("Starting backtests...")
    print("\n" + "=" * 80)
    print("RUNNING BACKTESTS")
    print("=" * 80 + "\n")

    try:
        comparison_df = runner.run_multiple_strategies(
            strategies=strategies,
            data=data,
            validate=not args.no_validation,
            save_results=True
        )
    except Exception as e:
        logger.error(f"Failed to run backtests: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Generate visualizations
    logger.info("Generating visualizations...")
    try:
        runner.generate_visualizations()
    except Exception as e:
        logger.warning(f"Failed to generate visualizations: {e}")

    # Generate capital allocation recommendations
    logger.info("Calculating optimal capital allocation...")
    print("\n")
    try:
        allocation_df = runner.recommend_capital_allocation(
            total_capital=args.capital,
            min_sharpe=1.0,
            max_strategies=3
        )

        # Save allocation
        if not allocation_df.empty:
            allocation_path = runner.output_dir / f"capital_allocation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            allocation_df.to_csv(allocation_path, index=False)
            logger.info(f"Saved allocation to {allocation_path}")
    except Exception as e:
        logger.warning(f"Failed to generate allocation: {e}")

    # Final summary
    print("\n" + "=" * 80)
    print("BACKTEST SUMMARY")
    print("=" * 80)
    print(f"Strategies Tested: {len(runner.backtest_results)}")
    print(f"Validated: {len(runner.validation_results)}")

    if runner.backtest_results:
        best_strategy = max(
            runner.backtest_results.items(),
            key=lambda x: x[1].metrics.sharpe_ratio
        )
        print(f"\nBest Strategy (by Sharpe): {best_strategy[0]}")
        print(f"  Sharpe Ratio: {best_strategy[1].metrics.sharpe_ratio:.2f}")
        print(f"  Total Return: {best_strategy[1].metrics.total_return:.1%}")
        print(f"  Max Drawdown: {best_strategy[1].metrics.max_drawdown:.1%}")

    print(f"\nResults saved to: {runner.output_dir}")
    print("=" * 80 + "\n")

    logger.info("Backtest run complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
