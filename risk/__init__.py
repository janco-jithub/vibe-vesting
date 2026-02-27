"""
Risk Management Package

World-class risk management for quantitative trading systems.

Components:
- dynamic_sizing: Volatility, correlation, and regime-aware position sizing
- portfolio_risk: Portfolio-level risk monitoring and controls
- adaptive_stops: Intelligent trailing stop management
- stress_test: Historical and hypothetical stress testing
- var_calculator: Value at Risk and tail risk metrics
- circuit_breakers: Automatic trading halts on risk violations
- position_sizing: Basic position sizing methods
- profit_optimizer: Profit maximization techniques

Academic References:
- Grinold & Kahn (2000): "Active Portfolio Management"
- Jorion (2006): "Value at Risk"
- Thorp (1969): "Optimal Gambling Systems for Favorable Games"
- Prado (2018): "Advances in Financial Machine Learning"
"""

# Import key classes for easy access
from .dynamic_sizing import (
    DynamicPositionSizer,
    PositionSizeParams,
    VolatilityRegime,
    MarketRegime
)

from .portfolio_risk import (
    PortfolioRiskManager,
    PortfolioRiskMetrics,
    RiskReductionAction,
    RiskViolationType
)

from .adaptive_stops import (
    AdaptiveStopManager,
    StopLossParams,
    StopType
)

from .stress_test import (
    StressTestEngine,
    StressScenario,
    StressTestResult,
    ScenarioType
)

from .var_calculator import (
    VaRCalculator,
    RiskMetrics,
    RiskMonitor
)

from .circuit_breakers import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerType,
    TradingHaltReason
)

from .position_sizing import (
    PositionSizer,
    PositionSizeResult
)

from .profit_optimizer import (
    ProfitOptimizer,
    PositionState,
    TradeAction,
    MarketPhase,
    VolatilityRegime as ProfitVolatilityRegime
)

__all__ = [
    # Dynamic sizing
    'DynamicPositionSizer',
    'PositionSizeParams',
    'VolatilityRegime',
    'MarketRegime',

    # Portfolio risk
    'PortfolioRiskManager',
    'PortfolioRiskMetrics',
    'RiskReductionAction',
    'RiskViolationType',

    # Adaptive stops
    'AdaptiveStopManager',
    'StopLossParams',
    'StopType',

    # Stress testing
    'StressTestEngine',
    'StressScenario',
    'StressTestResult',
    'ScenarioType',

    # VaR
    'VaRCalculator',
    'RiskMetrics',
    'RiskMonitor',

    # Circuit breakers
    'CircuitBreaker',
    'CircuitBreakerState',
    'CircuitBreakerType',
    'TradingHaltReason',

    # Position sizing
    'PositionSizer',
    'PositionSizeResult',

    # Profit optimizer
    'ProfitOptimizer',
    'PositionState',
    'TradeAction',
    'MarketPhase',
]
