# Quantitative Trading System

A world-class automated trading system with multi-factor strategies, regime detection, and advanced risk management.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```bash
# Alpaca API (Paper Trading)
APCA_API_KEY_ID=your_alpaca_key
APCA_API_SECRET_KEY=your_alpaca_secret
APCA_API_BASE_URL=https://paper-api.alpaca.markets

# Polygon API (Market Data)
POLYGON_API_KEY=your_polygon_key

# Optional: Slack Alerts
SLACK_WEBHOOK=https://hooks.slack.com/services/xxx/yyy/zzz
```

### 3. Start the Trading System

**Option A: Run with Auto-Restart Daemon (Recommended)**

```bash
python -m scripts.auto_trader_daemon --strategies factor_composite simple_momentum pairs_trading --interval 300
```

**Option B: Run Directly**

```bash
python -m scripts.auto_trader --strategies factor_composite simple_momentum --interval 300
```

**Option C: Check Status Only**

```bash
python -m scripts.auto_trader --status-only
```

## System Architecture

```
quant/
├── strategies/           # Trading strategies
│   ├── factor_composite.py   # Multi-factor strategy (Momentum, Quality, Low Vol, Value)
│   ├── simple_momentum.py    # Trend-following momentum
│   ├── pairs_trading.py      # Statistical arbitrage
│   ├── regime_detector.py    # Market regime detection (Bull/Bear/Sideways)
│   └── ...
├── risk/                 # Risk management
│   ├── kelly_sizing.py       # Kelly Criterion position sizing
│   ├── var_calculator.py     # VaR and CVaR risk metrics
│   ├── portfolio_construction.py  # HRP, Risk Parity allocation
│   ├── circuit_breakers.py   # Trading halts on drawdowns
│   └── profit_optimizer.py   # Trailing stops, scale-outs
├── execution/            # Order execution
│   ├── alpaca_client.py      # Alpaca API wrapper
│   ├── order_manager.py      # Order lifecycle management
│   └── position_tracker.py   # Position state tracking
├── data/                 # Data management
│   ├── polygon_client.py     # Market data from Polygon
│   └── storage.py            # SQLite database
├── monitoring/           # System monitoring
│   ├── health_monitor.py     # Health checks
│   └── alerting.py           # Slack/console alerts
├── scripts/              # Entry points
│   ├── auto_trader.py        # Main trading loop
│   └── auto_trader_daemon.py # Daemon with auto-restart
└── frontend/             # React dashboard
```

## Available Strategies

| Strategy | Description | Expected Sharpe |
|----------|-------------|-----------------|
| `factor_composite` | Multi-factor (Mom, Quality, LowVol, Value) | 1.2-1.8 |
| `simple_momentum` | 100-day SMA trend following | 1.0-1.4 |
| `pairs_trading` | Statistical arbitrage on correlated pairs | 1.0-1.3 |
| `swing_momentum` | Medium-term momentum swings | 0.8-1.2 |
| `ml_momentum` | Machine learning enhanced momentum | 1.0-1.5 |
| `dual_momentum` | Relative + absolute momentum | 0.9-1.3 |

## Key Features

### Regime Detection
- Automatically detects Bull/Bear/Sideways markets
- Reduces position sizes by 50% in bear markets
- Based on Kritzman et al. (2012)

### Kelly Position Sizing
- Uses fractional Kelly (1/4) for optimal bet sizing
- Adjusts for signal strength and market regime
- Max 15% per position, min 2%

### Risk Management
- VaR/CVaR monitoring with automatic alerts
- Circuit breakers halt trading at 5% daily loss
- Trailing stops and automatic profit-taking
- Bracket orders with take-profit and stop-loss

### Profit Optimization
- Scale out 50% at +3% profit
- Trailing stops at 3%
- Pyramiding into winners (max 2 add-ons)
- Fast exit at -2% loss

## Command Reference

### Auto Trader

```bash
# Full options
python -m scripts.auto_trader \
    --strategies factor_composite simple_momentum pairs_trading \
    --interval 300 \
    --db data/quant.db

# Run one cycle and exit
python -m scripts.auto_trader --run-once

# Status check
python -m scripts.auto_trader --status-only
```

### Daemon (Production)

```bash
# Start daemon with monitoring
python -m scripts.auto_trader_daemon \
    --strategies factor_composite simple_momentum \
    --interval 300 \
    --health-interval 60 \
    --max-restarts 5
```

### Frontend Dashboard

```bash
# Start API server
cd /Users/work/personal/quant
uvicorn api.main:app --reload --port 8000

# Start React frontend (separate terminal)
cd frontend
npm start
```

## Logs and Monitoring

- **Trading logs**: `logs/auto_trader.log`
- **Daemon logs**: `logs/daemon.log`
- **Alerts**: `logs/alerts.log`
- **Heartbeat**: `logs/auto_trader_heartbeat.json`

## Database

SQLite database at `data/quant.db` stores:
- Daily price bars
- Trade history
- Position state
- Strategy performance

## Performance Targets

| Metric | Target |
|--------|--------|
| Sharpe Ratio | 1.5-2.0 |
| Max Drawdown | < 15% |
| Win Rate | 58-65% |
| CAGR | 25-35% |

## Academic References

1. **Fama & French (1993)** - Value and Size factors
2. **Jegadeesh & Titman (1993)** - Momentum effect
3. **Asness et al. (2019)** - Quality factor
4. **Ang et al. (2006)** - Low volatility anomaly
5. **Kritzman et al. (2012)** - Regime detection
6. **Lopez de Prado (2016)** - Hierarchical Risk Parity
7. **Kelly (1956)** - Optimal position sizing

## Troubleshooting

### "Market closed" message
Normal outside trading hours (9:30 AM - 4:00 PM ET).

### "Insufficient qty available" error
Bracket orders lock shares. System automatically cancels existing orders before selling.

### High memory usage
Daemon performs hourly cleanup. Restart if memory exceeds 2GB.

### No signals generated
Check that market data is being fetched. Verify Polygon API key is valid.

## License

Private - All rights reserved.
