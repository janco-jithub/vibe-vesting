"""
Portfolio Stress Testing Framework

Implements comprehensive stress testing:
1. Historical scenarios (2008 crisis, 2020 COVID, 2022 bear)
2. Hypothetical scenarios (20% crash, sector rotation, rate spike)
3. Tail risk analysis (fat tails, extreme events)

Academic References:
- Basel Committee (2009): "Principles for sound stress testing practices"
- Jorion (2006): "Value at Risk" - stress testing methodologies
- Rebonato (2010): "Coherent Stress Testing" - scenario design
- Taleb (2007): "The Black Swan" - tail risk
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from enum import Enum
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ScenarioType(Enum):
    """Types of stress scenarios."""
    HISTORICAL = "historical"
    HYPOTHETICAL = "hypothetical"
    SENSITIVITY = "sensitivity"
    TAIL_RISK = "tail_risk"


@dataclass
class StressScenario:
    """Definition of a stress scenario."""
    name: str
    scenario_type: ScenarioType
    description: str

    # Price shocks (symbol -> % change)
    price_shocks: Dict[str, float]

    # Correlation shock
    correlation_increase: float = 0.0  # How much correlations increase

    # Volatility shock
    volatility_multiplier: float = 1.0  # Multiply volatilities by this

    # Market-wide shock (SPY change %)
    market_shock: float = 0.0


@dataclass
class StressTestResult:
    """Results of stress testing."""
    scenario_name: str
    scenario_type: ScenarioType

    # Portfolio impact
    pre_stress_value: float
    post_stress_value: float
    portfolio_loss: float
    portfolio_loss_pct: float

    # Position-level impacts
    position_losses: Dict[str, float]  # symbol -> loss $
    position_losses_pct: Dict[str, float]  # symbol -> loss %

    # Risk metrics under stress
    stressed_var_95: float
    stressed_cvar_95: float
    stressed_correlation: float

    # Circuit breaker check
    would_trigger_breakers: bool
    breaker_violations: List[str]

    timestamp: datetime


class StressTestEngine:
    """
    Portfolio stress testing engine.

    Applies various stress scenarios to portfolio to:
    - Estimate potential losses in extreme events
    - Identify vulnerabilities
    - Ensure risk controls would work under stress
    """

    def __init__(self):
        """Initialize stress test engine."""
        # Pre-defined historical scenarios
        self.historical_scenarios = self._define_historical_scenarios()

        # Pre-defined hypothetical scenarios
        self.hypothetical_scenarios = self._define_hypothetical_scenarios()

        logger.info("StressTestEngine initialized with scenarios")

    def _define_historical_scenarios(self) -> Dict[str, StressScenario]:
        """Define historical stress scenarios."""
        scenarios = {}

        # 2008 Financial Crisis (Sep-Oct 2008)
        scenarios['2008_financial_crisis'] = StressScenario(
            name="2008 Financial Crisis",
            scenario_type=ScenarioType.HISTORICAL,
            description="Sep-Oct 2008: Lehman collapse, market crash",
            price_shocks={
                'SPY': -0.35,    # S&P 500 down 35%
                'QQQ': -0.40,    # Nasdaq down 40%
                'IWM': -0.45,    # Small caps down 45%
                'XLF': -0.55,    # Financials down 55%
                'TLT': +0.15,    # Treasuries up 15% (flight to safety)
            },
            correlation_increase=0.30,  # Correlations spike in crisis
            volatility_multiplier=3.0,
            market_shock=-0.35
        )

        # 2020 COVID Crash (Feb-Mar 2020)
        scenarios['2020_covid_crash'] = StressScenario(
            name="2020 COVID Crash",
            scenario_type=ScenarioType.HISTORICAL,
            description="Feb-Mar 2020: Pandemic crash, fastest bear market",
            price_shocks={
                'SPY': -0.34,    # S&P 500 down 34%
                'QQQ': -0.27,    # Tech held up better
                'IWM': -0.41,    # Small caps hit harder
                'XLE': -0.55,    # Energy devastated
                'XLV': -0.15,    # Healthcare defensive
                'TLT': +0.20,    # Treasuries rallied
            },
            correlation_increase=0.35,
            volatility_multiplier=4.0,
            market_shock=-0.34
        )

        # 2022 Bear Market (Jan-Oct 2022)
        scenarios['2022_bear_market'] = StressScenario(
            name="2022 Bear Market",
            scenario_type=ScenarioType.HISTORICAL,
            description="Jan-Oct 2022: Rising rates, inflation, tech crash",
            price_shocks={
                'SPY': -0.25,    # S&P 500 down 25%
                'QQQ': -0.33,    # Tech down 33%
                'TLT': -0.30,    # Bonds down too (rate shock)
                'XLE': +0.40,    # Energy up
                'GLD': -0.05,    # Gold flat
            },
            correlation_increase=0.20,
            volatility_multiplier=2.0,
            market_shock=-0.25
        )

        # 1987 Black Monday (single day)
        scenarios['1987_black_monday'] = StressScenario(
            name="1987 Black Monday",
            scenario_type=ScenarioType.HISTORICAL,
            description="Oct 19, 1987: Single day crash",
            price_shocks={
                'SPY': -0.22,    # Down 22% in one day
            },
            correlation_increase=0.40,
            volatility_multiplier=5.0,
            market_shock=-0.22
        )

        return scenarios

    def _define_hypothetical_scenarios(self) -> Dict[str, StressScenario]:
        """Define hypothetical stress scenarios."""
        scenarios = {}

        # Standard crash scenario
        scenarios['market_crash_20'] = StressScenario(
            name="20% Market Crash",
            scenario_type=ScenarioType.HYPOTHETICAL,
            description="Hypothetical 20% market crash",
            price_shocks={
                'SPY': -0.20,
                'QQQ': -0.25,
                'IWM': -0.30,
            },
            correlation_increase=0.25,
            volatility_multiplier=2.5,
            market_shock=-0.20
        )

        # Severe crash
        scenarios['market_crash_40'] = StressScenario(
            name="40% Market Crash",
            scenario_type=ScenarioType.HYPOTHETICAL,
            description="Severe hypothetical crash",
            price_shocks={
                'SPY': -0.40,
                'QQQ': -0.45,
                'IWM': -0.50,
            },
            correlation_increase=0.40,
            volatility_multiplier=4.0,
            market_shock=-0.40
        )

        # Rate spike
        scenarios['rate_spike'] = StressScenario(
            name="Interest Rate Spike",
            scenario_type=ScenarioType.HYPOTHETICAL,
            description="Sudden 200bp rate increase",
            price_shocks={
                'SPY': -0.15,
                'TLT': -0.20,    # Bonds down
                'XLF': -0.25,    # Financials hurt
                'XLU': -0.20,    # Utilities hurt
            },
            correlation_increase=0.15,
            volatility_multiplier=1.5,
            market_shock=-0.15
        )

        # Sector rotation (tech crash, value rally)
        scenarios['sector_rotation'] = StressScenario(
            name="Tech Crash / Value Rally",
            scenario_type=ScenarioType.HYPOTHETICAL,
            description="Major sector rotation from growth to value",
            price_shocks={
                'QQQ': -0.30,    # Tech crashes
                'XLF': +0.15,    # Financials rally
                'XLE': +0.20,    # Energy rallies
                'XLV': +0.10,    # Healthcare holds
            },
            correlation_increase=-0.10,  # Negative correlation in rotation
            volatility_multiplier=1.8,
            market_shock=-0.05
        )

        # Liquidity crisis
        scenarios['liquidity_crisis'] = StressScenario(
            name="Liquidity Crisis",
            scenario_type=ScenarioType.HYPOTHETICAL,
            description="Sudden liquidity freeze",
            price_shocks={
                'SPY': -0.15,
                'IWM': -0.25,    # Small caps hit harder
                'TLT': +0.10,    # Flight to Treasuries
            },
            correlation_increase=0.30,
            volatility_multiplier=3.0,
            market_shock=-0.15
        )

        return scenarios

    def apply_scenario(
        self,
        scenario: StressScenario,
        positions: Dict[str, Dict],
        portfolio_value: float,
        returns_data: Optional[Dict[str, pd.Series]] = None
    ) -> StressTestResult:
        """
        Apply stress scenario to portfolio.

        Args:
            scenario: Stress scenario to apply
            positions: Current positions (symbol -> position data)
            portfolio_value: Current portfolio value
            returns_data: Historical returns for VaR calculation

        Returns:
            StressTestResult
        """
        position_losses = {}
        position_losses_pct = {}
        total_loss = 0.0

        # Apply shocks to each position
        for symbol, pos in positions.items():
            market_value = pos.get('market_value', 0)

            # Get shock for this symbol
            if symbol in scenario.price_shocks:
                shock = scenario.price_shocks[symbol]
            elif scenario.market_shock != 0:
                # Apply market shock as default
                shock = scenario.market_shock
            else:
                shock = 0.0

            # Calculate position loss
            position_loss = market_value * shock
            position_losses[symbol] = position_loss
            position_losses_pct[symbol] = shock
            total_loss += position_loss

        post_stress_value = portfolio_value + total_loss
        loss_pct = total_loss / portfolio_value if portfolio_value > 0 else 0

        # Calculate stressed risk metrics
        stressed_var_95 = abs(loss_pct) * 1.2  # Approximate
        stressed_cvar_95 = abs(loss_pct) * 1.5

        # Estimate stressed correlation
        base_corr = 0.5  # Assume base correlation
        stressed_correlation = min(0.95, base_corr + scenario.correlation_increase)

        # Check circuit breaker violations
        breaker_violations = []
        would_trigger = False

        # Daily loss check (-2%)
        if loss_pct < -0.02:
            breaker_violations.append("Daily loss limit exceeded")
            would_trigger = True

        # Drawdown check (-15%)
        if loss_pct < -0.15:
            breaker_violations.append("Max drawdown limit exceeded")
            would_trigger = True

        result = StressTestResult(
            scenario_name=scenario.name,
            scenario_type=scenario.scenario_type,
            pre_stress_value=portfolio_value,
            post_stress_value=post_stress_value,
            portfolio_loss=total_loss,
            portfolio_loss_pct=loss_pct,
            position_losses=position_losses,
            position_losses_pct=position_losses_pct,
            stressed_var_95=stressed_var_95,
            stressed_cvar_95=stressed_cvar_95,
            stressed_correlation=stressed_correlation,
            would_trigger_breakers=would_trigger,
            breaker_violations=breaker_violations,
            timestamp=datetime.now()
        )

        logger.info(
            f"Stress test '{scenario.name}': {loss_pct:+.1%} loss, "
            f"breakers triggered: {would_trigger}"
        )

        return result

    def run_all_scenarios(
        self,
        positions: Dict[str, Dict],
        portfolio_value: float,
        returns_data: Optional[Dict[str, pd.Series]] = None
    ) -> Dict[str, StressTestResult]:
        """
        Run all stress scenarios.

        Args:
            positions: Current positions
            portfolio_value: Current portfolio value
            returns_data: Historical returns data

        Returns:
            Dict of scenario_name -> StressTestResult
        """
        results = {}

        # Run historical scenarios
        for scenario_name, scenario in self.historical_scenarios.items():
            results[scenario_name] = self.apply_scenario(
                scenario, positions, portfolio_value, returns_data
            )

        # Run hypothetical scenarios
        for scenario_name, scenario in self.hypothetical_scenarios.items():
            results[scenario_name] = self.apply_scenario(
                scenario, positions, portfolio_value, returns_data
            )

        return results

    def print_stress_test_report(
        self,
        results: Dict[str, StressTestResult],
        show_position_detail: bool = False
    ) -> None:
        """Print formatted stress test report."""
        print("\n" + "=" * 80)
        print("PORTFOLIO STRESS TEST REPORT")
        print("=" * 80)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Summary table
        print("\nSCENARIO SUMMARY:")
        print(f"{'Scenario':<35} {'Loss %':<12} {'Loss $':<15} {'Breakers':<10}")
        print("-" * 80)

        for scenario_name, result in sorted(
            results.items(),
            key=lambda x: x[1].portfolio_loss_pct
        ):
            breaker_status = "✗ YES" if result.would_trigger_breakers else "✓ No"
            print(
                f"{result.scenario_name:<35} "
                f"{result.portfolio_loss_pct:>+10.1%}  "
                f"${result.portfolio_loss:>12,.0f}  "
                f"{breaker_status:<10}"
            )

        # Find worst case
        worst_scenario = min(results.items(), key=lambda x: x[1].portfolio_loss_pct)
        print(f"\n⚠ WORST CASE: {worst_scenario[1].scenario_name}")
        print(f"  Loss: {worst_scenario[1].portfolio_loss_pct:.1%} "
              f"(${worst_scenario[1].portfolio_loss:,.0f})")

        # Count scenarios triggering breakers
        breaker_count = sum(1 for r in results.values() if r.would_trigger_breakers)
        print(f"\n⚠ {breaker_count}/{len(results)} scenarios would trigger circuit breakers")

        # Historical vs Hypothetical
        historical_results = [
            r for r in results.values()
            if r.scenario_type == ScenarioType.HISTORICAL
        ]
        hypothetical_results = [
            r for r in results.values()
            if r.scenario_type == ScenarioType.HYPOTHETICAL
        ]

        if historical_results:
            avg_historical_loss = np.mean([r.portfolio_loss_pct for r in historical_results])
            print(f"\nHistorical scenarios average loss: {avg_historical_loss:.1%}")

        if hypothetical_results:
            avg_hypothetical_loss = np.mean([r.portfolio_loss_pct for r in hypothetical_results])
            print(f"Hypothetical scenarios average loss: {avg_hypothetical_loss:.1%}")

        # Position-level detail
        if show_position_detail and worst_scenario:
            print(f"\nPOSITION IMPACTS (Worst Case: {worst_scenario[1].scenario_name}):")
            for symbol, loss_pct in sorted(
                worst_scenario[1].position_losses_pct.items(),
                key=lambda x: x[1]
            ):
                loss_dollars = worst_scenario[1].position_losses[symbol]
                print(f"  {symbol:6s}: {loss_pct:>+7.1%}  (${loss_dollars:>10,.0f})")

        print("\n" + "=" * 80)

    def get_tail_risk_estimate(
        self,
        results: Dict[str, StressTestResult]
    ) -> Dict:
        """
        Estimate tail risk from stress test results.

        Returns:
            Dict with tail risk metrics
        """
        losses = [r.portfolio_loss_pct for r in results.values()]

        return {
            'worst_loss': min(losses),
            'avg_loss': np.mean(losses),
            'loss_volatility': np.std(losses),
            'percentile_5': np.percentile(losses, 5),
            'percentile_1': np.percentile(losses, 1),
            'scenarios_tested': len(results)
        }
