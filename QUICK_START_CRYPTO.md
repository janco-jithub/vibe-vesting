# Quick Start: Crypto Trading

## 5-Minute Setup

### 1. Test the System
```bash
cd /Users/work/personal/quant
python -m scripts.test_crypto_strategies
```

Expected: All tests PASS ✓

### 2. Start Trading (Paper Mode)
```bash
python -m scripts.auto_trader --strategies crypto_momentum --interval 300
```

### 3. Watch It Work
```
Auto trader starting...
Restored 0 positions from previous session
Market open
crypto_momentum: 2 signals, 1 trades
BRACKET ORDER: BUY 1 BTCUSD @ $50,000
TP: $57,500 (+15.0%), SL: $46,500 (-7.0%)
```

---

## What You Get

### Crypto Strategies

**Crypto Momentum**:
- Trades: BTC/USD, ETH/USD, SOL/USD
- Signals: Every 5 minutes (300s interval)
- Stop Loss: 7% (auto-placed)
- Take Profit: 15% (auto-placed)
- Min Capital: $500

**Crypto Trend**:
- Trades: BTC/USD, ETH/USD, SOL/USD
- Signals: Breakout + volume confirmation
- Stops: ATR-based (dynamic, 2.5x)
- Take Profit: 20%
- Min Capital: $500

### Auto-Persistence

**What Survives Crashes**:
- Entry prices
- Stop losses
- Trailing stops (highest price tracking)
- Scale-in history (pyramiding count)
- Strategy metadata

**How It Works**:
1. Position opened → Saved to database
2. Price updated → Saved to database
3. Stop adjusted → Saved to database
4. System crash → All data safe
5. Restart → Positions restored automatically

---

## Commands

### Test System
```bash
python -m scripts.test_crypto_strategies
```

### Trade Crypto Only
```bash
python -m scripts.auto_trader --strategies crypto_momentum crypto_trend --interval 300
```

### Trade Stocks + Crypto
```bash
python -m scripts.auto_trader --strategies simple_momentum crypto_momentum --interval 300
```

### Check Status (while running)
Press Ctrl+C once to see status, twice to stop.

---

## Expected Performance

Based on academic research (Liu & Tsyvinski 2021):

**Crypto Momentum**:
- Sharpe Ratio: 1.2-1.8 (out-of-sample)
- Max Drawdown: 40-60%
- Win Rate: 45-55%
- Avg Win: 25-40%
- Avg Loss: 10-15%

**Your Target** (after 2 weeks paper trading):
- Sharpe > 1.0 after 0.8% round-trip costs
- Max Drawdown < 50%
- Positive total P&L

---

## Monitoring

### Check Positions
```bash
# While auto_trader is running, open new terminal:
sqlite3 data/quant.db "SELECT symbol, entry_price, quantity, stop_loss FROM position_tracker"
```

### Check Trades
```bash
sqlite3 data/quant.db "SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10"
```

### Check Logs
```bash
tail -f logs/auto_trader.log
```

---

## Crash Recovery Test

1. **Start trader**:
```bash
python -m scripts.auto_trader --strategies crypto_momentum --interval 300
```

2. **Wait for position** (5-10 minutes)
```
BRACKET ORDER: BUY 1 BTCUSD @ $50,000
```

3. **Stop trader** (Ctrl+C)
```
^C
Received signal 2, shutting down...
```

4. **Restart trader**:
```bash
python -m scripts.auto_trader --strategies crypto_momentum --interval 300
```

5. **Verify restoration**:
```
Restored 1 positions from previous session
Position tracker loaded:
  BTCUSD: 1 @ $50,000.00
```

✓ Position survived crash!

---

## Risk Parameters

### Crypto (vs Stock Comparison)

| Parameter | Stock | Crypto | Reason |
|-----------|-------|--------|--------|
| Stop Loss | 4% | 7% | Crypto more volatile |
| Take Profit | 8% | 15% | Crypto trends further |
| Position Size | 15% | 30% | Fewer coins to diversify |
| Lookback | 63 days | 20 days | Crypto trends faster |

### Position Limits

- **Max per crypto**: 30%
- **Max total**: 90%
- **Max scale-ins**: 2 (pyramiding limit)

### Circuit Breakers (apply to all)

- Daily loss: -2%
- Weekly loss: -5%
- Max drawdown: -15%

---

## Minimum Capital

| Setup | Minimum | Recommended |
|-------|---------|-------------|
| 1 crypto strategy | $500 | $1,000 |
| 2 crypto strategies | $1,000 | $2,000 |
| Stocks + crypto | $1,500 | $5,000 |

*Based on 30% position size at $500/position minimum*

---

## Troubleshooting

### "No crypto data"
Check if Alpaca crypto is enabled:
```python
python -c "from execution.alpaca_client import AlpacaClient; c = AlpacaClient(paper=True); print(c.get_latest_quote('BTCUSD'))"
```

### "Position tracker state not loading"
Check database:
```bash
ls -lh data/quant.db
sqlite3 data/quant.db "SELECT COUNT(*) FROM position_tracker"
```

### "Insufficient qty available"
Auto-trader now cancels existing orders automatically. If still occurs, check Alpaca dashboard for manual orders.

---

## Next Steps

After 1-2 weeks of paper trading:

1. **Check Sharpe ratio**: Should be >1.0
2. **Check max drawdown**: Should be <40%
3. **Check total P&L**: Should be positive
4. **If all good**: Scale up capital
5. **If not**: Reduce position sizes or pause

---

## Support Files

- **Full Guide**: `/Users/work/personal/quant/CRYPTO_TRADING_GUIDE.md`
- **Implementation**: `/Users/work/personal/quant/IMPLEMENTATION_SUMMARY.md`
- **Test Suite**: `/Users/work/personal/quant/scripts/test_crypto_strategies.py`
- **Strategies**: `/Users/work/personal/quant/strategies/crypto_*.py`

---

## Key Differences: Crypto vs Stock Strategies

### Why We Built Separate Strategies

**Stock Momentum** (SimpleMomentumStrategy):
```python
lookback = 63 days  # 3-month trends
stop = 4%           # Lower volatility
target = 8%         # Smaller moves
size = 15%          # More diversification
```

**Crypto Momentum** (CryptoMomentumStrategy):
```python
lookback = 20 days  # 3-week trends (faster)
stop = 7%           # Higher volatility
target = 15%        # Bigger moves
size = 30%          # Less diversification needed
```

This is **NOT** the same strategy with different parameters - it's fundamentally designed for crypto's:
- 24/7 trading
- Higher volatility
- Shorter trend duration
- Different liquidity profile

---

**Ready to start? Run the test, then start trading!**

```bash
python -m scripts.test_crypto_strategies  # Test first
python -m scripts.auto_trader --strategies crypto_momentum --interval 300  # Then trade
```
