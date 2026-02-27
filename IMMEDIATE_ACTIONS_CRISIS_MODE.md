# IMMEDIATE ACTIONS - VIX CRISIS MODE
**Date**: February 13, 2026
**VIX**: 39.3 (CRISIS)
**Status**: URGENT ACTION REQUIRED

---

## TL;DR - Do This NOW

```bash
# 1. Emergency position reduction (choose one):
python -m scripts.emergency_profit_lock --reduce-50pct
# OR tighten all stops:
python -m scripts.emergency_profit_lock --breakeven-stops

# 2. Switch to crisis-mode strategies:
# Stop current auto trader (Ctrl+C)
# Restart with only dual_momentum:
python -m scripts.auto_trader --strategies dual_momentum --interval 300

# 3. Check status:
python scripts/show_system_status.py
```

---

## Why This Matters

**VIX 39.3 = CRISIS LEVEL** (same as COVID crash, 2008 financial crisis)

Your system is 62.8% deployed when it should be <25% in crisis mode.

**Academic Evidence** (Daniel & Moskowitz 2016):
- Momentum strategies crash -50% in 1-2 months after high volatility
- Expected Sharpe at VIX >30: **NEGATIVE** (-0.5 to -1.0)

**Current Risk**:
- $63,227 exposed × 50% crash = **-$31,614 potential loss**
- That's -31% account drawdown

---

## Immediate Actions (Next 2 Hours)

### 1. Reduce Exposure IMMEDIATELY

**Current**: 62.8% deployed ($63,227)
**Target**: 15-25% deployed ($15,000-$25,000)
**Need to Exit**: ~$40,000 worth of positions

**Option A: Reduce All Positions by 50%**
```bash
python -m scripts.emergency_profit_lock --reduce-50pct
```

**Option B: Exit Worst Performers**

Exit these positions NOW (manually or via script):
- **NVDA**: -1.0% loss, high volatility ($8,582 position)
- **QQQ**: -0.1% loss, tech heavy ($9,604 position)
- **IWM**: flat, small-cap risk ($7,253 position)
- **ARKK**: flat, speculative ($8,733 position)
- **TSLA**: -0.2% loss, extreme volatility ($7,483 position)

**Keep Only**:
- SOXX: +6.7% (trailing stop will protect)
- XLB: +4.7% (trailing stop will protect)
- XLP: +2.9% (defensive consumer staples)

**Result**: ~$16,400 deployed (16.4%) ✓ SAFE

### 2. Tighten Stop Losses on Remaining Positions

For positions you keep, raise stops to lock in profits:

```bash
python -m scripts.emergency_profit_lock --breakeven-stops
```

Or manually set stops:
- **SOXX**: Raise stop to $345 (lock in +4% profit)
- **XLB**: Raise stop to $51.50 (lock in +2% profit)
- **XLP**: Raise stop to $88.00 (lock in +1.5% profit)

### 3. Halt simple_momentum Strategy

**Current Problem**: simple_momentum inappropriate for VIX 39

**Stop the auto trader**:
```bash
# Press Ctrl+C to stop current daemon
# OR: pkill -f auto_trader
```

**Restart with crisis-appropriate strategy**:
```bash
python -m scripts.auto_trader --strategies dual_momentum --interval 300
```

**Why dual_momentum**:
- Includes absolute momentum filter (goes to bonds when markets negative)
- Performed better than momentum in 2008 GFC and 2020 COVID crash
- Has built-in crisis protection

---

## Short-Term Actions (This Weekend)

### 4. Fix Missing Data

Your backtests failed because 16 symbols missing historical data.

**Download missing data**:
```bash
source venv/bin/activate

# Download individual stocks
python -m scripts.download_historical \
  --symbols NVDA,TSLA,AAPL,MSFT,AMD,AMZN,GOOGL,META,JPM \
  --years 10

# Download ETFs
python -m scripts.download_historical \
  --symbols XLY,XLB,XLP,UPRO,TQQQ,SOXL,GLD,EFA \
  --years 10
```

**Time required**: 2-3 hours (Polygon rate limits: 5 calls/min)

### 5. Re-Run Backtests with Full Data

After downloading data:

```bash
# Comprehensive backtest 2014-2024
python scripts/run_comprehensive_backtest.py \
  --start-date 2014-01-01 \
  --end-date 2024-12-31 \
  --capital 100000
```

**Validation criteria** (academic minimum):
- Sharpe Ratio > 1.0
- Max Drawdown < 20%
- Win Rate > 55%

**If strategies fail**: HALT immediately, don't trade them.

### 6. Fix dual_momentum Parameters

**Current settings** (WRONG):
```python
DEFAULT_LOOKBACK = 126  # 6 months
DEFAULT_SKIP_DAYS = 10  # 2 weeks
```

**Academic standard** (Antonacci 2013):
```python
DEFAULT_LOOKBACK = 252  # 12 months ✓
DEFAULT_SKIP_DAYS = 21  # 1 month ✓
```

**Edit file**: `/Users/work/personal/quant/strategies/dual_momentum.py`

Change lines 61-62:
```python
DEFAULT_LOOKBACK = 252  # 12 months (was 126)
DEFAULT_SKIP_DAYS = 21  # 1 month (was 10)
```

Re-run backtest after fixing:
```bash
python -m scripts.run_backtest --strategy dual_momentum --start 2014-01-01 --end 2024-12-31
```

Expected improvement: Sharpe -3.44 → 0.8-1.2

---

## Next Week Actions

### 7. Integrate VIX Regime Detection

**Problem**: Strategies have `current_regime_multiplier=1.0` hardcoded

**Fix simple_momentum.py** (line 393):

```python
# Current (WRONG):
current_regime_multiplier=1.0  # TODO: integrate with regime detector

# Fixed:
from strategies.regime_detector import VIXRegimeDetector

# At top of calculate_position_size():
vix_detector = VIXRegimeDetector()
current_vix = self._get_current_vix()  # Add this helper method
_, regime_multiplier = vix_detector.detect_regime(current_vix)

# Then use it:
target_size = self.kelly_sizer.calculate_position_size(
    strategy_name=self.name,
    portfolio_value=portfolio_value,
    signal_strength=signal.strength,
    current_regime_multiplier=regime_multiplier  # VIX 39 = 0.25
)
```

**Repeat for factor_composite.py** (line 523)

**Expected impact**:
- VIX 39: Positions reduced to 25% of normal (12% → 3% max)
- VIX 25-35: Positions at 50% (12% → 6% max)
- VIX 15-25: Positions at 80% (12% → 9.6% max)
- VIX <15: Positions at 100% (12% max)

---

## Monitoring Checklist

### Daily (Every Morning Before Market Open)

```bash
# 1. Check VIX level
python -c "
from data.alpaca_data_client import AlpacaDataClient
client = AlpacaDataClient()
vix = client.get_current_quote('VIX')['last']
print(f'VIX: {vix:.1f}')
if vix > 35:
    print('⚠️  CRISIS MODE - Max 25% deployment')
elif vix > 30:
    print('⚠️  ELEVATED - Max 40% deployment')
elif vix > 25:
    print('⚠️  BEAR MODE - Max 60% deployment')
else:
    print('✓ Normal - Up to 95% deployment')
"

# 2. Check system status
python scripts/show_system_status.py | head -50

# 3. Check drawdown
python -m scripts.auto_trader --status-only | grep "Total P&L"
```

### When to Resume Normal Operations

**Criteria for exiting crisis mode**:
1. VIX drops below 30 for 3+ consecutive days
2. Account P&L back to breakeven or better
3. All strategies validated with Sharpe >1.0
4. No individual position down >3%

**Transition steps** (VIX 30 → 25):
1. Increase deployment to 40-50%
2. Add 1-2 defensive positions (XLP, XLV, XLU)
3. Keep simple_momentum paused until VIX <25

**Return to normal** (VIX <25):
1. Increase deployment to 70-80%
2. Resume simple_momentum (if validated)
3. Add factor_composite (if validated)
4. Max position size still 12% (don't get overconfident)

---

## Red Flags - Stop Trading If You See These

1. **VIX jumps >5 points in one day**
   - Action: Close all positions, go 100% cash

2. **Daily loss exceeds -5%**
   - Action: Circuit breaker should halt automatically
   - If not, manually stop trading

3. **Any position down >8%**
   - Action: Exit immediately (stop loss should trigger at -2%)
   - If not triggered, something is broken - investigate

4. **Correlation spike: All positions moving together**
   - Action: Diversification has failed, reduce to top 2-3 positions

5. **No new signals for 48+ hours**
   - Action: Data feed may be broken, check manually

---

## Emergency Contacts & Resources

### Check System Health
```bash
# Auto trader status
python -m scripts.auto_trader --status-only

# Recent logs
tail -100 logs/auto_trader_$(date +%Y%m%d).log

# Position tracker state
python -c "
from execution.position_tracker import PositionTracker
pt = PositionTracker()
print(f'Tracked positions: {len(pt.positions)}')
"
```

### Manual Override Commands

```bash
# Close ALL positions immediately (emergency)
python -c "
from execution.alpaca_client import AlpacaClient
client = AlpacaClient()
client.close_all_positions()
print('✓ All positions closed')
"

# Cancel ALL pending orders
python -c "
from execution.alpaca_client import AlpacaClient
client = AlpacaClient()
client.cancel_all_orders()
print('✓ All orders cancelled')
"
```

### Key Files to Monitor

- **Position tracker**: `data/quant.db` (SQLite table: position_tracker)
- **Trading logs**: `logs/auto_trader_$(date +%Y%m%d).log`
- **System health**: `logs/auto_trader_heartbeat.json`
- **Config**: `config/config.yaml`

---

## Expected Timeline

### Today (Feb 13)
- ✓ Read this document
- ⏳ Reduce positions to 15-25%
- ⏳ Tighten stop losses
- ⏳ Switch to dual_momentum only

### This Weekend (Feb 15-16)
- ⏳ Download missing historical data (2-3 hours)
- ⏳ Fix dual_momentum parameters
- ⏳ Re-run comprehensive backtests
- ⏳ Validate strategies meet academic standards

### Next Week (Feb 17-21)
- ⏳ Integrate VIX regime detection
- ⏳ Test VIX-adjusted position sizing
- ⏳ Monitor daily for VIX decline

### VIX Recovery (TBD)
- When VIX < 30: Gradually increase to 40-50%
- When VIX < 25: Resume normal operations
- When VIX < 20: Full deployment (with validated strategies)

---

## Success Metrics

**By end of crisis period** (VIX returns to <25):

1. **Capital Preservation**: Account value ≥ $98,000 (max -2.5% loss from today)
2. **Position Count**: 2-4 positions during crisis, scaling up as VIX drops
3. **Strategy Validation**: All live strategies have Sharpe >1.0 in backtests
4. **Risk Controls**: VIX regime detection integrated and working
5. **Preparedness**: Ready to scale up when opportunity returns

**Remember**: The goal during crisis is **survival, not growth**.

---

## One-Page Summary (Print This)

```
VIX CRISIS MODE CHECKLIST

[ ] IMMEDIATE (Today):
    [ ] Reduce positions to 15-25% deployment
    [ ] Tighten stops to breakeven on remaining positions
    [ ] Switch to dual_momentum strategy only
    [ ] Stop simple_momentum and factor_composite

[ ] THIS WEEKEND:
    [ ] Download missing data (2-3 hours)
    [ ] Fix dual_momentum lookback: 126→252 days
    [ ] Re-run backtests 2014-2024
    [ ] Validate Sharpe >1.0, DD <20%, WR >55%

[ ] NEXT WEEK:
    [ ] Integrate VIX regime detection in strategies
    [ ] Test VIX-adjusted position sizing
    [ ] Monitor VIX daily for decline signal

[ ] ONGOING:
    [ ] Daily VIX check before market open
    [ ] Keep deployment <25% until VIX <30
    [ ] No new positions unless VIX declining
    [ ] Raise stops weekly to lock profits

CRISIS EXIT CRITERIA:
• VIX <30 for 3+ days → increase to 50%
• VIX <25 for 1+ week → return to normal
• Account P&L positive
• All strategies validated

EMERGENCY STOP:
• Daily loss >-5% → halt all trading
• VIX jumps >5 in 1 day → 100% cash
• Any position down >8% → exit immediately
```

---

**BOTTOM LINE**: You're in a VIX 39 crisis environment with 62.8% deployment. This is like driving 100 mph on an icy road. **SLOW DOWN IMMEDIATELY** by cutting positions to <25%. Everything else can wait.

**Questions?** Check the full analysis: `STRATEGIC_ANALYSIS_VIX_CRISIS_20260213.md`
