# World-Class Risk Management System

## Overview

This directory contains a comprehensive, institutional-grade risk management system for quantitative trading. All components are based on proven academic research and industry best practices.

## Components

### 1. Dynamic Position Sizing (`dynamic_sizing.py`)

**Purpose**: Adapt position sizes to market conditions dynamically.

**Features**:
- Volatility-adjusted sizing (smaller positions in high volatility)
- Correlation-aware sizing (reduce size when portfolio is concentrated)
- Regime-aware sizing (reduce in bear markets, increase in bull markets)
- Kelly criterion using live trading results

**Academic Foundation**:
- Thorp (1969): Optimal Gambling Systems
- Grinold & Kahn (2000): Active Portfolio Management
- Prado (2018): Advances in Financial Machine Learning

**Usage**:
```python
from risk.dynamic_sizing import DynamicPositionSizer

sizer = DynamicPositionSizer(
    base_position_pct=0.10,  # 10% base allocation
    max_position_pct=0.15,   # 15% maximum
    kelly_fraction=0.25      # Quarter Kelly
)

params = sizer.calculate_position_size(
    symbol='AAPL',
    portfolio_value=100000,
    asset_volatility=0.25,
    vix=20.0,
    spy_data=spy_df,
    portfolio_returns=returns_df,
    strategy='momentum'
)

print(f"Recommended size: {params.final_size_pct:.1%}")
```

### 2. Portfolio Risk Management (`portfolio_risk.py`)

**Purpose**: Monitor and control portfolio-level risk.

**Features**:
- Portfolio heat tracking (total risk from all stop losses)
- Sector concentration limits
- Position correlation monitoring
- Daily/weekly drawdown limits
- Automatic risk reduction recommendations

**Limits** (configurable):
- Max portfolio heat: 20% of capital
- Max sector exposure: 30%
- Max average correlation: 0.6
- Daily loss limit: -2%
- Weekly loss limit: -5%
- Max drawdown: -15%

**Usage**:
```python
from risk.portfolio_risk import PortfolioRiskManager

risk_mgr = PortfolioRiskManager(
    max_portfolio_heat_pct=0.20,
    max_sector_exposure_pct=0.30,
    daily_drawdown_limit=0.02
)

metrics = risk_mgr.calculate_metrics(
    positions=positions,
    portfolio_value=100000,
    cash=20000,
    margin_used=0,
    margin_available=100000
)

risk_mgr.print_risk_summary(metrics)

# Get recommended actions
actions = risk_mgr.get_risk_reduction_actions(metrics, positions)
```

### 3. Adaptive Trailing Stops (`adaptive_stops.py`)

**Purpose**: Intelligent stop loss management that adapts to conditions.

**Features**:
- Tighter stops for larger gains (lock in profits)
- Wider stops in high volatility (avoid whipsaws)
- Time-based exits (stale positions)
- Volatility regime-adjusted ATR multiples

**Stop Tightening Schedule** (default):
- +5% profit → 2.5% stop
- +10% profit → 2.0% stop
- +15% profit → 1.5% stop
- +20% profit → 1.0% stop

**Usage**:
```python
from risk.adaptive_stops import AdaptiveStopManager

stop_mgr = AdaptiveStopManager(
    initial_stop_pct=0.04,
    trailing_stop_pct=0.03,
    max_hold_days=60
)

params = stop_mgr.calculate_stop_loss(
    symbol='AAPL',
    current_price=150.0,
    entry_price=145.0,
    entry_time=datetime(2024, 1, 1),
    current_stop=140.0,
    highest_price_since_entry=152.0,
    atr=3.5,
    vix=20.0
)

print(f"Recommended stop: ${params.recommended_stop:.2f}")
```

### 4. Stress Testing (`stress_test.py`)

**Purpose**: Test portfolio resilience to extreme scenarios.

**Scenarios**:

**Historical**:
- 2008 Financial Crisis (-35%)
- 2020 COVID Crash (-34%)
- 2022 Bear Market (-25%)
- 1987 Black Monday (-22%)

**Hypothetical**:
- 20% market crash
- 40% severe crash
- Interest rate spike
- Sector rotation
- Liquidity crisis

**Usage**:
```python
from risk.stress_test import StressTestEngine

engine = StressTestEngine()

# Run all scenarios
results = engine.run_all_scenarios(
    positions=positions,
    portfolio_value=100000
)

# Print report
engine.print_stress_test_report(results)

# Get worst case
tail_risk = engine.get_tail_risk_estimate(results)
```

### 5. Value at Risk (`var_calculator.py`)

**Purpose**: Calculate Value at Risk and tail risk metrics.

**Metrics**:
- VaR (95%, 99%) - Historical method
- CVaR (Expected Shortfall) - Captures tail risk
- Volatility (annualized)
- Maximum drawdown
- Skewness and kurtosis

**Usage**:
```python
from risk.var_calculator import VaRCalculator

var_calc = VaRCalculator(lookback_days=252)

metrics = var_calc.calculate_all_metrics(returns_series)
print(metrics.summary())

# Check limits
within_limits, violations = var_calc.check_risk_limits(metrics)
```

### 6. Circuit Breakers (`circuit_breakers.py`)

**Purpose**: Automatic trading halts on risk violations.

**Triggers**:
- Daily loss > 2%
- Weekly loss > 5%
- Drawdown > 15%
- Manual halt

**Usage**:
```python
from risk.circuit_breakers import CircuitBreaker

breaker = CircuitBreaker(
    daily_loss_limit=-0.02,
    weekly_loss_limit=-0.05,
    max_drawdown_limit=-0.15,
    initial_equity=100000
)

# Update with current equity
breaker.update(current_equity=98000)

# Check if trading allowed
can_trade, reason = breaker.can_trade()
if not can_trade:
    print(f"Trading halted: {reason}")
```

## Integration with Auto Trader

The risk management system integrates seamlessly with the auto trader:

```python
# In auto_trader.py initialization
from risk import (
    DynamicPositionSizer,
    PortfolioRiskManager,
    AdaptiveStopManager,
    StressTestEngine
)
from monitoring.risk_dashboard import RiskDashboard

# Initialize components
self.dynamic_sizer = DynamicPositionSizer()
self.portfolio_risk = PortfolioRiskManager()
self.adaptive_stops = AdaptiveStopManager()
self.stress_tester = StressTestEngine()

self.risk_dashboard = RiskDashboard(
    var_calculator=self.var_calculator,
    portfolio_risk_manager=self.portfolio_risk,
    circuit_breaker=self.circuit_breaker,
    adaptive_stop_manager=self.adaptive_stops,
    dynamic_sizer=self.dynamic_sizer
)

# In trading loop
def run_cycle(self):
    # Calculate position sizes dynamically
    size_params = self.dynamic_sizer.calculate_position_size(...)

    # Check portfolio risk
    risk_metrics = self.portfolio_risk.calculate_metrics(...)

    # Update stops adaptively
    stop_params = self.adaptive_stops.calculate_stop_loss(...)

    # Get risk snapshot
    snapshot = self.risk_dashboard.get_risk_snapshot(...)

    # Run stress tests periodically
    if should_stress_test:
        results = self.stress_tester.run_all_scenarios(...)
```

## Monitoring & Dashboards

### Real-Time Risk Dashboard (`monitoring/risk_dashboard.py`)

Provides comprehensive real-time risk monitoring:

```python
from monitoring.risk_dashboard import RiskDashboard

dashboard = RiskDashboard(
    var_calculator=var_calc,
    portfolio_risk_manager=risk_mgr,
    circuit_breaker=breaker,
    adaptive_stop_manager=stop_mgr
)

# Get snapshot
snapshot = dashboard.get_risk_snapshot(
    positions=positions,
    portfolio_value=100000,
    # ... other parameters
)

# Display
dashboard.print_dashboard(snapshot)

# Export
dashboard.export_snapshot(snapshot)
```

## Running the Demo

Test all components:

```bash
# Full demo
python scripts/risk_management_demo.py

# Individual demos
python scripts/risk_management_demo.py --demo sizing
python scripts/risk_management_demo.py --demo portfolio
python scripts/risk_management_demo.py --demo stops
python scripts/risk_management_demo.py --demo stress
python scripts/risk_management_demo.py --demo dashboard
```

## Academic References

1. **Position Sizing**:
   - Thorp, E. (1969). "Optimal Gambling Systems for Favorable Games"
   - Kelly, J. (1956). "A New Interpretation of Information Rate"
   - Prado, M. (2018). "Advances in Financial Machine Learning"

2. **Portfolio Risk**:
   - Grinold, R. & Kahn, R. (2000). "Active Portfolio Management"
   - Markowitz, H. (1952). "Portfolio Selection"

3. **Value at Risk**:
   - Jorion, P. (2006). "Value at Risk: The New Benchmark for Managing Financial Risk"
   - Artzner, P. et al. (1999). "Coherent Measures of Risk"

4. **Stress Testing**:
   - Basel Committee (2009). "Principles for Sound Stress Testing Practices"
   - Rebonato, R. (2010). "Coherent Stress Testing"

5. **Adaptive Stops**:
   - Kaufman, P. (2013). "Trading Systems and Methods"
   - Wilder, W. (1978). "New Concepts in Technical Trading Systems"
   - Chande, T. & Kroll, S. (1994). "The New Technical Trader"

## Key Features

✓ **Dynamic Position Sizing**: Adapts to volatility, correlation, and market regime
✓ **Portfolio-Level Controls**: Comprehensive risk limits and monitoring
✓ **Adaptive Stops**: Intelligent trailing stops that lock in profits
✓ **Stress Testing**: Historical and hypothetical scenario analysis
✓ **Real-Time Monitoring**: Comprehensive risk dashboard
✓ **Circuit Breakers**: Automatic trading halts on violations
✓ **VaR & CVaR**: Professional risk metrics
✓ **Academic Foundation**: All methods backed by peer-reviewed research

## Configuration

All risk parameters are configurable. See individual module documentation for details.

## Support

For questions or issues, consult:
- Individual module docstrings
- Demo script: `scripts/risk_management_demo.py`
- Academic references listed above
