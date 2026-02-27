# VIX Regime Quick Reference Card
**Last Updated**: February 13, 2026

---

## VIX Level Guide

| VIX Range | Regime | Max Deployment | Position Size | Active Strategies | Expected Sharpe |
|-----------|--------|----------------|---------------|-------------------|-----------------|
| **< 15** | Bull | 95% | 12% | All (momentum favored) | 1.5-2.0 |
| **15-25** | Normal | 80% | 10% | All strategies | 1.2-1.6 |
| **25-30** | Elevated | 60% | 8% | Dual momentum, factor, pairs | 0.8-1.2 |
| **30-35** | Bear | 40% | 6% | Dual momentum, defensive | 0.5-0.9 |
| **35-40** | **CRISIS** | **25%** | **3%** | **Dual momentum ONLY** | **<0.5** |
| **> 40** | Panic | 10% | 2% | Cash + bonds | Negative |

---

## Current Status (VIX 39.3)

### You Are Here: CRISIS MODE

```
✗ Current Deployment: 62.8% (TOO HIGH!)
✓ Target Deployment:  15-25%
! Gap:                -38% to -48% OVER-DEPLOYED
```

**Immediate Action**: Exit ~$40,000 of positions

---

## Trading Rules by VIX Level

### VIX < 15 (BULL MARKET)
```
✓ Aggressive momentum strategies
✓ Growth stocks, tech, small-caps
✓ Leveraged ETFs (TQQQ, UPRO) OK
✓ Full position sizes (12%)
✓ Looser stops (5-6%)

Strategy Mix:
- 40-45% simple_momentum
- 30-35% factor_composite
- 15-20% leveraged ETFs
- 5-10% pairs trading
```

### VIX 15-25 (NORMAL MARKET)
```
✓ Balanced strategy allocation
✓ Standard position sizes (10%)
✓ Normal stops (4%)
✓ All strategies active

Strategy Mix:
- 35-40% simple_momentum
- 25-30% factor_composite
- 15-20% pairs trading
- 10-15% dual_momentum
```

### VIX 25-30 (ELEVATED VOLATILITY)
```
⚠ Start reducing risk
⚠ Avoid leveraged ETFs
⚠ Reduce position sizes to 8%
⚠ Tighter stops (3%)

Strategy Mix:
- 25-30% dual_momentum
- 20-25% low_vol_factor
- 20-25% factor_composite
- 15-20% pairs trading
- 10-15% simple_momentum
```

### VIX 30-35 (BEAR MARKET)
```
⚠ High risk environment
⚠ Defensive only
⚠ Small positions (6%)
⚠ Very tight stops (2%)

Strategy Mix:
- 30-35% dual_momentum (bonds allocation)
- 25-30% defensive sectors (XLP, XLU, XLV)
- 20-25% low_vol_factor
- 15-20% pairs trading
- 0% momentum strategies
```

### VIX 35-40 (CRISIS) ← **YOU ARE HERE**
```
⚠️ CAPITAL PRESERVATION MODE ⚠️
✗ NO new positions unless VIX declining
✗ NO momentum strategies
✗ NO tech/growth/small-caps
✗ Tiny positions (3%)

Strategy Mix:
- 50-60% CASH
- 20-30% dual_momentum (bonds)
- 10-20% defensive sectors
- 0-10% pairs trading (if working)
```

### VIX > 40 (PANIC)
```
🚨 EMERGENCY MODE 🚨
• Go 90%+ CASH immediately
• Close all positions except bonds
• Wait for VIX to peak and decline
• DO NOT try to "buy the dip"
```

---

## Position Sizing Calculator

### Formula
```
Position Size = Base Size × Signal Strength × VIX Multiplier
```

### VIX Multipliers
```python
def get_vix_multiplier(vix: float) -> float:
    if vix < 15:
        return 1.0
    elif vix < 20:
        return 0.85  # -15%
    elif vix < 25:
        return 0.70  # -30%
    elif vix < 30:
        return 0.50  # -50%
    elif vix < 35:
        return 0.35  # -65%
    else:
        return 0.25  # -75% (CRISIS)
```

### Examples

**Base position: 12% of portfolio = $12,000**

| VIX | Multiplier | Adjusted Size | Dollar Amount |
|-----|------------|---------------|---------------|
| 12  | 1.00       | 12%           | $12,000       |
| 18  | 0.85       | 10.2%         | $10,200       |
| 22  | 0.70       | 8.4%          | $8,400        |
| 28  | 0.50       | 6.0%          | $6,000        |
| 32  | 0.35       | 4.2%          | $4,200        |
| **39** | **0.25** | **3.0%** | **$3,000** |
| 45  | 0.25       | 3.0%          | $3,000        |

---

## Stop Loss Adjustment by VIX

| VIX Range | Stop Loss | Trailing Stop | Rationale |
|-----------|-----------|---------------|-----------|
| < 15      | -3%       | 5%            | Tight (low volatility) |
| 15-25     | -4%       | 4%            | Normal |
| 25-30     | -5%       | 3%            | Wider (more volatility) |
| 30-35     | -6%       | 2.5%          | Much wider |
| **>35**   | **-2%**   | **2%**        | **Tight (protect capital)** |

**Crisis Mode Logic**: In VIX >35, use TIGHTER stops because:
1. Positions are already small (3% vs 12%)
2. False breakouts are common
3. Goal is preservation, not letting losses run

---

## Strategy Performance by VIX Regime

### Historical Sharpe Ratios (Academic Studies)

| Strategy | VIX <20 | VIX 20-30 | VIX >30 | Best Use |
|----------|---------|-----------|---------|----------|
| Momentum | 1.2-1.5 | 0.5-0.8 | **-0.5** | Bull only |
| Dual Momentum | 0.9-1.2 | 0.8-1.1 | 0.5-0.8 | All regimes |
| Low Vol Factor | 0.8-1.0 | 1.0-1.3 | 1.2-1.5 | High VIX |
| Pairs Trading | 1.0-1.2 | 1.2-1.4 | 1.3-1.5 | High VIX |
| Factor Composite | 1.2-1.5 | 1.0-1.3 | 0.6-0.9 | Normal |

**Key Insight**: Low-vol and pairs **improve** in high VIX, while momentum **crashes**.

---

## Daily VIX Check Script

Save this as `/Users/work/personal/quant/scripts/check_vix.py`:

```python
#!/usr/bin/env python3
"""Quick VIX regime check."""

from data.alpaca_data_client import AlpacaDataClient
from strategies.regime_detector import VIXRegimeDetector

client = AlpacaDataClient()
detector = VIXRegimeDetector()

# Get current VIX
vix_quote = client.get_current_quote("VIX")
vix = vix_quote['last']

# Detect regime
regime, multiplier = detector.detect_regime(vix)

# Calculate recommended deployment
base_deployment = 0.95  # 95% max in normal
recommended = base_deployment * multiplier

# Display
print("\n" + "="*60)
print(f"VIX REGIME CHECK - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("="*60)
print(f"VIX Level:              {vix:.1f}")
print(f"Regime:                 {regime.value.upper()}")
print(f"Position Multiplier:    {multiplier:.0%}")
print(f"Max Deployment:         {recommended:.0%}")
print(f"Max Position Size:      {0.12 * multiplier:.1%}")
print("="*60)

if vix > 35:
    print("🚨 CRISIS MODE - Reduce positions IMMEDIATELY")
    print("   Target: 15-25% total deployment")
    print("   Max position: 3%")
    print("   Strategies: dual_momentum ONLY")
elif vix > 30:
    print("⚠️  BEAR MODE - Reduce risk")
    print("   Target: 30-40% deployment")
    print("   Avoid: momentum strategies")
elif vix > 25:
    print("⚠️  ELEVATED - Be cautious")
    print("   Target: 50-60% deployment")
    print("   Reduce: high-beta positions")
elif vix > 20:
    print("✓ NORMAL-HIGH - Standard operations")
    print("   Target: 70-80% deployment")
else:
    print("✓ BULL MODE - Favorable conditions")
    print("   Target: 85-95% deployment")

print("="*60 + "\n")
```

Run daily:
```bash
python scripts/check_vix.py
```

---

## VIX Spike Emergency Procedure

### If VIX Jumps >5 Points in One Day

**Example**: VIX 25 → 32 in one session

**Immediate Actions** (within 1 hour):
1. Close all momentum positions
2. Keep only defensive positions (bonds, staples, utilities)
3. Raise all stops to current price - 2%
4. Go 50%+ cash
5. Monitor hourly for further deterioration

### If VIX Jumps >10 Points

**Example**: VIX 30 → 42 (black swan event)

**Emergency Protocol**:
1. **CLOSE ALL POSITIONS** - go 90%+ cash
2. Cancel all pending orders
3. Halt auto trader
4. Wait 24-48 hours for dust to settle
5. Reassess when VIX stabilizes

**DO NOT**:
- Try to "buy the dip"
- Average down on losing positions
- Use margin
- Trade options (except protective puts)

---

## Historical VIX Spikes (Reference)

| Event | Date | VIX Peak | Duration | Market Impact |
|-------|------|----------|----------|---------------|
| COVID Crash | Mar 2020 | 82.7 | 2 months | -34% SPY |
| Financial Crisis | Oct 2008 | 89.5 | 6 months | -57% SPY |
| Euro Crisis | Aug 2011 | 48.0 | 3 months | -19% SPY |
| Trump Election | Nov 2016 | 22.6 | 2 days | +5% SPY |
| Feb 2018 Volmageddon | Feb 2018 | 50.3 | 1 week | -10% SPY |
| COVID Peak 2 | Oct 2020 | 40.3 | 2 weeks | -8% SPY |
| 2022 Bear Market | Jun 2022 | 34.6 | 3 months | -25% SPY |

**Average VIX >35 event**:
- Duration: 2-8 weeks
- Market decline: -15% to -30%
- Recovery time: 3-6 months

---

## Exit Strategy: Crisis → Normal

### Phase 1: VIX Peaks (40+ → 35)
```
• Stay 75%+ cash
• Only trade dual_momentum
• Very tight stops (2%)
• Monitor hourly
```

### Phase 2: VIX Declining (35 → 30)
```
• Increase to 40% deployment
• Add defensive sectors
• Position size: 5-6%
• Monitor daily
```

### Phase 3: VIX Stabilizing (30 → 25)
```
• Increase to 60% deployment
• Add low-vol factor
• Position size: 8%
• Monitor daily
```

### Phase 4: VIX Normal (25 → 20)
```
• Return to 80% deployment
• Resume factor_composite
• Position size: 10%
• Resume normal operations
```

### Phase 5: VIX Bull (< 20)
```
• Full deployment 90-95%
• Resume all strategies
• Position size: 12%
• Watch for complacency
```

**Key Rule**: Wait for 3+ consecutive days below each threshold before advancing.

---

## Quick Commands

```bash
# Check VIX
python scripts/check_vix.py

# Check deployment
python scripts/show_system_status.py | grep "Capital Deployed"

# Emergency: Close 50% of all positions
python -m scripts.emergency_profit_lock --reduce-50pct

# Emergency: Go 100% cash
python -c "from execution.alpaca_client import AlpacaClient; AlpacaClient().close_all_positions()"

# Restart with crisis-mode strategy
python -m scripts.auto_trader --strategies dual_momentum --interval 300
```

---

## Phone App Alerts (If Available)

Set up alerts on your Alpaca mobile app:

1. **VIX Alerts**:
   - Alert at 30 (reduce risk)
   - Alert at 35 (crisis mode)
   - Alert at 40 (emergency)

2. **Position Alerts**:
   - Any position down 5%
   - Daily P&L down 3%
   - Total deployment >70% in crisis

3. **System Alerts**:
   - Auto trader stopped
   - Circuit breaker triggered
   - No signals in 48 hours

---

## Print This Page

**Laminate and keep at desk for quick reference during market hours.**

```
┌─────────────────────────────────────────────────┐
│ VIX QUICK GUIDE                                 │
├─────────────────────────────────────────────────┤
│ < 15   Bull    → 95% deployed, 12% positions    │
│ 15-25  Normal  → 80% deployed, 10% positions    │
│ 25-30  High    → 60% deployed, 8% positions     │
│ 30-35  Bear    → 40% deployed, 6% positions     │
│ 35-40  CRISIS  → 25% deployed, 3% positions ⚠️  │
│ > 40   PANIC   → 10% deployed, CASH MODE 🚨     │
├─────────────────────────────────────────────────┤
│ Current: VIX 39.3 = CRISIS MODE                 │
│ Action Required: Reduce to 25% deployment       │
└─────────────────────────────────────────────────┘
```

---

**Remember**: VIX is a measure of fear, not direction. High VIX means high uncertainty, which kills momentum strategies. When in doubt, **reduce size**.

**Golden Rule**: "In a crisis, he who panics first, panics best." Be proactive, not reactive.
