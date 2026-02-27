"""
Risk Management Package

Components:
- var_calculator: Value at Risk and tail risk metrics
- circuit_breakers: Automatic trading halts on risk violations
- position_sizing: Basic position sizing methods
- profit_optimizer: Profit maximization techniques
- kelly_sizing: Kelly Criterion position sizing
- correlation_manager: Prevent concentrated risk
"""

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
)

__all__ = [
    'VaRCalculator',
    'RiskMetrics',
    'RiskMonitor',
    'CircuitBreaker',
    'CircuitBreakerState',
    'CircuitBreakerType',
    'TradingHaltReason',
    'PositionSizer',
    'PositionSizeResult',
    'ProfitOptimizer',
    'PositionState',
    'TradeAction',
    'MarketPhase',
]
