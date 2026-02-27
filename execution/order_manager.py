"""
Order management system with risk validation.

Handles:
- Order creation and validation
- Pre-trade risk checks
- Order execution and tracking
- Position reconciliation
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
import logging

from execution.alpaca_client import AlpacaClient, AlpacaClientError
from execution.cash_manager import CashManager
from risk.circuit_breakers import CircuitBreaker, RiskManager
from risk.position_sizing import PositionSizer
from data.storage import TradingDatabase

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """Order lifecycle status."""
    PENDING = "pending"
    VALIDATED = "validated"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass
class Order:
    """Internal order representation."""
    id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: int
    order_type: str  # 'limit' or 'market'
    limit_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: Optional[str] = None
    filled_quantity: int = 0
    filled_price: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.now)
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    strategy: Optional[str] = None


class RiskLimitExceeded(Exception):
    """Raised when an order violates risk limits."""
    pass


class OrderManager:
    """
    Manages order lifecycle with integrated risk checks.

    Features:
    - Pre-trade risk validation
    - Limit order preference (no market orders by default)
    - Order tracking and status updates
    - Trade logging to database

    Attributes:
        alpaca: Alpaca client for order execution
        risk_manager: Risk manager for validation
        db: Database for trade logging
    """

    def __init__(
        self,
        alpaca_client: AlpacaClient,
        position_sizer: PositionSizer,
        circuit_breaker: CircuitBreaker,
        database: Optional[TradingDatabase] = None,
        limit_price_buffer_pct: float = 0.005
    ):
        """
        Initialize order manager.

        Args:
            alpaca_client: Alpaca API client
            position_sizer: Position sizing instance
            circuit_breaker: Circuit breaker instance
            database: Optional database for trade logging
            limit_price_buffer_pct: Buffer for limit orders (default 0.5%)
        """
        self.alpaca = alpaca_client
        self.position_sizer = position_sizer
        self.circuit_breaker = circuit_breaker
        self.risk_manager = RiskManager(position_sizer, circuit_breaker)
        self.cash_manager = CashManager(alpaca_client)
        self.db = database
        self.limit_price_buffer_pct = limit_price_buffer_pct

        # Track pending orders
        self.orders: Dict[str, Order] = {}
        self._order_counter = 0

        logger.info(
            "OrderManager initialized",
            extra={"limit_buffer": limit_price_buffer_pct}
        )

    def _generate_order_id(self) -> str:
        """Generate unique internal order ID."""
        self._order_counter += 1
        return f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{self._order_counter:04d}"

    def _get_current_positions(self) -> Dict[str, float]:
        """Get current positions as symbol -> market value dict."""
        try:
            positions = self.alpaca.get_positions()
            return {
                symbol: pos["market_value"]
                for symbol, pos in positions.items()
            }
        except AlpacaClientError:
            return {}

    def _calculate_limit_price(self, symbol: str, side: str) -> float:
        """
        Calculate limit price with buffer.

        For buys: slightly above current ask
        For sells: slightly below current bid
        """
        try:
            quote = self.alpaca.get_latest_quote(symbol)

            if side == "buy":
                # Buy at ask + buffer to ensure fill
                return quote["ask_price"] * (1 + self.limit_price_buffer_pct)
            else:
                # Sell at bid - buffer to ensure fill
                return quote["bid_price"] * (1 - self.limit_price_buffer_pct)
        except AlpacaClientError as e:
            logger.warning(f"Failed to get quote for limit price: {e}")
            # Fallback: use a reasonable default
            raise

    def create_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
        strategy: Optional[str] = None
    ) -> Order:
        """
        Create a new order (not yet submitted).

        Args:
            symbol: Symbol to trade
            side: 'buy' or 'sell'
            quantity: Number of shares
            order_type: 'limit' (recommended) or 'market'
            limit_price: Limit price (auto-calculated if None)
            strategy: Strategy that generated this order

        Returns:
            Order object in PENDING status
        """
        if order_type == "market":
            logger.warning(
                "Market order type specified - consider using limit orders",
                extra={"symbol": symbol, "side": side}
            )

        order = Order(
            id=self._generate_order_id(),
            symbol=symbol.upper(),
            side=side.lower(),
            quantity=abs(quantity),
            order_type=order_type,
            limit_price=limit_price,
            strategy=strategy
        )

        self.orders[order.id] = order

        logger.info(
            "Order created",
            extra={
                "order_id": order.id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": order.quantity,
                "type": order.order_type
            }
        )

        return order

    def validate_order(self, order: Order) -> tuple[bool, Optional[str]]:
        """
        Validate order against risk limits.

        Checks:
        - Circuit breakers
        - Position size limits
        - Sector exposure limits

        Args:
            order: Order to validate

        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        # Get current state
        try:
            equity = self.alpaca.get_equity()
            positions = self._get_current_positions()
        except AlpacaClientError as e:
            return False, f"Failed to get account state: {e}"

        # Estimate order value
        try:
            price = self.alpaca.get_latest_price(order.symbol)
        except AlpacaClientError:
            price = order.limit_price or 0

        order_value = order.quantity * price
        if order.side == "sell":
            order_value = -order_value

        # Validate through risk manager
        is_valid, reason = self.risk_manager.validate_order(
            symbol=order.symbol,
            order_value=order_value,
            portfolio_value=equity,
            current_positions=positions
        )

        if not is_valid:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = reason
            logger.warning(
                "Order rejected by risk validation",
                extra={"order_id": order.id, "reason": reason}
            )
            return is_valid, reason

        # CASH VALIDATION: For buy orders, verify sufficient cash available
        if order.side == "buy":
            # Get current price for validation
            price = order.limit_price if order.limit_price else price

            # Validate cash availability
            is_valid_cash, cash_reason = self.cash_manager.validate_cash_for_order(
                symbol=order.symbol,
                qty=order.quantity,
                limit_price=price
            )

            if not is_valid_cash:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = cash_reason
                logger.warning(
                    "Order rejected - insufficient cash",
                    extra={
                        "order_id": order.id,
                        "symbol": order.symbol,
                        "reason": cash_reason,
                        "cash_status": self.cash_manager.get_cash_status()
                    }
                )
                return False, cash_reason

        # All validations passed
        order.status = OrderStatus.VALIDATED
        logger.debug(f"Order {order.id} validated")
        return True, None

    def check_pending_order_conflicts(
        self,
        symbol: str,
        side: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check for pending orders that would conflict with this order.

        This prevents:
        - Duplicate buy orders on the same symbol
        - Selling positions that are locked in pending orders (bracket/stop orders)

        Args:
            symbol: Stock symbol
            side: Order side ('buy' or 'sell')

        Returns:
            Tuple of (is_valid, reason)
            - (True, None) if no conflicts
            - (False, reason) if conflicts exist
        """
        try:
            # Get open orders for this symbol
            open_orders = self.alpaca.get_open_orders_for_symbol(symbol)

            if side == "sell":
                # For sells: check if any pending orders lock the shares
                # (bracket orders, trailing stops, etc.)
                if len(open_orders) > 0:
                    order_types = [o.get('type', 'unknown') for o in open_orders]
                    reason = (
                        f"Cannot sell {symbol} - {len(open_orders)} pending orders "
                        f"may lock shares (types: {', '.join(order_types)})"
                    )
                    logger.warning(reason)
                    return False, reason

            elif side == "buy":
                # For buys: check for duplicate buy orders
                pending_buys = [o for o in open_orders if o.get('side') == 'buy']
                if len(pending_buys) > 0:
                    reason = f"Duplicate buy order exists for {symbol}"
                    logger.warning(reason)
                    return False, reason

            # No conflicts
            return True, None

        except Exception as e:
            logger.error(f"Error checking pending orders for {symbol}: {e}")
            # Fail safe: allow order but log warning
            logger.warning(
                f"Unable to check pending orders for {symbol}, allowing order"
            )
            return True, None

    def submit_order(self, order: Order, validate: bool = True) -> Order:
        """
        Submit order to broker.

        Args:
            order: Order to submit
            validate: Run risk validation first (default: True)

        Returns:
            Updated Order object

        Raises:
            RiskLimitExceeded: If validation fails
        """
        # Validate if requested
        if validate:
            is_valid, reason = self.validate_order(order)
            if not is_valid:
                raise RiskLimitExceeded(reason)

        # Calculate limit price if needed
        if order.order_type == "limit" and order.limit_price is None:
            try:
                order.limit_price = self._calculate_limit_price(order.symbol, order.side)
            except AlpacaClientError as e:
                order.status = OrderStatus.FAILED
                order.rejection_reason = f"Failed to calculate limit price: {e}"
                return order

        try:
            # Submit to Alpaca
            if order.order_type == "limit":
                result = self.alpaca.submit_limit_order(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=order.side,
                    limit_price=order.limit_price
                )
            else:
                result = self.alpaca.submit_market_order(
                    symbol=order.symbol,
                    qty=order.quantity,
                    side=order.side
                )

            # Update order with broker info
            order.broker_order_id = result["id"]
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now()

            logger.info(
                "Order submitted to broker",
                extra={
                    "order_id": order.id,
                    "broker_order_id": order.broker_order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "qty": order.quantity
                }
            )

        except AlpacaClientError as e:
            order.status = OrderStatus.FAILED
            order.rejection_reason = str(e)
            logger.error(
                "Order submission failed",
                extra={"order_id": order.id, "error": str(e)}
            )

        return order

    def check_order_status(self, order: Order) -> Order:
        """
        Check and update order status from broker.

        Args:
            order: Order to check

        Returns:
            Updated Order object
        """
        if not order.broker_order_id:
            return order

        try:
            broker_order = self.alpaca.get_order(order.broker_order_id)

            # Map broker status to our status
            status_map = {
                "new": OrderStatus.SUBMITTED,
                "partially_filled": OrderStatus.PARTIALLY_FILLED,
                "filled": OrderStatus.FILLED,
                "cancelled": OrderStatus.CANCELLED,
                "expired": OrderStatus.CANCELLED,
                "rejected": OrderStatus.REJECTED,
            }

            broker_status = broker_order["status"]
            if broker_status in status_map:
                order.status = status_map[broker_status]

            # Update fill info
            if broker_order["filled_qty"]:
                order.filled_quantity = int(float(broker_order["filled_qty"]))
            if broker_order["filled_avg_price"]:
                order.filled_price = float(broker_order["filled_avg_price"])

            # Log trade to database if filled
            if order.status == OrderStatus.FILLED and self.db:
                self._log_trade(order)
                order.filled_at = datetime.now()

        except AlpacaClientError as e:
            logger.error(f"Failed to check order status: {e}")

        return order

    def _log_trade(self, order: Order) -> None:
        """Log completed trade to database."""
        if not self.db or not order.filled_price:
            return

        try:
            self.db.insert_trade(
                timestamp=datetime.now(),
                symbol=order.symbol,
                action="BUY" if order.side == "buy" else "SELL",
                quantity=order.filled_quantity,
                price=order.filled_price,
                commission=0.0,  # Alpaca is commission-free
                order_id=order.broker_order_id,
                strategy=order.strategy
            )
        except Exception as e:
            logger.error(f"Failed to log trade: {e}")

    def cancel_order(self, order: Order) -> Order:
        """Cancel an order."""
        if not order.broker_order_id:
            order.status = OrderStatus.CANCELLED
            return order

        try:
            self.alpaca.cancel_order(order.broker_order_id)
            order.status = OrderStatus.CANCELLED

            logger.info(
                "Order cancelled",
                extra={"order_id": order.id, "broker_order_id": order.broker_order_id}
            )
        except AlpacaClientError as e:
            logger.error(f"Failed to cancel order: {e}")

        return order

    def execute_rebalance(
        self,
        target_positions: Dict[str, float],
        strategy: Optional[str] = None
    ) -> List[Order]:
        """
        Execute a portfolio rebalance to target positions.

        Args:
            target_positions: Dict of symbol -> target value in dollars
            strategy: Strategy name for logging

        Returns:
            List of submitted orders
        """
        orders = []

        # Get current positions
        current_positions = self._get_current_positions()

        # Calculate required trades
        all_symbols = set(target_positions.keys()) | set(current_positions.keys())

        for symbol in all_symbols:
            current_value = current_positions.get(symbol, 0.0)
            target_value = target_positions.get(symbol, 0.0)
            diff = target_value - current_value

            if abs(diff) < 100:  # Skip small differences (less than $100)
                continue

            # Get current price
            try:
                price = self.alpaca.get_latest_price(symbol)
            except AlpacaClientError:
                logger.warning(f"Could not get price for {symbol}, skipping")
                continue

            shares = int(abs(diff) / price)
            if shares == 0:
                continue

            side = "buy" if diff > 0 else "sell"

            # Create and submit order
            order = self.create_order(
                symbol=symbol,
                side=side,
                quantity=shares,
                order_type="limit",
                strategy=strategy
            )

            try:
                self.submit_order(order)
                orders.append(order)
            except RiskLimitExceeded as e:
                logger.warning(f"Rebalance order rejected for {symbol}: {e}")

        logger.info(
            "Rebalance executed",
            extra={"orders": len(orders), "symbols": list(all_symbols)}
        )

        return orders

    def get_open_orders(self) -> List[Order]:
        """Get all open orders."""
        return [
            o for o in self.orders.values()
            if o.status in (OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIALLY_FILLED)
        ]

    def sync_with_broker(self) -> None:
        """Sync local order state with broker."""
        for order in self.get_open_orders():
            self.check_order_status(order)
