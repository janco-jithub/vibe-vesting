# Backtesting Framework - Quick Start Guide

## Overview

This guide shows you how to use the professional backtesting framework to test trading strategies.

## Prerequisites

```bash
# Install required dependencies
pip install matplotlib scipy pandas numpy
```

## Quick Start

### 1. Run Comprehensive Backtest (All Strategies)

```bash
python scripts/run_comprehensive_backtest.py \
  --start-date 2024-01-01 \
  --end-date 2026-02-05 \
  --capital 100000
```

**Options**:
- `--start-date`: Backtest start date (YYYY-MM-DD)
- `--end-date`: Backtest end date (YYYY-MM-DD)
- `--capital`: Total capital for allocation recommendations
- `--no-validation`: Skip validation (faster, for quick tests)
- `--no-fetch`: Don't fetch missing data (use existing only)

### 2. Generate Report

```bash
python scripts/generate_backtest_report.py
```

This generates a comprehensive report with:
- Performance summary for all strategies
- Professional standards comparison
- Recommendations
- Academic references

### 3. View Results

Results are saved to:
- **Database**: `/data/quant.db` table `backtest_results`
- **CSV**: `/backtest_results/strategy_comparison_YYYYMMDD_HHMMSS.csv`
- **Charts**: `/backtest_results/backtest_comparison_YYYYMMDD_HHMMSS.png`
- **Allocation**: `/backtest_results/capital_allocation_YYYYMMDD_HHMMSS.csv`

## Python API Usage

### Run Single Strategy Backtest

```python
from backtest.runner import BacktestRunner
from strategies.simple_momentum import SimpleMomentumStrategy

# Initialize
runner = BacktestRunner()
strategy = SimpleMomentumStrategy(
    sma_period=100,
    momentum_period=63,
    max_positions=3
)

# Load data
data = runner.load_data_for_strategies([strategy])

# Run backtest
result, validation = runner.run_backtest(
    strategy=strategy,
    data=data,
    validate=True,
    save_results=True
)

# Access results
print(f"Sharpe Ratio: {result.metrics.sharpe_ratio:.2f}")
print(f"Total Return: {result.metrics.total_return:.1%}")
print(f"Max Drawdown: {result.metrics.max_drawdown:.1%}")
print(f"Is Robust: {validation.is_robust}")
```

### Compare Multiple Strategies

```python
from backtest.runner import BacktestRunner
from strategies.simple_momentum import SimpleMomentumStrategy
from strategies.dual_momentum import DualMomentumStrategy

runner = BacktestRunner()

strategies = [
    SimpleMomentumStrategy(),
    DualMomentumStrategy()
]

# Run all strategies
comparison_df = runner.run_multiple_strategies(
    strategies=strategies,
    validate=True
)

# View comparison
print(comparison_df)

# Get capital allocation
allocation_df = runner.recommend_capital_allocation(
    total_capital=100000.0,
    min_sharpe=1.0,
    max_strategies=2
)
print(allocation_df)
```

### Custom Validation

```python
from backtest.validator import StrategyValidator
from strategies.simple_momentum import SimpleMomentumStrategy

validator = StrategyValidator(
    min_sharpe_threshold=1.0,
    min_calmar_threshold=1.0
)

strategy = SimpleMomentumStrategy()

# Load data
from data.storage import TradingDatabase
db = TradingDatabase()
data = {
    symbol: db.get_daily_bars(symbol, '2022-01-01', '2026-02-05')
    for symbol in strategy.universe
}

# Validate
validation_result = validator.validate_strategy(
    strategy=strategy,
    data=data,
    n_simulations=100,
    parameter_grid={
        'sma_period': [50, 100, 150, 200],
        'momentum_period': [20, 40, 60, 90]
    }
)

# Check results
print(f"Is Robust: {validation_result.is_robust}")
print(f"Mean Sharpe: {validation_result.sharpe_mean:.2f}")
print(f"Consistency: {validation_result.consistency_score:.2f}")
print(f"Overfitting Risk: {validation_result.overfitting_probability:.1%}")

# Print full report
from backtest.validator import print_validation_results
print(print_validation_results(validation_result))
```

### Walk-Forward Optimization

```python
from backtest.engine import run_walk_forward
from strategies.simple_momentum import SimpleMomentumStrategy

strategy = SimpleMomentumStrategy()

# Load data (need 3+ years)
from data.storage import TradingDatabase
db = TradingDatabase()
data = {
    symbol: db.get_daily_bars(symbol, '2022-01-01', '2026-02-05')
    for symbol in strategy.universe
}

# Run walk-forward
results = run_walk_forward(
    strategy=strategy,
    data=data,
    train_years=2,      # Train on 2 years
    test_years=1,       # Test on 1 year
    step_months=6       # Step forward 6 months
)

# Analyze results
for i, result in enumerate(results):
    print(f"\nPeriod {i+1}: {result.start_date} to {result.end_date}")
    print(f"  Sharpe: {result.metrics.sharpe_ratio:.2f}")
    print(f"  Return: {result.metrics.total_return:.1%}")
    print(f"  Max DD: {result.metrics.max_drawdown:.1%}")

# Calculate aggregate metrics
sharpe_mean = sum(r.metrics.sharpe_ratio for r in results) / len(results)
print(f"\nAggregate Sharpe Ratio: {sharpe_mean:.2f}")
```

## Understanding the Metrics

### Sharpe Ratio
- **Formula**: (Return - Risk Free Rate) / Volatility
- **Interpretation**:
  - < 0.5: Poor
  - 0.5-1.0: Acceptable
  - 1.0-2.0: Good
  - > 2.0: Excellent
- **Minimum**: 1.0 for live trading

### Sortino Ratio
- Similar to Sharpe but only penalizes downside volatility
- Generally higher than Sharpe for profitable strategies

### Calmar Ratio
- **Formula**: CAGR / Max Drawdown
- **Interpretation**: Return per unit of worst-case loss
- **Minimum**: 1.0 (return should exceed drawdown)

### Max Drawdown
- Largest peak-to-trough decline
- **Maximum**: 25% (risk management threshold)
- **Target**: < 20%

### Alpha
- Excess return vs benchmark (SPY)
- Positive alpha = outperformance after adjusting for beta

### Beta
- Sensitivity to market movements
- Beta = 1.0: Moves with market
- Beta < 1.0: Less volatile than market
- Beta > 1.0: More volatile than market

## Interpreting Validation Results

### Robustness Criteria

A strategy is considered "robust" if:
1. Mean Sharpe Ratio ≥ 1.0
2. Consistency Score ≥ 0.5
3. Overfitting Probability < 0.5
4. Positive Sharpe in all major regimes

### Consistency Score
- 0.0-0.3: Very inconsistent (avoid)
- 0.3-0.5: Somewhat consistent
- 0.5-0.7: Consistent (good)
- 0.7-1.0: Very consistent (excellent)

### Overfitting Probability
- 0.0-0.3: Low risk (good)
- 0.3-0.5: Moderate risk (acceptable)
- 0.5-0.7: High risk (needs work)
- 0.7-1.0: Very high risk (avoid)

## Common Issues & Solutions

### Issue: No trades executed

**Possible Causes**:
- Insufficient historical data
- Signal thresholds too conservative
- No qualifying signals in test period

**Solutions**:
```python
# 1. Check data availability
from data.storage import TradingDatabase
db = TradingDatabase()
for symbol in strategy.universe:
    df = db.get_daily_bars(symbol)
    print(f"{symbol}: {len(df)} bars")

# 2. Lower signal thresholds
strategy = SimpleMomentumStrategy(
    sma_period=50,  # More responsive
    momentum_period=20,  # Shorter lookback
    position_size_pct=0.10  # Smaller positions = more opportunities
)

# 3. Test on different time period
runner.run_backtest(strategy, data, validate=False)
```

### Issue: Sharpe Ratio < 1.0

**Possible Causes**:
- Parameters not optimized
- Transaction costs too high
- Strategy doesn't work in current market regime

**Solutions**:
```python
# 1. Parameter optimization
from backtest.validator import StrategyValidator

validator = StrategyValidator()
validation = validator.validate_strategy(
    strategy=strategy,
    data=data,
    parameter_grid={
        'sma_period': [50, 100, 150, 200],
        'momentum_period': [20, 40, 60, 90, 126]
    }
)

# Check optimal parameters
print(validation.optimal_parameters)

# 2. Reduce transaction costs
params = strategy.get_backtest_params()
params.transaction_cost_bps = 5  # Lower costs
params.slippage_bps = 5

# 3. Test on different period
runner.run_backtest(
    strategy,
    data,
    validate=False,
    save_results=False
)
```

### Issue: High drawdown (> 25%)

**Possible Causes**:
- Position sizes too large
- No stop losses
- High concentration risk

**Solutions**:
```python
# Reduce position size
strategy = SimpleMomentumStrategy(
    position_size_pct=0.10,  # 10% instead of 20%
    max_positions=5  # More diversification
)

# Add stop loss logic in strategy
# (modify strategy class to include stop_loss_pct)
```

## Best Practices

### 1. Always Start with Validation

```python
# Good: Full validation
result, validation = runner.run_backtest(
    strategy=strategy,
    data=data,
    validate=True  # Monte Carlo, parameter sensitivity, regime analysis
)

# Bad: Skip validation
result, _ = runner.run_backtest(
    strategy=strategy,
    data=data,
    validate=False  # No confidence in results
)
```

### 2. Use Walk-Forward, Not In-Sample Only

```python
# Good: Out-of-sample testing
results = run_walk_forward(
    strategy=strategy,
    data=data,
    train_years=2,
    test_years=1,
    step_months=6
)

# Bad: Optimize on all data
result = runner.run_backtest(strategy, data)  # Overfitting risk
```

### 3. Test Multiple Parameter Sets

```python
# Good: Parameter sensitivity analysis
validation = validator.validate_strategy(
    strategy=strategy,
    data=data,
    parameter_grid={
        'sma_period': [50, 100, 150, 200],
        'momentum_period': [20, 40, 60, 90]
    }
)

# Bad: Single parameter set
result = runner.run_backtest(strategy, data)  # May be lucky
```

### 4. Require Minimum Sample Size

```python
# Check trade count
if result.trade_count < 100:
    print("WARNING: Insufficient trades for statistical significance")
    print(f"Current: {result.trade_count}, Need: 100+")
```

### 5. Compare to Benchmark

```python
# Always include SPY for alpha/beta calculation
data['SPY'] = db.get_daily_bars('SPY', start_date, end_date)

result = runner.run_backtest(strategy, data)

# Check alpha
if result.metrics.alpha and result.metrics.alpha > 0:
    print(f"✓ Positive alpha: {result.metrics.alpha:.1%}")
else:
    print(f"✗ Negative alpha: underperforming benchmark")
```

## Advanced Usage

### Custom Metrics

```python
from backtest.metrics import calculate_metrics

# Calculate metrics manually
metrics = calculate_metrics(
    returns=result.returns,
    equity_curve=result.equity_curve,
    trades=result.trades,
    initial_capital=100000.0,
    benchmark_returns=benchmark_returns
)

# Access custom calculations
print(f"VaR (95%): {metrics.var_95:.2%}")
print(f"CVaR (95%): {metrics.cvar_95:.2%}")
print(f"Skewness: {metrics.skewness:.2f}")
print(f"Kurtosis: {metrics.kurtosis:.2f}")
```

### Query Historical Backtests

```python
from data.storage import TradingDatabase

db = TradingDatabase()

# Get all backtest runs
with db.get_connection() as conn:
    df = pd.read_sql_query("""
        SELECT
            strategy_name,
            run_date,
            sharpe_ratio,
            total_return,
            max_drawdown
        FROM backtest_results
        ORDER BY sharpe_ratio DESC
        LIMIT 10
    """, conn)

print(df)
```

## Resources

### Documentation
- Full summary: `/BACKTEST_FRAMEWORK_SUMMARY.md`
- API docs: `/backtest/*.py` (docstrings)

### Examples
- Simple backtest: `/scripts/run_comprehensive_backtest.py`
- Report generation: `/scripts/generate_backtest_report.py`

### Academic Papers
See `BACKTEST_FRAMEWORK_SUMMARY.md` for complete references.

## Support

For issues or questions:
1. Check the error message
2. Review this guide
3. Inspect the code docstrings
4. Check the backtest_results directory for output files

## Quick Reference

| Task | Command |
|------|---------|
| Run all strategies | `python scripts/run_comprehensive_backtest.py` |
| Generate report | `python scripts/generate_backtest_report.py` |
| Quick test (no validation) | `python scripts/run_comprehensive_backtest.py --no-validation` |
| Custom date range | `python scripts/run_comprehensive_backtest.py --start-date 2022-01-01` |

## Minimum Viable Backtest Checklist

Before deploying a strategy to live trading:

- [ ] Sharpe Ratio ≥ 1.0
- [ ] Calmar Ratio ≥ 1.0
- [ ] Max Drawdown ≤ 25%
- [ ] Trade Count ≥ 100
- [ ] Consistency Score ≥ 0.5
- [ ] Overfitting Probability < 0.5
- [ ] Positive Sharpe in all regimes
- [ ] Positive alpha vs benchmark
- [ ] Walk-forward validated
- [ ] 3+ months paper trading
- [ ] Real slippage < 0.2%

---

**Last Updated**: 2026-02-06
