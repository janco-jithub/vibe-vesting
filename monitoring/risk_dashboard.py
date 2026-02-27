"""
Real-Time Risk Dashboard

Comprehensive real-time monitoring of:
1. Current VaR and CVaR
2. Portfolio beta and correlation
3. Sector exposures
4. Concentration risk
5. Margin utilization
6. Circuit breaker status

Provides both console display and data export for external monitoring.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, date
from pathlib import Path
import json
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class RiskDashboard:
    """
    Real-time risk monitoring dashboard.

    Aggregates data from all risk management components and
    presents unified view of portfolio risk.
    """

    def __init__(
        self,
        var_calculator,
        portfolio_risk_manager,
        circuit_breaker,
        adaptive_stop_manager,
        dynamic_sizer=None,
        export_dir: str = "logs/risk_snapshots"
    ):
        """
        Initialize risk dashboard.

        Args:
            var_calculator: VaRCalculator instance
            portfolio_risk_manager: PortfolioRiskManager instance
            circuit_breaker: CircuitBreaker instance
            adaptive_stop_manager: AdaptiveStopManager instance
            dynamic_sizer: DynamicPositionSizer instance (optional)
            export_dir: Directory for exporting risk snapshots
        """
        self.var_calculator = var_calculator
        self.portfolio_risk_manager = portfolio_risk_manager
        self.circuit_breaker = circuit_breaker
        self.adaptive_stop_manager = adaptive_stop_manager
        self.dynamic_sizer = dynamic_sizer

        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        logger.info("RiskDashboard initialized")

    def get_risk_snapshot(
        self,
        positions: Dict[str, Dict],
        portfolio_value: float,
        cash: float,
        margin_used: float,
        margin_available: float,
        returns_data: Optional[Dict[str, pd.Series]] = None,
        portfolio_returns: Optional[pd.Series] = None,
        spy_data: Optional[pd.DataFrame] = None,
        vix: float = 20.0
    ) -> Dict:
        """
        Get comprehensive risk snapshot.

        Args:
            positions: Current positions
            portfolio_value: Total portfolio value
            cash: Cash balance
            margin_used: Margin used
            margin_available: Total margin available
            returns_data: Position returns for correlation
            portfolio_returns: Portfolio return series for VaR
            spy_data: SPY data for beta calculation
            vix: Current VIX level

        Returns:
            Dict with all risk metrics
        """
        snapshot = {
            'timestamp': datetime.now().isoformat(),
            'portfolio_value': portfolio_value,
            'cash': cash,
            'vix': vix
        }

        # 1. VaR metrics
        if portfolio_returns is not None and len(portfolio_returns) >= 30:
            risk_metrics = self.var_calculator.calculate_all_metrics(portfolio_returns)
            within_limits, violations = self.var_calculator.check_risk_limits(risk_metrics)

            snapshot['var'] = {
                'var_95': risk_metrics.var_95,
                'var_99': risk_metrics.var_99,
                'cvar_95': risk_metrics.cvar_95,
                'cvar_99': risk_metrics.cvar_99,
                'volatility': risk_metrics.volatility,
                'max_drawdown': risk_metrics.max_drawdown,
                'skewness': risk_metrics.skewness,
                'kurtosis': risk_metrics.kurtosis,
                'within_limits': within_limits,
                'violations': violations
            }
        else:
            snapshot['var'] = {'status': 'insufficient_data'}

        # 2. Portfolio risk metrics
        portfolio_metrics = self.portfolio_risk_manager.calculate_metrics(
            positions=positions,
            portfolio_value=portfolio_value,
            cash=cash,
            margin_used=margin_used,
            margin_available=margin_available,
            returns_data=returns_data
        )

        snapshot['portfolio_risk'] = {
            'portfolio_heat': portfolio_metrics.portfolio_heat,
            'portfolio_heat_pct': portfolio_metrics.portfolio_heat_pct,
            'sector_exposures': portfolio_metrics.sector_exposures,
            'sector_exposures_pct': portfolio_metrics.sector_exposures_pct,
            'max_sector_exposure_pct': portfolio_metrics.max_sector_exposure_pct,
            'avg_correlation': portfolio_metrics.avg_correlation,
            'max_correlation': portfolio_metrics.max_correlation,
            'daily_pnl': portfolio_metrics.daily_pnl,
            'daily_return_pct': portfolio_metrics.daily_return_pct,
            'weekly_pnl': portfolio_metrics.weekly_pnl,
            'weekly_return_pct': portfolio_metrics.weekly_return_pct,
            'max_drawdown_pct': portfolio_metrics.max_drawdown_pct,
            'margin_utilization_pct': portfolio_metrics.margin_utilization_pct,
            'position_count': portfolio_metrics.position_count,
            'violations': [
                {'type': v[0].value, 'message': v[1]}
                for v in portfolio_metrics.violations
            ]
        }

        # 3. Circuit breaker status
        can_trade, halt_reason = self.circuit_breaker.can_trade()
        breaker_summary = self.circuit_breaker.get_risk_summary()

        snapshot['circuit_breaker'] = {
            'can_trade': can_trade,
            'halt_reason': halt_reason,
            'is_halted': self.circuit_breaker.state.is_halted,
            'summary': breaker_summary
        }

        # 4. Portfolio beta (if SPY data available)
        if spy_data is not None and portfolio_returns is not None and len(portfolio_returns) >= 30:
            # Calculate beta to SPY
            spy_returns = spy_data['close'].pct_change().dropna()

            # Align dates
            common_dates = spy_returns.index.intersection(portfolio_returns.index)
            if len(common_dates) >= 30:
                spy_aligned = spy_returns.loc[common_dates]
                port_aligned = portfolio_returns.loc[common_dates]

                # Calculate beta (covariance / variance)
                covariance = port_aligned.cov(spy_aligned)
                spy_variance = spy_aligned.var()
                beta = covariance / spy_variance if spy_variance > 0 else 0

                # Calculate correlation
                correlation = port_aligned.corr(spy_aligned)

                snapshot['market_exposure'] = {
                    'beta': beta,
                    'correlation_to_spy': correlation,
                    'market_exposure_pct': beta * 1.0  # Assume 100% invested
                }
        else:
            snapshot['market_exposure'] = {'status': 'insufficient_data'}

        # 5. Position-level risk
        position_risks = []
        for symbol, pos in positions.items():
            market_value = pos.get('market_value', 0)
            current_price = pos.get('current_price', 0)
            stop_loss = pos.get('stop_loss')

            # Calculate position risk
            if stop_loss and current_price > 0:
                risk_pct = abs(current_price - stop_loss) / current_price
                risk_dollars = market_value * risk_pct
            else:
                risk_pct = 0.10
                risk_dollars = market_value * risk_pct

            position_risks.append({
                'symbol': symbol,
                'market_value': market_value,
                'weight_pct': market_value / portfolio_value if portfolio_value > 0 else 0,
                'risk_dollars': risk_dollars,
                'risk_pct': risk_pct,
                'unrealized_pnl_pct': pos.get('unrealized_plpc', 0)
            })

        # Sort by risk contribution
        position_risks.sort(key=lambda x: x['risk_dollars'], reverse=True)
        snapshot['position_risks'] = position_risks

        # 6. Risk capacity remaining
        snapshot['risk_capacity'] = {
            'daily_loss_remaining': (
                self.circuit_breaker.daily_loss_limit -
                portfolio_metrics.daily_return_pct
            ),
            'weekly_loss_remaining': (
                self.circuit_breaker.weekly_loss_limit -
                portfolio_metrics.weekly_return_pct
            ),
            'drawdown_remaining': (
                self.circuit_breaker.max_drawdown_limit -
                portfolio_metrics.max_drawdown_pct
            ),
            'heat_remaining': (
                self.portfolio_risk_manager.max_portfolio_heat_pct -
                portfolio_metrics.portfolio_heat_pct
            ),
            'positions_remaining': (
                self.portfolio_risk_manager.max_positions -
                portfolio_metrics.position_count
            )
        }

        return snapshot

    def print_dashboard(self, snapshot: Dict) -> None:
        """Print formatted dashboard to console."""
        print("\n" + "=" * 100)
        print("REAL-TIME RISK DASHBOARD".center(100))
        print("=" * 100)
        print(f"Timestamp: {snapshot['timestamp']}")
        print(f"Portfolio Value: ${snapshot['portfolio_value']:,.2f} | "
              f"Cash: ${snapshot['cash']:,.2f} | VIX: {snapshot['vix']:.1f}")

        # Circuit breaker status
        print("\n" + "-" * 100)
        print("CIRCUIT BREAKER STATUS")
        print("-" * 100)
        cb = snapshot['circuit_breaker']
        status = "✓ ACTIVE" if cb['can_trade'] else "✗ HALTED"
        status_color = status

        print(f"Status: {status_color}")
        if cb['halt_reason']:
            print(f"  Reason: {cb['halt_reason']}")

        # VaR metrics
        print("\n" + "-" * 100)
        print("VALUE AT RISK (VaR)")
        print("-" * 100)
        if 'var_95' in snapshot['var']:
            var = snapshot['var']
            print(f"VaR (95%):  {var['var_95']:.2%}  |  VaR (99%):  {var['var_99']:.2%}")
            print(f"CVaR (95%): {var['cvar_95']:.2%}  |  CVaR (99%): {var['cvar_99']:.2%}")
            print(f"Volatility: {var['volatility']:.2%}  |  Max DD:     {var['max_drawdown']:.2%}")
            print(f"Skewness: {var['skewness']:>6.2f}  |  Kurtosis: {var['kurtosis']:>6.2f}")

            if not var['within_limits']:
                print("\n⚠ VaR VIOLATIONS:")
                for v in var['violations']:
                    print(f"  - {v}")
        else:
            print("  Insufficient data for VaR calculation")

        # Portfolio risk
        print("\n" + "-" * 100)
        print("PORTFOLIO RISK")
        print("-" * 100)
        pr = snapshot['portfolio_risk']

        # Heat
        heat_status = "✓" if pr['portfolio_heat_pct'] <= self.portfolio_risk_manager.max_portfolio_heat_pct else "✗"
        print(f"Portfolio Heat: ${pr['portfolio_heat']:,.0f} ({pr['portfolio_heat_pct']:.1%}) {heat_status}")

        # Drawdown
        print(f"\nDrawdown:")
        print(f"  Daily:  {pr['daily_return_pct']:>+7.2%}  (P&L: ${pr['daily_pnl']:>+10,.0f})")
        print(f"  Weekly: {pr['weekly_return_pct']:>+7.2%}  (P&L: ${pr['weekly_pnl']:>+10,.0f})")
        print(f"  Max DD: {pr['max_drawdown_pct']:>+7.2%}")

        # Correlation
        print(f"\nCorrelation:")
        print(f"  Average: {pr['avg_correlation']:.2f} (limit: {self.portfolio_risk_manager.max_avg_correlation:.2f})")
        print(f"  Maximum: {pr['max_correlation']:.2f} (limit: {self.portfolio_risk_manager.max_pairwise_correlation:.2f})")

        # Margin
        margin_status = "✓" if pr['margin_utilization_pct'] <= self.portfolio_risk_manager.max_margin_utilization else "✗"
        print(f"\nMargin Utilization: {pr['margin_utilization_pct']:.1%} {margin_status}")

        # Positions
        print(f"Position Count: {pr['position_count']} / {self.portfolio_risk_manager.max_positions}")

        # Sector exposure
        if pr['sector_exposures_pct']:
            print(f"\nSector Exposures:")
            for sector, pct in sorted(pr['sector_exposures_pct'].items(), key=lambda x: x[1], reverse=True)[:5]:
                bar_length = int(pct * 50)
                bar = "█" * bar_length
                print(f"  {sector:15s} {pct:>5.1%} {bar}")

        # Market exposure
        print("\n" + "-" * 100)
        print("MARKET EXPOSURE")
        print("-" * 100)
        if 'beta' in snapshot['market_exposure']:
            me = snapshot['market_exposure']
            print(f"Beta to SPY: {me['beta']:.2f}")
            print(f"Correlation: {me['correlation_to_spy']:.2f}")
        else:
            print("  Insufficient data")

        # Top position risks
        print("\n" + "-" * 100)
        print("TOP POSITION RISKS")
        print("-" * 100)
        print(f"{'Symbol':<8} {'Weight':>8} {'Risk $':>12} {'Risk %':>8} {'P&L':>8}")
        print("-" * 100)

        for pos in snapshot['position_risks'][:10]:
            print(
                f"{pos['symbol']:<8} "
                f"{pos['weight_pct']:>7.1%} "
                f"${pos['risk_dollars']:>10,.0f} "
                f"{pos['risk_pct']:>7.1%} "
                f"{pos['unrealized_pnl_pct']:>+7.1%}"
            )

        # Risk capacity
        print("\n" + "-" * 100)
        print("RISK CAPACITY REMAINING")
        print("-" * 100)
        rc = snapshot['risk_capacity']
        print(f"Daily Loss Capacity:    {rc['daily_loss_remaining']:>+7.2%}")
        print(f"Weekly Loss Capacity:   {rc['weekly_loss_remaining']:>+7.2%}")
        print(f"Drawdown Capacity:      {rc['drawdown_remaining']:>+7.2%}")
        print(f"Heat Capacity:          {rc['heat_remaining']:>+7.2%}")
        print(f"Position Capacity:      {rc['positions_remaining']:>3d} positions")

        # Violations summary
        if pr['violations']:
            print("\n" + "-" * 100)
            print("⚠ ACTIVE VIOLATIONS")
            print("-" * 100)
            for v in pr['violations']:
                print(f"  {v['type'].upper()}: {v['message']}")

        print("\n" + "=" * 100 + "\n")

    def export_snapshot(self, snapshot: Dict, filename: Optional[str] = None) -> Path:
        """
        Export risk snapshot to JSON file.

        Args:
            snapshot: Risk snapshot dict
            filename: Optional filename (default: timestamp-based)

        Returns:
            Path to exported file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"risk_snapshot_{timestamp}.json"

        filepath = self.export_dir / filename

        with open(filepath, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)

        logger.info(f"Risk snapshot exported to {filepath}")
        return filepath

    def export_to_dataframe(self, snapshot: Dict) -> pd.DataFrame:
        """
        Convert risk snapshot to pandas DataFrame for analysis.

        Args:
            snapshot: Risk snapshot dict

        Returns:
            DataFrame with risk metrics
        """
        # Flatten nested dict for DataFrame
        flat_data = {
            'timestamp': snapshot['timestamp'],
            'portfolio_value': snapshot['portfolio_value'],
            'cash': snapshot['cash'],
            'vix': snapshot['vix']
        }

        # VaR metrics
        if 'var_95' in snapshot.get('var', {}):
            flat_data.update({
                f"var_{k}": v for k, v in snapshot['var'].items()
                if k not in ['within_limits', 'violations']
            })

        # Portfolio risk
        pr = snapshot.get('portfolio_risk', {})
        flat_data.update({
            'portfolio_heat': pr.get('portfolio_heat'),
            'portfolio_heat_pct': pr.get('portfolio_heat_pct'),
            'avg_correlation': pr.get('avg_correlation'),
            'daily_return_pct': pr.get('daily_return_pct'),
            'weekly_return_pct': pr.get('weekly_return_pct'),
            'max_drawdown_pct': pr.get('max_drawdown_pct'),
            'margin_utilization_pct': pr.get('margin_utilization_pct'),
            'position_count': pr.get('position_count')
        })

        # Market exposure
        if 'beta' in snapshot.get('market_exposure', {}):
            flat_data['beta'] = snapshot['market_exposure']['beta']
            flat_data['correlation_to_spy'] = snapshot['market_exposure']['correlation_to_spy']

        # Circuit breaker
        flat_data['can_trade'] = snapshot['circuit_breaker']['can_trade']

        return pd.DataFrame([flat_data])

    def export_history_to_csv(
        self,
        snapshots: List[Dict],
        filename: str = "risk_history.csv"
    ) -> Path:
        """
        Export multiple snapshots to CSV for historical analysis.

        Args:
            snapshots: List of risk snapshot dicts
            filename: Output filename

        Returns:
            Path to CSV file
        """
        dfs = [self.export_to_dataframe(s) for s in snapshots]
        df = pd.concat(dfs, ignore_index=True)

        filepath = self.export_dir / filename
        df.to_csv(filepath, index=False)

        logger.info(f"Risk history exported to {filepath}")
        return filepath
