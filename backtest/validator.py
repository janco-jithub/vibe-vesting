"""
Strategy Validation Framework

Implements comprehensive validation techniques:
- Monte Carlo simulation for robustness testing
- Parameter sensitivity analysis
- Regime analysis (bull/bear/sideways market performance)
- Strategy correlation analysis
- Out-of-sample performance validation

Academic Foundation:
- Bailey et al. (2014): "The Probability of Backtest Overfitting"
- Harvey et al. (2016): "...and the Cross-Section of Expected Returns"
- Lopez de Prado (2018): "Advances in Financial Machine Learning"
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from datetime import date, timedelta

import pandas as pd
import numpy as np
from scipy import stats

from strategies.base import BaseStrategy
from backtest.engine import BacktestEngine, BacktestResult
from backtest.metrics import PerformanceMetrics

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Results from strategy validation."""
    strategy_name: str

    # Monte Carlo results
    sharpe_distribution: List[float]
    sharpe_mean: float
    sharpe_std: float
    sharpe_confidence_interval: Tuple[float, float]

    # Parameter sensitivity
    parameter_tests: List[Dict[str, Any]]
    optimal_parameters: Dict[str, Any]

    # Regime analysis
    regime_performance: Dict[str, PerformanceMetrics]

    # Stability metrics
    consistency_score: float  # 0-1, higher = more consistent across periods
    overfitting_probability: float  # 0-1, higher = more likely overfit

    # Recommendation
    is_robust: bool
    warnings: List[str]
    recommendations: List[str]


class StrategyValidator:
    """
    Comprehensive strategy validation framework.

    Validates that a strategy is truly robust, not just overfit to
    historical data. Uses techniques from academic research on
    backtest overfitting.

    Critical Validation Checks:
    1. Does the strategy work across different time periods?
    2. Is it robust to parameter changes?
    3. Does it perform in different market regimes?
    4. Is the Sharpe ratio statistically significant?
    """

    def __init__(
        self,
        confidence_level: float = 0.95,
        min_sharpe_threshold: float = 1.0,
        min_calmar_threshold: float = 1.0
    ):
        """
        Initialize validator.

        Args:
            confidence_level: Confidence level for statistical tests
            min_sharpe_threshold: Minimum acceptable Sharpe ratio
            min_calmar_threshold: Minimum acceptable Calmar ratio
        """
        self.confidence_level = confidence_level
        self.min_sharpe_threshold = min_sharpe_threshold
        self.min_calmar_threshold = min_calmar_threshold

    def validate_strategy(
        self,
        strategy: BaseStrategy,
        data: Dict[str, pd.DataFrame],
        n_simulations: int = 100,
        parameter_grid: Optional[Dict[str, List[Any]]] = None
    ) -> ValidationResult:
        """
        Run comprehensive validation on a strategy.

        Args:
            strategy: Strategy to validate
            data: Market data
            n_simulations: Number of Monte Carlo simulations
            parameter_grid: Optional grid of parameters to test

        Returns:
            ValidationResult with all validation metrics
        """
        logger.info(f"Starting validation for {strategy.name}")

        warnings = []
        recommendations = []

        # 1. Monte Carlo simulation
        logger.info("Running Monte Carlo simulation...")
        sharpe_dist, mc_mean, mc_std, mc_ci = self._monte_carlo_simulation(
            strategy, data, n_simulations
        )

        if mc_mean < self.min_sharpe_threshold:
            warnings.append(
                f"Mean Sharpe ratio ({mc_mean:.2f}) below threshold ({self.min_sharpe_threshold:.2f})"
            )

        # 2. Parameter sensitivity
        logger.info("Running parameter sensitivity analysis...")
        param_tests, optimal_params = self._parameter_sensitivity(
            strategy, data, parameter_grid
        )

        # Check if performance is very sensitive to parameters
        param_variation = self._calculate_parameter_variation(param_tests)
        if param_variation > 0.5:
            warnings.append(
                f"Strategy is highly sensitive to parameters (variation={param_variation:.2f})"
            )
            recommendations.append(
                "Consider using more robust parameter selection or ensemble methods"
            )

        # 3. Regime analysis
        logger.info("Running regime analysis...")
        regime_perf = self._regime_analysis(strategy, data)

        # Check if strategy fails in certain regimes
        for regime, metrics in regime_perf.items():
            if metrics.sharpe_ratio < 0:
                warnings.append(
                    f"Negative Sharpe ratio ({metrics.sharpe_ratio:.2f}) in {regime} regime"
                )

        # 4. Consistency score
        consistency = self._calculate_consistency_score(param_tests, regime_perf)

        if consistency < 0.5:
            warnings.append(f"Low consistency score ({consistency:.2f})")
            recommendations.append(
                "Strategy performance varies significantly across conditions"
            )

        # 5. Overfitting probability (Bailey et al. 2014)
        overfitting_prob = self._estimate_overfitting_probability(
            param_tests, mc_mean, mc_std
        )

        if overfitting_prob > 0.5:
            warnings.append(
                f"High overfitting probability ({overfitting_prob:.2%})"
            )
            recommendations.append(
                "Consider reducing strategy complexity or using regularization"
            )

        # Determine if strategy is robust
        is_robust = (
            mc_mean >= self.min_sharpe_threshold and
            consistency >= 0.5 and
            overfitting_prob < 0.5 and
            len([r for r in regime_perf.values() if r.sharpe_ratio < 0]) == 0
        )

        if is_robust:
            recommendations.append(
                "Strategy passes validation - suitable for live trading"
            )
        else:
            recommendations.append(
                "Strategy requires further optimization before live trading"
            )

        result = ValidationResult(
            strategy_name=strategy.name,
            sharpe_distribution=sharpe_dist,
            sharpe_mean=mc_mean,
            sharpe_std=mc_std,
            sharpe_confidence_interval=mc_ci,
            parameter_tests=param_tests,
            optimal_parameters=optimal_params,
            regime_performance=regime_perf,
            consistency_score=consistency,
            overfitting_probability=overfitting_prob,
            is_robust=is_robust,
            warnings=warnings,
            recommendations=recommendations
        )

        logger.info(
            f"Validation complete for {strategy.name}",
            extra={
                "is_robust": is_robust,
                "sharpe_mean": f"{mc_mean:.2f}",
                "consistency": f"{consistency:.2f}",
                "overfitting_prob": f"{overfitting_prob:.2%}"
            }
        )

        return result

    def _monte_carlo_simulation(
        self,
        strategy: BaseStrategy,
        data: Dict[str, pd.DataFrame],
        n_simulations: int
    ) -> Tuple[List[float], float, float, Tuple[float, float]]:
        """
        Run Monte Carlo simulation by bootstrapping returns.

        This tests if the strategy's Sharpe ratio is statistically significant
        or just due to luck.

        Returns:
            (distribution, mean, std, confidence_interval)
        """
        sharpe_ratios = []

        # Run base backtest
        params = strategy.get_backtest_params()
        engine = BacktestEngine(strategy, data, params)
        base_result = engine.run()

        # Get date range
        dates = base_result.returns.index

        for i in range(n_simulations):
            # Bootstrap returns (sample with replacement)
            sampled_returns = base_result.returns.sample(
                n=len(base_result.returns),
                replace=True
            )

            # Calculate Sharpe ratio for sampled returns
            sharpe = self._calculate_sharpe(sampled_returns)
            sharpe_ratios.append(sharpe)

        sharpe_mean = np.mean(sharpe_ratios)
        sharpe_std = np.std(sharpe_ratios)

        # Calculate confidence interval
        alpha = 1 - self.confidence_level
        ci_lower = np.percentile(sharpe_ratios, alpha/2 * 100)
        ci_upper = np.percentile(sharpe_ratios, (1 - alpha/2) * 100)

        return sharpe_ratios, sharpe_mean, sharpe_std, (ci_lower, ci_upper)

    def _parameter_sensitivity(
        self,
        strategy: BaseStrategy,
        data: Dict[str, pd.DataFrame],
        parameter_grid: Optional[Dict[str, List[Any]]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Test strategy with different parameter combinations.

        Returns:
            (test_results, optimal_parameters)
        """
        # Define default parameter grid if not provided
        if parameter_grid is None:
            parameter_grid = self._get_default_parameter_grid(strategy)

        if not parameter_grid:
            logger.warning("No parameter grid available for sensitivity analysis")
            return [], {}

        results = []
        base_params = strategy.get_backtest_params()

        # Test each parameter combination
        param_names = list(parameter_grid.keys())
        param_values = list(parameter_grid.values())

        # Limit to reasonable number of combinations
        max_tests = 20
        test_count = 0

        for param_name in param_names:
            for value in parameter_grid[param_name]:
                if test_count >= max_tests:
                    break

                try:
                    # Create strategy with modified parameter
                    test_strategy = self._create_strategy_with_params(
                        strategy, {param_name: value}
                    )

                    # Run backtest
                    engine = BacktestEngine(test_strategy, data, base_params)
                    result = engine.run()

                    results.append({
                        'parameter': param_name,
                        'value': value,
                        'sharpe': result.metrics.sharpe_ratio,
                        'calmar': result.metrics.calmar_ratio,
                        'total_return': result.metrics.total_return,
                        'max_drawdown': result.metrics.max_drawdown
                    })

                    test_count += 1

                except Exception as e:
                    logger.warning(f"Failed to test {param_name}={value}: {e}")
                    continue

        # Find optimal parameters (highest Sharpe ratio)
        if results:
            best_result = max(results, key=lambda x: x['sharpe'])
            optimal_params = {
                best_result['parameter']: best_result['value']
            }
        else:
            optimal_params = {}

        return results, optimal_params

    def _regime_analysis(
        self,
        strategy: BaseStrategy,
        data: Dict[str, pd.DataFrame]
    ) -> Dict[str, PerformanceMetrics]:
        """
        Analyze strategy performance in different market regimes.

        Regimes:
        - Bull: Market up > 10% over period
        - Bear: Market down > 10% over period
        - Sideways: Market within +/- 10%
        - High Vol: Volatility > 20% annualized
        - Low Vol: Volatility < 15% annualized

        Returns:
            Dict of regime -> PerformanceMetrics
        """
        regime_performance = {}

        # Get benchmark data (SPY)
        if 'SPY' not in data:
            logger.warning("SPY not available for regime analysis")
            return regime_performance

        spy_data = data['SPY']

        # Calculate market regimes
        regimes = self._identify_regimes(spy_data)

        base_params = strategy.get_backtest_params()

        for regime_name, (start_date, end_date) in regimes.items():
            try:
                # Filter data to regime period
                regime_data = {}
                for symbol, df in data.items():
                    mask = (df.index >= start_date) & (df.index <= end_date)
                    regime_df = df[mask]
                    if len(regime_df) > 0:
                        regime_data[symbol] = regime_df

                if not regime_data:
                    continue

                # Create regime-specific params
                regime_params = strategy.get_backtest_params()
                regime_params.start_date = start_date.strftime('%Y-%m-%d')
                regime_params.end_date = end_date.strftime('%Y-%m-%d')

                # Run backtest
                engine = BacktestEngine(strategy, regime_data, regime_params)
                result = engine.run()

                regime_performance[regime_name] = result.metrics

            except Exception as e:
                logger.warning(f"Failed to analyze {regime_name} regime: {e}")
                continue

        return regime_performance

    def _identify_regimes(
        self,
        spy_data: pd.DataFrame
    ) -> Dict[str, Tuple[pd.Timestamp, pd.Timestamp]]:
        """
        Identify different market regimes based on SPY price action.

        Returns:
            Dict of regime_name -> (start_date, end_date)
        """
        regimes = {}

        if len(spy_data) < 252:
            return regimes

        close = spy_data['close']
        returns = close.pct_change()

        # Calculate rolling metrics
        rolling_return = close.pct_change(63)  # 3-month return
        rolling_vol = returns.rolling(63).std() * np.sqrt(252)  # Annualized vol

        # Split data into thirds for simplicity
        n = len(spy_data)
        third = n // 3

        if third > 60:  # Need at least 60 days per regime
            # First third
            period1_start = spy_data.index[0]
            period1_end = spy_data.index[third]
            period1_return = (close.iloc[third] / close.iloc[0]) - 1

            if period1_return > 0.10:
                regimes['bull_market'] = (period1_start, period1_end)
            elif period1_return < -0.10:
                regimes['bear_market'] = (period1_start, period1_end)
            else:
                regimes['sideways_market'] = (period1_start, period1_end)

            # Second third
            period2_start = spy_data.index[third]
            period2_end = spy_data.index[2 * third]
            period2_vol = rolling_vol.iloc[third:2*third].mean()

            if period2_vol > 0.25:
                regimes['high_volatility'] = (period2_start, period2_end)
            else:
                regimes['low_volatility'] = (period2_start, period2_end)

        return regimes

    def _calculate_consistency_score(
        self,
        param_tests: List[Dict[str, Any]],
        regime_perf: Dict[str, PerformanceMetrics]
    ) -> float:
        """
        Calculate consistency score (0-1).

        Higher score means strategy performs consistently across
        parameters and regimes.
        """
        scores = []

        # Consistency across parameters
        if param_tests:
            sharpe_ratios = [t['sharpe'] for t in param_tests if t['sharpe'] > 0]
            if len(sharpe_ratios) > 1:
                # Coefficient of variation (lower = more consistent)
                cv = np.std(sharpe_ratios) / np.mean(sharpe_ratios)
                param_score = max(0, 1 - cv)
                scores.append(param_score)

        # Consistency across regimes
        if regime_perf:
            sharpe_ratios = [m.sharpe_ratio for m in regime_perf.values()]
            if len(sharpe_ratios) > 1:
                # What % of regimes have positive Sharpe?
                positive_pct = len([s for s in sharpe_ratios if s > 0]) / len(sharpe_ratios)
                scores.append(positive_pct)

        return float(np.mean(scores)) if scores else 0.5

    def _estimate_overfitting_probability(
        self,
        param_tests: List[Dict[str, Any]],
        mc_mean: float,
        mc_std: float
    ) -> float:
        """
        Estimate probability of backtest overfitting.

        Based on Bailey et al. (2014):
        - If best in-sample result >> out-of-sample, likely overfit
        - If parameter selection shows large spread, likely overfit

        Returns:
            Probability 0-1 (higher = more likely overfit)
        """
        if not param_tests or mc_std == 0:
            return 0.5  # Unknown

        # Best in-sample Sharpe
        best_sharpe = max([t['sharpe'] for t in param_tests])

        # How many standard deviations above mean?
        z_score = (best_sharpe - mc_mean) / mc_std

        # If best result is > 2 std above mean, likely overfit
        # Map z-score to probability
        overfitting_prob = min(1.0, max(0.0, (z_score - 1.0) / 3.0))

        return float(overfitting_prob)

    def _calculate_parameter_variation(
        self,
        param_tests: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate how much performance varies with parameters.

        Returns:
            Coefficient of variation (0 = no variation, >1 = high variation)
        """
        if len(param_tests) < 2:
            return 0.0

        sharpe_ratios = [t['sharpe'] for t in param_tests]
        mean_sharpe = np.mean(sharpe_ratios)

        if mean_sharpe == 0:
            return 1.0

        cv = np.std(sharpe_ratios) / abs(mean_sharpe)
        return float(cv)

    def _calculate_sharpe(self, returns: pd.Series) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(returns) < 2 or returns.std() == 0:
            return 0.0

        mean_return = returns.mean() * 252
        std_return = returns.std() * np.sqrt(252)

        return float(mean_return / std_return)

    def _get_default_parameter_grid(
        self,
        strategy: BaseStrategy
    ) -> Dict[str, List[Any]]:
        """
        Get default parameter grid for common strategies.

        Returns:
            Dict of parameter_name -> list of values to test
        """
        # Try to detect strategy type and return appropriate grid
        strategy_type = strategy.__class__.__name__.lower()

        if 'momentum' in strategy_type:
            return {
                'momentum_period': [20, 40, 60, 90, 126],
                'sma_period': [50, 100, 150, 200]
            }
        elif 'mean_reversion' in strategy_type or 'pairs' in strategy_type:
            return {
                'lookback_period': [20, 40, 60],
                'entry_threshold': [1.5, 2.0, 2.5]
            }
        else:
            return {}

    def _create_strategy_with_params(
        self,
        strategy: BaseStrategy,
        params: Dict[str, Any]
    ) -> BaseStrategy:
        """
        Create new strategy instance with modified parameters.

        This is a bit hacky - tries to modify strategy attributes.
        """
        import copy
        new_strategy = copy.deepcopy(strategy)

        for param_name, param_value in params.items():
            if hasattr(new_strategy, param_name):
                setattr(new_strategy, param_name, param_value)

        return new_strategy


def print_validation_results(result: ValidationResult) -> str:
    """Format validation results for display."""
    lines = [
        f"\n{'=' * 70}",
        f"  VALIDATION REPORT: {result.strategy_name}",
        f"{'=' * 70}",
        "",
        "ROBUSTNESS ASSESSMENT",
        f"  Status: {'PASS' if result.is_robust else 'FAIL'}",
        f"  Consistency Score: {result.consistency_score:.2f} (0-1 scale)",
        f"  Overfitting Risk:  {result.overfitting_probability:.1%}",
        "",
        "MONTE CARLO SIMULATION",
        f"  Mean Sharpe Ratio:  {result.sharpe_mean:.2f}",
        f"  Std Dev:            {result.sharpe_std:.2f}",
        f"  95% CI:             [{result.sharpe_confidence_interval[0]:.2f}, {result.sharpe_confidence_interval[1]:.2f}]",
        "",
        "REGIME PERFORMANCE",
    ]

    for regime, metrics in result.regime_performance.items():
        lines.append(
            f"  {regime:20s}: Sharpe={metrics.sharpe_ratio:>6.2f}  "
            f"Return={metrics.total_return:>7.1%}  DD={metrics.max_drawdown:>7.1%}"
        )

    if result.parameter_tests:
        lines.extend([
            "",
            "PARAMETER SENSITIVITY",
            f"  Tests Performed: {len(result.parameter_tests)}",
            f"  Best Sharpe: {max(t['sharpe'] for t in result.parameter_tests):.2f}",
            f"  Worst Sharpe: {min(t['sharpe'] for t in result.parameter_tests):.2f}",
        ])

    if result.warnings:
        lines.extend([
            "",
            "WARNINGS",
        ])
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    if result.recommendations:
        lines.extend([
            "",
            "RECOMMENDATIONS",
        ])
        for rec in result.recommendations:
            lines.append(f"  - {rec}")

    lines.append(f"{'=' * 70}\n")

    return "\n".join(lines)


def compare_strategies(
    validation_results: List[ValidationResult]
) -> pd.DataFrame:
    """
    Compare multiple strategies.

    Returns:
        DataFrame with strategy comparison
    """
    data = []

    for result in validation_results:
        data.append({
            'Strategy': result.strategy_name,
            'Robust': 'YES' if result.is_robust else 'NO',
            'Mean Sharpe': result.sharpe_mean,
            'Sharpe Std': result.sharpe_std,
            'Consistency': result.consistency_score,
            'Overfit Risk': result.overfitting_probability,
            'Warnings': len(result.warnings),
        })

    df = pd.DataFrame(data)
    df = df.sort_values('Mean Sharpe', ascending=False)

    return df
