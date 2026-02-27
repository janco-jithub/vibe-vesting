"""
Alpaca API client for paper and live trading.

Provides a clean interface for:
- Account information
- Position management
- Order submission and tracking
- Market data (real-time quotes)

Optimized for long-running operation with:
- Request timeouts to prevent hangs
- Circuit breaker for API failures
- Connection reuse
"""

import os
import time
import threading
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from decimal import Decimal
import logging
from functools import wraps

from requests.adapters import HTTPAdapter
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    TrailingStopOrderRequest,
    GetOrdersRequest,
    TakeProfitRequest,
    StopLossRequest
)
from alpaca.trading.enums import (
    OrderSide,
    OrderType,
    TimeInForce,
    OrderStatus,
    QueryOrderStatus
)
from alpaca.data.historical import StockHistoricalDataClient, CryptoHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest, CryptoLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from dotenv import load_dotenv


class TimeoutHTTPAdapter(HTTPAdapter):
    """HTTPAdapter with a default timeout to prevent indefinite hangs."""

    def __init__(self, timeout: int = 30, **kwargs):
        self.timeout = timeout
        super().__init__(**kwargs)

    def send(self, request, **kwargs):
        # Must check for None explicitly - Session.request() passes timeout=None
        # which means setdefault() won't override it
        if kwargs.get('timeout') is None:
            kwargs['timeout'] = self.timeout
        return super().send(request, **kwargs)

load_dotenv()

logger = logging.getLogger(__name__)


class AlpacaClientError(Exception):
    """Custom exception for Alpaca API errors."""
    pass


def with_circuit_breaker(func):
    """Decorator to add circuit breaker protection to API calls."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self._check_circuit_breaker():
            raise AlpacaClientError("Circuit breaker OPEN - too many recent failures")
        try:
            result = func(self, *args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise
    return wrapper


class AlpacaClient:
    """
    Unified Alpaca API client for trading operations.

    Supports both paper and live trading based on configuration.

    Attributes:
        api_key: Alpaca API key
        secret_key: Alpaca secret key
        paper: Whether using paper trading (default: True)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True
    ):
        """
        Initialize Alpaca client.

        Args:
            api_key: API key (defaults to env var)
            secret_key: Secret key (defaults to env var)
            paper: Use paper trading (default: True for safety)
        """
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")
        self.paper = paper

        if not self.api_key or not self.secret_key:
            raise AlpacaClientError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set"
            )

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._max_failures = 5
        self._circuit_timeout = 60.0  # 1 minute
        self._lock = threading.Lock()

        # Initialize trading client
        self.trading_client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=paper
        )

        # Initialize data client (for quotes)
        self.data_client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )

        # Initialize crypto data client (for crypto quotes)
        self.crypto_data_client = CryptoHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )

        # Set 30-second timeout on all API clients to prevent indefinite hangs
        # (e.g., when laptop sleeps and network connections drop)
        timeout_adapter = TimeoutHTTPAdapter(timeout=30)
        for client in [self.trading_client, self.data_client, self.crypto_data_client]:
            if hasattr(client, '_session'):
                client._session.mount('https://', timeout_adapter)
                client._session.mount('http://', timeout_adapter)

        logger.info(
            "AlpacaClient initialized",
            extra={"paper": paper}
        )

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker is open. Returns True if we should proceed."""
        with self._lock:
            if self._consecutive_failures >= self._max_failures:
                if time.time() < self._circuit_open_until:
                    logger.warning("Alpaca circuit breaker OPEN - skipping API call")
                    return False
                self._consecutive_failures = 0
            return True

    def _record_success(self) -> None:
        """Record successful API call."""
        with self._lock:
            self._consecutive_failures = 0

    def _record_failure(self) -> None:
        """Record failed API call."""
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_failures:
                self._circuit_open_until = time.time() + self._circuit_timeout
                logger.warning(
                    f"Alpaca circuit breaker OPEN - will retry after {self._circuit_timeout}s"
                )

    # ==================== Account ====================

    @with_circuit_breaker
    def get_account(self) -> Dict[str, Any]:
        """
        Get account information.

        Returns:
            Dict with account details including:
            - equity: Total portfolio value
            - cash: Available cash
            - buying_power: Available buying power
            - portfolio_value: Total value of positions
        """
        try:
            account = self.trading_client.get_account()

            return {
                "account_number": account.account_number,
                "status": account.status,
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "portfolio_value": float(account.portfolio_value),
                "currency": account.currency,
                "pattern_day_trader": account.pattern_day_trader,
                "trading_blocked": account.trading_blocked,
                "account_blocked": account.account_blocked,
            }
        except Exception as e:
            logger.error(f"Failed to get account: {e}")
            raise AlpacaClientError(f"Failed to get account: {e}")

    def get_buying_power(self) -> float:
        """Get available buying power."""
        account = self.get_account()
        return account["buying_power"]

    def get_equity(self) -> float:
        """Get total portfolio equity."""
        account = self.get_account()
        return account["equity"]

    # ==================== Positions ====================

    @with_circuit_breaker
    def get_positions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all open positions.

        Returns:
            Dict mapping symbol to position details
        """
        try:
            positions = self.trading_client.get_all_positions()

            return {
                pos.symbol: {
                    "symbol": pos.symbol,
                    "qty": int(pos.qty),
                    "market_value": float(pos.market_value),
                    "cost_basis": float(pos.cost_basis),
                    "unrealized_pl": float(pos.unrealized_pl),
                    "unrealized_plpc": float(pos.unrealized_plpc),
                    "current_price": float(pos.current_price),
                    "avg_entry_price": float(pos.avg_entry_price),
                    "side": pos.side,
                }
                for pos in positions
            }
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            raise AlpacaClientError(f"Failed to get positions: {e}")

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for a specific symbol."""
        positions = self.get_positions()
        return positions.get(symbol.upper())

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """
        Close an entire position.

        Args:
            symbol: Symbol to close

        Returns:
            Order details
        """
        try:
            order = self.trading_client.close_position(symbol.upper())

            logger.info(
                "Position closed",
                extra={"symbol": symbol, "order_id": order.id}
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            raise AlpacaClientError(f"Failed to close position: {e}")

    def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all open positions."""
        try:
            orders = self.trading_client.close_all_positions()

            logger.warning("Closed all positions", extra={"count": len(orders)})

            return [self._order_to_dict(o) for o in orders]
        except Exception as e:
            logger.error(f"Failed to close all positions: {e}")
            raise AlpacaClientError(f"Failed to close all positions: {e}")

    # ==================== Orders ====================

    def submit_market_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """
        Submit a market order.

        WARNING: Market orders should be avoided in live trading.
        Use limit orders instead.

        Args:
            symbol: Symbol to trade
            qty: Number of shares
            side: 'buy' or 'sell'
            time_in_force: 'day', 'gtc', 'ioc', 'fok'

        Returns:
            Order details
        """
        logger.warning(
            "Market order submitted - prefer limit orders",
            extra={"symbol": symbol, "qty": qty, "side": side}
        )

        try:
            order_data = MarketOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=self._parse_tif(time_in_force)
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(
                "Market order submitted",
                extra={
                    "order_id": order.id,
                    "symbol": symbol,
                    "qty": qty,
                    "side": side
                }
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to submit market order: {e}")
            raise AlpacaClientError(f"Failed to submit order: {e}")

    def submit_limit_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """
        Submit a limit order.

        This is the preferred order type for all trading.

        Args:
            symbol: Symbol to trade
            qty: Number of shares
            side: 'buy' or 'sell'
            limit_price: Maximum (buy) or minimum (sell) price
            time_in_force: 'day', 'gtc', 'ioc', 'fok'

        Returns:
            Order details
        """
        try:
            order_data = LimitOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=self._parse_tif(time_in_force),
                limit_price=round(limit_price, 2)
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(
                "Limit order submitted",
                extra={
                    "order_id": order.id,
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "limit_price": limit_price
                }
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to submit limit order: {e}")
            raise AlpacaClientError(f"Failed to submit order: {e}")

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order by ID."""
        try:
            order = self.trading_client.get_order_by_id(order_id)
            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            raise AlpacaClientError(f"Failed to get order: {e}")

    def get_orders(
        self,
        status: str = "open",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get orders by status.

        Args:
            status: 'open', 'closed', or 'all'
            limit: Maximum number of orders to return

        Returns:
            List of order details
        """
        try:
            status_map = {
                "open": QueryOrderStatus.OPEN,
                "closed": QueryOrderStatus.CLOSED,
                "all": QueryOrderStatus.ALL
            }

            request = GetOrdersRequest(
                status=status_map.get(status, QueryOrderStatus.OPEN),
                limit=limit
            )

            orders = self.trading_client.get_orders(request)
            return [self._order_to_dict(o) for o in orders]
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            raise AlpacaClientError(f"Failed to get orders: {e}")

    def cancel_order(self, order_id: str) -> None:
        """Cancel an order by ID."""
        try:
            self.trading_client.cancel_order_by_id(order_id)
            logger.info("Order cancelled", extra={"order_id": order_id})
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            raise AlpacaClientError(f"Failed to cancel order: {e}")

    def cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        try:
            self.trading_client.cancel_orders()
            logger.warning("All orders cancelled")
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            raise AlpacaClientError(f"Failed to cancel orders: {e}")

    def submit_bracket_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        take_profit_price: float,
        stop_loss_price: float,
        time_in_force: str = "gtc"
    ) -> Dict[str, Any]:
        """
        Submit a bracket order with take profit and stop loss.

        This is the RECOMMENDED way to enter positions - always use risk management!

        Args:
            symbol: Symbol to trade
            qty: Number of shares
            side: 'buy' or 'sell'
            limit_price: Entry limit price
            take_profit_price: Price to take profit (sell)
            stop_loss_price: Price to stop loss (sell)
            time_in_force: 'day' or 'gtc' (recommended: gtc)

        Returns:
            Order details with leg information
        """
        try:
            order_data = LimitOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=self._parse_tif(time_in_force),
                limit_price=round(limit_price, 2),
                order_class="bracket",
                take_profit=TakeProfitRequest(limit_price=round(take_profit_price, 2)),
                stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2))
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(
                "Bracket order submitted",
                extra={
                    "order_id": order.id,
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "entry": limit_price,
                    "take_profit": take_profit_price,
                    "stop_loss": stop_loss_price
                }
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to submit bracket order: {e}")
            raise AlpacaClientError(f"Failed to submit bracket order: {e}")

    def submit_oto_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        stop_loss_price: float,
        time_in_force: str = "gtc"
    ) -> Dict[str, Any]:
        """
        Submit a market order with attached stop loss (One-Triggers-Other).

        Use this for immediate entry with downside protection.

        Args:
            symbol: Symbol to trade
            qty: Number of shares
            side: 'buy' or 'sell'
            stop_loss_price: Price to stop loss
            time_in_force: 'day' or 'gtc'

        Returns:
            Order details
        """
        try:
            order_data = MarketOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=self._parse_tif(time_in_force),
                order_class="oto",
                stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2))
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(
                "OTO order submitted (market + stop loss)",
                extra={
                    "order_id": order.id,
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "stop_loss": stop_loss_price
                }
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to submit OTO order: {e}")
            raise AlpacaClientError(f"Failed to submit OTO order: {e}")

    def submit_limit_oto_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        stop_loss_price: float,
        time_in_force: str = "gtc"
    ) -> Dict[str, Any]:
        """
        Submit a limit order with attached stop loss only (no take profit).

        This is for Option B profit optimization - the profit optimizer handles
        exits (scale-outs, trailing stops) instead of bracket order take-profits.

        Args:
            symbol: Symbol to trade
            qty: Number of shares
            side: 'buy' or 'sell'
            limit_price: Entry limit price
            stop_loss_price: Price to stop loss
            time_in_force: 'day' or 'gtc' (recommended: gtc)

        Returns:
            Order details
        """
        try:
            order_data = LimitOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=self._parse_tif(time_in_force),
                limit_price=round(limit_price, 2),
                order_class="oto",
                stop_loss=StopLossRequest(stop_price=round(stop_loss_price, 2))
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(
                "Limit OTO order submitted (limit entry + stop loss only)",
                extra={
                    "order_id": order.id,
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "entry": limit_price,
                    "stop_loss": stop_loss_price
                }
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to submit limit OTO order: {e}")
            raise AlpacaClientError(f"Failed to submit limit OTO order: {e}")

    # ==================== Market Data ====================

    def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get latest quote for a symbol (stocks or crypto).

        Automatically detects if symbol is crypto based on suffix (USD).

        Returns:
            Dict with bid, ask, last prices
        """
        try:
            is_crypto = symbol.upper().endswith("USD") and len(symbol) > 3

            if is_crypto:
                # Use crypto data client
                request = CryptoLatestQuoteRequest(symbol_or_symbols=symbol.upper())
                quotes = self.crypto_data_client.get_crypto_latest_quote(request)
                quote = quotes[symbol.upper()]
            else:
                # Use stock data client
                request = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
                quotes = self.data_client.get_stock_latest_quote(request)
                quote = quotes[symbol.upper()]

            return {
                "symbol": symbol.upper(),
                "bid_price": float(quote.bid_price) if quote.bid_price else float(quote.ask_price),
                "bid_size": quote.bid_size if hasattr(quote, 'bid_size') else 0,
                "ask_price": float(quote.ask_price),
                "ask_size": quote.ask_size if hasattr(quote, 'ask_size') else 0,
                "timestamp": quote.timestamp.isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            raise AlpacaClientError(f"Failed to get quote: {e}")

    def get_latest_price(self, symbol: str) -> float:
        """Get latest mid price for a symbol (stocks or crypto)."""
        quote = self.get_latest_quote(symbol)
        bid = quote["bid_price"] or quote["ask_price"]
        ask = quote["ask_price"]
        return (bid + ask) / 2 if bid and ask else ask

    # ==================== Helpers ====================

    def _parse_tif(self, tif: str) -> TimeInForce:
        """Parse time in force string."""
        tif_map = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK
        }
        return tif_map.get(tif.lower(), TimeInForce.DAY)

    def _order_to_dict(self, order: Any) -> Dict[str, Any]:
        """Convert order object to dict."""
        return {
            "id": str(order.id),
            "client_order_id": order.client_order_id,
            "symbol": order.symbol,
            "qty": str(order.qty),
            "filled_qty": str(order.filled_qty) if order.filled_qty else "0",
            "side": order.side.value,
            "type": order.type.value,
            "status": order.status.value,
            "limit_price": str(order.limit_price) if order.limit_price else None,
            "filled_avg_price": str(order.filled_avg_price) if order.filled_avg_price else None,
            "created_at": order.created_at.isoformat() if order.created_at else None,
            "filled_at": order.filled_at.isoformat() if order.filled_at else None,
            "time_in_force": order.time_in_force.value,
        }

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        try:
            clock = self.trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"Failed to check market status: {e}")
            return False

    def get_market_hours(self) -> Dict[str, Any]:
        """Get today's market hours."""
        try:
            clock = self.trading_client.get_clock()
            return {
                "is_open": clock.is_open,
                "next_open": clock.next_open.isoformat() if clock.next_open else None,
                "next_close": clock.next_close.isoformat() if clock.next_close else None,
            }
        except Exception as e:
            logger.error(f"Failed to get market hours: {e}")
            raise AlpacaClientError(f"Failed to get market hours: {e}")

    # ==================== Advanced Order Types ====================

    def submit_trailing_stop_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        trail_percent: Optional[float] = None,
        trail_price: Optional[float] = None,
        time_in_force: str = "gtc"
    ) -> Dict[str, Any]:
        """
        Submit a trailing stop order.

        Trailing stops automatically adjust as price moves in your favor:
        - For long positions: Stop follows price up, locking in gains
        - For short positions: Stop follows price down

        Must specify either trail_percent OR trail_price, not both.

        Args:
            symbol: Symbol to trade
            qty: Number of shares
            side: 'buy' or 'sell' (use 'sell' for long position trailing stop)
            trail_percent: Trailing percentage (e.g., 3.0 for 3%)
            trail_price: Trailing dollar amount (e.g., 1.50 for $1.50 trail)
            time_in_force: 'day' or 'gtc'

        Returns:
            Order details
        """
        if trail_percent is None and trail_price is None:
            raise AlpacaClientError("Must specify either trail_percent or trail_price")
        if trail_percent is not None and trail_price is not None:
            raise AlpacaClientError("Cannot specify both trail_percent and trail_price")

        try:
            order_data = TrailingStopOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=self._parse_tif(time_in_force),
                trail_percent=trail_percent,
                trail_price=trail_price
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(
                "Trailing stop order submitted",
                extra={
                    "order_id": order.id,
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "trail_percent": trail_percent,
                    "trail_price": trail_price
                }
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to submit trailing stop order: {e}")
            raise AlpacaClientError(f"Failed to submit trailing stop order: {e}")

    def submit_stop_order(
        self,
        symbol: str,
        qty: int,
        side: str,
        stop_price: float,
        time_in_force: str = "gtc"
    ) -> Dict[str, Any]:
        """
        Submit a stop order (becomes market order when stop price hit).

        Args:
            symbol: Symbol to trade
            qty: Number of shares
            side: 'buy' or 'sell'
            stop_price: Trigger price
            time_in_force: 'day' or 'gtc'

        Returns:
            Order details
        """
        try:
            order_data = StopOrderRequest(
                symbol=symbol.upper(),
                qty=qty,
                side=OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL,
                time_in_force=self._parse_tif(time_in_force),
                stop_price=round(stop_price, 2)
            )

            order = self.trading_client.submit_order(order_data)

            logger.info(
                "Stop order submitted",
                extra={
                    "order_id": order.id,
                    "symbol": symbol,
                    "qty": qty,
                    "side": side,
                    "stop_price": stop_price
                }
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to submit stop order: {e}")
            raise AlpacaClientError(f"Failed to submit stop order: {e}")

    def replace_order(
        self,
        order_id: str,
        qty: Optional[int] = None,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        trail: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Replace (modify) an existing order.

        Useful for:
        - Updating trailing stops
        - Adjusting take profit levels
        - Changing position size

        Args:
            order_id: ID of order to replace
            qty: New quantity (optional)
            limit_price: New limit price (optional)
            stop_price: New stop price (optional)
            trail: New trailing amount (optional)

        Returns:
            Updated order details
        """
        try:
            # Build request data
            request_data = {}
            if qty is not None:
                request_data['qty'] = qty
            if limit_price is not None:
                request_data['limit_price'] = round(limit_price, 2)
            if stop_price is not None:
                request_data['stop_price'] = round(stop_price, 2)
            if trail is not None:
                request_data['trail'] = trail

            order = self.trading_client.replace_order_by_id(order_id, request_data)

            logger.info(
                "Order replaced",
                extra={"order_id": order_id, "updates": request_data}
            )

            return self._order_to_dict(order)
        except Exception as e:
            logger.error(f"Failed to replace order {order_id}: {e}")
            raise AlpacaClientError(f"Failed to replace order: {e}")

    def get_open_orders_for_symbol(self, symbol: str) -> List[Dict[str, Any]]:
        """
        Get all open orders for a specific symbol.

        Useful for checking if we already have stops/take-profits in place.

        Args:
            symbol: Symbol to query

        Returns:
            List of open orders for the symbol
        """
        try:
            request = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol.upper()]
            )
            orders = self.trading_client.get_orders(request)
            return [self._order_to_dict(o) for o in orders]
        except Exception as e:
            logger.error(f"Failed to get orders for {symbol}: {e}")
            raise AlpacaClientError(f"Failed to get orders: {e}")

    def cancel_orders_for_symbol(self, symbol: str) -> int:
        """
        Cancel all open orders for a specific symbol.

        Useful when repositioning or exiting a position.

        Args:
            symbol: Symbol to cancel orders for

        Returns:
            Number of orders cancelled
        """
        try:
            open_orders = self.get_open_orders_for_symbol(symbol)
            cancelled_count = 0

            for order in open_orders:
                try:
                    self.cancel_order(order['id'])
                    cancelled_count += 1
                except Exception as e:
                    logger.warning(f"Failed to cancel order {order['id']}: {e}")

            logger.info(
                f"Cancelled {cancelled_count} orders for {symbol}"
            )

            return cancelled_count
        except Exception as e:
            logger.error(f"Failed to cancel orders for {symbol}: {e}")
            return 0
