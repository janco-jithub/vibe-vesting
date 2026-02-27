"""
Backtest Runner - Orchestrates comprehensive backtesting and reporting.

This module provides high-level functions to:
1. Run backtests on multiple strategies
2. Store results to database
3. Generate comparison reports
4. Recommend optimal capital allocation
"""

import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date
import json

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path

from strategies.base import BaseStrategy
from backtest.engine import BacktestEngine, BacktestResult
from backtest.validator import StrategyValidator, ValidationResult, print_validation_results, compare_strategies
from backtest.metrics import print_metrics
from data.storage import TradingDatabase

logger = logging.getLogger(__name__)


class BacktestRunner:
    """
    Orchestrates comprehensive backtesting workflow.

    Workflow:
    1. Load historical data
    2. Run backtests on multiple strategies
    3. Validate each strategy
    4. Compare results
    5. Generate reports and visualizations
    6. Save to database
    """

    def __init__(
        self,
        db: Optional[TradingDatabase] = None,
        output_dir: str = "backtest_results"
    ):
        """
        Initialize backtest runner.

        Args:
            db: Database instance for storing results
            output_dir: Directory for saving reports and charts
        """
        self.db = db or TradingDatabase()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True, parents=True)

        self.validator = StrategyValidator(
            min_sharpe_threshold=1.0,
            min_calmar_threshold=1.0
        )

        # Results cache
        self.backtest_results: Dict[str, BacktestResult] = {}
        self.validation_results: Dict[str, ValidationResult] = {}

    def load_data_for_strategies(
        self,
        strategies: List[BaseStrategy],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Load historical data for all symbols needed by strategies.

        Args:
            strategies: List of strategies to get symbols from
            start_date: Optional start date (YYYY-MM-DD)
            end_date: Optional end date (YYYY-MM-DD)

        Returns:
            Dict mapping symbol -> DataFrame with OHLCV data
        """
        # Collect all unique symbols
        all_symbols = set()
        for strategy in strategies:
            all_symbols.update(strategy.universe)

        # Always include SPY as benchmark
        all_symbols.add('SPY')

        logger.info(f"Loading data for {len(all_symbols)} symbols")

        # Load from database
        data = {}
        for symbol in all_symbols:
            df = self.db.get_daily_bars(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date
            )

            if df is not None and len(df) > 0:
                data[symbol] = df
                logger.debug(f"Loaded {len(df)} bars for {symbol}")
            else:
                logger.warning(f"No data available for {symbol}")

        if not data:
            raise ValueError("No historical data available. Please fetch data first.")

        return data

    def run_backtest(
        self,
        strategy: BaseStrategy,
        data: Dict[str, pd.DataFrame],
        validate: bool = True,
        save_results: bool = True
    ) -> Tuple[BacktestResult, Optional[ValidationResult]]:
        """
        Run backtest on a single strategy.

        Args:
            strategy: Strategy to test
            data: Market data
            validate: Whether to run validation
            save_results: Whether to save to database

        Returns:
            (backtest_result, validation_result)
        """
        logger.info(f"Running backtest for {strategy.name}")

        # Filter data to only include strategy universe + SPY
        strategy_data = {
            symbol: df for symbol, df in data.items()
            if symbol in strategy.universe or symbol == 'SPY'
        }

        if not strategy_data:
            raise ValueError(f"No data available for {strategy.name} universe")

        # Run backtest
        params = strategy.get_backtest_params()
        engine = BacktestEngine(strategy, strategy_data, params)
        result = engine.run()

        # Store result
        self.backtest_results[strategy.name] = result

        # Print metrics
        print(print_metrics(result.metrics, f"Backtest: {strategy.name}"))

        # Run validation
        validation_result = None
        if validate:
            logger.info(f"Validating {strategy.name}")
            validation_result = self.validator.validate_strategy(
                strategy=strategy,
                data=strategy_data,
                n_simulations=100
            )
            self.validation_results[strategy.name] = validation_result
            print(print_validation_results(validation_result))

        # Save to database
        if save_results:
            self._save_backtest_result(result, validation_result)

        return result, validation_result

    def run_multiple_strategies(
        self,
        strategies: List[BaseStrategy],
        data: Optional[Dict[str, pd.DataFrame]] = None,
        validate: bool = True,
        save_results: bool = True
    ) -> pd.DataFrame:
        """
        Run backtests on multiple strategies.

        Args:
            strategies: List of strategies to test
            data: Optional market data (will load if None)
            validate: Whether to run validation
            save_results: Whether to save to database

        Returns:
            DataFrame comparing all strategies
        """
        logger.info(f"Running backtests for {len(strategies)} strategies")

        # Load data if not provided
        if data is None:
            data = self.load_data_for_strategies(strategies)

        # Run each strategy
        for strategy in strategies:
            try:
                self.run_backtest(strategy, data, validate, save_results)
            except Exception as e:
                logger.error(f"Failed to backtest {strategy.name}: {e}")
                continue

        # Generate comparison
        comparison = self.compare_results()

        # Save comparison
        comparison_path = self.output_dir / f"strategy_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        comparison.to_csv(comparison_path, index=False)
        logger.info(f"Saved comparison to {comparison_path}")

        # Print comparison
        print("\n" + "=" * 120)
        print("STRATEGY COMPARISON")
        print("=" * 120)
        print(comparison.to_string(index=False))
        print("=" * 120 + "\n")

        return comparison

    def compare_results(self) -> pd.DataFrame:
        """
        Compare all backtest results.

        Returns:
            DataFrame with strategy comparison
        """
        data = []

        for name, result in self.backtest_results.items():
            metrics = result.metrics
            validation = self.validation_results.get(name)

            row = {
                'Strategy': name,
                'Total Return': metrics.total_return,
                'CAGR': metrics.cagr,
                'Sharpe Ratio': metrics.sharpe_ratio,
                'Sortino Ratio': metrics.sortino_ratio,
                'Calmar Ratio': metrics.calmar_ratio,
                'Max Drawdown': metrics.max_drawdown,
                'Win Rate': metrics.win_rate,
                'Profit Factor': metrics.profit_factor,
                'Trades': metrics.trade_count,
                'Alpha': metrics.alpha if metrics.alpha else 0.0,
                'Beta': metrics.beta if metrics.beta else 1.0,
                'Robust': validation.is_robust if validation else False,
                'Consistency': validation.consistency_score if validation else 0.0,
                'Overfit Risk': validation.overfitting_probability if validation else 1.0,
            }
            data.append(row)

        df = pd.DataFrame(data)

        # Sort by Sharpe ratio
        df = df.sort_values('Sharpe Ratio', ascending=False)

        return df

    def recommend_capital_allocation(
        self,
        total_capital: float = 100000.0,
        min_sharpe: float = 1.0,
        max_strategies: int = 3
    ) -> pd.DataFrame:
        """
        Recommend capital allocation across strategies.

        Uses risk parity / mean-variance optimization to allocate capital.

        Args:
            total_capital: Total capital to allocate
            min_sharpe: Minimum Sharpe ratio for consideration
            max_strategies: Maximum number of strategies to use

        Returns:
            DataFrame with allocation recommendations
        """
        logger.info("Calculating optimal capital allocation")

        # Filter to robust strategies with good Sharpe
        qualified_strategies = []

        for name, result in self.backtest_results.items():
            validation = self.validation_results.get(name)

            if (
                result.metrics.sharpe_ratio >= min_sharpe and
                validation and
                validation.is_robust
            ):
                qualified_strategies.append((name, result))

        if not qualified_strategies:
            logger.warning("No strategies meet allocation criteria")
            return pd.DataFrame()

        # Sort by Sharpe ratio
        qualified_strategies.sort(
            key=lambda x: x[1].metrics.sharpe_ratio,
            reverse=True
        )

        # Take top N
        selected_strategies = qualified_strategies[:max_strategies]

        # Calculate weights using inverse volatility (risk parity)
        volatilities = [r.metrics.annual_volatility for _, r in selected_strategies]
        inv_vols = [1/v for v in volatilities]
        total_inv_vol = sum(inv_vols)
        weights = [iv / total_inv_vol for iv in inv_vols]

        # Create allocation table
        allocations = []
        for (name, result), weight in zip(selected_strategies, weights):
            allocation = total_capital * weight

            allocations.append({
                'Strategy': name,
                'Weight': weight,
                'Allocation': allocation,
                'Expected_Annual_Return': result.metrics.cagr * allocation,
                'Sharpe_Ratio': result.metrics.sharpe_ratio,
                'Max_Drawdown': result.metrics.max_drawdown,
                'Trades_Per_Year': result.metrics.trade_count / (
                    (result.end_date - result.start_date).days / 365
                )
            })

        df = pd.DataFrame(allocations)

        print("\n" + "=" * 100)
        print(f"RECOMMENDED CAPITAL ALLOCATION (Total: ${total_capital:,.0f})")
        print("=" * 100)
        print(df.to_string(index=False))
        print("=" * 100 + "\n")

        # Calculate portfolio metrics
        portfolio_return = sum(df['Expected_Annual_Return'])
        portfolio_sharpe = np.average(df['Sharpe_Ratio'], weights=df['Weight'])

        print(f"Portfolio Expected Return: ${portfolio_return:,.0f} ({portfolio_return/total_capital:.1%})")
        print(f"Portfolio Sharpe Ratio: {portfolio_sharpe:.2f}")
        print()

        return df

    def generate_visualizations(
        self,
        strategies: Optional[List[str]] = None
    ):
        """
        Generate comparison charts.

        Args:
            strategies: Optional list of strategy names to plot
        """
        if not self.backtest_results:
            logger.warning("No backtest results to visualize")
            return

        strategies = strategies or list(self.backtest_results.keys())

        # Create figure with subplots
        fig, axes = plt.subplots(2, 2, figsize=(16, 12))
        fig.suptitle('Strategy Backtest Comparison', fontsize=16, fontweight='bold')

        # 1. Equity Curves
        ax1 = axes[0, 0]
        for name in strategies:
            if name in self.backtest_results:
                result = self.backtest_results[name]
                equity_normalized = result.equity_curve / result.initial_capital
                ax1.plot(equity_normalized.index, equity_normalized.values, label=name, linewidth=2)

        ax1.set_title('Equity Curves (Normalized)', fontweight='bold')
        ax1.set_xlabel('Date')
        ax1.set_ylabel('Portfolio Value (normalized)')
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # 2. Drawdowns
        ax2 = axes[0, 1]
        for name in strategies:
            if name in self.backtest_results:
                result = self.backtest_results[name]
                ax2.plot(result.drawdown.index, result.drawdown.values * 100, label=name, linewidth=2)

        ax2.set_title('Drawdowns', fontweight='bold')
        ax2.set_xlabel('Date')
        ax2.set_ylabel('Drawdown (%)')
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        # 3. Rolling Sharpe Ratio (252-day)
        ax3 = axes[1, 0]
        for name in strategies:
            if name in self.backtest_results:
                result = self.backtest_results[name]
                rolling_sharpe = (
                    result.returns.rolling(252).mean() /
                    result.returns.rolling(252).std() *
                    np.sqrt(252)
                )
                ax3.plot(rolling_sharpe.index, rolling_sharpe.values, label=name, linewidth=2)

        ax3.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5)
        ax3.set_title('Rolling Sharpe Ratio (1-year)', fontweight='bold')
        ax3.set_xlabel('Date')
        ax3.set_ylabel('Sharpe Ratio')
        ax3.legend()
        ax3.grid(True, alpha=0.3)

        # 4. Return Distribution
        ax4 = axes[1, 1]
        for name in strategies:
            if name in self.backtest_results:
                result = self.backtest_results[name]
                ax4.hist(result.returns * 100, bins=50, alpha=0.5, label=name)

        ax4.set_title('Return Distribution', fontweight='bold')
        ax4.set_xlabel('Daily Return (%)')
        ax4.set_ylabel('Frequency')
        ax4.legend()
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()

        # Save figure
        chart_path = self.output_dir / f"backtest_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(chart_path, dpi=150, bbox_inches='tight')
        logger.info(f"Saved charts to {chart_path}")

        plt.close()

    def _save_backtest_result(
        self,
        result: BacktestResult,
        validation: Optional[ValidationResult] = None
    ):
        """Save backtest result to database."""
        try:
            # Create backtest_results table if not exists
            with self.db.get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS backtest_results (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        strategy_name TEXT NOT NULL,
                        run_date DATETIME NOT NULL,
                        start_date DATE NOT NULL,
                        end_date DATE NOT NULL,
                        initial_capital REAL NOT NULL,
                        final_equity REAL NOT NULL,
                        total_return REAL NOT NULL,
                        cagr REAL NOT NULL,
                        sharpe_ratio REAL NOT NULL,
                        sortino_ratio REAL NOT NULL,
                        calmar_ratio REAL NOT NULL,
                        max_drawdown REAL NOT NULL,
                        win_rate REAL NOT NULL,
                        profit_factor REAL NOT NULL,
                        trade_count INTEGER NOT NULL,
                        alpha REAL,
                        beta REAL,
                        is_robust BOOLEAN,
                        consistency_score REAL,
                        overfitting_probability REAL,
                        parameters TEXT
                    )
                """)

                # Insert result
                conn.execute("""
                    INSERT INTO backtest_results (
                        strategy_name, run_date, start_date, end_date,
                        initial_capital, final_equity, total_return, cagr,
                        sharpe_ratio, sortino_ratio, calmar_ratio, max_drawdown,
                        win_rate, profit_factor, trade_count,
                        alpha, beta, is_robust, consistency_score, overfitting_probability,
                        parameters
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result.strategy_name,
                    datetime.now(),
                    result.start_date,
                    result.end_date,
                    result.initial_capital,
                    result.final_equity,
                    result.metrics.total_return,
                    result.metrics.cagr,
                    result.metrics.sharpe_ratio,
                    result.metrics.sortino_ratio,
                    result.metrics.calmar_ratio,
                    result.metrics.max_drawdown,
                    result.metrics.win_rate,
                    result.metrics.profit_factor,
                    result.metrics.trade_count,
                    result.metrics.alpha,
                    result.metrics.beta,
                    validation.is_robust if validation else None,
                    validation.consistency_score if validation else None,
                    validation.overfitting_probability if validation else None,
                    json.dumps(result.params.__dict__)
                ))

                logger.info(f"Saved backtest result for {result.strategy_name} to database")

        except Exception as e:
            logger.error(f"Failed to save backtest result: {e}")

    def get_historical_backtests(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 10
    ) -> pd.DataFrame:
        """
        Get historical backtest results from database.

        Args:
            strategy_name: Optional strategy name filter
            limit: Maximum number of results

        Returns:
            DataFrame with historical results
        """
        try:
            with self.db.get_connection() as conn:
                if strategy_name:
                    query = """
                        SELECT * FROM backtest_results
                        WHERE strategy_name = ?
                        ORDER BY run_date DESC
                        LIMIT ?
                    """
                    df = pd.read_sql_query(query, conn, params=(strategy_name, limit))
                else:
                    query = """
                        SELECT * FROM backtest_results
                        ORDER BY run_date DESC
                        LIMIT ?
                    """
                    df = pd.read_sql_query(query, conn, params=(limit,))

                return df

        except Exception as e:
            logger.error(f"Failed to load historical backtests: {e}")
            return pd.DataFrame()
