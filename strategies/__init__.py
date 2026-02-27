"""Trading strategies module."""

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams
from strategies.dual_momentum import DualMomentumStrategy
from strategies.swing_momentum import SwingMomentumStrategy
from strategies.ml_momentum import MLMomentumStrategy
from strategies.pairs_trading import PairsTradingStrategy
from strategies.volatility_breakout import VolatilityBreakoutStrategy

__all__ = [
    "BaseStrategy",
    "Signal",
    "SignalType",
    "BacktestParams",
    "DualMomentumStrategy",
    "SwingMomentumStrategy",
    "MLMomentumStrategy",
    "PairsTradingStrategy",
    "VolatilityBreakoutStrategy",
]
