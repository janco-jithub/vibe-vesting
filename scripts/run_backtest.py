#!/usr/bin/env python3
"""
Run strategy backtest.

Usage:
    python -m scripts.run_backtest
    python -m scripts.run_backtest --strategy dual_momentum --start 2015-01-01 --end 2024-12-31
"""

import argparse
import logging
import sys
from datetime import date

from data.storage import TradingDatabase
from strategies.dual_momentum import DualMomentumStrategy
from strategies.simple_momentum import SimpleMomentumStrategy
from strategies.factor_composite import FactorCompositeStrategy
from backtest.engine import BacktestEngine, run_walk_forward
from backtest.metrics import print_metrics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_backtest(
    strategy_name: str = "dual_momentum",
    start_date: str = "2014-01-01",
    end_date: str = "2024-12-31",
    initial_capital: float = 10000.0,
    db_path: str = "data/quant.db",
    walk_forward: bool = False
) -> None:
    """
    Run strategy backtest.

    Args:
        strategy_name: Strategy to backtest
        start_date: Backtest start date
        end_date: Backtest end date
        initial_capital: Starting capital
        db_path: Path to database with historical data
        walk_forward: Run walk-forward analysis instead of single backtest
    """
    # Initialize database
    db = TradingDatabase(db_path)

    # Initialize strategy
    if strategy_name == "dual_momentum":
        strategy = DualMomentumStrategy()
    elif strategy_name == "simple_momentum":
        strategy = SimpleMomentumStrategy()
    elif strategy_name == "factor_composite":
        strategy = FactorCompositeStrategy()
    else:
        raise ValueError(f"Unknown strategy: {strategy_name}")

    # Load data
    logger.info(f"Loading data for {strategy.universe}...")
    data = db.get_multiple_symbols(strategy.universe)

    # Check data availability
    for symbol in strategy.universe:
        if symbol not in data or data[symbol].empty:
            logger.error(f"No data for {symbol}. Run download_historical.py first.")
            sys.exit(1)

        logger.info(f"  {symbol}: {len(data[symbol])} bars "
                   f"({data[symbol].index.min().date()} to {data[symbol].index.max().date()})")

    if walk_forward:
        # Run walk-forward analysis
        logger.info("\nRunning walk-forward analysis...")
        results = run_walk_forward(
            strategy=strategy,
            data=data,
            train_years=5,
            test_years=1,
            step_months=12
        )

        print("\n" + "=" * 60)
        print("Walk-Forward Analysis Results")
        print("=" * 60)

        for i, result in enumerate(results):
            print(f"\nPeriod {i + 1}: {result.start_date} to {result.end_date}")
            print(f"  Return: {result.metrics.total_return:.2%}")
            print(f"  Sharpe: {result.metrics.sharpe_ratio:.2f}")
            print(f"  Max DD: {result.metrics.max_drawdown:.2%}")

        # Aggregate statistics
        avg_return = sum(r.metrics.total_return for r in results) / len(results)
        avg_sharpe = sum(r.metrics.sharpe_ratio for r in results) / len(results)
        worst_dd = min(r.metrics.max_drawdown for r in results)

        print("\n" + "-" * 60)
        print("Aggregate Statistics:")
        print(f"  Avg Period Return: {avg_return:.2%}")
        print(f"  Avg Sharpe Ratio:  {avg_sharpe:.2f}")
        print(f"  Worst Max DD:      {worst_dd:.2%}")
        print("=" * 60)

    else:
        # Single backtest
        params = strategy.get_backtest_params()
        params.start_date = start_date
        params.end_date = end_date
        params.initial_capital = initial_capital

        logger.info(f"\nRunning backtest: {start_date} to {end_date}")
        logger.info(f"Initial capital: ${initial_capital:,.2f}")

        engine = BacktestEngine(strategy, data, params)
        result = engine.run()

        # Print results
        print(print_metrics(result.metrics, f"{strategy.name} Backtest Results"))

        print("\nTrade Summary:")
        print(f"  Total Trades:    {result.trade_count}")
        print(f"  Total Commissions: ${result.total_commissions:,.2f}")
        print(f"  Total Slippage:    ${result.total_slippage:,.2f}")

        print(f"\nEquity:")
        print(f"  Initial: ${result.initial_capital:,.2f}")
        print(f"  Final:   ${result.final_equity:,.2f}")
        print(f"  P&L:     ${result.final_equity - result.initial_capital:,.2f}")

        # Save equity curve to CSV
        equity_file = "logs/equity_curve.csv"
        result.equity_curve.to_csv(equity_file)
        logger.info(f"Equity curve saved to {equity_file}")

        # Check validation criteria
        print("\n" + "=" * 50)
        print("Validation Criteria")
        print("=" * 50)

        criteria = [
            ("Sharpe Ratio > 1.0", result.metrics.sharpe_ratio > 1.0, f"{result.metrics.sharpe_ratio:.2f}"),
            ("Max Drawdown < 20%", result.metrics.max_drawdown > -0.20, f"{result.metrics.max_drawdown:.2%}"),
            ("Win Rate > 50%", result.metrics.win_rate > 0.50, f"{result.metrics.win_rate:.2%}"),
        ]

        all_passed = True
        for name, passed, value in criteria:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}: {value}")
            if not passed:
                all_passed = False

        print("=" * 50)
        if all_passed:
            print("All validation criteria PASSED")
        else:
            print("Some validation criteria FAILED")


def main():
    parser = argparse.ArgumentParser(description="Run strategy backtest")
    parser.add_argument(
        "--strategy",
        type=str,
        default="dual_momentum",
        help="Strategy to backtest (default: dual_momentum)"
    )
    parser.add_argument(
        "--start",
        type=str,
        default="2014-01-01",
        help="Start date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--end",
        type=str,
        default="2024-12-31",
        help="End date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=10000.0,
        help="Initial capital (default: 10000)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/quant.db",
        help="Path to database"
    )
    parser.add_argument(
        "--walk-forward",
        action="store_true",
        help="Run walk-forward analysis"
    )

    args = parser.parse_args()

    try:
        run_backtest(
            strategy_name=args.strategy,
            start_date=args.start,
            end_date=args.end,
            initial_capital=args.capital,
            db_path=args.db,
            walk_forward=args.walk_forward
        )
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise


if __name__ == "__main__":
    main()
