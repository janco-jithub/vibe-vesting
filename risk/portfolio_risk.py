"""
Portfolio-Level Risk Controls

Implements comprehensive portfolio risk management:
1. Maximum portfolio heat (total risk across all positions)
2. Sector concentration limits
3. Correlation limits between positions
4. Daily/weekly drawdown limits with automatic position reduction
5. Margin utilization limits

Academic References:
- Grinold & Kahn (2000): "Active Portfolio Management" - risk budgeting
- Jorion (2006): "Value at Risk" - portfolio risk measurement
- Basel Committee (2019): "Minimum capital requirements for market risk"
- Markowitz (1952): "Portfolio Selection" - diversification theory
"""

import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, date, timedelta
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RiskViolationType(Enum):
    """Types of risk violations."""
    PORTFOLIO_HEAT = "portfolio_heat"
    SECTOR_CONCENTRATION = "sector_concentration"
    CORRELATION_LIMIT = "correlation_limit"
    DAILY_DRAWDOWN = "daily_drawdown"
    WEEKLY_DRAWDOWN = "weekly_drawdown"
    MARGIN_UTILIZATION = "margin_utilization"
    POSITION_COUNT = "position_count"


@dataclass
class PortfolioRiskMetrics:
    """Current portfolio risk metrics."""
    total_portfolio_value: float
    total_exposure: float
    cash: float

    # Heat metrics
    portfolio_heat: float              # Total dollar risk (sum of stop distances)
    portfolio_heat_pct: float          # Heat as % of portfolio

    # Sector exposure
    sector_exposures: Dict[str, float] # Sector -> exposure value
    sector_exposures_pct: Dict[str, float]  # Sector -> exposure %
    max_sector_exposure_pct: float     # Highest sector concentration

    # Correlation metrics
    avg_correlation: float             # Average correlation between positions
    max_correlation: float             # Maximum pairwise correlation

    # Drawdown
    daily_pnl: float
    daily_return_pct: float
    weekly_pnl: float
    weekly_return_pct: float
    max_drawdown_pct: float

    # Margin
    margin_used: float
    margin_available: float
    margin_utilization_pct: float

    # Position count
    position_count: int

    # Violations
    violations: List[Tuple[RiskViolationType, str]]

    timestamp: datetime


@dataclass
class RiskReductionAction:
    """Recommended action to reduce risk."""
    action_type: str  # 'reduce_position', 'close_position', 'halt_new_entries'
    symbol: Optional[str]
    current_size: float
    target_size: float
    reason: str
    urgency: str  # 'low', 'medium', 'high', 'critical'


class PortfolioRiskManager:
    """
    Portfolio-level risk management and monitoring.

    Enforces limits on:
    - Portfolio heat (total risk from all stop losses)
    - Sector concentration
    - Position correlation
    - Drawdowns (daily and weekly)
    - Margin utilization
    """

    def __init__(
        self,
        # Portfolio heat limits
        max_portfolio_heat_pct: float = 0.20,      # Max 20% total portfolio at risk

        # Sector limits
        max_sector_exposure_pct: float = 0.30,     # Max 30% in any sector
        max_single_position_pct: float = 0.15,     # Max 15% in single position

        # Correlation limits
        max_avg_correlation: float = 0.6,          # Max 0.6 average correlation
        max_pairwise_correlation: float = 0.8,     # Max 0.8 between any two positions

        # Drawdown limits
        daily_drawdown_limit: float = 0.02,        # -2% daily limit
        weekly_drawdown_limit: float = 0.05,       # -5% weekly limit
        max_drawdown_limit: float = 0.15,          # -15% max drawdown

        # Position limits
        max_positions: int = 10,                   # Max 10 concurrent positions

        # Margin limits
        max_margin_utilization: float = 0.50,      # Use max 50% of margin

        # Auto-reduction settings
        enable_auto_reduction: bool = True,         # Automatically reduce risk
        reduction_threshold_pct: float = 0.90,      # Reduce at 90% of limit
    ):
        """
        Initialize portfolio risk manager.

        Args:
            max_portfolio_heat_pct: Maximum total portfolio heat
            max_sector_exposure_pct: Maximum exposure to any sector
            max_single_position_pct: Maximum single position size
            max_avg_correlation: Maximum average correlation
            max_pairwise_correlation: Maximum correlation between any two positions
            daily_drawdown_limit: Daily drawdown limit (positive number, e.g., 0.02 = 2%)
            weekly_drawdown_limit: Weekly drawdown limit
            max_drawdown_limit: Maximum drawdown before intervention
            max_positions: Maximum number of positions
            max_margin_utilization: Maximum margin utilization
            enable_auto_reduction: Enable automatic risk reduction
            reduction_threshold_pct: Trigger reduction at this % of limit
        """
        self.max_portfolio_heat_pct = max_portfolio_heat_pct
        self.max_sector_exposure_pct = max_sector_exposure_pct
        self.max_single_position_pct = max_single_position_pct

        self.max_avg_correlation = max_avg_correlation
        self.max_pairwise_correlation = max_pairwise_correlation

        self.daily_drawdown_limit = daily_drawdown_limit
        self.weekly_drawdown_limit = weekly_drawdown_limit
        self.max_drawdown_limit = max_drawdown_limit

        self.max_positions = max_positions
        self.max_margin_utilization = max_margin_utilization

        self.enable_auto_reduction = enable_auto_reduction
        self.reduction_threshold_pct = reduction_threshold_pct

        # Track equity for drawdown calculation
        self._daily_start_equity: Optional[float] = None
        self._weekly_start_equity: Optional[float] = None
        self._peak_equity: Optional[float] = None
        self._last_update_date: Optional[date] = None

        # Sector mapping (symbol -> sector)
        self._sector_map: Dict[str, str] = {}

        logger.info(
            "PortfolioRiskManager initialized",
            extra={
                "max_heat": max_portfolio_heat_pct,
                "max_sector": max_sector_exposure_pct,
                "max_positions": max_positions,
                "daily_dd_limit": daily_drawdown_limit,
                "weekly_dd_limit": weekly_drawdown_limit
            }
        )

    def set_sector_map(self, sector_map: Dict[str, str]) -> None:
        """
        Set sector mapping for positions.

        Args:
            sector_map: Dict mapping symbol -> sector name
        """
        self._sector_map = sector_map
        logger.info(f"Sector map updated: {len(sector_map)} symbols")

    def calculate_portfolio_heat(
        self,
        positions: Dict[str, Dict]
    ) -> Tuple[float, float]:
        """
        Calculate total portfolio heat (dollar risk from stop losses).

        Portfolio heat = sum of (position_size * distance_to_stop) for all positions

        Args:
            positions: Dict of symbol -> position info (must have 'market_value', 'stop_loss', 'current_price')

        Returns:
            (heat_dollars, heat_pct)
        """
        total_heat = 0.0

        for symbol, pos in positions.items():
            market_value = pos.get('market_value', 0)
            current_price = pos.get('current_price', 0)
            stop_loss = pos.get('stop_loss')

            if stop_loss is None or current_price == 0:
                # No stop loss defined - assume 10% risk (conservative)
                position_heat = market_value * 0.10
            else:
                # Calculate distance to stop
                stop_distance_pct = abs(current_price - stop_loss) / current_price
                position_heat = market_value * stop_distance_pct

            total_heat += position_heat

        # Calculate as percentage of portfolio
        total_value = sum(p.get('market_value', 0) for p in positions.values())
        heat_pct = total_heat / total_value if total_value > 0 else 0

        return total_heat, heat_pct

    def calculate_sector_exposures(
        self,
        positions: Dict[str, Dict]
    ) -> Tuple[Dict[str, float], Dict[str, float]]:
        """
        Calculate exposure by sector.

        Args:
            positions: Dict of symbol -> position info

        Returns:
            (sector_values, sector_percentages)
        """
        sector_values = {}
        total_value = sum(p.get('market_value', 0) for p in positions.values())

        for symbol, pos in positions.items():
            sector = self._sector_map.get(symbol, 'Unknown')
            market_value = pos.get('market_value', 0)

            if sector not in sector_values:
                sector_values[sector] = 0
            sector_values[sector] += market_value

        # Calculate percentages
        sector_percentages = {
            sector: value / total_value if total_value > 0 else 0
            for sector, value in sector_values.items()
        }

        return sector_values, sector_percentages

    def calculate_correlation_metrics(
        self,
        returns_data: Dict[str, pd.Series]
    ) -> Tuple[float, float]:
        """
        Calculate correlation metrics for portfolio.

        Args:
            returns_data: Dict of symbol -> returns series

        Returns:
            (avg_correlation, max_correlation)
        """
        if len(returns_data) < 2:
            return 0.0, 0.0

        # Build correlation matrix
        symbols = list(returns_data.keys())
        correlations = []
        max_corr = 0.0

        for i, sym1 in enumerate(symbols):
            for sym2 in symbols[i+1:]:
                # Find common dates
                common_dates = returns_data[sym1].index.intersection(
                    returns_data[sym2].index
                )

                if len(common_dates) < 20:
                    continue

                ret1 = returns_data[sym1].loc[common_dates]
                ret2 = returns_data[sym2].loc[common_dates]

                corr = ret1.corr(ret2)
                if not np.isnan(corr):
                    correlations.append(abs(corr))
                    max_corr = max(max_corr, abs(corr))

        avg_corr = np.mean(correlations) if correlations else 0.0

        return avg_corr, max_corr

    def calculate_drawdown_metrics(
        self,
        current_equity: float,
        current_date: date
    ) -> Tuple[float, float, float, float]:
        """
        Calculate daily P&L, weekly P&L, and drawdown.

        Args:
            current_equity: Current portfolio equity
            current_date: Current date

        Returns:
            (daily_pnl, daily_return_pct, weekly_pnl, weekly_return_pct)
        """
        # Initialize tracking on first call
        if self._daily_start_equity is None:
            self._daily_start_equity = current_equity
            self._weekly_start_equity = current_equity
            self._peak_equity = current_equity
            self._last_update_date = current_date

        # Check for new day
        if current_date > self._last_update_date:
            self._daily_start_equity = current_equity

            # Check for new week (Monday)
            if current_date.weekday() == 0:
                self._weekly_start_equity = current_equity

            self._last_update_date = current_date

        # Update peak
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        # Calculate metrics
        daily_pnl = current_equity - self._daily_start_equity
        daily_return_pct = daily_pnl / self._daily_start_equity if self._daily_start_equity > 0 else 0

        weekly_pnl = current_equity - self._weekly_start_equity
        weekly_return_pct = weekly_pnl / self._weekly_start_equity if self._weekly_start_equity > 0 else 0

        return daily_pnl, daily_return_pct, weekly_pnl, weekly_return_pct

    def calculate_metrics(
        self,
        positions: Dict[str, Dict],
        portfolio_value: float,
        cash: float,
        margin_used: float,
        margin_available: float,
        returns_data: Optional[Dict[str, pd.Series]] = None,
        current_date: Optional[date] = None
    ) -> PortfolioRiskMetrics:
        """
        Calculate comprehensive portfolio risk metrics.

        Args:
            positions: Dict of symbol -> position info
            portfolio_value: Total portfolio value
            cash: Cash balance
            margin_used: Margin currently used
            margin_available: Total margin available
            returns_data: Optional dict of symbol -> returns for correlation
            current_date: Current date for drawdown tracking

        Returns:
            PortfolioRiskMetrics object
        """
        current_date = current_date or date.today()

        # Portfolio heat
        heat_dollars, heat_pct = self.calculate_portfolio_heat(positions)

        # Sector exposures
        sector_values, sector_pcts = self.calculate_sector_exposures(positions)
        max_sector_pct = max(sector_pcts.values()) if sector_pcts else 0.0

        # Correlation
        avg_corr, max_corr = 0.0, 0.0
        if returns_data:
            avg_corr, max_corr = self.calculate_correlation_metrics(returns_data)

        # Drawdown metrics
        daily_pnl, daily_ret, weekly_pnl, weekly_ret = self.calculate_drawdown_metrics(
            portfolio_value, current_date
        )

        # Max drawdown
        max_dd_pct = 0.0
        if self._peak_equity and self._peak_equity > 0:
            max_dd_pct = (portfolio_value - self._peak_equity) / self._peak_equity

        # Margin utilization
        margin_util_pct = margin_used / margin_available if margin_available > 0 else 0

        # Position count
        position_count = len(positions)

        # Total exposure
        total_exposure = sum(p.get('market_value', 0) for p in positions.values())

        # Check violations
        violations = []

        if heat_pct > self.max_portfolio_heat_pct:
            violations.append((
                RiskViolationType.PORTFOLIO_HEAT,
                f"Portfolio heat {heat_pct:.1%} > limit {self.max_portfolio_heat_pct:.1%}"
            ))

        if max_sector_pct > self.max_sector_exposure_pct:
            violations.append((
                RiskViolationType.SECTOR_CONCENTRATION,
                f"Sector concentration {max_sector_pct:.1%} > limit {self.max_sector_exposure_pct:.1%}"
            ))

        if avg_corr > self.max_avg_correlation:
            violations.append((
                RiskViolationType.CORRELATION_LIMIT,
                f"Avg correlation {avg_corr:.2f} > limit {self.max_avg_correlation:.2f}"
            ))

        if daily_ret < -self.daily_drawdown_limit:
            violations.append((
                RiskViolationType.DAILY_DRAWDOWN,
                f"Daily return {daily_ret:.2%} < limit {-self.daily_drawdown_limit:.2%}"
            ))

        if weekly_ret < -self.weekly_drawdown_limit:
            violations.append((
                RiskViolationType.WEEKLY_DRAWDOWN,
                f"Weekly return {weekly_ret:.2%} < limit {-self.weekly_drawdown_limit:.2%}"
            ))

        if max_dd_pct < -self.max_drawdown_limit:
            violations.append((
                RiskViolationType.CORRELATION_LIMIT,
                f"Max drawdown {max_dd_pct:.2%} < limit {-self.max_drawdown_limit:.2%}"
            ))

        if margin_util_pct > self.max_margin_utilization:
            violations.append((
                RiskViolationType.MARGIN_UTILIZATION,
                f"Margin utilization {margin_util_pct:.1%} > limit {self.max_margin_utilization:.1%}"
            ))

        if position_count > self.max_positions:
            violations.append((
                RiskViolationType.POSITION_COUNT,
                f"Position count {position_count} > limit {self.max_positions}"
            ))

        metrics = PortfolioRiskMetrics(
            total_portfolio_value=portfolio_value,
            total_exposure=total_exposure,
            cash=cash,
            portfolio_heat=heat_dollars,
            portfolio_heat_pct=heat_pct,
            sector_exposures=sector_values,
            sector_exposures_pct=sector_pcts,
            max_sector_exposure_pct=max_sector_pct,
            avg_correlation=avg_corr,
            max_correlation=max_corr,
            daily_pnl=daily_pnl,
            daily_return_pct=daily_ret,
            weekly_pnl=weekly_pnl,
            weekly_return_pct=weekly_ret,
            max_drawdown_pct=max_dd_pct,
            margin_used=margin_used,
            margin_available=margin_available,
            margin_utilization_pct=margin_util_pct,
            position_count=position_count,
            violations=violations,
            timestamp=datetime.now()
        )

        if violations:
            logger.warning(
                f"RISK VIOLATIONS: {len(violations)} violations detected",
                extra={'violations': [v[1] for v in violations]}
            )

        return metrics

    def get_risk_reduction_actions(
        self,
        metrics: PortfolioRiskMetrics,
        positions: Dict[str, Dict]
    ) -> List[RiskReductionAction]:
        """
        Generate recommended actions to reduce risk.

        Args:
            metrics: Current portfolio risk metrics
            positions: Current positions

        Returns:
            List of recommended actions
        """
        if not self.enable_auto_reduction:
            return []

        actions = []

        # Portfolio heat too high - reduce largest positions
        if metrics.portfolio_heat_pct > self.max_portfolio_heat_pct * self.reduction_threshold_pct:
            # Sort positions by risk contribution
            position_risks = []
            for symbol, pos in positions.items():
                market_value = pos.get('market_value', 0)
                current_price = pos.get('current_price', 0)
                stop_loss = pos.get('stop_loss')

                if stop_loss and current_price > 0:
                    stop_distance_pct = abs(current_price - stop_loss) / current_price
                    risk = market_value * stop_distance_pct
                else:
                    risk = market_value * 0.10

                position_risks.append((symbol, risk, market_value))

            # Sort by risk contribution (highest first)
            position_risks.sort(key=lambda x: x[1], reverse=True)

            # Reduce top 2-3 positions
            for symbol, risk, market_value in position_risks[:3]:
                # Reduce by 30%
                target_size = market_value * 0.7

                actions.append(RiskReductionAction(
                    action_type='reduce_position',
                    symbol=symbol,
                    current_size=market_value,
                    target_size=target_size,
                    reason=f"Portfolio heat at {metrics.portfolio_heat_pct:.1%}",
                    urgency='high'
                ))

        # Sector concentration too high - reduce largest position in overweight sector
        if metrics.max_sector_exposure_pct > self.max_sector_exposure_pct * self.reduction_threshold_pct:
            overweight_sector = max(
                metrics.sector_exposures_pct.items(),
                key=lambda x: x[1]
            )[0]

            # Find largest position in that sector
            sector_positions = [
                (sym, pos) for sym, pos in positions.items()
                if self._sector_map.get(sym) == overweight_sector
            ]

            if sector_positions:
                largest_sym, largest_pos = max(
                    sector_positions,
                    key=lambda x: x[1].get('market_value', 0)
                )

                market_value = largest_pos.get('market_value', 0)
                target_size = market_value * 0.7

                actions.append(RiskReductionAction(
                    action_type='reduce_position',
                    symbol=largest_sym,
                    current_size=market_value,
                    target_size=target_size,
                    reason=f"Sector {overweight_sector} at {metrics.max_sector_exposure_pct:.1%}",
                    urgency='medium'
                ))

        # Daily drawdown hit - halt new entries
        if metrics.daily_return_pct < -self.daily_drawdown_limit * self.reduction_threshold_pct:
            actions.append(RiskReductionAction(
                action_type='halt_new_entries',
                symbol=None,
                current_size=0,
                target_size=0,
                reason=f"Daily drawdown at {metrics.daily_return_pct:.2%}",
                urgency='high'
            ))

        # Max drawdown hit - close smallest/worst positions
        if metrics.max_drawdown_pct < -self.max_drawdown_limit * self.reduction_threshold_pct:
            # Close losing positions
            losing_positions = [
                (sym, pos) for sym, pos in positions.items()
                if pos.get('unrealized_plpc', 0) < 0
            ]

            # Sort by P&L (worst first)
            losing_positions.sort(key=lambda x: x[1].get('unrealized_plpc', 0))

            for symbol, pos in losing_positions[:2]:  # Close worst 2
                actions.append(RiskReductionAction(
                    action_type='close_position',
                    symbol=symbol,
                    current_size=pos.get('market_value', 0),
                    target_size=0,
                    reason=f"Max drawdown at {metrics.max_drawdown_pct:.2%}",
                    urgency='critical'
                ))

        return actions

    def print_risk_summary(self, metrics: PortfolioRiskMetrics) -> None:
        """Print formatted risk summary."""
        print("\n" + "=" * 70)
        print("PORTFOLIO RISK SUMMARY")
        print("=" * 70)

        print(f"\nPortfolio Value: ${metrics.total_portfolio_value:,.2f}")
        print(f"Total Exposure:  ${metrics.total_exposure:,.2f}")
        print(f"Cash:            ${metrics.cash:,.2f}")

        print(f"\nPortfolio Heat: ${metrics.portfolio_heat:,.2f} "
              f"({metrics.portfolio_heat_pct:.1%} of portfolio)")
        print(f"  Limit: {self.max_portfolio_heat_pct:.1%}")
        status = "✓ OK" if metrics.portfolio_heat_pct <= self.max_portfolio_heat_pct else "✗ OVER LIMIT"
        print(f"  Status: {status}")

        print(f"\nSector Exposures:")
        for sector, pct in sorted(
            metrics.sector_exposures_pct.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            value = metrics.sector_exposures[sector]
            print(f"  {sector:20s}: ${value:>10,.0f} ({pct:>5.1%})")
        print(f"  Max Sector Limit: {self.max_sector_exposure_pct:.1%}")

        print(f"\nCorrelation:")
        print(f"  Average: {metrics.avg_correlation:.2f} (limit: {self.max_avg_correlation:.2f})")
        print(f"  Maximum: {metrics.max_correlation:.2f} (limit: {self.max_pairwise_correlation:.2f})")

        print(f"\nDrawdown:")
        print(f"  Daily:   {metrics.daily_return_pct:>+6.2%} (limit: {-self.daily_drawdown_limit:.2%})")
        print(f"  Weekly:  {metrics.weekly_return_pct:>+6.2%} (limit: {-self.weekly_drawdown_limit:.2%})")
        print(f"  Max DD:  {metrics.max_drawdown_pct:>+6.2%} (limit: {-self.max_drawdown_limit:.2%})")

        print(f"\nMargin:")
        print(f"  Used:      ${metrics.margin_used:,.2f}")
        print(f"  Available: ${metrics.margin_available:,.2f}")
        print(f"  Utilization: {metrics.margin_utilization_pct:.1%} (limit: {self.max_margin_utilization:.1%})")

        print(f"\nPositions: {metrics.position_count} / {self.max_positions}")

        if metrics.violations:
            print(f"\n⚠ VIOLATIONS ({len(metrics.violations)}):")
            for violation_type, message in metrics.violations:
                print(f"  - {message}")
        else:
            print(f"\n✓ All risk limits within acceptable ranges")

        print("=" * 70 + "\n")
