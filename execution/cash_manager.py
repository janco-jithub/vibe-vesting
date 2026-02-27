"""
Cash Manager - Tracks available cash and prevents order errors.

This module provides centralized cash management that:
- Calculates true available cash (excluding pending orders)
- Never uses buying power (margin/borrowed money)
- Validates orders have sufficient cash before submission
- Maintains a safety buffer to prevent over-deployment

Critical: This is the ONLY place that should calculate available trading cash.
"""

import logging
import time
from typing import Dict, Optional, Any, TYPE_CHECKING
from pathlib import Path
import yaml

if TYPE_CHECKING:
    from execution.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


class CashManagerError(Exception):
    """Raised when cash manager encounters an error."""
    pass


class CashManager:
    """
    Manages cash availability and validates orders against available funds.

    Key Features:
    - Tracks cash locked in pending buy orders
    - Never uses buying_power (margin)
    - Enforces minimum cash buffer ($2000 default)
    - Caches account data to reduce API calls

    Example:
        >>> cash_mgr = CashManager(alpaca_client)
        >>> available = cash_mgr.get_available_cash()
        >>> is_valid, reason = cash_mgr.validate_cash_for_order("SPY", 10, 450.0)
    """

    def __init__(
        self,
        alpaca_client: "AlpacaClient",
        config_path: Optional[str] = None
    ):
        """
        Initialize cash manager.

        Args:
            alpaca_client: Alpaca client for account/order data
            config_path: Path to cash_management.yaml config file
        """
        self.alpaca = alpaca_client

        # Load configuration
        if config_path is None:
            config_path = "config/cash_management.yaml"

        self.config = self._load_config(config_path)

        # Cache settings
        self._cache_ttl = 30.0  # Cache for 30 seconds
        self._last_cache_time = 0.0
        self._cached_account = None

        logger.info(
            "CashManager initialized",
            extra={
                "min_reserve": self.config['cash_buffer']['minimum_reserve'],
                "max_usage_pct": self.config['cash_buffer']['max_usage_per_order_pct'],
                "allow_margin": self.config['margin']['allow_buying_power']
            }
        )

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        try:
            path = Path(config_path)
            if not path.exists():
                logger.warning(f"Config file not found: {config_path}, using defaults")
                return self._get_default_config()

            with open(path, 'r') as f:
                config = yaml.safe_load(f)

            logger.info(f"Loaded cash management config from {config_path}")
            return config

        except Exception as e:
            logger.error(f"Failed to load config: {e}, using defaults")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'cash_buffer': {
                'minimum_reserve': 2000.0,
                'max_usage_per_order_pct': 0.95
            },
            'order_cancellation': {
                'max_wait_seconds': 10.0,
                'max_retries': 3,
                'retry_interval': 0.5
            },
            'margin': {
                'allow_buying_power': False
            },
            'logging': {
                'log_cash_status_every_cycle': True,
                'log_skipped_orders': True,
                'log_level': 'INFO'
            }
        }

    def _get_account_cached(self) -> Dict[str, Any]:
        """
        Get account data with caching to reduce API calls.

        Returns:
            Account dict with cash, buying_power, equity, etc.
        """
        current_time = time.time()

        # Return cached data if still fresh
        if (self._cached_account is not None and
            (current_time - self._last_cache_time) < self._cache_ttl):
            return self._cached_account

        # Fetch fresh data
        try:
            account = self.alpaca.get_account()
            self._cached_account = account
            self._last_cache_time = current_time
            return account

        except Exception as e:
            logger.error(f"Failed to get account data: {e}")
            # If we have cached data, use it even if stale
            if self._cached_account is not None:
                logger.warning("Using stale cached account data due to API error")
                return self._cached_account
            raise CashManagerError(f"Cannot get account data: {e}")

    def get_available_cash(self) -> float:
        """
        Calculate available cash for trading.

        Formula:
            available_cash = account.cash - locked_in_pending_orders - minimum_reserve

        CRITICAL: Never uses buying_power (margin). Only uses actual cash.

        Returns:
            Float: Available cash in dollars

        Raises:
            CashManagerError: If unable to calculate cash
        """
        try:
            # Get account cash (NOT buying_power)
            account = self._get_account_cached()
            total_cash = float(account.get('cash', 0.0))

            # Calculate cash locked in pending buy orders
            locked_cash = self._calculate_locked_cash()

            # Apply minimum reserve buffer
            min_reserve = self.config['cash_buffer']['minimum_reserve']

            # Available = total - locked - buffer
            available = total_cash - locked_cash - min_reserve

            # Never negative
            available = max(0.0, available)

            logger.debug(
                "Calculated available cash",
                extra={
                    "total_cash": total_cash,
                    "locked_cash": locked_cash,
                    "min_reserve": min_reserve,
                    "available_cash": available
                }
            )

            return available

        except Exception as e:
            logger.error(f"Error calculating available cash: {e}")
            raise CashManagerError(f"Cannot calculate available cash: {e}")

    def _calculate_locked_cash(self) -> float:
        """
        Calculate cash locked in pending buy orders.

        Returns:
            Float: Total cash locked in pending orders
        """
        try:
            # Get all open orders
            open_orders = self.alpaca.get_orders()

            locked = 0.0
            for order in open_orders:
                # Only count buy orders
                if order.get('side') != 'buy':
                    continue

                # Calculate order value
                qty = float(order.get('qty', 0))

                # Use limit_price if available, otherwise use filled_avg_price or 0
                price = float(
                    order.get('limit_price') or
                    order.get('filled_avg_price') or
                    0.0
                )

                order_value = qty * price
                locked += order_value

            return locked

        except Exception as e:
            logger.warning(f"Error calculating locked cash: {e}, assuming 0")
            return 0.0

    def get_pending_order_cash_requirements(
        self,
        symbol: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Get cash requirements broken down by symbol.

        Args:
            symbol: Optional symbol to filter by

        Returns:
            Dict mapping symbol to locked cash, e.g., {'SPY': 1500.0, 'QQQ': 2300.0}
        """
        try:
            open_orders = self.alpaca.get_orders()

            requirements = {}
            for order in open_orders:
                # Only count buy orders
                if order.get('side') != 'buy':
                    continue

                order_symbol = order.get('symbol')

                # Filter by symbol if specified
                if symbol is not None and order_symbol != symbol:
                    continue

                # Calculate order value
                qty = float(order.get('qty', 0))
                price = float(
                    order.get('limit_price') or
                    order.get('filled_avg_price') or
                    0.0
                )
                order_value = qty * price

                # Add to symbol total
                if order_symbol in requirements:
                    requirements[order_symbol] += order_value
                else:
                    requirements[order_symbol] = order_value

            return requirements

        except Exception as e:
            logger.error(f"Error getting pending order requirements: {e}")
            return {}

    def validate_cash_for_order(
        self,
        symbol: str,
        qty: int,
        limit_price: float
    ) -> tuple[bool, Optional[str]]:
        """
        Validate if sufficient cash exists for a buy order.

        Checks:
        1. Order cost <= available cash
        2. Order doesn't exceed max_usage_per_order_pct of available
        3. Account has minimum reserve after order

        Args:
            symbol: Stock symbol
            qty: Number of shares
            limit_price: Limit price per share

        Returns:
            Tuple of (is_valid: bool, reason: Optional[str])
            - (True, None) if order is valid
            - (False, reason) if order should be rejected
        """
        try:
            # Calculate order cost
            order_cost = qty * limit_price

            # Get available cash
            available_cash = self.get_available_cash()

            # Check if sufficient cash
            if order_cost > available_cash:
                reason = (
                    f"Insufficient cash for {symbol}: "
                    f"need ${order_cost:,.2f}, have ${available_cash:,.2f}"
                )
                logger.warning(reason)
                return False, reason

            # Check max usage per order
            max_usage_pct = self.config['cash_buffer']['max_usage_per_order_pct']
            max_order_cost = available_cash * max_usage_pct

            if order_cost > max_order_cost:
                reason = (
                    f"Order exceeds max usage for {symbol}: "
                    f"${order_cost:,.2f} > ${max_order_cost:,.2f} "
                    f"({max_usage_pct*100:.0f}% of available)"
                )
                logger.warning(reason)
                return False, reason

            # Validation passed
            logger.debug(
                f"Cash validation passed for {symbol}: "
                f"${order_cost:,.2f} of ${available_cash:,.2f} available"
            )
            return True, None

        except Exception as e:
            logger.error(f"Error validating cash for {symbol}: {e}")
            # Fail safe: reject order if we can't validate
            return False, f"Cash validation error: {e}"

    def get_cash_status(self) -> Dict[str, Any]:
        """
        Get detailed cash status for monitoring/debugging.

        Returns:
            Dict with:
            - total_cash: Total cash in account
            - locked_cash: Cash locked in pending orders
            - minimum_reserve: Configured minimum buffer
            - available_cash: Cash available for new orders
            - pending_buy_orders: Count of pending buy orders
            - details_by_symbol: Per-symbol breakdown
        """
        try:
            account = self._get_account_cached()
            total_cash = float(account.get('cash', 0.0))

            locked_cash = self._calculate_locked_cash()
            min_reserve = self.config['cash_buffer']['minimum_reserve']
            available_cash = max(0.0, total_cash - locked_cash - min_reserve)

            # Get pending order details
            requirements = self.get_pending_order_cash_requirements()
            pending_count = len(requirements)

            return {
                'total_cash': total_cash,
                'locked_cash': locked_cash,
                'minimum_reserve': min_reserve,
                'available_cash': available_cash,
                'pending_buy_orders': pending_count,
                'details_by_symbol': requirements,
                'timestamp': time.time()
            }

        except Exception as e:
            logger.error(f"Error getting cash status: {e}")
            return {
                'error': str(e),
                'timestamp': time.time()
            }

    def invalidate_cache(self) -> None:
        """Force refresh of cached account data on next access."""
        self._last_cache_time = 0.0
        self._cached_account = None
        logger.debug("Cash manager cache invalidated")
