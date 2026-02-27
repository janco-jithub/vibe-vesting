"""
Value at Risk (VaR) and Conditional VaR Calculator.

Based on:
- Basel III regulatory framework for risk measurement
- Artzner et al. (1999): "Coherent Measures of Risk"

VaR: Maximum expected loss at a given confidence level
CVaR (Expected Shortfall): Average loss beyond VaR threshold

CVaR is preferred because it:
1. Accounts for tail risk
2. Is a coherent risk measure (subadditive)
3. Better captures extreme losses
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from scipy import stats
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class RiskMetrics:
    """Portfolio risk metrics."""
    var_95: float  # 95% VaR (1-day)
    var_99: float  # 99% VaR (1-day)
    cvar_95: float  # 95% CVaR (Expected Shortfall)
    cvar_99: float  # 99% CVaR
    volatility: float  # Annualized volatility
    max_drawdown: float  # Maximum drawdown
    skewness: float  # Return distribution skewness
    kurtosis: float  # Return distribution kurtosis (excess)
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            'var_95': self.var_95,
            'var_99': self.var_99,
            'cvar_95': self.cvar_95,
            'cvar_99': self.cvar_99,
            'volatility': self.volatility,
            'max_drawdown': self.max_drawdown,
            'skewness': self.skewness,
            'kurtosis': self.kurtosis,
            'timestamp': self.timestamp.isoformat()
        }

    def summary(self) -> str:
        return (
            f"Risk Metrics:\n"
            f"  VaR (95%): {self.var_95:.2%} | VaR (99%): {self.var_99:.2%}\n"
            f"  CVaR (95%): {self.cvar_95:.2%} | CVaR (99%): {self.cvar_99:.2%}\n"
            f"  Volatility: {self.volatility:.2%} | Max DD: {self.max_drawdown:.2%}\n"
            f"  Skew: {self.skewness:.2f} | Kurtosis: {self.kurtosis:.2f}"
        )


class VaRCalculator:
    """
    Calculate Value at Risk and related risk metrics.

    Methods:
    1. Historical VaR: Percentile of historical returns
    2. Parametric VaR: Assumes normal distribution
    3. Monte Carlo VaR: Simulation-based

    We primarily use Historical VaR as it:
    - Makes no distributional assumptions
    - Captures fat tails naturally
    - Is industry standard
    """

    # Risk limits (can be adjusted)
    DEFAULT_LIMITS = {
        'var_95_limit': 0.02,   # Max 2% daily VaR at 95%
        'var_99_limit': 0.04,   # Max 4% daily VaR at 99%
        'cvar_95_limit': 0.03,  # Max 3% daily CVaR at 95%
        'cvar_99_limit': 0.06,  # Max 6% daily CVaR at 99%
        'max_drawdown_limit': 0.15  # Max 15% drawdown before intervention
    }

    def __init__(
        self,
        lookback_days: int = 252,  # 1 year of data
        confidence_levels: List[float] = [0.95, 0.99],
        limits: Optional[Dict[str, float]] = None
    ):
        """
        Initialize VaR calculator.

        Args:
            lookback_days: Days of history to use
            confidence_levels: Confidence levels for VaR calculation
            limits: Risk limits (override defaults)
        """
        self.lookback_days = lookback_days
        self.confidence_levels = confidence_levels
        self.limits = limits or self.DEFAULT_LIMITS

        self._last_metrics: Optional[RiskMetrics] = None

    def calculate_historical_var(
        self,
        returns: pd.Series,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Historical VaR.

        VaR at 95% = 5th percentile of returns
        Interpretation: 95% of the time, losses won't exceed this amount.

        Args:
            returns: Series of daily returns
            confidence: Confidence level (0.95 = 95%)

        Returns:
            VaR as a positive number (loss)
        """
        if len(returns) < 30:
            logger.warning("Insufficient data for reliable VaR calculation")
            return 0.05  # Conservative default

        var = np.percentile(returns, (1 - confidence) * 100)
        return abs(var)

    def calculate_cvar(
        self,
        returns: pd.Series,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Conditional VaR (Expected Shortfall).

        CVaR = Average of returns worse than VaR
        Better captures tail risk than VaR.

        Args:
            returns: Series of daily returns
            confidence: Confidence level

        Returns:
            CVaR as a positive number (expected loss in tail)
        """
        var = -self.calculate_historical_var(returns, confidence)
        tail_returns = returns[returns <= var]

        if len(tail_returns) == 0:
            return abs(var)

        cvar = tail_returns.mean()
        return abs(cvar)

    def calculate_parametric_var(
        self,
        returns: pd.Series,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Parametric (Normal) VaR.

        Assumes returns are normally distributed.
        VaR = μ - z * σ

        Less accurate for fat-tailed distributions but useful for comparison.
        """
        mu = returns.mean()
        sigma = returns.std()
        z = stats.norm.ppf(1 - confidence)

        var = mu + z * sigma  # z is negative for left tail
        return abs(var)

    def calculate_cornish_fisher_var(
        self,
        returns: pd.Series,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Cornish-Fisher VaR.

        Adjusts for skewness and kurtosis in the distribution.
        More accurate than parametric when returns are non-normal.
        """
        mu = returns.mean()
        sigma = returns.std()
        skew = returns.skew()
        kurt = returns.kurtosis()  # Excess kurtosis

        z = stats.norm.ppf(1 - confidence)

        # Cornish-Fisher expansion
        z_cf = (z +
                (z**2 - 1) * skew / 6 +
                (z**3 - 3*z) * kurt / 24 -
                (2*z**3 - 5*z) * skew**2 / 36)

        var = mu + z_cf * sigma
        return abs(var)

    def calculate_portfolio_var(
        self,
        positions: Dict[str, float],
        returns_data: Dict[str, pd.Series],
        confidence: float = 0.95
    ) -> float:
        """
        Calculate portfolio VaR using covariance matrix.

        For multi-asset portfolios, accounts for diversification.

        Args:
            positions: Dict mapping symbol to position value
            returns_data: Dict mapping symbol to return series
            confidence: Confidence level

        Returns:
            Portfolio VaR
        """
        symbols = list(positions.keys())
        weights = np.array([positions[s] for s in symbols])
        weights = weights / weights.sum()  # Normalize to sum to 1

        # Build returns matrix
        returns_matrix = pd.DataFrame({s: returns_data[s] for s in symbols if s in returns_data})

        if returns_matrix.empty:
            return 0.05

        # Calculate covariance matrix
        cov_matrix = returns_matrix.cov() * 252  # Annualized

        # Portfolio variance
        portfolio_var = np.sqrt(weights.T @ cov_matrix.values @ weights)

        # Convert to VaR
        z = stats.norm.ppf(1 - confidence)
        var_daily = abs(z) * portfolio_var / np.sqrt(252)

        return var_daily

    def calculate_all_metrics(self, returns: pd.Series) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics.

        Args:
            returns: Series of daily returns

        Returns:
            RiskMetrics object
        """
        # Limit to lookback period
        returns = returns.iloc[-self.lookback_days:] if len(returns) > self.lookback_days else returns

        # VaR and CVaR
        var_95 = self.calculate_historical_var(returns, 0.95)
        var_99 = self.calculate_historical_var(returns, 0.99)
        cvar_95 = self.calculate_cvar(returns, 0.95)
        cvar_99 = self.calculate_cvar(returns, 0.99)

        # Volatility (annualized)
        volatility = returns.std() * np.sqrt(252)

        # Max drawdown
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.cummax()
        drawdowns = (cumulative - running_max) / running_max
        max_drawdown = abs(drawdowns.min())

        # Higher moments
        skewness = returns.skew()
        kurtosis = returns.kurtosis()

        metrics = RiskMetrics(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            cvar_99=cvar_99,
            volatility=volatility,
            max_drawdown=max_drawdown,
            skewness=skewness,
            kurtosis=kurtosis,
            timestamp=datetime.now()
        )

        self._last_metrics = metrics
        return metrics

    def check_risk_limits(self, metrics: RiskMetrics) -> Tuple[bool, List[str]]:
        """
        Check if risk metrics exceed limits.

        Args:
            metrics: RiskMetrics to check

        Returns:
            (within_limits, list_of_violations)
        """
        violations = []

        if metrics.var_95 > self.limits['var_95_limit']:
            violations.append(f"VaR(95%) {metrics.var_95:.2%} > {self.limits['var_95_limit']:.2%}")

        if metrics.var_99 > self.limits['var_99_limit']:
            violations.append(f"VaR(99%) {metrics.var_99:.2%} > {self.limits['var_99_limit']:.2%}")

        if metrics.cvar_95 > self.limits['cvar_95_limit']:
            violations.append(f"CVaR(95%) {metrics.cvar_95:.2%} > {self.limits['cvar_95_limit']:.2%}")

        if metrics.cvar_99 > self.limits['cvar_99_limit']:
            violations.append(f"CVaR(99%) {metrics.cvar_99:.2%} > {self.limits['cvar_99_limit']:.2%}")

        if metrics.max_drawdown > self.limits['max_drawdown_limit']:
            violations.append(f"MaxDD {metrics.max_drawdown:.2%} > {self.limits['max_drawdown_limit']:.2%}")

        return len(violations) == 0, violations

    def get_position_adjustment_factor(self, metrics: RiskMetrics) -> float:
        """
        Calculate position size adjustment based on risk.

        If risk is high, reduce position sizes.

        Returns:
            Multiplier for position sizes (0.5 to 1.0)
        """
        # Check how close we are to limits
        var_ratio = metrics.var_95 / self.limits['var_95_limit']
        cvar_ratio = metrics.cvar_95 / self.limits['cvar_95_limit']
        dd_ratio = metrics.max_drawdown / self.limits['max_drawdown_limit']

        max_ratio = max(var_ratio, cvar_ratio, dd_ratio)

        if max_ratio < 0.7:
            return 1.0  # Well within limits
        elif max_ratio < 0.9:
            return 0.9  # Slight reduction
        elif max_ratio < 1.0:
            return 0.7  # Moderate reduction
        else:
            return 0.5  # At or over limits - significant reduction

    def calculate_marginal_var(
        self,
        portfolio_returns: pd.Series,
        position_returns: pd.Series,
        position_weight: float,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate marginal VaR contribution of a position.

        Marginal VaR = Change in portfolio VaR from small change in position.
        Useful for understanding which positions contribute most to risk.

        Args:
            portfolio_returns: Current portfolio returns
            position_returns: Returns of the position
            position_weight: Weight of position in portfolio
            confidence: Confidence level

        Returns:
            Marginal VaR contribution
        """
        # Calculate correlation
        corr = portfolio_returns.corr(position_returns)

        # Portfolio and position volatility
        port_vol = portfolio_returns.std()
        pos_vol = position_returns.std()

        # Marginal VaR = weight * position_vol * correlation * VaR_factor
        z = abs(stats.norm.ppf(1 - confidence))
        marginal_var = position_weight * pos_vol * corr * z

        return marginal_var


class RiskMonitor:
    """
    Continuous risk monitoring with alerts.
    """

    def __init__(self, var_calculator: VaRCalculator):
        self.var_calculator = var_calculator
        self._alert_history: List[dict] = []

    def monitor(self, returns: pd.Series) -> Tuple[RiskMetrics, List[str]]:
        """
        Monitor risk and generate alerts if needed.

        Returns:
            (metrics, alerts)
        """
        metrics = self.var_calculator.calculate_all_metrics(returns)
        within_limits, violations = self.var_calculator.check_risk_limits(metrics)

        alerts = []
        if not within_limits:
            for v in violations:
                alert = {
                    'timestamp': datetime.now().isoformat(),
                    'type': 'RISK_LIMIT_BREACH',
                    'message': v
                }
                alerts.append(v)
                self._alert_history.append(alert)
                logger.warning(f"RISK ALERT: {v}")

        return metrics, alerts
