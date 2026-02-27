# Risk Management Integration Guide

## Quick Start: Integrating World-Class Risk Management into Auto Trader

This guide shows how to integrate the new risk management components into your existing `auto_trader.py`.

## Step 1: Import New Components

Add these imports to `auto_trader.py`:

```python
# Add to imports section
from risk.dynamic_sizing import DynamicPositionSizer
from risk.portfolio_risk import PortfolioRiskManager
from risk.adaptive_stops import AdaptiveStopManager
from risk.stress_test import StressTestEngine
from monitoring.risk_dashboard import RiskDashboard
```

## Step 2: Initialize in AutoTrader.__init__()

Add these initializations in the `__init__` method:

```python
def __init__(self, ...):
    # ... existing initialization ...

    # Dynamic Position Sizing (replaces simple PositionSizer)
    self.dynamic_sizer = DynamicPositionSizer(
        base_position_pct=0.10,        # 10% base position
        max_position_pct=0.15,         # 15% maximum
        min_position_pct=0.02,         # 2% minimum
        kelly_fraction=0.25,           # Quarter Kelly for safety
        target_position_volatility=0.15  # Target 15% position volatility
    )

    # Portfolio-Level Risk Management
    self.portfolio_risk_manager = PortfolioRiskManager(
        max_portfolio_heat_pct=0.20,      # Max 20% portfolio at risk
        max_sector_exposure_pct=0.30,     # Max 30% in any sector
        max_single_position_pct=0.15,     # Max 15% single position
        max_avg_correlation=0.6,          # Max 0.6 average correlation
        daily_drawdown_limit=0.02,        # -2% daily limit
        weekly_drawdown_limit=0.05,       # -5% weekly limit
        max_drawdown_limit=0.15,          # -15% max drawdown
        max_positions=10,                 # Max 10 concurrent positions
        enable_auto_reduction=True        # Auto-reduce risk on violations
    )

    # Set sector mapping (customize for your universe)
    sector_map = {
        'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology',
        'NVDA': 'Technology', 'META': 'Technology', 'AMZN': 'Technology',
        'TSLA': 'Automotive', 'F': 'Automotive', 'GM': 'Automotive',
        'JPM': 'Financials', 'BAC': 'Financials', 'GS': 'Financials',
        'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy',
        'JNJ': 'Healthcare', 'UNH': 'Healthcare', 'PFE': 'Healthcare',
        'SPY': 'ETF', 'QQQ': 'ETF', 'IWM': 'ETF'
    }
    self.portfolio_risk_manager.set_sector_map(sector_map)

    # Adaptive Stop Management (replaces simple ProfitOptimizer)
    self.adaptive_stop_manager = AdaptiveStopManager(
        initial_stop_pct=0.04,            # 4% initial stop
        trailing_stop_pct=0.03,           # 3% trailing stop
        initial_stop_atr_multiple=2.0,    # Or 2x ATR
        trailing_stop_atr_multiple=2.5,   # Or 2.5x ATR
        max_hold_days=60,                 # Exit after 60 days
        stale_position_days=30,           # Tighten after 30 days
        use_atr=True                      # Use ATR-based stops
    )

    # Stress Testing (run periodically)
    self.stress_test_engine = StressTestEngine()
    self._last_stress_test = None
    self._stress_test_interval = timedelta(days=7)  # Weekly stress tests

    # Risk Dashboard
    self.risk_dashboard = RiskDashboard(
        var_calculator=self.var_calculator,
        portfolio_risk_manager=self.portfolio_risk_manager,
        circuit_breaker=self.circuit_breaker,
        adaptive_stop_manager=self.adaptive_stop_manager,
        dynamic_sizer=self.dynamic_sizer
    )

    # Risk snapshot history for tracking
    self._risk_snapshots: List[Dict] = []
```

## Step 3: Update Position Sizing Logic

Replace your position sizing in `process_signals()`:

```python
def process_signals(self, signals: List[Signal], strategy_name: str):
    # ... existing code ...

    for signal in signals:
        if signal.signal_type == SignalType.BUY:
            # OLD WAY:
            # target_value = self.position_sizer.calculate_position_size(...)

            # NEW WAY: Dynamic position sizing
            # Get asset volatility
            try:
                df = self.db.get_daily_bars(symbol, start_date - timedelta(days=60))
                returns = df['close'].pct_change().dropna()
                asset_volatility = returns.std() * np.sqrt(252)  # Annualized
            except:
                asset_volatility = 0.25  # Default 25%

            # Get portfolio returns for correlation analysis
            portfolio_returns = None
            if len(self._portfolio_returns) >= 30:
                portfolio_returns = pd.DataFrame({
                    sym: self.db.get_daily_bars(sym, ...)['close'].pct_change()
                    for sym in self.position_tracker.positions.keys()
                })

            # Get SPY data for regime detection
            spy_data = self.db.get_daily_bars('SPY', start_date - timedelta(days=250))

            # Get new asset returns
            new_asset_returns = returns

            # Calculate dynamic size
            size_params = self.dynamic_sizer.calculate_position_size(
                symbol=symbol,
                portfolio_value=equity,
                asset_volatility=asset_volatility,
                vix=self.current_vix,
                spy_data=spy_data,
                portfolio_returns=portfolio_returns,
                new_asset_returns=new_asset_returns,
                strategy=strategy_name,
                # Kelly params calculated from live results (if available)
                win_rate=self.kelly_sizer._strategy_stats.get(strategy_name, {}).get('win_rate'),
                avg_win=self.kelly_sizer._strategy_stats.get(strategy_name, {}).get('avg_win'),
                avg_loss=self.kelly_sizer._strategy_stats.get(strategy_name, {}).get('avg_loss')
            )

            target_value = size_params.final_size_pct * equity
            shares = int(target_value / price)

            logger.info(
                f"Dynamic sizing for {symbol}: {size_params.final_size_pct:.1%} "
                f"({size_params.reasoning})"
            )
```

## Step 4: Add Portfolio Risk Monitoring to run_cycle()

Add this to your main trading loop:

```python
def run_cycle(self):
    # ... existing market data updates ...

    # Calculate portfolio risk metrics
    try:
        account = self.alpaca.get_account()
        positions = self.alpaca.get_positions()

        # Calculate portfolio risk
        portfolio_metrics = self.portfolio_risk_manager.calculate_metrics(
            positions=positions,
            portfolio_value=account['equity'],
            cash=account['cash'],
            margin_used=0,  # Get from account if using margin
            margin_available=account['buying_power'],
            returns_data=None,  # Optional: pass returns for correlation
            current_date=date.today()
        )

        # Log violations
        if portfolio_metrics.violations:
            logger.warning(
                f"Portfolio risk violations: {len(portfolio_metrics.violations)}"
            )
            for vtype, message in portfolio_metrics.violations:
                logger.warning(f"  {vtype.value}: {message}")

            # Get risk reduction recommendations
            actions = self.portfolio_risk_manager.get_risk_reduction_actions(
                portfolio_metrics, positions
            )

            for action in actions:
                logger.warning(
                    f"Recommended: {action.action_type} {action.symbol} - "
                    f"{action.reason} (urgency: {action.urgency})"
                )

                # Optionally: auto-execute reduction actions
                if action.urgency == 'critical':
                    # Execute the action
                    pass

    except Exception as e:
        logger.error(f"Error calculating portfolio risk: {e}")

    # ... rest of trading logic ...
```

## Step 5: Use Adaptive Stops Instead of Simple Trailing Stops

Replace your stop management in `optimize_positions()`:

```python
def optimize_positions(self):
    # ... get positions ...

    # Calculate adaptive stops for all positions
    stops = self.adaptive_stop_manager.calculate_batch_stops(
        positions=positions_dict,  # Format: {symbol: {current_price, entry_price, ...}}
        vix=self.current_vix
    )

    # Update stops that have been raised
    for symbol, params in stops.items():
        if params.recommended_stop > params.current_stop:
            logger.info(
                f"Raising stop for {symbol}: ${params.current_stop:.2f} -> "
                f"${params.recommended_stop:.2f} ({params.stop_type.value})"
            )

            # Cancel existing orders
            self.alpaca.cancel_orders_for_symbol(symbol)

            # Submit new trailing stop
            self.alpaca.submit_stop_order(
                symbol=symbol,
                qty=positions[symbol]['qty'],
                side='sell',
                stop_price=params.recommended_stop,
                time_in_force='gtc'
            )

            # Update position tracker
            self.position_tracker.update_stop_loss(
                symbol=symbol,
                new_stop=params.recommended_stop
            )
```

## Step 6: Add Periodic Stress Testing

Add weekly stress tests:

```python
def run_cycle(self):
    # ... existing code ...

    # Run stress test weekly
    now = datetime.now()
    if (self._last_stress_test is None or
        now - self._last_stress_test > self._stress_test_interval):

        logger.info("Running weekly stress test...")

        try:
            positions = self.alpaca.get_positions()
            account = self.alpaca.get_account()

            results = self.stress_test_engine.run_all_scenarios(
                positions=positions,
                portfolio_value=account['equity']
            )

            # Log worst case
            worst = min(results.values(), key=lambda r: r.portfolio_loss_pct)
            logger.warning(
                f"Stress test worst case: {worst.scenario_name} "
                f"({worst.portfolio_loss_pct:.1%} loss)"
            )

            # Check how many scenarios trigger breakers
            breaker_count = sum(1 for r in results.values() if r.would_trigger_breakers)
            logger.info(
                f"Stress test: {breaker_count}/{len(results)} scenarios "
                f"would trigger circuit breakers"
            )

            self._last_stress_test = now

        except Exception as e:
            logger.error(f"Stress test failed: {e}")
```

## Step 7: Add Risk Dashboard Reporting

Add this to your status printing:

```python
def print_status(self):
    # ... existing status printing ...

    # Get comprehensive risk snapshot
    try:
        account = self.alpaca.get_account()
        positions = self.alpaca.get_positions()

        snapshot = self.risk_dashboard.get_risk_snapshot(
            positions=positions,
            portfolio_value=account['equity'],
            cash=account['cash'],
            margin_used=0,
            margin_available=account['buying_power'],
            returns_data=None,  # Optional
            portfolio_returns=pd.Series(self._portfolio_returns) if self._portfolio_returns else None,
            spy_data=self.db.get_daily_bars('SPY', date.today() - timedelta(days=250)),
            vix=self.current_vix
        )

        # Print dashboard
        self.risk_dashboard.print_dashboard(snapshot)

        # Save snapshot for history
        self._risk_snapshots.append(snapshot)

        # Export snapshot every hour
        if len(self._risk_snapshots) % 12 == 0:  # Every ~hour at 5min intervals
            self.risk_dashboard.export_snapshot(snapshot)

    except Exception as e:
        logger.error(f"Error generating risk dashboard: {e}")
```

## Step 8: Record Trade Results for Kelly Sizing

When closing positions, record results:

```python
def close_position(self, symbol: str, exit_price: float, reason: str):
    # ... existing close logic ...

    # Record trade result for Kelly sizing
    if symbol in self.position_tracker.positions:
        pos = self.position_tracker.positions[symbol]

        self.dynamic_sizer.record_trade_result(
            symbol=symbol,
            strategy=pos.strategy,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            entry_time=pos.entry_time,
            exit_time=datetime.now(),
            side='long'  # or 'short'
        )
```

## Testing Your Integration

1. **Test with demo mode first**:
```bash
python scripts/risk_management_demo.py --demo all
```

2. **Run auto trader with status-only**:
```bash
python scripts/auto_trader.py --status-only
```

3. **Run one cycle**:
```bash
python scripts/auto_trader.py --run-once
```

4. **Monitor logs**:
```bash
tail -f logs/auto_trader.log | grep -i "risk\|violation\|stop\|sizing"
```

## Key Benefits

✓ **Dynamic Sizing**: Positions automatically adapt to volatility and market conditions
✓ **Portfolio Protection**: Automatic detection and reduction of concentrated risks
✓ **Intelligent Stops**: Stops that tighten with profits and widen in high volatility
✓ **Stress Awareness**: Know your portfolio's resilience to crisis scenarios
✓ **Real-Time Monitoring**: Comprehensive risk dashboard with all metrics
✓ **Circuit Breakers**: Automatic halt on dangerous conditions
✓ **Academic Rigor**: All methods backed by peer-reviewed research

## Customization

All risk parameters are configurable. Adjust them in the initialization based on your:
- Risk tolerance
- Capital size
- Strategy characteristics
- Market exposure
- Regulatory requirements

See individual module documentation in `/Users/work/personal/quant/risk/README.md` for detailed parameter descriptions.

## Support Files

- **Demo**: `/Users/work/personal/quant/scripts/risk_management_demo.py`
- **Documentation**: `/Users/work/personal/quant/risk/README.md`
- **Modules**: `/Users/work/personal/quant/risk/`
- **Dashboard**: `/Users/work/personal/quant/monitoring/risk_dashboard.py`
