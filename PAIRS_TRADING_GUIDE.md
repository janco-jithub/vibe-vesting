# Pairs Trading Strategy - Quick Start Guide

## Overview

The Pairs Trading strategy is a **market-neutral, mean-reversion** strategy that simultaneously goes long one asset and short another when their historical relationship diverges. Based on Gatev et al. (2006), it has a proven track record with Sharpe ratios of 1.0-1.4.

## How It Works

### 1. Formation Period (60 days)
The strategy analyzes pairs of ETFs to find strong statistical relationships:

```python
# Example: SPY vs IWM
correlation = 0.82  # High correlation
cointegrated = True  # Spread is stationary
hedge_ratio = 1.15  # For every $1 of SPY, short $1.15 of IWM
```

### 2. Trading Period
Monitor the spread and trade when it diverges:

```
Spread = Price_A - (Hedge_Ratio × Price_B)
Z-Score = (Spread - Mean) / Std_Dev

If Z-Score > +2.0:  Short A, Long B  (spread too wide)
If Z-Score < -2.0:  Long A, Short B   (spread too low)
If |Z-Score| < 0.5: Exit position     (convergence)
```

### 3. Real Example

```
Date: 2024-01-15
Pair: SPY/IWM
Current prices: SPY=$450, IWM=$185
Hedge ratio: 1.20

Spread = 450 - (1.20 × 185) = 450 - 222 = 228
Historical mean: 220
Historical std: 8

Z-Score = (228 - 220) / 8 = +1.0

Action: HOLD (not at +2.0 threshold yet)
```

## Running the Strategy

### 1. Standalone Backtest

```bash
cd /Users/work/personal/quant

# Run backtest on historical data
python scripts/run_backtest.py --strategy pairs_trading \
    --start-date 2020-01-01 \
    --end-date 2024-12-31 \
    --initial-capital 10000
```

### 2. With Auto Trader

```bash
# Run paper trading with pairs trading
python -m scripts.auto_trader \
    --strategies pairs_trading swing_momentum dual_momentum \
    --interval 300
```

### 3. Via Python API

```python
from strategies.pairs_trading import PairsTradingStrategy
from data.storage import TradingDatabase
from datetime import date, timedelta

# Initialize
db = TradingDatabase()
strategy = PairsTradingStrategy(
    lookback_days=60,
    entry_threshold=2.0,
    exit_threshold=0.5,
    min_correlation=0.75
)

# Load data
end_date = date.today()
start_date = end_date - timedelta(days=120)
data = db.get_multiple_symbols(strategy.universe, start_date=start_date)

# Get current signals
signals = strategy.get_current_signal(data)

for signal in signals:
    print(f"{signal.signal_type.value} {signal.symbol} - Z-score: {signal.metadata['z_score']:.2f}")
```

## Configuration Options

### Basic Parameters

```python
PairsTradingStrategy(
    pairs=[("SPY", "IWM"), ("QQQ", "SPY")],  # Custom pairs
    lookback_days=60,           # Formation period (default: 60)
    entry_threshold=2.0,        # Z-score to enter (default: 2.0)
    exit_threshold=0.5,         # Z-score to exit (default: 0.5)
    min_correlation=0.75,       # Min correlation (default: 0.75)
    check_cointegration=True    # Test cointegration (default: True)
)
```

### Position Sizing

The strategy allocates:
- **7.5% per leg** (15% total per pair)
- With 5-6 active pairs: 75-90% invested
- Hedge ratio adjusts position automatically

Example:
```
Portfolio: $10,000
Signal: Long SPY, Short IWM
Hedge ratio: 1.20

SPY position: $750 (7.5%)
IWM position: $900 (7.5% × 1.20)
```

## Monitoring via API

### Get All Pair Statuses

```bash
curl http://localhost:8000/api/pairs-status
```

Response:
```json
{
  "pairs": [
    {
      "pair": "SPY/IWM",
      "status": "watching",
      "z_score": 1.2,
      "correlation": 0.85,
      "hedge_ratio": 1.18,
      "is_cointegrated": true
    },
    {
      "pair": "QQQ/SPY",
      "status": "entry_signal",
      "z_score": 2.4,
      "correlation": 0.92,
      "hedge_ratio": 1.05,
      "is_cointegrated": true
    }
  ],
  "count": 6
}
```

### Get Current Signals

```bash
curl http://localhost:8000/api/signals/all
```

Will include pairs trading signals with metadata:
```json
{
  "strategy": "Pairs Trading",
  "symbol": "SPY",
  "signal_type": "SELL",
  "strength": 0.8,
  "description": "Pair: SPY/IWM, Z-score: 2.40, SHORT",
  "metadata": {
    "pair_symbol": "IWM",
    "z_score": 2.4,
    "correlation": 0.85,
    "hedge_ratio": 1.18,
    "position": "short"
  }
}
```

## Default Trading Pairs

The strategy monitors these pairs by default:

| Pair | Type | Rationale |
|------|------|-----------|
| SPY/IWM | Size Factor | Large cap vs Small cap spread |
| QQQ/SPY | Tech Factor | Tech-heavy vs Broad market |
| XLF/XLV | Sector Pair | Financials vs Healthcare |
| XLK/XLC | Sector Pair | Technology vs Communications |
| XLE/XLU | Sector Pair | Energy vs Utilities (cyclical vs defensive) |
| XLF/XLK | Sector Pair | Financials vs Technology |

All pairs are chosen for:
- High liquidity (tight spreads)
- Economic relationships
- Historical mean reversion

## Understanding Z-Scores

### Z-Score Interpretation

- **Z > +2.0**: Spread is 2 standard deviations above mean → Short A, Long B
- **-0.5 < Z < +0.5**: At equilibrium → No position or exit
- **Z < -2.0**: Spread is 2 standard deviations below mean → Long A, Short B

### Example Trading Cycle

```
Day 1:  Z-score = +0.5   → No action (watching)
Day 5:  Z-score = +1.8   → No action (not at threshold)
Day 8:  Z-score = +2.3   → ENTER: Short SPY, Long IWM
Day 12: Z-score = +1.5   → Hold position
Day 18: Z-score = +0.4   → EXIT: Close both legs
Day 20: Z-score = -0.2   → No position

Result: Captured mean reversion from +2.3 to +0.4
```

## Risk Management

### Circuit Breakers Apply
- Daily loss > -2%: Trading halted
- Weekly loss > -5%: Trading halted
- Max drawdown > -15%: Trading halted

### Position Limits
- Single position: 5% max (enforced by PositionSizer)
- Each pair leg: 7.5% (total 15% per pair)
- Maximum 6 pairs = 90% total exposure

### Stop-Loss (Built-in)
- Z-score reversal beyond entry point triggers review
- Large adverse moves checked by circuit breakers
- Cointegration re-tested periodically

## Common Issues & Solutions

### 1. "Pair not cointegrated"
**Cause**: Spread is not mean-reverting
**Solution**: Pair won't trade (by design). Check correlation strength.

### 2. "Short selling not supported"
**Cause**: Alpaca paper trading limitations
**Solution**:
```python
# In alpaca_client.py, positions return 0 for short signals
# This is expected in paper trading
# Live trading with margin account supports shorts
```

### 3. Low signal frequency
**Cause**: Pairs are near equilibrium
**Solution**: Normal behavior. Pairs trading has ~10-20 trades/year per pair.

### 4. High correlation but no signals
**Cause**: Spread is stable (good thing!)
**Solution**: Monitor z-scores. Signals come when spread diverges.

## Performance Expectations

### Academic Results (Gatev et al. 2006)
- **Annual Return**: 11-12% (after costs)
- **Sharpe Ratio**: 1.0-1.4
- **Max Drawdown**: 10-15%
- **Win Rate**: 65-70%
- **Beta to SPY**: ~0 (market-neutral)

### Modern Implementation (2020-2024)
- Lower returns due to efficiency (8-10% expected)
- Still market-neutral with low correlation to SPY
- Works best in mean-reverting markets
- Struggles in strong trending markets

## Debugging & Monitoring

### Check Pair Correlations

```python
from strategies.pairs_trading import PairsTradingStrategy

strategy = PairsTradingStrategy()
pair_status = strategy.get_pair_status(data)

for status in pair_status:
    print(f"{status['pair']}: corr={status['correlation']:.2f}, z={status['z_score']:.2f}")
```

### Visualize Spreads

```python
import matplotlib.pyplot as plt

# Get spread data
symbol_a, symbol_b = "SPY", "IWM"
prices_a = data[symbol_a]["close"]
prices_b = data[symbol_b]["close"]

hedge_ratio = 1.18
spread = prices_a - hedge_ratio * prices_b

# Plot
plt.figure(figsize=(12, 6))
plt.plot(spread, label="Spread")
plt.axhline(spread.mean(), color='black', linestyle='--', label="Mean")
plt.axhline(spread.mean() + 2*spread.std(), color='red', linestyle='--', label="+2σ")
plt.axhline(spread.mean() - 2*spread.std(), color='green', linestyle='--', label="-2σ")
plt.legend()
plt.title(f"{symbol_a}/{symbol_b} Spread")
plt.show()
```

### Enable Debug Logging

```python
import logging

logging.getLogger("strategies.pairs_trading").setLevel(logging.DEBUG)
```

## Integration with Other Strategies

### Multi-Strategy Portfolio

```python
# Auto trader runs all strategies together
strategies = [
    "dual_momentum",     # Monthly momentum (concentrated)
    "swing_momentum",    # Daily technical (active)
    "ml_momentum",       # ML predictions (adaptive)
    "pairs_trading"      # Market-neutral (diversifier)
]

# Complementary benefits:
# - Dual momentum: Trend following, 100% allocated
# - Swing: Tactical, 15% per position, diversified
# - ML: Data-driven, 10% per position
# - Pairs: Market-neutral, 15% per pair, low correlation
```

### Correlation Matrix (Expected)

|              | Dual Mom | Swing | ML  | Pairs |
|--------------|----------|-------|-----|-------|
| Dual Mom     | 1.00     | 0.60  | 0.50| 0.10  |
| Swing        | 0.60     | 1.00  | 0.70| 0.15  |
| ML           | 0.50     | 0.70  | 1.00| 0.20  |
| Pairs        | 0.10     | 0.15  | 0.20| 1.00  |

Pairs trading provides **low correlation** to momentum strategies, improving Sharpe ratio.

## Next Steps

1. **Backtest**: Run on historical data (2020-2024)
2. **Paper Trade**: Deploy for 3 months minimum
3. **Monitor**: Check z-scores and correlations weekly
4. **Optimize**: Adjust thresholds based on performance
5. **Scale**: Add more pairs as system proves itself

## References

- **Gatev, E., Goetzmann, W., & Rouwenhorst, K. G. (2006)**. "Pairs Trading: Performance of a Relative-Value Arbitrage Rule." Review of Financial Studies, 19(3), 797-827.

- **Engle, R. F., & Granger, C. W. (1987)**. "Co-integration and Error Correction: Representation, Estimation, and Testing." Econometrica, 55(2), 251-276.

## Support

For issues or questions:
1. Check logs: `/Users/work/personal/quant/logs/`
2. Review API: `http://localhost:8000/api/pairs-status`
3. Monitor database: SQLite at `/Users/work/personal/quant/data/quant.db`

---

**Remember**: Pairs trading is a patient strategy. It may take weeks for good entry opportunities. This is normal and expected behavior.
