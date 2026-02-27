"""
Advanced Alpaca Trading Features: Short Selling and Options Trading

This module implements production-ready short selling and options trading capabilities
for quantitative trading systems using the Alpaca API.

Key Features:
- Short selling with margin management
- Single-leg and multi-leg options strategies
- Risk management for short positions
- ETB/HTB stock borrow monitoring
- Options contract selection and filtering

References:
- Alpaca API Documentation: https://docs.alpaca.markets/
- Short Selling: https://docs.alpaca.markets/docs/margin-and-short-selling
- Options Trading: https://docs.alpaca.markets/docs/options-trading
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from zoneinfo import ZoneInfo

import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    GetOptionContractsRequest,
    MarketOrderRequest,
    LimitOrderRequest,
    ClosePositionRequest,
    OptionLegRequest
)
from alpaca.trading.enums import (
    AssetStatus,
    ExerciseStyle,
    OrderSide,
    OrderClass,
    OrderType,
    TimeInForce,
    ContractType
)
from alpaca.data.historical.stock import StockHistoricalDataClient, StockLatestTradeRequest
from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.requests import (
    OptionLatestQuoteRequest,
    OptionChainRequest
)
from alpaca.common.exceptions import APIError


class PositionType(Enum):
    """Position direction types."""
    LONG = "LONG"
    SHORT = "SHORT"


class OptionsLevel(Enum):
    """Alpaca options trading levels."""
    DISABLED = 0
    LEVEL_1 = 1  # Covered calls, cash-secured puts
    LEVEL_2 = 2  # Level 1 + buying calls/puts
    LEVEL_3 = 3  # Level 1-2 + spreads


@dataclass
class MarginRequirement:
    """Margin requirement information for a position."""
    initial_margin: float
    maintenance_margin: float
    buying_power_effect: float
    is_marginable: bool
    short_requirement: Optional[float] = None


@dataclass
class OptionsContract:
    """Options contract details."""
    symbol: str
    underlying_symbol: str
    expiration_date: datetime
    strike_price: float
    contract_type: ContractType  # CALL or PUT
    style: ExerciseStyle
    open_interest: int
    bid: float
    ask: float
    mid_price: float
    implied_volatility: Optional[float] = None


class AlpacaAdvancedTrading:
    """
    Advanced trading features for Alpaca: short selling and options.

    This class provides production-ready implementations of:
    1. Short selling with proper margin checks
    2. Single-leg options trading
    3. Multi-leg options strategies (spreads, straddles, strangles)
    4. Risk management for short positions
    5. Options contract selection and filtering

    Account Requirements:
    - Minimum $2,000 equity for margin/short selling
    - Options trading approval (automatic in paper trading)
    - Pattern Day Trading (PDT) flag for accounts with $25,000+ equity
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True
    ):
        """
        Initialize Alpaca Advanced Trading client.

        Args:
            api_key: Alpaca API key (defaults to ALPACA_API_KEY env var)
            secret_key: Alpaca secret key (defaults to ALPACA_SECRET_KEY env var)
            paper: Use paper trading (default: True)
        """
        self.api_key = api_key or os.environ.get('ALPACA_API_KEY')
        self.secret_key = secret_key or os.environ.get('ALPACA_SECRET_KEY')
        self.paper = paper

        if not self.api_key or not self.secret_key:
            raise ValueError("Alpaca API credentials not provided")

        self.trading_client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=self.paper
        )
        self.stock_data_client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )
        self.option_data_client = OptionHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )

        self.tz = ZoneInfo("America/New_York")

    # ==================== SHORT SELLING METHODS ====================

    def check_short_eligibility(self) -> Dict[str, any]:
        """
        Check if account is eligible for short selling.

        Requirements:
        - Account equity >= $2,000
        - shorting_enabled flag = True
        - Margin account

        Returns:
            Dict with eligibility info and account details
        """
        account = self.trading_client.get_account()

        equity = float(account.equity)
        shorting_enabled = account.shorting_enabled

        eligible = equity >= 2000.0 and shorting_enabled

        return {
            'eligible': eligible,
            'equity': equity,
            'shorting_enabled': shorting_enabled,
            'buying_power': float(account.buying_power),
            'short_market_value': float(account.short_market_value) if account.short_market_value else 0.0,
            'initial_margin': float(account.initial_margin) if account.initial_margin else 0.0,
            'maintenance_margin': float(account.maintenance_margin) if account.maintenance_margin else 0.0,
            'daytrading_buying_power': float(account.daytrading_buying_power) if account.daytrading_buying_power else 0.0,
            'pattern_day_trader': account.pattern_day_trader
        }

    def calculate_short_margin_requirement(
        self,
        symbol: str,
        quantity: int,
        price: Optional[float] = None
    ) -> MarginRequirement:
        """
        Calculate margin requirements for a short position.

        Alpaca Margin Requirements (Overnight):
        - Price < $5.00: Greater of $2.50/share or 100% of market value
        - Price >= $5.00: Greater of $5.00/share or 30% of market value

        Initial margin: 50% (Regulation T)

        Args:
            symbol: Stock symbol
            quantity: Number of shares to short
            price: Current price (if None, fetches latest)

        Returns:
            MarginRequirement object
        """
        if price is None:
            price = self.get_current_price(symbol)

        position_value = price * quantity

        # Initial margin (Regulation T): 50%
        initial_margin = position_value * 0.50

        # Maintenance margin (overnight)
        if price < 5.00:
            maintenance_margin = max(2.50 * quantity, position_value)
        else:
            maintenance_margin = max(5.00 * quantity, position_value * 0.30)

        # Buying power effect (how much buying power is consumed)
        buying_power_effect = initial_margin + position_value

        return MarginRequirement(
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
            buying_power_effect=buying_power_effect,
            is_marginable=True,
            short_requirement=maintenance_margin
        )

    def submit_short_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str = "market",
        limit_price: Optional[float] = None,
        check_margin: bool = True
    ) -> Optional[Dict]:
        """
        Submit a short sell order.

        IMPORTANT: Alpaca only supports shorting ETB (easy-to-borrow) stocks.
        HTB (hard-to-borrow) stocks will be rejected.

        Args:
            symbol: Stock symbol to short
            quantity: Number of shares (positive number)
            order_type: 'market' or 'limit'
            limit_price: Required if order_type='limit'
            check_margin: Verify sufficient buying power before submitting

        Returns:
            Order response dict or None if failed

        Example:
            >>> trader.submit_short_order("SPY", 100, order_type="limit", limit_price=450.00)
        """
        # Check short eligibility
        eligibility = self.check_short_eligibility()
        if not eligibility['eligible']:
            raise ValueError(
                f"Account not eligible for short selling. "
                f"Equity: ${eligibility['equity']:.2f}, "
                f"Shorting enabled: {eligibility['shorting_enabled']}"
            )

        # Check margin requirements
        if check_margin:
            margin_req = self.calculate_short_margin_requirement(symbol, quantity)
            available_bp = eligibility['buying_power']

            if margin_req.buying_power_effect > available_bp:
                raise ValueError(
                    f"Insufficient buying power. "
                    f"Required: ${margin_req.buying_power_effect:.2f}, "
                    f"Available: ${available_bp:.2f}"
                )

        # Submit order
        try:
            if order_type.lower() == "market":
                order_request = MarketOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=OrderSide.SELL,  # SELL side for short
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
            elif order_type.lower() == "limit":
                if limit_price is None:
                    raise ValueError("limit_price required for limit orders")
                order_request = LimitOrderRequest(
                    symbol=symbol,
                    qty=quantity,
                    side=OrderSide.SELL,
                    limit_price=limit_price,
                    type=OrderType.LIMIT,
                    time_in_force=TimeInForce.DAY
                )
            else:
                raise ValueError(f"Invalid order_type: {order_type}")

            order = self.trading_client.submit_order(order_request)

            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': order.qty,
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }

        except APIError as e:
            print(f"Error submitting short order for {symbol}: {e}")
            return None

    def cover_short_position(
        self,
        symbol: str,
        quantity: Optional[int] = None,
        order_type: str = "market",
        limit_price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Cover (close) a short position by buying shares.

        Args:
            symbol: Stock symbol to cover
            quantity: Number of shares to cover (None = close entire position)
            order_type: 'market' or 'limit'
            limit_price: Required if order_type='limit'

        Returns:
            Order response dict or None if failed

        Example:
            >>> trader.cover_short_position("SPY")  # Close entire position
            >>> trader.cover_short_position("SPY", quantity=50)  # Partial cover
        """
        # Get current position
        try:
            position = self.trading_client.get_open_position(symbol)
            current_qty = int(position.qty)

            # Check if it's actually a short position
            if current_qty >= 0:
                raise ValueError(f"{symbol} is not a short position (qty={current_qty})")

            # Determine quantity to cover
            cover_qty = abs(current_qty) if quantity is None else quantity

            if cover_qty > abs(current_qty):
                raise ValueError(
                    f"Cannot cover {cover_qty} shares, only {abs(current_qty)} shares short"
                )

        except APIError as e:
            print(f"Error getting position for {symbol}: {e}")
            return None

        # Submit buy order to cover
        try:
            if order_type.lower() == "market":
                order_request = MarketOrderRequest(
                    symbol=symbol,
                    qty=cover_qty,
                    side=OrderSide.BUY,  # BUY side to cover short
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
            elif order_type.lower() == "limit":
                if limit_price is None:
                    raise ValueError("limit_price required for limit orders")
                order_request = LimitOrderRequest(
                    symbol=symbol,
                    qty=cover_qty,
                    side=OrderSide.BUY,
                    limit_price=limit_price,
                    type=OrderType.LIMIT,
                    time_in_force=TimeInForce.DAY
                )
            else:
                raise ValueError(f"Invalid order_type: {order_type}")

            order = self.trading_client.submit_order(order_request)

            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': order.qty,
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }

        except APIError as e:
            print(f"Error covering short position for {symbol}: {e}")
            return None

    def get_short_positions(self) -> List[Dict]:
        """
        Get all current short positions.

        Returns:
            List of short position dictionaries with details
        """
        positions = self.trading_client.get_all_positions()

        short_positions = []
        for position in positions:
            qty = int(position.qty)
            if qty < 0:  # Negative quantity = short position
                short_positions.append({
                    'symbol': position.symbol,
                    'qty': qty,
                    'market_value': float(position.market_value),
                    'cost_basis': float(position.cost_basis),
                    'unrealized_pl': float(position.unrealized_pl),
                    'unrealized_plpc': float(position.unrealized_plpc),
                    'current_price': float(position.current_price),
                    'avg_entry_price': float(position.avg_entry_price)
                })

        return short_positions

    # ==================== OPTIONS TRADING METHODS ====================

    def check_options_eligibility(self) -> Dict[str, any]:
        """
        Check options trading eligibility and level.

        Returns:
            Dict with options trading level and account details
        """
        account = self.trading_client.get_account()

        # In paper trading, options are enabled by default
        # In live trading, check account.options_trading_level
        options_level = 3 if self.paper else getattr(account, 'options_trading_level', 0)

        return {
            'options_enabled': options_level > 0,
            'options_level': options_level,
            'equity': float(account.equity),
            'buying_power': float(account.buying_power),
            'options_buying_power': float(account.options_buying_power) if hasattr(account, 'options_buying_power') else 0.0
        }

    def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        request = StockLatestTradeRequest(symbol_or_symbols=symbol)
        response = self.stock_data_client.get_stock_latest_trade(request)
        return float(response[symbol].price)

    def find_options_contracts(
        self,
        underlying_symbol: str,
        contract_type: ContractType,
        expiration_min_days: int = 7,
        expiration_max_days: int = 60,
        strike_min: Optional[float] = None,
        strike_max: Optional[float] = None,
        min_open_interest: int = 100
    ) -> List[OptionsContract]:
        """
        Find options contracts matching specified criteria.

        Args:
            underlying_symbol: Stock symbol (e.g., 'SPY')
            contract_type: ContractType.CALL or ContractType.PUT
            expiration_min_days: Minimum days to expiration
            expiration_max_days: Maximum days to expiration
            strike_min: Minimum strike price
            strike_max: Maximum strike price
            min_open_interest: Minimum open interest

        Returns:
            List of OptionsContract objects

        Example:
            >>> contracts = trader.find_options_contracts(
            ...     'SPY', ContractType.PUT, expiration_min_days=30, expiration_max_days=45
            ... )
        """
        now = datetime.now(tz=self.tz)
        exp_min_date = (now + timedelta(days=expiration_min_days)).date()
        exp_max_date = (now + timedelta(days=expiration_max_days)).date()

        request = GetOptionContractsRequest(
            underlying_symbols=[underlying_symbol],
            status=AssetStatus.ACTIVE,
            expiration_date_gte=exp_min_date,
            expiration_date_lte=exp_max_date,
            type=contract_type,
            style=ExerciseStyle.AMERICAN,
            strike_price_gte=str(strike_min) if strike_min else None,
            strike_price_lte=str(strike_max) if strike_max else None,
            limit=1000
        )

        response = self.trading_client.get_option_contracts(request)

        # Get market data for contracts
        symbols = [c.symbol for c in response.option_contracts]
        if not symbols:
            return []

        quote_request = OptionLatestQuoteRequest(symbol_or_symbols=symbols)
        quotes = self.option_data_client.get_option_latest_quote(quote_request)

        contracts = []
        for contract in response.option_contracts:
            # Filter by open interest
            oi = int(contract.open_interest) if contract.open_interest else 0
            if oi < min_open_interest:
                continue

            # Get bid/ask
            quote = quotes.get(contract.symbol)
            if quote:
                bid = float(quote.bid_price)
                ask = float(quote.ask_price)
                mid = (bid + ask) / 2.0
            else:
                bid = ask = mid = 0.0

            contracts.append(OptionsContract(
                symbol=contract.symbol,
                underlying_symbol=contract.underlying_symbol,
                expiration_date=contract.expiration_date,
                strike_price=float(contract.strike_price),
                contract_type=contract_type,
                style=contract.style,
                open_interest=oi,
                bid=bid,
                ask=ask,
                mid_price=mid
            ))

        return contracts

    def find_nearest_strike(
        self,
        underlying_symbol: str,
        contract_type: ContractType,
        target_price: Optional[float] = None,
        expiration_min_days: int = 7,
        expiration_max_days: int = 60
    ) -> Optional[OptionsContract]:
        """
        Find options contract with strike nearest to target price.

        Args:
            underlying_symbol: Stock symbol
            contract_type: ContractType.CALL or ContractType.PUT
            target_price: Target strike price (defaults to current stock price)
            expiration_min_days: Minimum days to expiration
            expiration_max_days: Maximum days to expiration

        Returns:
            OptionsContract with nearest strike or None
        """
        if target_price is None:
            target_price = self.get_current_price(underlying_symbol)

        # Search within 5% of target
        strike_min = target_price * 0.95
        strike_max = target_price * 1.05

        contracts = self.find_options_contracts(
            underlying_symbol=underlying_symbol,
            contract_type=contract_type,
            expiration_min_days=expiration_min_days,
            expiration_max_days=expiration_max_days,
            strike_min=strike_min,
            strike_max=strike_max,
            min_open_interest=50
        )

        if not contracts:
            return None

        # Find contract with strike nearest to target
        best_contract = min(
            contracts,
            key=lambda c: abs(c.strike_price - target_price)
        )

        return best_contract

    def buy_option(
        self,
        option_symbol: str,
        quantity: int = 1,
        order_type: str = "market",
        limit_price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Buy an options contract (single-leg).

        Args:
            option_symbol: Options contract symbol
            quantity: Number of contracts
            order_type: 'market' or 'limit'
            limit_price: Required if order_type='limit'

        Returns:
            Order response dict or None if failed

        Example:
            >>> trader.buy_option("SPY250321P00450000", quantity=1)
        """
        eligibility = self.check_options_eligibility()
        if not eligibility['options_enabled']:
            raise ValueError("Options trading not enabled on account")

        try:
            if order_type.lower() == "market":
                order_request = MarketOrderRequest(
                    symbol=option_symbol,
                    qty=quantity,
                    side=OrderSide.BUY,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
            elif order_type.lower() == "limit":
                if limit_price is None:
                    raise ValueError("limit_price required for limit orders")
                order_request = LimitOrderRequest(
                    symbol=option_symbol,
                    qty=quantity,
                    side=OrderSide.BUY,
                    limit_price=limit_price,
                    type=OrderType.LIMIT,
                    time_in_force=TimeInForce.DAY
                )
            else:
                raise ValueError(f"Invalid order_type: {order_type}")

            order = self.trading_client.submit_order(order_request)

            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': order.qty,
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }

        except APIError as e:
            print(f"Error buying option {option_symbol}: {e}")
            return None

    def sell_option(
        self,
        option_symbol: str,
        quantity: int = 1,
        order_type: str = "market",
        limit_price: Optional[float] = None
    ) -> Optional[Dict]:
        """
        Sell an options contract (close long position or open short position).

        Args:
            option_symbol: Options contract symbol
            quantity: Number of contracts
            order_type: 'market' or 'limit'
            limit_price: Required if order_type='limit'

        Returns:
            Order response dict or None if failed
        """
        try:
            if order_type.lower() == "market":
                order_request = MarketOrderRequest(
                    symbol=option_symbol,
                    qty=quantity,
                    side=OrderSide.SELL,
                    type=OrderType.MARKET,
                    time_in_force=TimeInForce.DAY
                )
            elif order_type.lower() == "limit":
                if limit_price is None:
                    raise ValueError("limit_price required for limit orders")
                order_request = LimitOrderRequest(
                    symbol=option_symbol,
                    qty=quantity,
                    side=OrderSide.SELL,
                    limit_price=limit_price,
                    type=OrderType.LIMIT,
                    time_in_force=TimeInForce.DAY
                )
            else:
                raise ValueError(f"Invalid order_type: {order_type}")

            order = self.trading_client.submit_order(order_request)

            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': order.qty,
                'side': order.side.value,
                'type': order.type.value,
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }

        except APIError as e:
            print(f"Error selling option {option_symbol}: {e}")
            return None

    # ==================== MULTI-LEG OPTIONS STRATEGIES ====================

    def execute_long_straddle(
        self,
        underlying_symbol: str,
        quantity: int = 1,
        strike_price: Optional[float] = None,
        expiration_days: int = 30
    ) -> Optional[Dict]:
        """
        Execute a long straddle strategy (buy ATM call + buy ATM put).

        Use Case: Profit from large price movements in either direction.
        Best when: Expecting high volatility but uncertain of direction.

        Args:
            underlying_symbol: Stock symbol (e.g., 'SPY')
            quantity: Number of straddles (contracts per leg)
            strike_price: Strike price (defaults to current stock price)
            expiration_days: Days to expiration (target, ±7 days)

        Returns:
            Order response dict with both legs or None if failed

        Risk: Limited to premium paid. Profit: Unlimited if price moves significantly.

        Example:
            >>> trader.execute_long_straddle('SPY', quantity=1, expiration_days=30)
        """
        eligibility = self.check_options_eligibility()
        if eligibility['options_level'] < OptionsLevel.LEVEL_2.value:
            raise ValueError(f"Requires Level 2 options. Current: {eligibility['options_level']}")

        if strike_price is None:
            strike_price = self.get_current_price(underlying_symbol)

        # Find call and put contracts
        call_contract = self.find_nearest_strike(
            underlying_symbol,
            ContractType.CALL,
            strike_price,
            expiration_days - 7,
            expiration_days + 7
        )

        put_contract = self.find_nearest_strike(
            underlying_symbol,
            ContractType.PUT,
            strike_price,
            expiration_days - 7,
            expiration_days + 7
        )

        if not call_contract or not put_contract:
            print(f"Could not find suitable call/put contracts for {underlying_symbol}")
            return None

        # Ensure same expiration and strike
        if call_contract.expiration_date != put_contract.expiration_date:
            print("Call and put have different expirations")
            return None

        # Create multi-leg order
        order_legs = [
            OptionLegRequest(
                symbol=call_contract.symbol,
                side=OrderSide.BUY,
                ratio_qty=quantity
            ),
            OptionLegRequest(
                symbol=put_contract.symbol,
                side=OrderSide.BUY,
                ratio_qty=quantity
            )
        ]

        try:
            order_request = MarketOrderRequest(
                qty=quantity,
                order_class=OrderClass.MLEG,
                time_in_force=TimeInForce.DAY,
                legs=order_legs
            )

            order = self.trading_client.submit_order(order_request)

            return {
                'order_id': order.id,
                'strategy': 'long_straddle',
                'underlying': underlying_symbol,
                'qty': quantity,
                'call_symbol': call_contract.symbol,
                'put_symbol': put_contract.symbol,
                'strike': call_contract.strike_price,
                'expiration': call_contract.expiration_date,
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }

        except APIError as e:
            print(f"Error executing long straddle: {e}")
            return None

    def execute_protective_put(
        self,
        underlying_symbol: str,
        shares_owned: int,
        strike_price: Optional[float] = None,
        expiration_days: int = 60
    ) -> Optional[Dict]:
        """
        Execute protective put strategy (own stock + buy put).

        Use Case: Protect long stock position against downside risk.
        Best when: Holding stock but want insurance against declines.

        Args:
            underlying_symbol: Stock symbol
            shares_owned: Number of shares owned (or to buy)
            strike_price: Put strike price (defaults to 5% below current price)
            expiration_days: Days to expiration

        Returns:
            Order response dict or None if failed

        Risk: Limited to (stock_price - strike_price - premium).
        Profit: Unlimited upside minus put premium.

        Example:
            >>> trader.execute_protective_put('AAPL', shares_owned=100, expiration_days=90)
        """
        eligibility = self.check_options_eligibility()
        if eligibility['options_level'] < OptionsLevel.LEVEL_2.value:
            raise ValueError(f"Requires Level 2 options. Current: {eligibility['options_level']}")

        current_price = self.get_current_price(underlying_symbol)

        if strike_price is None:
            strike_price = current_price * 0.95  # 5% below current

        # Find protective put (OTM put)
        put_contract = self.find_nearest_strike(
            underlying_symbol,
            ContractType.PUT,
            strike_price,
            expiration_days - 7,
            expiration_days + 7
        )

        if not put_contract:
            print(f"Could not find suitable put contract for {underlying_symbol}")
            return None

        # Calculate contracts needed (1 contract = 100 shares)
        contracts_needed = shares_owned // 100
        if contracts_needed == 0:
            raise ValueError(f"Need at least 100 shares for 1 put contract. Got {shares_owned}")

        # Buy puts
        result = self.buy_option(put_contract.symbol, quantity=contracts_needed)

        if result:
            result['strategy'] = 'protective_put'
            result['underlying'] = underlying_symbol
            result['shares_protected'] = contracts_needed * 100
            result['strike'] = put_contract.strike_price
            result['expiration'] = put_contract.expiration_date

        return result

    def execute_covered_call(
        self,
        underlying_symbol: str,
        shares_owned: int,
        strike_price: Optional[float] = None,
        expiration_days: int = 30
    ) -> Optional[Dict]:
        """
        Execute covered call strategy (own stock + sell call).

        Use Case: Generate income from stock holdings.
        Best when: Stock is range-bound or slightly bullish.

        Args:
            underlying_symbol: Stock symbol
            shares_owned: Number of shares owned
            strike_price: Call strike price (defaults to 5% above current)
            expiration_days: Days to expiration

        Returns:
            Order response dict or None if failed

        Risk: Upside capped at strike price. Downside = stock ownership.
        Profit: Premium + (strike - stock_price) if called away.

        Example:
            >>> trader.execute_covered_call('TSLA', shares_owned=100, expiration_days=30)
        """
        eligibility = self.check_options_eligibility()
        if eligibility['options_level'] < OptionsLevel.LEVEL_1.value:
            raise ValueError(f"Requires Level 1 options. Current: {eligibility['options_level']}")

        current_price = self.get_current_price(underlying_symbol)

        if strike_price is None:
            strike_price = current_price * 1.05  # 5% above current

        # Find OTM call
        call_contract = self.find_nearest_strike(
            underlying_symbol,
            ContractType.CALL,
            strike_price,
            expiration_days - 7,
            expiration_days + 7
        )

        if not call_contract:
            print(f"Could not find suitable call contract for {underlying_symbol}")
            return None

        # Calculate contracts (1 contract = 100 shares)
        contracts = shares_owned // 100
        if contracts == 0:
            raise ValueError(f"Need at least 100 shares for 1 call contract. Got {shares_owned}")

        # Sell calls
        result = self.sell_option(call_contract.symbol, quantity=contracts)

        if result:
            result['strategy'] = 'covered_call'
            result['underlying'] = underlying_symbol
            result['shares_covered'] = contracts * 100
            result['strike'] = call_contract.strike_price
            result['expiration'] = call_contract.expiration_date

        return result

    def execute_bull_call_spread(
        self,
        underlying_symbol: str,
        quantity: int = 1,
        expiration_days: int = 30,
        width: float = 5.0
    ) -> Optional[Dict]:
        """
        Execute bull call spread (buy lower strike call + sell higher strike call).

        Use Case: Moderately bullish outlook with limited risk/reward.
        Best when: Expecting stock to rise but want to reduce cost.

        Args:
            underlying_symbol: Stock symbol
            quantity: Number of spreads
            expiration_days: Days to expiration
            width: Strike price difference (e.g., 5 = $5 wide spread)

        Returns:
            Order response dict or None if failed

        Risk: Limited to net premium paid.
        Profit: Limited to (width - net_premium) per spread.

        Example:
            >>> trader.execute_bull_call_spread('QQQ', quantity=2, width=5.0)
        """
        eligibility = self.check_options_eligibility()
        if eligibility['options_level'] < OptionsLevel.LEVEL_3.value:
            raise ValueError(f"Requires Level 3 options. Current: {eligibility['options_level']}")

        current_price = self.get_current_price(underlying_symbol)

        # Buy call slightly OTM
        long_strike = current_price * 1.02  # 2% above
        short_strike = long_strike + width

        # Find contracts
        long_call = self.find_nearest_strike(
            underlying_symbol,
            ContractType.CALL,
            long_strike,
            expiration_days - 7,
            expiration_days + 7
        )

        short_call = self.find_nearest_strike(
            underlying_symbol,
            ContractType.CALL,
            short_strike,
            expiration_days - 7,
            expiration_days + 7
        )

        if not long_call or not short_call:
            print(f"Could not find suitable call contracts for spread")
            return None

        # Ensure same expiration
        if long_call.expiration_date != short_call.expiration_date:
            print("Calls have different expirations")
            return None

        # Create multi-leg order
        order_legs = [
            OptionLegRequest(
                symbol=long_call.symbol,
                side=OrderSide.BUY,
                ratio_qty=quantity
            ),
            OptionLegRequest(
                symbol=short_call.symbol,
                side=OrderSide.SELL,
                ratio_qty=quantity
            )
        ]

        try:
            order_request = MarketOrderRequest(
                qty=quantity,
                order_class=OrderClass.MLEG,
                time_in_force=TimeInForce.DAY,
                legs=order_legs
            )

            order = self.trading_client.submit_order(order_request)

            return {
                'order_id': order.id,
                'strategy': 'bull_call_spread',
                'underlying': underlying_symbol,
                'qty': quantity,
                'long_call': long_call.symbol,
                'short_call': short_call.symbol,
                'long_strike': long_call.strike_price,
                'short_strike': short_call.strike_price,
                'width': short_call.strike_price - long_call.strike_price,
                'expiration': long_call.expiration_date,
                'status': order.status.value,
                'submitted_at': order.submitted_at
            }

        except APIError as e:
            print(f"Error executing bull call spread: {e}")
            return None

    def get_options_positions(self) -> List[Dict]:
        """
        Get all current options positions.

        Returns:
            List of options position dictionaries
        """
        positions = self.trading_client.get_all_positions()

        options_positions = []
        for position in positions:
            # Options symbols contain expiration date (e.g., SPY250321P00450000)
            if len(position.symbol) > 10 and any(char.isdigit() for char in position.symbol[3:9]):
                options_positions.append({
                    'symbol': position.symbol,
                    'qty': int(position.qty),
                    'market_value': float(position.market_value),
                    'cost_basis': float(position.cost_basis),
                    'unrealized_pl': float(position.unrealized_pl),
                    'unrealized_plpc': float(position.unrealized_plpc),
                    'current_price': float(position.current_price),
                    'avg_entry_price': float(position.avg_entry_price)
                })

        return options_positions


# ==================== RISK MANAGEMENT FOR SHORT POSITIONS ====================

class ShortPositionRiskManager:
    """
    Risk management specifically for short positions.

    Short selling carries unique risks:
    - Unlimited loss potential (stock can rise indefinitely)
    - Margin calls and forced liquidation
    - Short squeeze risk
    - Borrow fees (HTB stocks)
    """

    def __init__(self, max_short_exposure_pct: float = 0.25):
        """
        Initialize short position risk manager.

        Args:
            max_short_exposure_pct: Maximum short exposure as % of portfolio (default: 25%)
        """
        self.max_short_exposure_pct = max_short_exposure_pct

    def check_short_exposure(
        self,
        account_equity: float,
        current_short_value: float,
        new_short_value: float
    ) -> Tuple[bool, str]:
        """
        Check if adding new short position exceeds risk limits.

        Args:
            account_equity: Total account equity
            current_short_value: Absolute value of current short positions
            new_short_value: Absolute value of new short position

        Returns:
            (allowed, reason) tuple
        """
        total_short_value = current_short_value + new_short_value
        short_exposure_pct = total_short_value / account_equity

        if short_exposure_pct > self.max_short_exposure_pct:
            return False, (
                f"Short exposure {short_exposure_pct:.1%} exceeds limit "
                f"{self.max_short_exposure_pct:.1%}"
            )

        return True, "OK"

    def calculate_stop_loss_price(
        self,
        entry_price: float,
        max_loss_pct: float = 0.15
    ) -> float:
        """
        Calculate stop loss price for short position.

        For short positions: stop loss is ABOVE entry price.

        Args:
            entry_price: Short entry price
            max_loss_pct: Maximum loss tolerance (default: 15%)

        Returns:
            Stop loss price
        """
        return entry_price * (1 + max_loss_pct)

    def should_cover_short(
        self,
        entry_price: float,
        current_price: float,
        stop_loss_pct: float = 0.15,
        take_profit_pct: float = 0.20
    ) -> Tuple[bool, str]:
        """
        Determine if short position should be covered.

        Args:
            entry_price: Short entry price
            current_price: Current stock price
            stop_loss_pct: Stop loss threshold (default: 15%)
            take_profit_pct: Take profit threshold (default: 20%)

        Returns:
            (should_cover, reason) tuple
        """
        pnl_pct = (entry_price - current_price) / entry_price

        # Stop loss: price rose too much
        if pnl_pct < -stop_loss_pct:
            return True, f"STOP_LOSS: Loss {pnl_pct:.1%} exceeds {stop_loss_pct:.1%}"

        # Take profit: price fell enough
        if pnl_pct > take_profit_pct:
            return True, f"TAKE_PROFIT: Profit {pnl_pct:.1%} exceeds {take_profit_pct:.1%}"

        return False, "HOLD"


if __name__ == "__main__":
    # Example usage
    print("Alpaca Advanced Trading - Short Selling and Options")
    print("=" * 60)

    # Initialize (uses paper trading by default)
    trader = AlpacaAdvancedTrading(paper=True)

    # Check eligibility
    print("\n1. Short Selling Eligibility:")
    eligibility = trader.check_short_eligibility()
    print(f"   Eligible: {eligibility['eligible']}")
    print(f"   Equity: ${eligibility['equity']:,.2f}")
    print(f"   Buying Power: ${eligibility['buying_power']:,.2f}")

    print("\n2. Options Trading Eligibility:")
    options_info = trader.check_options_eligibility()
    print(f"   Enabled: {options_info['options_enabled']}")
    print(f"   Level: {options_info['options_level']}")

    # Example: Calculate margin for short position
    print("\n3. Short Margin Calculation (Example: SPY 100 shares @ $450):")
    margin = trader.calculate_short_margin_requirement("SPY", 100, 450.0)
    print(f"   Initial Margin: ${margin.initial_margin:,.2f}")
    print(f"   Maintenance Margin: ${margin.maintenance_margin:,.2f}")
    print(f"   Buying Power Effect: ${margin.buying_power_effect:,.2f}")

    print("\n4. Current Positions:")
    short_positions = trader.get_short_positions()
    print(f"   Short Positions: {len(short_positions)}")

    options_positions = trader.get_options_positions()
    print(f"   Options Positions: {len(options_positions)}")

    print("\n" + "=" * 60)
    print("Module ready. Use trader.submit_short_order() or trader.execute_long_straddle()")
