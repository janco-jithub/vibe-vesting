# Code Changes - Bracket Order Fix

## File Modified: `/Users/work/personal/quant/scripts/auto_trader.py`

### Location: Lines 765-854

### BEFORE (Original Code):

```python
elif signal.signal_type == SignalType.SELL:
    # Only sell if we have a position
    if current_position <= 0:
        continue

    position_data = positions[symbol]
    shares = int(position_data["qty"])

    # Create and submit sell order
    order = self.order_manager.create_order(
        symbol=symbol,
        side="sell",
        quantity=shares,
        order_type="limit",
        strategy=strategy_name
    )

    self.order_manager.submit_order(order)

    executed.append({
        "symbol": symbol,
        "action": "SELL",
        "shares": shares,
        "strategy": strategy_name,
        "strength": signal.strength,
        "order_id": order.id
    })

    self.recent_trades[symbol] = datetime.now()

    logger.info(
        f"SELL {shares} shares of {symbol}",
        extra={
            "strategy": strategy_name,
            "strength": signal.strength,
            "order_id": order.id
        }
    )
```

### AFTER (Fixed Code):

```python
elif signal.signal_type == SignalType.SELL:
    # Only sell if we have a position
    if current_position <= 0:
        continue

    position_data = positions[symbol]
    shares = int(position_data["qty"])

    # CRITICAL FIX: Cancel any existing orders (bracket legs, stops) before selling
    # This prevents "insufficient qty available" errors from locked shares
    cancelled_count = 0
    try:
        cancelled_count = self.alpaca.cancel_orders_for_symbol(symbol)
        if cancelled_count > 0:
            logger.info(
                f"Cancelled {cancelled_count} existing orders for {symbol} before strategy SELL"
            )
            # Small delay to ensure cancellations are processed
            time.sleep(0.5)
    except AlpacaClientError as e:
        logger.warning(f"Failed to cancel orders for {symbol}: {e}")
        # Continue anyway - sell might still work

    # Create and submit sell order
    order = self.order_manager.create_order(
        symbol=symbol,
        side="sell",
        quantity=shares,
        order_type="limit",
        strategy=strategy_name
    )

    try:
        self.order_manager.submit_order(order)

        # Remove from position tracker since we're exiting
        if symbol in self.position_tracker.positions:
            self.position_tracker.remove_position(
                symbol=symbol,
                reason=f"Strategy SELL signal (strength: {signal.strength:.2f})"
            )

        executed.append({
            "symbol": symbol,
            "action": "SELL",
            "shares": shares,
            "strategy": strategy_name,
            "strength": signal.strength,
            "order_id": order.id
        })

        self.recent_trades[symbol] = datetime.now()

        logger.info(
            f"SELL {shares} shares of {symbol}",
            extra={
                "strategy": strategy_name,
                "strength": signal.strength,
                "order_id": order.id
            }
        )

    except (RiskLimitExceeded, AlpacaClientError) as e:
        # Sell failed - re-protect the position if we cancelled stops
        logger.error(f"SELL order failed for {symbol}: {e}")

        if cancelled_count > 0:
            logger.warning(
                f"Re-adding stop protection for {symbol} since SELL failed"
            )
            try:
                # Re-add basic stop loss protection
                current_price = position_data["current_price"]
                stop_price = current_price * (1 - self.stop_loss_pct)

                self.alpaca.submit_stop_order(
                    symbol=symbol,
                    qty=shares,
                    side="sell",
                    stop_price=stop_price,
                    time_in_force="gtc"
                )
                logger.info(f"Re-added stop loss for {symbol} @ ${stop_price:.2f}")
            except AlpacaClientError as stop_error:
                logger.error(
                    f"Failed to re-add stop protection for {symbol}: {stop_error}"
                )

        # Don't add to executed list since order failed
        continue
```

## Key Additions

### 1. Order Cancellation (New)
```python
cancelled_count = 0
try:
    cancelled_count = self.alpaca.cancel_orders_for_symbol(symbol)
    if cancelled_count > 0:
        logger.info(
            f"Cancelled {cancelled_count} existing orders for {symbol} before strategy SELL"
        )
        time.sleep(0.5)  # Wait for cancellations to process
except AlpacaClientError as e:
    logger.warning(f"Failed to cancel orders for {symbol}: {e}")
```

### 2. Try-Except Wrapper Around Submit (New)
```python
try:
    self.order_manager.submit_order(order)
    # ... existing success logic ...
except (RiskLimitExceeded, AlpacaClientError) as e:
    # ... re-protection logic ...
```

### 3. Position Tracker Cleanup (New)
```python
if symbol in self.position_tracker.positions:
    self.position_tracker.remove_position(
        symbol=symbol,
        reason=f"Strategy SELL signal (strength: {signal.strength:.2f})"
    )
```

### 4. Re-Protection Logic (New)
```python
if cancelled_count > 0:
    logger.warning(f"Re-adding stop protection for {symbol} since SELL failed")
    try:
        current_price = position_data["current_price"]
        stop_price = current_price * (1 - self.stop_loss_pct)

        self.alpaca.submit_stop_order(
            symbol=symbol,
            qty=shares,
            side="sell",
            stop_price=stop_price,
            time_in_force="gtc"
        )
        logger.info(f"Re-added stop loss for {symbol} @ ${stop_price:.2f}")
    except AlpacaClientError as stop_error:
        logger.error(f"Failed to re-add stop protection for {symbol}: {stop_error}")
```

## Dependencies (No Changes Required)

These existing methods in `/Users/work/personal/quant/execution/alpaca_client.py` are used:

1. `cancel_orders_for_symbol(symbol: str) -> int` (lines 816-846)
   - Already implemented, returns number of orders cancelled

2. `submit_stop_order(symbol, qty, side, stop_price, time_in_force)` (lines 695-741)
   - Already implemented, submits stop loss order

3. `get_open_orders_for_symbol(symbol: str)` (lines 793-814)
   - Already implemented, used internally by cancel_orders_for_symbol

## Testing the Fix

### Manual Test:
1. Start auto_trader with a strategy that uses bracket orders
2. Wait for a BUY signal and bracket order to be placed
3. Wait for a SELL signal
4. Verify in logs:
   ```
   Cancelled N existing orders for SYMBOL before strategy SELL
   SELL X shares of SYMBOL
   ```

### Automated Verification:
```bash
python -m scripts.verify_bracket_fix
```

### Log Monitoring:
```bash
tail -f logs/auto_trader.log | grep -E "(Cancelled|SELL|Re-adding)"
```

## Rollback Plan

If issues occur, revert by replacing the new SELL block with the original simple version:

```python
elif signal.signal_type == SignalType.SELL:
    if current_position <= 0:
        continue

    position_data = positions[symbol]
    shares = int(position_data["qty"])

    order = self.order_manager.create_order(
        symbol=symbol, side="sell", quantity=shares,
        order_type="limit", strategy=strategy_name
    )
    self.order_manager.submit_order(order)

    executed.append({
        "symbol": symbol, "action": "SELL", "shares": shares,
        "strategy": strategy_name, "strength": signal.strength,
        "order_id": order.id
    })
    self.recent_trades[symbol] = datetime.now()
    logger.info(f"SELL {shares} shares of {symbol}",
                extra={"strategy": strategy_name, "strength": signal.strength,
                       "order_id": order.id})
```

## Impact Analysis

**Lines Changed:** ~30 lines added/modified
**Risk Level:** Low - isolated to SELL signal processing
**Performance Impact:** +500ms per SELL order (acceptable)
**Safety Impact:** Improved - ensures positions can be exited + maintains protection
**Testing Required:** 3-5 days paper trading recommended
