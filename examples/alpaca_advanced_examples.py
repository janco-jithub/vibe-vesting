"""
Alpaca Advanced Trading Examples

Quick reference examples for short selling and options trading with Alpaca.
Run these examples in paper trading mode to familiarize yourself with the API.

Prerequisites:
- Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables
- Ensure account has $2,000+ equity for margin/short access
- Options enabled (automatic in paper trading)

Usage:
    python examples/alpaca_advanced_examples.py
"""

import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from execution.broker.alpaca_advanced import (
    AlpacaAdvancedTrading,
    ShortPositionRiskManager,
    PositionType
)
from alpaca.trading.enums import ContractType


def example_1_check_eligibility():
    """Example 1: Check account eligibility for short selling and options."""
    print("\n" + "="*70)
    print("EXAMPLE 1: Check Eligibility")
    print("="*70)

    trader = AlpacaAdvancedTrading(paper=True)

    # Check short selling eligibility
    print("\nShort Selling Eligibility:")
    short_info = trader.check_short_eligibility()
    print(f"  Eligible: {short_info['eligible']}")
    print(f"  Account Equity: ${short_info['equity']:,.2f}")
    print(f"  Buying Power: ${short_info['buying_power']:,.2f}")
    print(f"  Short Market Value: ${short_info['short_market_value']:,.2f}")
    print(f"  Shorting Enabled: {short_info['shorting_enabled']}")

    # Check options eligibility
    print("\nOptions Trading Eligibility:")
    options_info = trader.check_options_eligibility()
    print(f"  Options Enabled: {options_info['options_enabled']}")
    print(f"  Options Level: {options_info['options_level']}")
    print(f"  Options Buying Power: ${options_info['options_buying_power']:,.2f}")

    return trader


def example_2_calculate_margin(trader):
    """Example 2: Calculate margin requirements for short positions."""
    print("\n" + "="*70)
    print("EXAMPLE 2: Calculate Short Margin Requirements")
    print("="*70)

    symbols = [
        ("SPY", 100, 450.0),
        ("AAPL", 200, 175.0),
        ("TSLA", 50, 250.0),
        ("QQQ", 100, 380.0)
    ]

    print("\n{:<10} {:>10} {:>12} {:>18} {:>22} {:>22}".format(
        "Symbol", "Qty", "Price", "Initial Margin", "Maintenance Margin", "Buying Power Effect"
    ))
    print("-" * 105)

    for symbol, qty, price in symbols:
        margin = trader.calculate_short_margin_requirement(symbol, qty, price)
        print("{:<10} {:>10} {:>12.2f} {:>18,.2f} {:>22,.2f} {:>22,.2f}".format(
            symbol, qty, price,
            margin.initial_margin,
            margin.maintenance_margin,
            margin.buying_power_effect
        ))


def example_3_short_position_lifecycle(trader):
    """Example 3: Complete short position lifecycle (paper trading)."""
    print("\n" + "="*70)
    print("EXAMPLE 3: Short Position Lifecycle (PAPER TRADING)")
    print("="*70)

    symbol = "SPY"

    # Step 1: Check if we can short
    print(f"\nStep 1: Checking eligibility to short {symbol}...")
    eligibility = trader.check_short_eligibility()
    if not eligibility['eligible']:
        print("  ERROR: Not eligible for short selling")
        return

    print(f"  OK: Buying power = ${eligibility['buying_power']:,.2f}")

    # Step 2: Calculate margin requirement
    print(f"\nStep 2: Calculating margin requirements...")
    current_price = trader.get_current_price(symbol)
    margin = trader.calculate_short_margin_requirement(symbol, 10, current_price)
    print(f"  Current Price: ${current_price:.2f}")
    print(f"  Initial Margin (50%): ${margin.initial_margin:,.2f}")
    print(f"  Maintenance Margin: ${margin.maintenance_margin:,.2f}")
    print(f"  Buying Power Required: ${margin.buying_power_effect:,.2f}")

    # Step 3: Submit short order
    print(f"\nStep 3: Submitting short order for {symbol}...")
    try:
        order = trader.submit_short_order(
            symbol=symbol,
            quantity=10,
            order_type="market",
            check_margin=True
        )

        if order:
            print(f"  Order submitted successfully!")
            print(f"  Order ID: {order['order_id']}")
            print(f"  Status: {order['status']}")
        else:
            print("  Order submission failed")
            return

    except Exception as e:
        print(f"  ERROR: {e}")
        return

    # Step 4: Monitor position
    print(f"\nStep 4: Monitoring short positions...")
    short_positions = trader.get_short_positions()

    if short_positions:
        for pos in short_positions:
            if pos['symbol'] == symbol:
                print(f"  Symbol: {pos['symbol']}")
                print(f"  Quantity: {pos['qty']}")
                print(f"  Entry Price: ${pos['avg_entry_price']:.2f}")
                print(f"  Current Price: ${pos['current_price']:.2f}")
                print(f"  Unrealized P/L: ${pos['unrealized_pl']:,.2f} ({pos['unrealized_plpc']:.2%})")

    # Step 5: Cover position (commented out - enable if you want to close immediately)
    """
    print(f"\nStep 5: Covering short position...")
    try:
        cover_result = trader.cover_short_position(
            symbol=symbol,
            quantity=None,  # Cover entire position
            order_type="market"
        )

        if cover_result:
            print(f"  Cover order submitted!")
            print(f"  Order ID: {cover_result['order_id']}")
    except Exception as e:
        print(f"  ERROR covering position: {e}")
    """


def example_4_short_risk_management():
    """Example 4: Risk management for short positions."""
    print("\n" + "="*70)
    print("EXAMPLE 4: Short Position Risk Management")
    print("="*70)

    risk_mgr = ShortPositionRiskManager(max_short_exposure_pct=0.25)

    # Scenario 1: Check exposure limits
    print("\nScenario 1: Checking exposure limits")
    account_equity = 100000.0
    current_short_value = 15000.0
    new_short_value = 10000.0

    allowed, reason = risk_mgr.check_short_exposure(
        account_equity, current_short_value, new_short_value
    )

    print(f"  Account Equity: ${account_equity:,.0f}")
    print(f"  Current Short Exposure: ${current_short_value:,.0f} ({current_short_value/account_equity:.1%})")
    print(f"  New Short: ${new_short_value:,.0f}")
    print(f"  Total Short Exposure: ${current_short_value + new_short_value:,.0f} ({(current_short_value + new_short_value)/account_equity:.1%})")
    print(f"  Allowed: {allowed} - {reason}")

    # Scenario 2: Calculate stop loss
    print("\nScenario 2: Calculate stop loss price")
    entry_price = 450.0
    stop_price = risk_mgr.calculate_stop_loss_price(entry_price, max_loss_pct=0.15)

    print(f"  Entry Price: ${entry_price:.2f}")
    print(f"  Max Loss: 15%")
    print(f"  Stop Loss Price: ${stop_price:.2f}")
    print(f"  (Price rises above ${stop_price:.2f} = Stop out)")

    # Scenario 3: Monitor position
    print("\nScenario 3: Should we cover this position?")

    test_cases = [
        (450.0, 470.0, "Price rose 4.4% - approaching stop"),
        (450.0, 520.0, "Price rose 15.6% - STOP LOSS HIT"),
        (450.0, 360.0, "Price fell 20% - TAKE PROFIT HIT"),
        (450.0, 430.0, "Price fell 4.4% - Hold position")
    ]

    for entry, current, description in test_cases:
        should_cover, reason = risk_mgr.should_cover_short(
            entry_price=entry,
            current_price=current,
            stop_loss_pct=0.15,
            take_profit_pct=0.20
        )

        pnl_pct = (entry - current) / entry
        print(f"\n  {description}")
        print(f"    Entry: ${entry:.2f}, Current: ${current:.2f}")
        print(f"    P/L: {pnl_pct:+.1%}")
        print(f"    Action: {'COVER' if should_cover else 'HOLD'} - {reason}")


def example_5_find_options_contracts(trader):
    """Example 5: Find and filter options contracts."""
    print("\n" + "="*70)
    print("EXAMPLE 5: Find Options Contracts")
    print("="*70)

    symbol = "SPY"

    print(f"\nSearching for {symbol} options contracts...")
    print("  Contract Type: PUT")
    print("  Expiration: 30-60 days")
    print("  Min Open Interest: 100")

    try:
        contracts = trader.find_options_contracts(
            underlying_symbol=symbol,
            contract_type=ContractType.PUT,
            expiration_min_days=30,
            expiration_max_days=60,
            min_open_interest=100
        )

        print(f"\nFound {len(contracts)} contracts")

        # Display top 10
        print("\nTop 10 contracts by open interest:")
        print("{:<30} {:>12} {:>15} {:>15} {:>10} {:>10}".format(
            "Symbol", "Strike", "Expiration", "Open Interest", "Bid", "Ask"
        ))
        print("-" * 105)

        sorted_contracts = sorted(contracts, key=lambda c: c.open_interest, reverse=True)[:10]
        for contract in sorted_contracts:
            print("{:<30} ${:>11.2f} {:>15} {:>15,} ${:>9.2f} ${:>9.2f}".format(
                contract.symbol,
                contract.strike_price,
                contract.expiration_date.strftime("%Y-%m-%d"),
                contract.open_interest,
                contract.bid,
                contract.ask
            ))

        # Find ATM contract
        print(f"\nFinding ATM (at-the-money) contract...")
        atm_contract = trader.find_nearest_strike(
            underlying_symbol=symbol,
            contract_type=ContractType.PUT,
            target_price=None,  # Current stock price
            expiration_min_days=30,
            expiration_max_days=45
        )

        if atm_contract:
            current_price = trader.get_current_price(symbol)
            print(f"  {symbol} Current Price: ${current_price:.2f}")
            print(f"  ATM Contract: {atm_contract.symbol}")
            print(f"  Strike: ${atm_contract.strike_price:.2f}")
            print(f"  Expiration: {atm_contract.expiration_date.strftime('%Y-%m-%d')}")
            print(f"  Open Interest: {atm_contract.open_interest:,}")
            print(f"  Mid Price: ${atm_contract.mid_price:.2f}")

    except Exception as e:
        print(f"  ERROR: {e}")


def example_6_options_strategies(trader):
    """Example 6: Execute multi-leg options strategies (paper trading)."""
    print("\n" + "="*70)
    print("EXAMPLE 6: Options Strategies (PAPER TRADING)")
    print("="*70)

    # Check options eligibility
    options_info = trader.check_options_eligibility()
    if not options_info['options_enabled']:
        print("ERROR: Options trading not enabled")
        return

    print(f"Options Level: {options_info['options_level']}")

    # Strategy 1: Long Straddle
    print("\n--- Strategy 1: Long Straddle (SPY) ---")
    print("Use Case: Profit from large price movement in either direction")
    print("Best When: Expecting high volatility (earnings, FOMC, etc.)")

    try:
        result = trader.execute_long_straddle(
            underlying_symbol="SPY",
            quantity=1,
            strike_price=None,  # ATM
            expiration_days=30
        )

        if result:
            print(f"  Order submitted successfully!")
            print(f"  Order ID: {result['order_id']}")
            print(f"  Call: {result['call_symbol']}")
            print(f"  Put: {result['put_symbol']}")
            print(f"  Strike: ${result['strike']:.2f}")
            print(f"  Expiration: {result['expiration'].strftime('%Y-%m-%d')}")

    except Exception as e:
        print(f"  ERROR: {e}")

    # Strategy 2: Protective Put (requires owning stock first)
    print("\n--- Strategy 2: Protective Put (AAPL) ---")
    print("Use Case: Protect long stock position from downside")
    print("Best When: Market volatility elevated, want to keep stock")
    print("NOTE: Requires owning 100 shares of AAPL first")
    print("  (Skipping execution in this example)")

    # Strategy 3: Covered Call (requires owning stock first)
    print("\n--- Strategy 3: Covered Call (TSLA) ---")
    print("Use Case: Generate income from stock holdings")
    print("Best When: Stock is range-bound or low volatility")
    print("NOTE: Requires owning 100 shares of TSLA first")
    print("  (Skipping execution in this example)")

    # Strategy 4: Bull Call Spread
    print("\n--- Strategy 4: Bull Call Spread (QQQ) ---")
    print("Use Case: Moderately bullish with limited risk/reward")
    print("Best When: Expecting stock to rise but want to reduce cost")

    try:
        result = trader.execute_bull_call_spread(
            underlying_symbol="QQQ",
            quantity=1,
            expiration_days=30,
            width=5.0  # $5 strike width
        )

        if result:
            print(f"  Order submitted successfully!")
            print(f"  Order ID: {result['order_id']}")
            print(f"  Long Call: {result['long_call']}")
            print(f"  Short Call: {result['short_call']}")
            print(f"  Long Strike: ${result['long_strike']:.2f}")
            print(f"  Short Strike: ${result['short_strike']:.2f}")
            print(f"  Width: ${result['width']:.2f}")

    except Exception as e:
        print(f"  ERROR: {e}")


def example_7_monitor_positions(trader):
    """Example 7: Monitor all positions."""
    print("\n" + "="*70)
    print("EXAMPLE 7: Monitor Current Positions")
    print("="*70)

    # Get all positions
    all_positions = trader.trading_client.get_all_positions()

    if not all_positions:
        print("\nNo open positions")
        return

    # Separate long, short, and options
    long_positions = [p for p in all_positions if int(p.qty) > 0 and len(p.symbol) <= 5]
    short_positions = trader.get_short_positions()
    options_positions = trader.get_options_positions()

    # Display long positions
    print("\n--- Long Stock Positions ---")
    if long_positions:
        print("{:<10} {:>10} {:>15} {:>15} {:>18}".format(
            "Symbol", "Qty", "Entry Price", "Current Price", "Unrealized P/L"
        ))
        print("-" * 75)
        for pos in long_positions:
            print("{:<10} {:>10} ${:>14.2f} ${:>14.2f} ${:>11,.2f} ({:+.2%})".format(
                pos.symbol,
                pos.qty,
                float(pos.avg_entry_price),
                float(pos.current_price),
                float(pos.unrealized_pl),
                float(pos.unrealized_plpc)
            ))
    else:
        print("  No long positions")

    # Display short positions
    print("\n--- Short Stock Positions ---")
    if short_positions:
        print("{:<10} {:>10} {:>15} {:>15} {:>18}".format(
            "Symbol", "Qty", "Entry Price", "Current Price", "Unrealized P/L"
        ))
        print("-" * 75)
        for pos in short_positions:
            print("{:<10} {:>10} ${:>14.2f} ${:>14.2f} ${:>11,.2f} ({:+.2%})".format(
                pos['symbol'],
                pos['qty'],
                pos['avg_entry_price'],
                pos['current_price'],
                pos['unrealized_pl'],
                pos['unrealized_plpc']
            ))
    else:
        print("  No short positions")

    # Display options positions
    print("\n--- Options Positions ---")
    if options_positions:
        print("{:<30} {:>10} {:>15} {:>15} {:>18}".format(
            "Symbol", "Qty", "Entry Price", "Current Price", "Unrealized P/L"
        ))
        print("-" * 95)
        for pos in options_positions:
            print("{:<30} {:>10} ${:>14.2f} ${:>14.2f} ${:>11,.2f} ({:+.2%})".format(
                pos['symbol'],
                pos['qty'],
                pos['avg_entry_price'],
                pos['current_price'],
                pos['unrealized_pl'],
                pos['unrealized_plpc']
            ))
    else:
        print("  No options positions")

    # Portfolio summary
    print("\n--- Portfolio Summary ---")
    account = trader.trading_client.get_account()
    print(f"  Account Equity: ${float(account.equity):,.2f}")
    print(f"  Cash: ${float(account.cash):,.2f}")
    print(f"  Buying Power: ${float(account.buying_power):,.2f}")
    print(f"  Long Market Value: ${float(account.long_market_value):,.2f}")
    print(f"  Short Market Value: ${float(account.short_market_value):,.2f}")


def main():
    """Run all examples."""
    print("\n" + "="*70)
    print("ALPACA ADVANCED TRADING EXAMPLES")
    print("Short Selling and Options Trading")
    print("="*70)

    # Initialize trader
    trader = example_1_check_eligibility()

    # Run examples
    example_2_calculate_margin(trader)
    example_3_short_position_lifecycle(trader)
    example_4_short_risk_management()
    example_5_find_options_contracts(trader)
    example_6_options_strategies(trader)
    example_7_monitor_positions(trader)

    print("\n" + "="*70)
    print("All examples completed!")
    print("="*70)

    print("\nNOTE: Examples 3 and 6 submit paper trading orders.")
    print("Check your Alpaca dashboard to see the orders.")
    print("\nTo run individual examples:")
    print("  from examples.alpaca_advanced_examples import example_1_check_eligibility")
    print("  trader = example_1_check_eligibility()")


if __name__ == "__main__":
    main()
