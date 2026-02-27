"""
Dynamic Position Sizing System

Implements institutional-grade dynamic position sizing that adapts to:
1. Volatility conditions (reduce size in high vol)
2. Correlation between positions (reduce size when highly correlated)
3. Market regimes (reduce in bear markets)
4. Live trading results (Kelly criterion with actual edge)

Academic References:
- Thorp (1969): "Optimal Gambling Systems for Favorable Games" - Kelly Criterion
- Grinold & Kahn (2000): "Active Portfolio Management" - Information Ratio, risk budgeting
- Prado (2018): "Advances in Financial Machine Learning" - bet sizing, correlation clustering
- Peters (1999): "Optimal Leverage from Non-Ergodicity" - fractional Kelly for safety
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class VolatilityRegime(Enum):
    """Volatility regime classification."""
    VERY_LOW = "very_low"    # VIX < 12
    LOW = "low"              # VIX 12-15
    NORMAL = "normal"        # VIX 15-20
    ELEVATED = "elevated"    # VIX 20-30
    HIGH = "high"            # VIX 30-40
    EXTREME = "extreme"      # VIX > 40


class MarketRegime(Enum):
    """Market regime classification."""
    STRONG_BULL = "strong_bull"      # SPY > 200MA, rising strongly
    BULL = "bull"                    # SPY > 200MA
    NEUTRAL = "neutral"              # SPY near 200MA
    BEAR = "bear"                    # SPY < 200MA
    STRONG_BEAR = "strong_bear"      # SPY << 200MA, falling


@dataclass
class PositionSizeParams:
    """Parameters for position size calculation."""
    symbol: str
    base_size_pct: float              # Base allocation (0-1)
    volatility_scalar: float          # Volatility adjustment (0.5-1.5)
    correlation_scalar: float         # Correlation adjustment (0.5-1.0)
    regime_scalar: float              # Regime adjustment (0.5-1.5)
    kelly_scalar: float               # Kelly adjustment based on edge (0-2.0)
    final_size_pct: float             # Final position size (0-1)
    reasoning: List[str]              # Explanation of adjustments


class DynamicPositionSizer:
    """
    Dynamic position sizing that adapts to market conditions.

    Key features:
    1. Volatility adjustment: Reduce size in high vol to maintain constant dollar risk
    2. Correlation adjustment: Reduce size when portfolio is highly correlated
    3. Regime adjustment: Reduce size in bear markets, increase in bull markets
    4. Kelly sizing: Use actual win rate and payoff ratio from live results

    All adjustments are multiplicative and conservative (biased toward smaller sizes).
    """

    def __init__(
        self,
        base_position_pct: float = 0.10,        # 10% base position
        max_position_pct: float = 0.15,         # 15% maximum
        min_position_pct: float = 0.02,         # 2% minimum
        kelly_fraction: float = 0.25,           # Quarter Kelly for safety

        # Volatility thresholds
        target_position_volatility: float = 0.15,  # Target 15% annualized position volatility

        # Correlation thresholds
        low_correlation_threshold: float = 0.3,    # Below this is diversified
        high_correlation_threshold: float = 0.7,   # Above this is highly correlated

        # VIX thresholds
        vix_normal_low: float = 15.0,
        vix_normal_high: float = 20.0,
        vix_elevated: float = 30.0,
        vix_high: float = 40.0,

        # Trade statistics for Kelly
        min_trades_for_kelly: int = 20,            # Need 20+ trades for reliable stats
    ):
        """
        Initialize dynamic position sizer.

        Args:
            base_position_pct: Starting position size (before adjustments)
            max_position_pct: Maximum allowed position size
            min_position_pct: Minimum position size (0 to disable)
            kelly_fraction: Fraction of Kelly to use (0.25 = quarter Kelly)
            target_position_volatility: Target volatility per position
            low_correlation_threshold: Correlation threshold for diversified portfolio
            high_correlation_threshold: Correlation threshold for concentrated portfolio
            vix_normal_low: VIX level defining low end of normal range
            vix_normal_high: VIX level defining high end of normal range
            vix_elevated: VIX level defining elevated volatility
            vix_high: VIX level defining high volatility
            min_trades_for_kelly: Minimum trades needed to use Kelly sizing
        """
        self.base_position_pct = base_position_pct
        self.max_position_pct = max_position_pct
        self.min_position_pct = min_position_pct
        self.kelly_fraction = kelly_fraction

        self.target_position_volatility = target_position_volatility

        self.low_correlation_threshold = low_correlation_threshold
        self.high_correlation_threshold = high_correlation_threshold

        self.vix_normal_low = vix_normal_low
        self.vix_normal_high = vix_normal_high
        self.vix_elevated = vix_elevated
        self.vix_high = vix_high

        self.min_trades_for_kelly = min_trades_for_kelly

        # Track trade results for Kelly calculation
        self._trade_results: List[Dict] = []

        logger.info(
            "DynamicPositionSizer initialized",
            extra={
                "base_pct": base_position_pct,
                "max_pct": max_position_pct,
                "kelly_fraction": kelly_fraction,
                "target_volatility": target_position_volatility
            }
        )

    def get_volatility_regime(self, vix: float) -> VolatilityRegime:
        """Classify volatility regime based on VIX."""
        if vix < 12:
            return VolatilityRegime.VERY_LOW
        elif vix < self.vix_normal_low:
            return VolatilityRegime.LOW
        elif vix < self.vix_normal_high:
            return VolatilityRegime.NORMAL
        elif vix < self.vix_elevated:
            return VolatilityRegime.ELEVATED
        elif vix < self.vix_high:
            return VolatilityRegime.HIGH
        else:
            return VolatilityRegime.EXTREME

    def calculate_volatility_scalar(
        self,
        asset_volatility: float,
        vix: float
    ) -> Tuple[float, str]:
        """
        Calculate position size adjustment based on volatility.

        Two approaches:
        1. Asset-specific: Scale position inversely to asset volatility
        2. Market-wide: Reduce all positions in high VIX environments

        Args:
            asset_volatility: Annualized volatility of the asset
            vix: Current VIX level

        Returns:
            (scalar, reasoning)
        """
        reasoning_parts = []

        # Asset-specific volatility scaling
        # Target: constant dollar risk across positions
        # If asset vol = 30% and target = 15%, scalar = 15/30 = 0.5
        if asset_volatility > 0:
            vol_scalar = min(
                1.5,  # Max 1.5x for low vol assets
                self.target_position_volatility / asset_volatility
            )
            vol_scalar = max(0.5, vol_scalar)  # Min 0.5x for high vol assets
            reasoning_parts.append(
                f"asset_vol={asset_volatility:.1%} -> {vol_scalar:.2f}x"
            )
        else:
            vol_scalar = 1.0
            reasoning_parts.append("no vol data, using 1.0x")

        # Market-wide VIX adjustment
        regime = self.get_volatility_regime(vix)

        if regime == VolatilityRegime.VERY_LOW:
            vix_scalar = 1.2  # Can use slightly larger positions
        elif regime == VolatilityRegime.LOW:
            vix_scalar = 1.1
        elif regime == VolatilityRegime.NORMAL:
            vix_scalar = 1.0
        elif regime == VolatilityRegime.ELEVATED:
            vix_scalar = 0.8
        elif regime == VolatilityRegime.HIGH:
            vix_scalar = 0.6
        else:  # EXTREME
            vix_scalar = 0.4

        reasoning_parts.append(f"VIX={vix:.1f} ({regime.value}) -> {vix_scalar:.2f}x")

        # Combined scalar (multiplicative)
        combined_scalar = vol_scalar * vix_scalar

        return combined_scalar, "; ".join(reasoning_parts)

    def calculate_correlation_scalar(
        self,
        symbol: str,
        portfolio_returns: pd.DataFrame,
        new_asset_returns: pd.Series
    ) -> Tuple[float, str]:
        """
        Calculate position size adjustment based on correlation to existing portfolio.

        High correlation = concentrated risk = smaller positions
        Low correlation = diversification = can use larger positions

        Args:
            symbol: Symbol being sized
            portfolio_returns: DataFrame of existing position returns
            new_asset_returns: Series of new asset returns

        Returns:
            (scalar, reasoning)
        """
        if portfolio_returns.empty or len(new_asset_returns) < 20:
            return 1.0, "insufficient data for correlation analysis"

        # Calculate correlation with existing portfolio
        portfolio_aggregate = portfolio_returns.mean(axis=1)

        # Align dates
        common_dates = portfolio_aggregate.index.intersection(new_asset_returns.index)
        if len(common_dates) < 20:
            return 1.0, "insufficient overlapping data"

        portfolio_aligned = portfolio_aggregate.loc[common_dates]
        asset_aligned = new_asset_returns.loc[common_dates]

        correlation = portfolio_aligned.corr(asset_aligned)

        # Convert correlation to scalar
        # High correlation (>0.7) = reduce to 0.5x
        # Low correlation (<0.3) = can use 1.0x
        # Negative correlation = can use 1.2x (hedge)

        if correlation < -0.3:
            # Negative correlation is valuable (hedge)
            scalar = 1.2
            reason = f"negative correlation ({correlation:.2f}) - hedge value"
        elif correlation < self.low_correlation_threshold:
            # Good diversification
            scalar = 1.0
            reason = f"low correlation ({correlation:.2f}) - well diversified"
        elif correlation < self.high_correlation_threshold:
            # Moderate correlation
            scalar = 0.8
            reason = f"moderate correlation ({correlation:.2f})"
        else:
            # High correlation - concentrated risk
            scalar = 0.6
            reason = f"high correlation ({correlation:.2f}) - concentrated risk"

        return scalar, reason

    def calculate_regime_scalar(
        self,
        spy_data: pd.DataFrame
    ) -> Tuple[float, str]:
        """
        Calculate position size adjustment based on market regime.

        Bear markets: reduce size (higher correlation, more downside risk)
        Bull markets: can use normal or slightly larger size

        Args:
            spy_data: DataFrame with SPY price history (needs 'close' column)

        Returns:
            (scalar, reasoning)
        """
        if len(spy_data) < 200:
            return 1.0, "insufficient data for regime detection"

        # Calculate 200-day moving average
        spy_data = spy_data.copy()
        spy_data['ma200'] = spy_data['close'].rolling(200).mean()

        latest = spy_data.iloc[-1]
        price = latest['close']
        ma200 = latest['ma200']

        if pd.isna(ma200):
            return 1.0, "MA200 not available"

        # Distance from MA200
        distance_pct = (price - ma200) / ma200

        # Classify regime
        if distance_pct > 0.10:
            regime = MarketRegime.STRONG_BULL
            scalar = 1.2  # Can be more aggressive in strong bull markets
        elif distance_pct > 0:
            regime = MarketRegime.BULL
            scalar = 1.0
        elif distance_pct > -0.05:
            regime = MarketRegime.NEUTRAL
            scalar = 0.9
        elif distance_pct > -0.10:
            regime = MarketRegime.BEAR
            scalar = 0.7  # Reduce size in bear markets
        else:
            regime = MarketRegime.STRONG_BEAR
            scalar = 0.5  # Significant reduction in strong bear

        reason = f"{regime.value}: SPY {distance_pct:+.1%} from 200MA"

        return scalar, reason

    def calculate_kelly_scalar(
        self,
        strategy: str,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None
    ) -> Tuple[float, str]:
        """
        Calculate position size adjustment using Kelly Criterion.

        Kelly formula: f* = (p*b - q) / b
        where:
            p = win rate
            q = loss rate (1-p)
            b = win/loss ratio (avg_win / avg_loss)

        We use fractional Kelly (default 0.25) for safety.

        Args:
            strategy: Strategy name (to look up historical results)
            win_rate: Override win rate (if None, calculate from trade history)
            avg_win: Override average win
            avg_loss: Override average loss

        Returns:
            (scalar, reasoning)
        """
        # Calculate from trade history if not provided
        if win_rate is None or avg_win is None or avg_loss is None:
            strategy_trades = [
                t for t in self._trade_results
                if t.get('strategy') == strategy
            ]

            if len(strategy_trades) < self.min_trades_for_kelly:
                return 1.0, f"insufficient trades ({len(strategy_trades)}/{self.min_trades_for_kelly})"

            wins = [t['pnl_pct'] for t in strategy_trades if t['pnl_pct'] > 0]
            losses = [abs(t['pnl_pct']) for t in strategy_trades if t['pnl_pct'] <= 0]

            if not wins or not losses:
                return 1.0, "no wins or losses to calculate Kelly"

            win_rate = len(wins) / len(strategy_trades)
            avg_win = np.mean(wins)
            avg_loss = np.mean(losses)

        # Kelly calculation
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return 1.0, "invalid Kelly inputs"

        b = avg_win / avg_loss  # Win/loss ratio
        p = win_rate
        q = 1 - p

        kelly_fraction_full = (p * b - q) / b

        if kelly_fraction_full <= 0:
            # Negative edge - should not trade
            return 0.0, "negative Kelly (no edge detected)"

        # Apply Kelly fraction for safety (typically 0.25)
        kelly_adjusted = kelly_fraction_full * self.kelly_fraction

        # Convert to scalar (Kelly gives fraction of bankroll)
        # We use it relative to base position size
        scalar = kelly_adjusted / self.base_position_pct
        scalar = min(2.0, scalar)  # Cap at 2x

        reason = (
            f"Kelly: win_rate={win_rate:.1%}, b={b:.2f} -> "
            f"full={kelly_fraction_full:.2%}, adjusted={kelly_adjusted:.2%}, "
            f"scalar={scalar:.2f}x"
        )

        return scalar, reason

    def calculate_position_size(
        self,
        symbol: str,
        portfolio_value: float,
        asset_volatility: float,
        vix: float,
        spy_data: Optional[pd.DataFrame] = None,
        portfolio_returns: Optional[pd.DataFrame] = None,
        new_asset_returns: Optional[pd.Series] = None,
        strategy: Optional[str] = None,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None
    ) -> PositionSizeParams:
        """
        Calculate dynamic position size with all adjustments.

        Args:
            symbol: Symbol to size
            portfolio_value: Total portfolio value
            asset_volatility: Annualized volatility of the asset
            vix: Current VIX level
            spy_data: SPY historical data for regime detection
            portfolio_returns: Existing portfolio returns for correlation
            new_asset_returns: Returns of new asset for correlation
            strategy: Strategy name for Kelly sizing
            win_rate: Override for Kelly calculation
            avg_win: Override for Kelly calculation
            avg_loss: Override for Kelly calculation

        Returns:
            PositionSizeParams with final size and reasoning
        """
        reasoning = []

        # Start with base size
        current_size = self.base_position_pct
        reasoning.append(f"Base: {current_size:.1%}")

        # 1. Volatility adjustment
        vol_scalar, vol_reason = self.calculate_volatility_scalar(
            asset_volatility, vix
        )
        current_size *= vol_scalar
        reasoning.append(f"Vol: {vol_reason}")

        # 2. Correlation adjustment
        corr_scalar = 1.0
        if portfolio_returns is not None and new_asset_returns is not None:
            corr_scalar, corr_reason = self.calculate_correlation_scalar(
                symbol, portfolio_returns, new_asset_returns
            )
            current_size *= corr_scalar
            reasoning.append(f"Corr: {corr_reason}")
        else:
            reasoning.append("Corr: no data, 1.0x")

        # 3. Regime adjustment
        regime_scalar = 1.0
        if spy_data is not None:
            regime_scalar, regime_reason = self.calculate_regime_scalar(spy_data)
            current_size *= regime_scalar
            reasoning.append(f"Regime: {regime_reason}")
        else:
            reasoning.append("Regime: no data, 1.0x")

        # 4. Kelly adjustment
        kelly_scalar = 1.0
        if strategy:
            kelly_scalar, kelly_reason = self.calculate_kelly_scalar(
                strategy, win_rate, avg_win, avg_loss
            )
            current_size *= kelly_scalar
            reasoning.append(f"Kelly: {kelly_reason}")
        else:
            reasoning.append("Kelly: no strategy, 1.0x")

        # Apply min/max bounds
        final_size = max(self.min_position_pct, min(self.max_position_pct, current_size))

        if final_size != current_size:
            if final_size == self.max_position_pct:
                reasoning.append(f"Capped at max: {self.max_position_pct:.1%}")
            elif final_size == self.min_position_pct:
                reasoning.append(f"Floored at min: {self.min_position_pct:.1%}")

        params = PositionSizeParams(
            symbol=symbol,
            base_size_pct=self.base_position_pct,
            volatility_scalar=vol_scalar,
            correlation_scalar=corr_scalar,
            regime_scalar=regime_scalar,
            kelly_scalar=kelly_scalar,
            final_size_pct=final_size,
            reasoning=reasoning
        )

        logger.info(
            f"Dynamic sizing for {symbol}: {final_size:.2%} "
            f"(vol={vol_scalar:.2f}x, corr={corr_scalar:.2f}x, "
            f"regime={regime_scalar:.2f}x, kelly={kelly_scalar:.2f}x)"
        )

        return params

    def record_trade_result(
        self,
        symbol: str,
        strategy: str,
        entry_price: float,
        exit_price: float,
        entry_time: datetime,
        exit_time: datetime,
        side: str = 'long'
    ) -> None:
        """
        Record trade result for Kelly calculation.

        Args:
            symbol: Symbol traded
            strategy: Strategy name
            entry_price: Entry price
            exit_price: Exit price
            entry_time: Entry timestamp
            exit_time: Exit timestamp
            side: 'long' or 'short'
        """
        if side == 'long':
            pnl_pct = (exit_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - exit_price) / entry_price

        holding_days = (exit_time - entry_time).days

        self._trade_results.append({
            'symbol': symbol,
            'strategy': strategy,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'entry_time': entry_time,
            'exit_time': exit_time,
            'pnl_pct': pnl_pct,
            'holding_days': holding_days,
            'side': side
        })

        # Keep only last 500 trades to prevent unbounded growth
        if len(self._trade_results) > 500:
            self._trade_results = self._trade_results[-500:]

        logger.debug(
            f"Recorded trade: {symbol} {strategy} "
            f"{pnl_pct:+.2%} ({holding_days} days)"
        )

    def get_strategy_statistics(self, strategy: str) -> Dict:
        """Get performance statistics for a strategy."""
        strategy_trades = [
            t for t in self._trade_results
            if t.get('strategy') == strategy
        ]

        if not strategy_trades:
            return {
                'trade_count': 0,
                'win_rate': None,
                'avg_win': None,
                'avg_loss': None,
                'avg_pnl': None
            }

        wins = [t['pnl_pct'] for t in strategy_trades if t['pnl_pct'] > 0]
        losses = [t['pnl_pct'] for t in strategy_trades if t['pnl_pct'] <= 0]
        all_pnl = [t['pnl_pct'] for t in strategy_trades]

        return {
            'trade_count': len(strategy_trades),
            'win_rate': len(wins) / len(strategy_trades) if strategy_trades else 0,
            'avg_win': np.mean(wins) if wins else 0,
            'avg_loss': abs(np.mean(losses)) if losses else 0,
            'avg_pnl': np.mean(all_pnl) if all_pnl else 0,
            'win_count': len(wins),
            'loss_count': len(losses)
        }
