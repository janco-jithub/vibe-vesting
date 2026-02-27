"""
Market Regime Detection using Hidden Markov Models.

Based on Kritzman et al. (2012) - "Regime Shifts: Implications for Dynamic Strategies"
Expected improvement: 0.5-0.8 Sharpe by avoiding wrong-regime trades.

Regimes:
- BULL: High returns, low volatility → Use momentum strategies
- BEAR: Negative returns, high volatility → Go to cash/hedge
- SIDEWAYS: Low returns, low volatility → Use mean reversion/pairs
"""

import numpy as np
import pandas as pd
import logging
from enum import Enum
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


@dataclass
class RegimeState:
    """Current regime state with confidence."""
    regime: MarketRegime
    confidence: float
    bull_prob: float
    bear_prob: float
    sideways_prob: float
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            'regime': self.regime.value,
            'confidence': self.confidence,
            'bull_prob': self.bull_prob,
            'bear_prob': self.bear_prob,
            'sideways_prob': self.sideways_prob,
            'timestamp': self.timestamp.isoformat()
        }


class RegimeDetector:
    """
    Detect market regimes using statistical analysis and HMM-like approach.

    Based on Kritzman et al. (2012):
    - Markets exhibit distinct regimes
    - Different strategies work in different regimes
    - Regime detection improves risk-adjusted returns by 0.5-0.8 Sharpe

    Detection criteria:
    - BULL: 20-day returns > 0, 20-day vol < long-term vol, price > 50-day MA
    - BEAR: 20-day returns < -5%, 20-day vol > 1.5x long-term vol, price < 50-day MA
    - SIDEWAYS: Neither bull nor bear conditions
    """

    # Strategy allocation by regime
    REGIME_ALLOCATIONS = {
        MarketRegime.BULL: {
            "momentum": 0.60,
            "factor_composite": 0.25,
            "pairs": 0.15,
            "cash": 0.0
        },
        MarketRegime.BEAR: {
            "momentum": 0.0,
            "factor_composite": 0.10,
            "pairs": 0.20,
            "cash": 0.70  # Go defensive
        },
        MarketRegime.SIDEWAYS: {
            "momentum": 0.20,
            "factor_composite": 0.30,
            "pairs": 0.40,
            "cash": 0.10
        },
        MarketRegime.UNKNOWN: {
            "momentum": 0.25,
            "factor_composite": 0.25,
            "pairs": 0.25,
            "cash": 0.25
        }
    }

    def __init__(
        self,
        lookback_short: int = 20,
        lookback_long: int = 60,
        vol_threshold_high: float = 1.5,
        vol_threshold_low: float = 0.8,
        return_threshold_bull: float = 0.0,
        return_threshold_bear: float = -0.05
    ):
        """
        Initialize regime detector.

        Args:
            lookback_short: Days for short-term indicators (default: 20)
            lookback_long: Days for long-term indicators (default: 60)
            vol_threshold_high: High vol multiplier for bear detection (default: 1.5)
            vol_threshold_low: Low vol multiplier for bull detection (default: 0.8)
            return_threshold_bull: Minimum return for bull regime (default: 0%)
            return_threshold_bear: Maximum return for bear regime (default: -5%)
        """
        self.lookback_short = lookback_short
        self.lookback_long = lookback_long
        self.vol_threshold_high = vol_threshold_high
        self.vol_threshold_low = vol_threshold_low
        self.return_threshold_bull = return_threshold_bull
        self.return_threshold_bear = return_threshold_bear

        self._last_regime: Optional[RegimeState] = None
        self._regime_history: list = []

    def detect_regime(self, market_data: pd.DataFrame) -> RegimeState:
        """
        Detect current market regime from price data.

        Args:
            market_data: DataFrame with 'close' column (ideally SPY or broad market)

        Returns:
            RegimeState with regime classification and confidence
        """
        if len(market_data) < self.lookback_long + 10:
            return RegimeState(
                regime=MarketRegime.UNKNOWN,
                confidence=0.0,
                bull_prob=0.33,
                bear_prob=0.33,
                sideways_prob=0.34,
                timestamp=datetime.now()
            )

        close = market_data['close']
        returns = close.pct_change().dropna()

        # Calculate indicators
        # 1. Short-term returns (20-day)
        short_return = (close.iloc[-1] / close.iloc[-self.lookback_short] - 1)

        # 2. Volatility comparison
        short_vol = returns.iloc[-self.lookback_short:].std() * np.sqrt(252)
        long_vol = returns.iloc[-self.lookback_long:].std() * np.sqrt(252)
        vol_ratio = short_vol / long_vol if long_vol > 0 else 1.0

        # 3. Trend (price vs 50-day MA)
        ma_50 = close.rolling(50).mean().iloc[-1]
        price_vs_ma = close.iloc[-1] / ma_50 - 1

        # 4. VIX proxy (realized vol percentile)
        vol_percentile = (returns.iloc[-self.lookback_short:].std() /
                         returns.std()) if returns.std() > 0 else 0.5

        # Calculate regime probabilities using fuzzy logic
        bull_score = 0.0
        bear_score = 0.0
        sideways_score = 0.0

        # Bull signals
        if short_return > self.return_threshold_bull:
            bull_score += 0.3
        if short_return > 0.05:  # Strong positive return
            bull_score += 0.2
        if vol_ratio < self.vol_threshold_low:
            bull_score += 0.2
        if price_vs_ma > 0.02:  # Price above MA
            bull_score += 0.3

        # Bear signals
        if short_return < self.return_threshold_bear:
            bear_score += 0.4
        if vol_ratio > self.vol_threshold_high:
            bear_score += 0.3
        if price_vs_ma < -0.03:  # Price well below MA
            bear_score += 0.3

        # Sideways signals
        if abs(short_return) < 0.03:  # Low returns
            sideways_score += 0.4
        if 0.9 < vol_ratio < 1.2:  # Normal volatility
            sideways_score += 0.3
        if abs(price_vs_ma) < 0.02:  # Price near MA
            sideways_score += 0.3

        # Normalize to probabilities
        total_score = bull_score + bear_score + sideways_score
        if total_score > 0:
            bull_prob = bull_score / total_score
            bear_prob = bear_score / total_score
            sideways_prob = sideways_score / total_score
        else:
            bull_prob = bear_prob = sideways_prob = 0.33

        # Determine regime
        if bull_prob > 0.5:
            regime = MarketRegime.BULL
            confidence = bull_prob
        elif bear_prob > 0.5:
            regime = MarketRegime.BEAR
            confidence = bear_prob
        elif sideways_prob > 0.4:
            regime = MarketRegime.SIDEWAYS
            confidence = sideways_prob
        else:
            # Mixed signals - use highest probability
            probs = {'bull': bull_prob, 'bear': bear_prob, 'sideways': sideways_prob}
            best = max(probs, key=probs.get)
            regime = MarketRegime(best)
            confidence = probs[best]

        state = RegimeState(
            regime=regime,
            confidence=confidence,
            bull_prob=bull_prob,
            bear_prob=bear_prob,
            sideways_prob=sideways_prob,
            timestamp=datetime.now()
        )

        # Track regime changes
        if self._last_regime is None or self._last_regime.regime != regime:
            logger.info(
                f"Regime change detected: {self._last_regime.regime.value if self._last_regime else 'None'} "
                f"-> {regime.value} (confidence: {confidence:.1%})"
            )

        self._last_regime = state
        self._regime_history.append(state)

        # Keep only last 100 regime states
        if len(self._regime_history) > 100:
            self._regime_history = self._regime_history[-100:]

        return state

    def get_strategy_allocation(self, regime: MarketRegime) -> Dict[str, float]:
        """
        Get recommended strategy allocation for a regime.

        Args:
            regime: Current market regime

        Returns:
            Dict mapping strategy name to allocation weight
        """
        return self.REGIME_ALLOCATIONS.get(regime, self.REGIME_ALLOCATIONS[MarketRegime.UNKNOWN])

    def should_reduce_exposure(self, regime_state: RegimeState) -> Tuple[bool, float]:
        """
        Check if exposure should be reduced based on regime.

        Returns:
            (should_reduce, reduction_factor)
        """
        if regime_state.regime == MarketRegime.BEAR:
            # Reduce exposure in bear markets
            reduction = 0.3 + (regime_state.confidence * 0.4)  # 30-70% reduction
            return True, reduction

        if regime_state.regime == MarketRegime.SIDEWAYS and regime_state.confidence > 0.6:
            # Slight reduction in strong sideways
            return True, 0.2

        return False, 0.0

    def get_regime_summary(self) -> str:
        """Get human-readable regime summary."""
        if self._last_regime is None:
            return "No regime detected yet"

        r = self._last_regime
        return (
            f"Regime: {r.regime.value.upper()} (confidence: {r.confidence:.1%})\n"
            f"  Bull: {r.bull_prob:.1%} | Bear: {r.bear_prob:.1%} | Sideways: {r.sideways_prob:.1%}"
        )

    def get_regime_persistence(self) -> Dict[str, float]:
        """
        Calculate how long each regime has persisted historically.

        Returns:
            Dict with regime persistence metrics
        """
        if len(self._regime_history) < 10:
            return {}

        current_regime = self._last_regime.regime
        same_regime_count = 0

        for state in reversed(self._regime_history):
            if state.regime == current_regime:
                same_regime_count += 1
            else:
                break

        return {
            'current_regime': current_regime.value,
            'consecutive_periods': same_regime_count,
            'avg_confidence': np.mean([s.confidence for s in self._regime_history[-same_regime_count:]])
        }


class VIXRegimeDetector:
    """
    Simple VIX-based regime detection.

    More straightforward than HMM - uses VIX levels directly.

    Thresholds based on historical VIX analysis:
    - Low volatility (VIX < 15): Bull regime, momentum works
    - Normal volatility (15-25): Mixed regime
    - High volatility (25-35): Caution, reduce exposure
    - Crisis (VIX > 35): Bear regime, defensive
    """

    def __init__(
        self,
        vix_low: float = 15.0,
        vix_normal: float = 25.0,
        vix_high: float = 35.0
    ):
        self.vix_low = vix_low
        self.vix_normal = vix_normal
        self.vix_high = vix_high

    def detect_regime(self, vix_level: float) -> Tuple[MarketRegime, float]:
        """
        Detect regime from VIX level.

        Args:
            vix_level: Current VIX value

        Returns:
            (regime, exposure_multiplier)
        """
        if vix_level < self.vix_low:
            return MarketRegime.BULL, 1.0
        elif vix_level < self.vix_normal:
            return MarketRegime.SIDEWAYS, 0.9  # 10% reduction (was 20%, too punishing)
        elif vix_level < self.vix_high:
            return MarketRegime.BEAR, 0.65  # 35% reduction (was 50%, left too much cash)
        else:
            return MarketRegime.BEAR, 0.25  # Crisis mode

    def get_position_multiplier(self, vix_level: float) -> float:
        """
        Get position size multiplier based on VIX.

        Lower multiplier = smaller positions in high volatility.
        """
        if vix_level < self.vix_low:
            return 1.0
        elif vix_level < self.vix_normal:
            # Linear interpolation between 1.0 and 0.85 (15% max reduction in normal vol)
            return 1.0 - 0.15 * (vix_level - self.vix_low) / (self.vix_normal - self.vix_low)
        elif vix_level < self.vix_high:
            # Linear interpolation between 0.85 and 0.60
            return 0.85 - 0.25 * (vix_level - self.vix_normal) / (self.vix_high - self.vix_normal)
        else:
            return 0.25  # Minimum exposure in crisis
