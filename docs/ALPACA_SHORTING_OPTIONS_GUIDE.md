# Alpaca Shorting and Options Trading: Complete Integration Guide

## Executive Summary

This guide provides a comprehensive analysis of Alpaca's short selling and options trading capabilities, with production-ready code for integrating these features into quantitative trading systems.

**Key Capabilities:**
- ✅ Commission-free short selling (ETB stocks only)
- ✅ Options trading (Levels 1-3 supported)
- ✅ Multi-leg options strategies (spreads, straddles, condors)
- ✅ Full API support for programmatic trading
- ❌ HTB (hard-to-borrow) stocks not yet supported
- ❌ Bracket orders not supported for options

---

## Part 1: Short Selling on Alpaca

### 1.1 Requirements and Eligibility

**Minimum Account Requirements:**
- Account equity: **$2,000 or more**
- Account type: Margin account (all Alpaca accounts are margin by default)
- `shorting_enabled` flag: Must be `True`

**Verification Code:**
```python
from execution.broker.alpaca_advanced import AlpacaAdvancedTrading

trader = AlpacaAdvancedTrading(paper=True)
eligibility = trader.check_short_eligibility()

print(f"Eligible: {eligibility['eligible']}")
print(f"Equity: ${eligibility['equity']:,.2f}")
print(f"Shorting Enabled: {eligibility['shorting_enabled']}")
print(f"Buying Power: ${eligibility['buying_power']:,.2f}")
```

### 1.2 Margin Requirements

**Initial Margin (Regulation T):**
- **50%** of position value for marginable securities
- **100%** for non-marginable securities

**Maintenance Margin (Overnight):**

| Position Type | Price Condition | Requirement |
|--------------|----------------|-------------|
| **Short** | Price < $5.00 | Greater of **$2.50/share** or **100% of market value** |
| **Short** | Price ≥ $5.00 | Greater of **$5.00/share** or **30% of market value** |
| **Long** | Price < $2.50 | **100%** of market value |
| **Long** | Price ≥ $2.50 | **30%** of market value |

**Example Calculation:**
```python
# Short 100 shares of SPY @ $450
margin = trader.calculate_short_margin_requirement("SPY", 100, 450.0)

print(f"Initial Margin: ${margin.initial_margin:,.2f}")        # $22,500 (50%)
print(f"Maintenance Margin: ${margin.maintenance_margin:,.2f}") # $13,500 (30%)
print(f"Buying Power Effect: ${margin.buying_power_effect:,.2f}") # $67,500
```

**Margin Interest Rates (2026):**
- Elite users (≥$100K): **4.75%** annually
- Non-elite users: **6.25%** annually
- Calculation: `(overnight debit balance × rate) / 360`

### 1.3 ETB vs HTB Stocks

**Easy-to-Borrow (ETB):**
- ✅ **5,000+ stocks** available for shorting
- ✅ **$0 borrow fees** (as of October 2025)
- ✅ Commission-free trading
- ✅ Fully supported via API

**Hard-to-Borrow (HTB):**
- ❌ **Not currently supported** for opening new positions
- ⚠️ If an existing short position transitions from ETB → HTB overnight:
  - Open short orders are **automatically cancelled** before market open
  - Existing short positions **remain open** but incur daily borrow fees
  - Borrow fee: `(position value × HTB rate) / 360`
  - Fees charged in round lots (100 shares minimum)

**Risk Management:**
No public API endpoint currently exists to check ETB/HTB status before shorting. Recommendation:
1. Monitor Alpaca community forums for ETB list updates
2. Implement order rejection handling (failed shorts likely due to HTB status)
3. Focus on large-cap, highly liquid stocks (less likely to become HTB)

### 1.4 API Implementation

**Submitting a Short Order:**
```python
# Market order
order = trader.submit_short_order(
    symbol="SPY",
    quantity=100,
    order_type="market",
    check_margin=True  # Verify sufficient buying power
)

# Limit order
order = trader.submit_short_order(
    symbol="SPY",
    quantity=100,
    order_type="limit",
    limit_price=450.00,
    check_margin=True
)

print(f"Order ID: {order['order_id']}")
print(f"Status: {order['status']}")
```

**Covering a Short Position:**
```python
# Cover entire position
result = trader.cover_short_position(
    symbol="SPY",
    quantity=None,  # None = close entire position
    order_type="market"
)

# Partial cover
result = trader.cover_short_position(
    symbol="SPY",
    quantity=50,  # Cover 50 shares
    order_type="limit",
    limit_price=445.00
)
```

**Monitoring Short Positions:**
```python
# Get all short positions
short_positions = trader.get_short_positions()

for position in short_positions:
    print(f"{position['symbol']}: {position['qty']} shares")
    print(f"  Entry: ${position['avg_entry_price']:.2f}")
    print(f"  Current: ${position['current_price']:.2f}")
    print(f"  Unrealized P/L: ${position['unrealized_pl']:.2f}")
```

**Account Information (Short-Related Fields):**
```python
account = trading_client.get_account()

# Key fields for short selling
short_market_value = float(account.short_market_value)  # Negative value
shorting_enabled = account.shorting_enabled  # Boolean
initial_margin = float(account.initial_margin)
maintenance_margin = float(account.maintenance_margin)
buying_power = float(account.buying_power)
```

### 1.5 Risk Management for Short Positions

**Unique Risks:**
1. **Unlimited Loss Potential**: Stock can rise indefinitely
2. **Short Squeeze Risk**: Rapid price increases force covering
3. **Margin Calls**: Insufficient maintenance margin triggers liquidation
4. **Borrow Fees**: HTB stocks incur daily fees
5. **Regulatory Risk**: Short sale restrictions during high volatility

**Risk Management Implementation:**
```python
from execution.broker.alpaca_advanced import ShortPositionRiskManager

risk_mgr = ShortPositionRiskManager(max_short_exposure_pct=0.25)

# Check exposure limits before shorting
allowed, reason = risk_mgr.check_short_exposure(
    account_equity=100000.0,
    current_short_value=15000.0,
    new_short_value=10000.0
)

if not allowed:
    print(f"Cannot short: {reason}")

# Calculate stop loss price (ABOVE entry for shorts)
stop_price = risk_mgr.calculate_stop_loss_price(
    entry_price=450.0,
    max_loss_pct=0.15  # 15% maximum loss
)
print(f"Stop Loss: ${stop_price:.2f}")  # $517.50

# Monitor position and determine if should cover
should_cover, reason = risk_mgr.should_cover_short(
    entry_price=450.0,
    current_price=470.0,
    stop_loss_pct=0.15,
    take_profit_pct=0.20
)

if should_cover:
    print(f"Cover position: {reason}")
```

**Recommended Limits:**
- Maximum short exposure: **25%** of portfolio
- Position-level stop loss: **15%**
- Single position max: **5%** of portfolio
- Short only highly liquid stocks (avg volume > 1M shares/day)

---

## Part 2: Options Trading on Alpaca

### 2.1 Options Trading Levels

Alpaca supports three levels of options trading:

| Level | Strategies | Requirements |
|-------|-----------|--------------|
| **Level 0** | Disabled | N/A |
| **Level 1** | Covered calls, cash-secured puts | Must own underlying shares or have cash |
| **Level 2** | Level 1 + buying calls/puts | Adequate options buying power |
| **Level 3** | Level 1-2 + spreads (vertical, calendar, iron condors) | Sufficient options buying power |

**Paper Trading:** Level 3 enabled by default
**Live Trading:** Requires account approval (contact Alpaca support)

**Checking Options Level:**
```python
options_info = trader.check_options_eligibility()

print(f"Options Enabled: {options_info['options_enabled']}")
print(f"Options Level: {options_info['options_level']}")
print(f"Options Buying Power: ${options_info['options_buying_power']:,.2f}")
```

### 2.2 Supported Options Types

**Contract Details:**
- Exchange-listed US equity and ETF options
- **American style** (can exercise before expiration)
- Standard expiration cycles (monthly, weekly)
- Standard contract size: **100 shares**

**Order Types:**
- Market orders
- Limit orders
- Stop orders (single-leg only)
- Stop-limit orders (single-leg only)

**Restrictions:**
- `time_in_force`: **DAY only** (no GTC for options)
- `extended_hours`: Must be `False` (no pre/post market)
- Orders must use **whole numbers** for quantity
- Expiration day orders: Must submit before **3:15 PM ET**
- Auto-liquidation: Expiring positions liquidated starting **3:30 PM ET**

### 2.3 API Endpoints

**Finding Options Contracts:**
```python
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import AssetStatus, ContractType, ExerciseStyle
from datetime import datetime, timedelta

# Find SPY put options expiring in 30-60 days
now = datetime.now()
exp_min = (now + timedelta(days=30)).date()
exp_max = (now + timedelta(days=60)).date()

request = GetOptionContractsRequest(
    underlying_symbols=["SPY"],
    status=AssetStatus.ACTIVE,
    expiration_date_gte=exp_min,
    expiration_date_lte=exp_max,
    type=ContractType.PUT,
    style=ExerciseStyle.AMERICAN,
    strike_price_gte="440.00",
    strike_price_lte="460.00",
    limit=100
)

contracts = trading_client.get_option_contracts(request)

for contract in contracts.option_contracts:
    print(f"{contract.symbol}: Strike ${contract.strike_price}, "
          f"Exp {contract.expiration_date}, OI {contract.open_interest}")
```

**High-Level Helper (Using Our Implementation):**
```python
# Find contracts matching criteria
contracts = trader.find_options_contracts(
    underlying_symbol="SPY",
    contract_type=ContractType.PUT,
    expiration_min_days=30,
    expiration_max_days=60,
    strike_min=440.0,
    strike_max=460.0,
    min_open_interest=100
)

# Find contract with strike nearest to current price
contract = trader.find_nearest_strike(
    underlying_symbol="SPY",
    contract_type=ContractType.CALL,
    target_price=None,  # Defaults to current stock price
    expiration_min_days=30,
    expiration_max_days=45
)
```

**Getting Market Data:**
```python
from alpaca.data.requests import OptionLatestQuoteRequest, OptionChainRequest

# Latest quote for specific contract
quote_req = OptionLatestQuoteRequest(symbol_or_symbols=["SPY250321P00450000"])
quotes = option_data_client.get_option_latest_quote(quote_req)

quote = quotes["SPY250321P00450000"]
print(f"Bid: ${quote.bid_price:.2f}, Ask: ${quote.ask_price:.2f}")
print(f"Bid Size: {quote.bid_size}, Ask Size: {quote.ask_size}")

# Full option chain for underlying
chain_req = OptionChainRequest(underlying_symbol="SPY")
chain = option_data_client.get_option_chain(chain_req)
```

**Placing Options Orders:**
```python
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

# Market order (single-leg)
order = trading_client.submit_order(
    MarketOrderRequest(
        symbol="SPY250321P00450000",
        qty=1,
        side=OrderSide.BUY,
        type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY
    )
)

# Limit order (single-leg)
order = trading_client.submit_order(
    LimitOrderRequest(
        symbol="SPY250321P00450000",
        qty=1,
        side=OrderSide.BUY,
        limit_price=5.50,
        type=OrderType.LIMIT,
        time_in_force=TimeInForce.DAY
    )
)
```

### 2.4 Multi-Leg Options Strategies

**Long Straddle (Level 2):**
```python
# Buy ATM call + Buy ATM put (expect volatility)
result = trader.execute_long_straddle(
    underlying_symbol="SPY",
    quantity=1,
    strike_price=None,  # Defaults to current price
    expiration_days=30
)

print(f"Strategy: {result['strategy']}")
print(f"Call: {result['call_symbol']}")
print(f"Put: {result['put_symbol']}")
print(f"Strike: ${result['strike']:.2f}")
```

**Protective Put (Level 2):**
```python
# Own stock + Buy OTM put (downside protection)
result = trader.execute_protective_put(
    underlying_symbol="AAPL",
    shares_owned=100,
    strike_price=None,  # Defaults to 5% below current
    expiration_days=60
)

print(f"Protected {result['shares_protected']} shares")
print(f"Strike: ${result['strike']:.2f}")
```

**Covered Call (Level 1):**
```python
# Own stock + Sell OTM call (generate income)
result = trader.execute_covered_call(
    underlying_symbol="TSLA",
    shares_owned=100,
    strike_price=None,  # Defaults to 5% above current
    expiration_days=30
)

print(f"Covered {result['shares_covered']} shares")
print(f"Strike: ${result['strike']:.2f}")
```

**Bull Call Spread (Level 3):**
```python
# Buy lower strike call + Sell higher strike call (bullish with limited risk)
result = trader.execute_bull_call_spread(
    underlying_symbol="QQQ",
    quantity=2,
    expiration_days=30,
    width=5.0  # $5 strike width
)

print(f"Long Strike: ${result['long_strike']:.2f}")
print(f"Short Strike: ${result['short_strike']:.2f}")
print(f"Width: ${result['width']:.2f}")
```

**Manual Multi-Leg Order:**
```python
from alpaca.trading.requests import OptionLegRequest
from alpaca.trading.enums import OrderClass

# Create legs
legs = [
    OptionLegRequest(
        symbol="SPY250321C00450000",  # Buy call
        side=OrderSide.BUY,
        ratio_qty=1
    ),
    OptionLegRequest(
        symbol="SPY250321C00455000",  # Sell call
        side=OrderSide.SELL,
        ratio_qty=1
    )
]

# Submit multi-leg order
order = trading_client.submit_order(
    MarketOrderRequest(
        qty=1,
        order_class=OrderClass.MLEG,
        time_in_force=TimeInForce.DAY,
        legs=legs
    )
)
```

### 2.5 Exercise and Assignment

**Exercising Options:**
```python
# Exercise an option position
trading_client.exercise_option(
    symbol_or_contract_id="SPY250321C00450000"
)
```

**Important Notes:**
- Options assignments are **not delivered via WebSocket** (must poll REST API)
- Paper trading: Exercises/assignments sync **next day only**
- Exercise requests between market close and midnight are **rejected**
- American options can be exercised **any time before expiration**

---

## Part 3: Integration Opportunities

### 3.1 Momentum Strategies with Short Selling

**Academic Evidence:**
- **Jegadeesh & Titman (1993)**: "Returns to Buying Winners and Selling Losers"
  - 12-month momentum generates 1% monthly return
  - Long/short portfolio (buy winners, short losers) delivers higher Sharpe ratios

- **Asness, Moskowitz & Pedersen (2013)**: "Value and Momentum Everywhere"
  - Short side contributes ~40% of total momentum returns
  - Long/short momentum works across asset classes

- **Israel & Moskowitz (2013)**: "The Role of Shorting, Firm Size, and Time on Market Anomalies"
  - Short selling significantly improves momentum strategy performance
  - Effect is strongest in small/mid caps

**Implementation:**
```python
from strategies.long_short_momentum import LongShortMomentumStrategy

# Long/short momentum strategy
strategy = LongShortMomentumStrategy(
    universe=['AAPL', 'MSFT', 'GOOGL', ...],  # S&P 500 or liquid stocks
    lookback_months=12,
    skip_month=True,  # Skip most recent month (reversal effect)
    enable_shorting=True,
    max_short_pct=0.25,  # 25% max short exposure
    long_positions=10,
    short_positions=10
)

# Generate signals
signals = strategy.generate_signals(price_data)

# Execute via Alpaca
from strategies.long_short_momentum import LongShortMomentumExecutor

executor = LongShortMomentumExecutor(trader, strategy)
results = executor.execute_signals(signals)

print(f"Long orders: {len(results['long_orders'])}")
print(f"Short orders: {len(results['short_orders'])}")
```

**Benefits of Long/Short vs Long-Only:**
- **Market neutrality**: Reduces exposure to market beta
- **Higher Sharpe ratios**: ~1.5-2.0 vs ~1.0 for long-only
- **Diversification**: Short side provides negative correlation during market stress
- **Alpha extraction**: Pure momentum factor exposure without market risk

**When to Use:**
- Sideways or declining markets (long-only underperforms)
- High correlation environments (market beta dominates)
- When seeking absolute returns vs relative returns

### 3.2 Options Strategies for Trend-Following

**Protective Puts for Tail Risk Hedging:**

Academic evidence:
- **Gao, Gao & Song (2018)**: "Do hedge funds use options to hedge?"
  - Protective puts reduce drawdowns during market crashes
  - Cost: ~1-2% annually in normal markets
  - Benefit: 10-20% downside protection during crashes

**Implementation:**
```python
# Add protective puts when VIX is elevated
strategy = LongShortMomentumStrategy(
    universe=universe,
    use_protective_puts=True,
    vix_threshold_puts=25.0  # Buy puts when VIX > 25
)

# Manual protective put
trader.execute_protective_put(
    underlying_symbol="AAPL",
    shares_owned=100,
    strike_price=None,  # 5% OTM
    expiration_days=60
)
```

**When to Use:**
- High VIX environments (elevated volatility)
- During extended uptrends (protect accumulated gains)
- Before known risk events (earnings, FOMC, elections)

**Covered Calls for Income Generation:**

Academic evidence:
- **Whaley (2002)**: "Return and Risk of CBOE Buy-Write Monthly Index"
  - Covered calls enhance returns in flat/declining markets
  - Reduce volatility by ~30%
  - Underperform in strong bull markets (upside capped)

**Implementation:**
```python
# Sell covered calls when VIX is low (range-bound market)
strategy = LongShortMomentumStrategy(
    universe=universe,
    use_covered_calls=True,
    vix_threshold_calls=15.0  # Sell calls when VIX < 15
)

# Manual covered call
trader.execute_covered_call(
    underlying_symbol="TSLA",
    shares_owned=100,
    strike_price=None,  # 5% OTM
    expiration_days=30
)
```

**When to Use:**
- Low VIX environments (low volatility, range-bound)
- When holding stock for long-term but expect sideways movement
- To enhance yield on dividend stocks

**Bull Call Spreads for Defined-Risk Trending:**

Use case: Reduce capital requirements and risk for momentum positions

**Implementation:**
```python
# Instead of buying stock outright, use bull call spread
trader.execute_bull_call_spread(
    underlying_symbol="QQQ",
    quantity=1,
    expiration_days=45,
    width=5.0
)
```

**Benefits:**
- Lower capital requirement (pay net premium vs full stock price)
- Defined maximum loss (limited to premium paid)
- Still captures majority of upside (up to short strike)

**Trade-offs:**
- Upside capped at short strike
- Time decay works against you (theta)
- Less suitable for long-term holds (usually 30-60 days)

### 3.3 Risk Management Considerations

**Position Sizing with Shorts:**
```python
# Conservative approach: Kelly Criterion with short penalty
def calculate_position_size_long_short(
    signal_strength: float,
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    position_type: str,
    portfolio_value: float
) -> float:
    """
    Calculate position size using fractional Kelly.

    Reduce size for short positions due to unlimited loss potential.
    """
    # Kelly fraction
    kelly_fraction = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win

    # Use 25% of Kelly (fractional Kelly for safety)
    fractional_kelly = 0.25 * kelly_fraction

    # Further reduce for shorts (50% of normal size)
    if position_type == "SHORT":
        fractional_kelly *= 0.5

    position_size = portfolio_value * fractional_kelly * signal_strength

    return position_size
```

**Circuit Breakers:**
```python
# Stop trading if losses exceed thresholds
def check_circuit_breakers(
    daily_pnl_pct: float,
    weekly_pnl_pct: float,
    drawdown_pct: float
) -> tuple[bool, str]:
    """Check if circuit breakers are triggered."""

    # Daily loss limit: -2%
    if daily_pnl_pct < -0.02:
        return True, "DAILY_LOSS_LIMIT"

    # Weekly loss limit: -5%
    if weekly_pnl_pct < -0.05:
        return True, "WEEKLY_LOSS_LIMIT"

    # Maximum drawdown: -15%
    if drawdown_pct < -0.15:
        return True, "MAX_DRAWDOWN"

    return False, "OK"
```

**Margin Monitoring:**
```python
# Monitor maintenance margin to avoid margin calls
def monitor_margin_health(trader: AlpacaAdvancedTrading) -> dict:
    """Monitor margin health and warn of potential issues."""

    account_info = trader.check_short_eligibility()

    equity = account_info['equity']
    maintenance_margin = account_info['maintenance_margin']

    # Maintenance margin ratio
    margin_ratio = maintenance_margin / equity if equity > 0 else 0

    # FINRA minimum: 25%
    # Alpaca may be higher based on concentration
    # Warning threshold: 40% (gives buffer before margin call)

    status = {
        'equity': equity,
        'maintenance_margin': maintenance_margin,
        'margin_ratio': margin_ratio,
        'warning': margin_ratio > 0.40,
        'critical': margin_ratio > 0.60
    }

    return status
```

**Options Expiration Management:**
```python
from datetime import datetime, timedelta

def manage_options_expirations(
    trader: AlpacaAdvancedTrading,
    days_before_expiry: int = 7
) -> list:
    """
    Close options positions approaching expiration.

    Best practice: Close positions 5-7 days before expiry to avoid:
    - Gamma risk (rapid delta changes)
    - Pin risk (settlement at strike price)
    - Assignment risk (early exercise)
    """
    positions = trader.get_options_positions()

    cutoff_date = datetime.now() + timedelta(days=days_before_expiry)
    positions_to_close = []

    for position in positions:
        # Parse expiration from symbol (e.g., SPY250321P00450000)
        # Format: SYMBOL + YYMMDD + C/P + STRIKE
        symbol = position['symbol']

        try:
            exp_str = symbol[-15:-9]  # Extract YYMMDD
            exp_date = datetime.strptime(exp_str, "%y%m%d")

            if exp_date <= cutoff_date:
                positions_to_close.append(position)

        except Exception as e:
            print(f"Error parsing expiration for {symbol}: {e}")

    return positions_to_close
```

---

## Part 4: Production Deployment Checklist

### 4.1 Pre-Deployment Testing

**Paper Trading Validation:**
```bash
# Run strategy in paper trading for minimum 3 months
# Target metrics:
# - Sharpe ratio > 1.0 after transaction costs
# - Maximum drawdown < 20%
# - Win rate > 45%
# - Profit factor > 1.3
```

**Backtesting with Realistic Costs:**
```python
backtest_params = BacktestParams(
    start_date="2015-01-01",
    end_date="2024-12-31",
    initial_capital=100000.0,
    transaction_cost_bps=10,   # 0.10% per trade
    slippage_bps=15,           # 0.15% slippage (higher for shorts)
    rebalance_frequency="monthly"
)
```

### 4.2 Risk Limits Configuration

**Account-Level Limits:**
```python
RISK_LIMITS = {
    # Position limits
    'max_position_pct': 0.05,           # 5% per position
    'max_sector_pct': 0.25,             # 25% per sector
    'max_short_exposure_pct': 0.25,     # 25% total short exposure

    # Loss limits
    'daily_loss_limit_pct': 0.02,       # -2% daily
    'weekly_loss_limit_pct': 0.05,      # -5% weekly
    'max_drawdown_pct': 0.15,           # -15% max drawdown

    # Options limits
    'max_options_pct': 0.10,            # 10% in options
    'min_days_to_expiry': 7,            # Close 7 days before expiry

    # Margin limits
    'min_buying_power_pct': 0.20,       # Keep 20% cash buffer
    'margin_call_threshold': 0.40        # Warning at 40% margin ratio
}
```

### 4.3 Monitoring and Alerts

**Key Metrics to Monitor:**
```python
def generate_daily_report(trader: AlpacaAdvancedTrading) -> dict:
    """Generate daily monitoring report."""

    account = trader.check_short_eligibility()
    short_positions = trader.get_short_positions()
    options_positions = trader.get_options_positions()

    # Calculate portfolio metrics
    total_long_value = sum([abs(p['market_value']) for p in all_positions if p['qty'] > 0])
    total_short_value = abs(account['short_market_value'])
    net_exposure = (total_long_value - total_short_value) / account['equity']

    report = {
        'date': datetime.now().date(),
        'equity': account['equity'],
        'buying_power': account['buying_power'],
        'long_value': total_long_value,
        'short_value': total_short_value,
        'net_exposure': net_exposure,
        'short_positions_count': len(short_positions),
        'options_positions_count': len(options_positions),
        'margin_ratio': account['maintenance_margin'] / account['equity'],
        'day_pnl': None,  # Calculate from previous day
        'alerts': []
    }

    # Generate alerts
    if net_exposure > 1.5:
        report['alerts'].append("HIGH_NET_EXPOSURE")

    if report['margin_ratio'] > 0.40:
        report['alerts'].append("MARGIN_WARNING")

    if len(short_positions) > 20:
        report['alerts'].append("TOO_MANY_SHORTS")

    return report
```

**Automated Alerts:**
- Email/Slack notification on margin warnings
- Daily P&L reports
- Position concentration alerts
- Options expiration reminders (T-7, T-3, T-1)
- Short squeeze detection (rapid price increase + high short interest)

### 4.4 Disaster Recovery

**Emergency Liquidation Plan:**
```python
def emergency_liquidation(
    trader: AlpacaAdvancedTrading,
    reason: str
) -> dict:
    """
    Emergency liquidation of all positions.

    Use only in critical situations:
    - Margin call imminent
    - System malfunction
    - Force majeure event
    """

    print(f"EMERGENCY LIQUIDATION TRIGGERED: {reason}")

    results = {
        'timestamp': datetime.now(),
        'reason': reason,
        'positions_closed': [],
        'errors': []
    }

    # Close all positions
    positions = trader.trading_client.get_all_positions()

    for position in positions:
        try:
            trader.trading_client.close_position(position.symbol)
            results['positions_closed'].append(position.symbol)
        except Exception as e:
            results['errors'].append({
                'symbol': position.symbol,
                'error': str(e)
            })

    return results
```

---

## Part 5: Cost Analysis

### 5.1 Transaction Costs

**Trading Costs:**
- Stock trading (long/short): **$0 commission**
- Options trading: **$0 commission** (per contract)
- ETB short borrow fees: **$0** (as of October 2025)
- HTB short borrow fees: Variable (daily calculation, not currently supported)

**Spread Costs (Hidden Cost):**
- Large caps: ~0.01-0.05% bid-ask spread
- Mid caps: ~0.05-0.15% bid-ask spread
- Options: ~$0.05-0.20 per contract (depending on liquidity)

**Slippage Estimates:**
```python
SLIPPAGE_ESTIMATES = {
    'large_cap_long': 0.05,    # 0.05% = 5 bps
    'large_cap_short': 0.10,   # 0.10% = 10 bps (harder to execute)
    'mid_cap_long': 0.15,      # 0.15% = 15 bps
    'mid_cap_short': 0.25,     # 0.25% = 25 bps
    'options_liquid': 0.50,    # 0.50% of premium
    'options_illiquid': 2.00   # 2.00% of premium
}
```

### 5.2 Margin Costs

**Margin Interest (2026 Rates):**
```python
def calculate_annual_margin_cost(
    average_debit_balance: float,
    account_tier: str = "standard"
) -> float:
    """Calculate annual margin interest cost."""

    rates = {
        'elite': 0.0475,      # 4.75% for $100K+
        'standard': 0.0625    # 6.25% for < $100K
    }

    rate = rates[account_tier]
    annual_cost = average_debit_balance * rate

    return annual_cost

# Example: $50K average debit, standard account
cost = calculate_annual_margin_cost(50000, "standard")
print(f"Annual margin cost: ${cost:,.2f}")  # $3,125
```

### 5.3 Options Costs

**Options Premium Costs:**
- Protective puts (5% OTM, 60 days): ~1-2% of stock value
- Covered calls (5% OTM, 30 days): +0.5-1.5% income
- Bull call spreads: Net premium varies widely

**Example Analysis:**
```python
# Portfolio: $100K
# Long positions: $100K in stocks
# Short positions: $25K in stocks

# Costs per year:
# - Spread costs (50 rebalances/year, 0.10% avg): $125
# - Slippage (50 rebalances, 0.10% avg): $125
# - Margin interest ($25K short, 6.25%): $1,562
# - Protective puts (10% of portfolio, 1.5% cost): $1,500

# Total annual costs: $3,312 (3.3% of portfolio)
# Required gross return to break even: 3.3% + target net return
```

---

## Part 6: Recommended Workflow

### Step 1: Account Setup
1. Open Alpaca account (paper or live)
2. Fund with minimum $2,000 (for margin/short access)
3. Verify `shorting_enabled = True`
4. Request options approval (if live trading)

### Step 2: Strategy Development
```python
# 1. Define universe
universe = ['AAPL', 'MSFT', 'GOOGL', ...]  # 50-100 liquid stocks

# 2. Initialize strategy
strategy = LongShortMomentumStrategy(
    universe=universe,
    lookback_months=12,
    enable_shorting=True,
    max_short_pct=0.25
)

# 3. Backtest with realistic costs
# (Use zipline, backtrader, or vectorbt)

# 4. Paper trade for 3 months minimum
```

### Step 3: Risk Management Setup
```python
# Configure risk limits
risk_config = {
    'max_short_exposure_pct': 0.25,
    'position_stop_loss_pct': 0.15,
    'daily_loss_limit_pct': 0.02,
    'max_drawdown_pct': 0.15
}

# Initialize risk manager
risk_mgr = ShortPositionRiskManager(
    max_short_exposure_pct=risk_config['max_short_exposure_pct']
)
```

### Step 4: Execution
```python
# 1. Load data
price_data = load_price_data(universe, start_date, end_date)

# 2. Generate signals
signals = strategy.generate_signals(price_data)

# 3. Execute via Alpaca
trader = AlpacaAdvancedTrading(paper=True)
executor = LongShortMomentumExecutor(trader, strategy)
results = executor.execute_signals(signals)

# 4. Monitor positions
symbols_to_cover = executor.monitor_short_positions()
if symbols_to_cover:
    executor.auto_cover_positions(symbols_to_cover)
```

### Step 5: Monitoring
```python
# Daily tasks:
# - Check margin health
# - Monitor short positions for stop losses
# - Review options positions approaching expiration
# - Generate daily P&L report

# Weekly tasks:
# - Review strategy performance
# - Check for regime changes (VIX, correlations)
# - Adjust risk limits if needed

# Monthly tasks:
# - Rebalance portfolio
# - Update backtests with new data
# - Review options strategies (protective puts, covered calls)
```

---

## Resources and References

**Alpaca Documentation:**
- [Margin and Short Selling](https://docs.alpaca.markets/docs/margin-and-short-selling)
- [Options Trading](https://docs.alpaca.markets/docs/options-trading)
- [Options Trading Overview](https://docs.alpaca.markets/docs/options-trading-overview)
- [How to Trade Options with Alpaca](https://alpaca.markets/learn/how-to-trade-options-with-alpaca)
- [Trading Account Plans](https://docs.alpaca.markets/docs/account-plans)

**Alpaca Support:**
- [Short Selling Fees](https://alpaca.markets/support/short-selling-fees)
- [Margin Account Determination](https://alpaca.markets/support/determine-margin-account)
- [Short Stocks V2 API](https://alpaca.markets/support/short-stocks-v2-api)

**Academic References:**
- Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency." *Journal of Finance*, 48(1), 65-91.
- Asness, C. S., Moskowitz, T. J., & Pedersen, L. H. (2013). "Value and Momentum Everywhere." *Journal of Finance*, 68(3), 929-985.
- Israel, R., & Moskowitz, T. J. (2013). "The Role of Shorting, Firm Size, and Time on Market Anomalies." *Journal of Financial Economics*, 108(2), 275-301.
- Gao, G. P., Gao, P., & Song, Z. (2018). "Do Hedge Funds Use Options to Hedge? Evidence from Portfolio Holdings." Working Paper.
- Whaley, R. E. (2002). "Return and Risk of CBOE Buy Write Monthly Index." *Journal of Derivatives*, 10(2), 35-42.

**Code Files:**
- `/Users/work/personal/quant/execution/broker/alpaca_advanced.py` - Advanced trading implementation
- `/Users/work/personal/quant/strategies/long_short_momentum.py` - Long/short momentum strategy

---

## Conclusion

Alpaca provides robust API support for both short selling and options trading, enabling quantitative traders to implement sophisticated market-neutral and hedged strategies. Key takeaways:

**Short Selling:**
✅ Commission-free with $0 borrow fees (ETB stocks)
✅ 5,000+ stocks available
✅ Full API support
⚠️ HTB stocks not supported yet
⚠️ Requires $2,000 minimum equity

**Options Trading:**
✅ Level 3 strategies supported (spreads, straddles, condors)
✅ Zero commissions
✅ Multi-leg orders via API
✅ Paper trading enabled by default
⚠️ Live trading requires approval
⚠️ Day orders only (no GTC)

**Integration Benefits:**
- Long/short momentum delivers higher Sharpe ratios (~1.5-2.0 vs ~1.0)
- Options hedging reduces tail risk during market crashes
- Covered calls enhance income in range-bound markets
- Market-neutral strategies reduce correlation to market beta

**Next Steps:**
1. Review code implementations in `alpaca_advanced.py` and `long_short_momentum.py`
2. Backtest long/short momentum with realistic costs
3. Paper trade for 3+ months to validate strategy
4. Deploy with conservative risk limits
5. Monitor daily and adjust as needed

For questions or support, refer to Alpaca's documentation or community forums.
