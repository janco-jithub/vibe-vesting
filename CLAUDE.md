# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A professional-grade quantitative trading system focused on maximizing risk-adjusted returns using academically-validated strategies. Python 3.11+ with strict risk management and correctness-over-cleverness philosophy.

## Commands

```bash
# Activate virtual environment
source venv/bin/activate

# === DASHBOARD ===
# Start the web dashboard (API + React frontend)
./scripts/start_dashboard.sh
# Or start separately:
python -m uvicorn api.server:app --port 8000  # API: http://localhost:8000
cd frontend && npm run dev                     # UI: http://localhost:5173

# === DATA ===
# Download historical data (required before backtesting)
python -m scripts.download_historical --symbols SPY,QQQ,TLT --years 10

# === BACKTESTING ===
# Run backtest
python -m scripts.run_backtest --strategy dual_momentum --start 2014-01-01 --end 2024-12-31

# Run walk-forward analysis
python -m scripts.run_backtest --strategy dual_momentum --walk-forward

# === PAPER TRADING ===
# Start paper trading
python -m scripts.run_paper_trading --strategy dual_momentum

# Check paper trading status only
python -m scripts.run_paper_trading --check-only

# === TESTING ===
# Run tests with coverage
pytest tests/ -v --cov=.

# Run single test file
pytest tests/unit/test_strategy.py -v
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      TRADING SYSTEM                         │
├─────────────┬─────────────┬─────────────┬───────────────────┤
│  Data Layer │  Strategy   │    Risk     │    Execution      │
│             │   Engine    │  Management │                   │
├─────────────┼─────────────┼─────────────┼───────────────────┤
│ • Ingestion │ • Signals   │ • Position  │ • Order Mgmt      │
│ • Storage   │ • Backtest  │   Sizing    │ • Broker API      │
│ • Features  │ • ML Models │ • Limits    │ • Fills Tracking  │
└─────────────┴─────────────┴─────────────┴───────────────────┘
```

- **data/**: Polygon.io client with rate limiting, SQLite storage, data validation
- **strategies/**: BaseStrategy abstract class, DualMomentumStrategy implementation
- **backtest/**: Backtesting engine with transaction costs, performance metrics (Sharpe, Sortino, etc.)
- **risk/**: Position sizing (fixed, Kelly), circuit breakers (daily/weekly loss, max drawdown)
- **execution/**: Alpaca client (paper trading), order manager with risk validation
- **monitoring/**: Structured logging (structlog)
- **scripts/**: CLI tools for data download, backtesting, paper trading

## Key Patterns

### Strategy Implementation
All strategies inherit from `BaseStrategy` (strategies/base.py) and must implement:
- `generate_signals(data: Dict[str, pd.DataFrame]) -> List[Signal]`
- `calculate_position_size(signal, portfolio_value, current_positions) -> float`
- `get_backtest_params() -> BacktestParams`

### Risk Validation
Every order must pass through the risk manager (risk/circuit_breakers.py):
```python
if not risk_manager.validate_order(order):
    raise RiskLimitExceeded(risk_manager.get_violation_reason())
```

### Hard-Coded Risk Limits (from config/config.yaml)
- Max single position: 5% of portfolio
- Max sector exposure: 25% of portfolio
- Daily loss limit: -2% (halts trading until next day)
- Weekly loss limit: -5% (halts trading until next week)
- Maximum drawdown halt: -15% (requires manual resume)

## Critical Requirements

### Backtesting Integrity
- Transaction costs: 10 bps (0.1%) per trade
- Slippage: 10 bps (0.1%) market impact
- Walk-forward validation only (no random train/test splits)
- Point-in-time data (avoid look-ahead bias)

### Code Standards
- Type hints required on all functions
- Docstrings required on public functions/classes
- Structured logging: `logger.info("event_name", key=value)`
- UTC timezone internally for all timestamps

### Data Validation (data/storage.py)
- Check for missing values
- Verify price continuity (no >20% gaps without corporate actions)

## Environment Variables (.env)

```bash
ALPACA_API_KEY=           # Trading API key
ALPACA_SECRET_KEY=        # Trading API secret
POLYGON_API_KEY=          # Market data API key
DATABASE_PATH=data/quant.db
TRADING_ENV=paper         # paper | live
LOG_LEVEL=INFO
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| Data Storage | SQLite (local) |
| Market Data | Polygon.io (free tier: 5 calls/min) |
| Execution | Alpaca API (paper trading) |
| Backend API | FastAPI (Python) |
| Frontend | React + TypeScript + Tailwind + Recharts |
| Testing | pytest (55 tests, >90% coverage target) |

## Current Strategy: Dual Momentum

Based on Antonacci (2013) - combines relative and absolute momentum:
1. Monthly rebalancing (end of month)
2. Compare 12-month returns of SPY vs QQQ
3. If both negative: hold TLT (bonds)
4. If positive: hold the stronger performer

Historical performance (expected): Sharpe ~1.0-1.4, Max DD ~20%
