"""
Circuit breaker implementation for trading risk management.

Circuit breakers automatically halt trading when predefined risk
thresholds are breached. This is a critical safety mechanism.

Thresholds (from .copilot.md):
- Daily loss limit: -2%
- Weekly loss limit: -5%
- Maximum drawdown halt: -15%
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# Hard limits from .copilot.md
DAILY_LOSS_LIMIT = -0.02      # -2% daily
WEEKLY_LOSS_LIMIT = -0.05     # -5% weekly
MAX_DRAWDOWN_LIMIT = -0.15    # -15% from peak


class CircuitBreakerType(Enum):
    """Types of circuit breakers."""
    DAILY_LOSS = "daily_loss"
    WEEKLY_LOSS = "weekly_loss"
    MAX_DRAWDOWN = "max_drawdown"
    MANUAL = "manual"


class TradingHaltReason(Enum):
    """Reasons for trading halt."""
    DAILY_LOSS_EXCEEDED = "Daily loss limit exceeded"
    WEEKLY_LOSS_EXCEEDED = "Weekly loss limit exceeded"
    MAX_DRAWDOWN_EXCEEDED = "Maximum drawdown limit exceeded"
    MANUAL_HALT = "Manual trading halt"
    SYSTEM_ERROR = "System error triggered halt"


@dataclass
class CircuitBreakerState:
    """Current state of circuit breakers."""
    is_halted: bool = False
    halt_reason: Optional[TradingHaltReason] = None
    halt_time: Optional[datetime] = None
    resume_time: Optional[datetime] = None
    breaker_type: Optional[CircuitBreakerType] = None

    # Current metrics
    daily_pnl: float = 0.0
    daily_return: float = 0.0
    weekly_pnl: float = 0.0
    weekly_return: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    drawdown: float = 0.0

    # History
    halt_history: List[Dict[str, Any]] = field(default_factory=list)


class CircuitBreaker:
    """
    Trading circuit breaker system.

    Monitors portfolio performance and halts trading when risk
    thresholds are breached.

    Attributes:
        daily_loss_limit: Maximum daily loss before halt (default: -2%)
        weekly_loss_limit: Maximum weekly loss before halt (default: -5%)
        max_drawdown_limit: Maximum drawdown before halt (default: -15%)
    """

    def __init__(
        self,
        daily_loss_limit: float = DAILY_LOSS_LIMIT,
        weekly_loss_limit: float = WEEKLY_LOSS_LIMIT,
        max_drawdown_limit: float = MAX_DRAWDOWN_LIMIT,
        initial_equity: float = 0.0
    ):
        """
        Initialize circuit breaker.

        Args:
            daily_loss_limit: Daily loss threshold (negative decimal)
            weekly_loss_limit: Weekly loss threshold (negative decimal)
            max_drawdown_limit: Drawdown threshold (negative decimal)
            initial_equity: Starting portfolio value
        """
        self.daily_loss_limit = daily_loss_limit
        self.weekly_loss_limit = weekly_loss_limit
        self.max_drawdown_limit = max_drawdown_limit

        self.state = CircuitBreakerState(
            peak_equity=initial_equity,
            current_equity=initial_equity
        )

        # Track daily/weekly starting values
        self._day_start_equity = initial_equity
        self._week_start_equity = initial_equity
        self._last_update_date: Optional[date] = None

        logger.info(
            "CircuitBreaker initialized",
            extra={
                "daily_limit": daily_loss_limit,
                "weekly_limit": weekly_loss_limit,
                "max_drawdown_limit": max_drawdown_limit
            }
        )

    def update(self, current_equity: float, update_date: Optional[date] = None) -> None:
        """
        Update circuit breaker with current portfolio value.

        Call this after each trade or at least daily.

        Args:
            current_equity: Current total portfolio value
            update_date: Date of update (default: today)
        """
        update_date = update_date or date.today()

        # Handle day/week rollover
        if self._last_update_date:
            # New day
            if update_date > self._last_update_date:
                self._day_start_equity = self.state.current_equity

                # New week (Monday)
                if update_date.weekday() == 0:
                    self._week_start_equity = self.state.current_equity

                # Reset daily halt at new day
                if (self.state.is_halted and
                    self.state.breaker_type == CircuitBreakerType.DAILY_LOSS and
                    update_date > self.state.halt_time.date()):
                    self._reset_halt("New trading day")

        self._last_update_date = update_date
        self.state.current_equity = current_equity

        # Update peak
        if current_equity > self.state.peak_equity:
            self.state.peak_equity = current_equity

        # Calculate metrics
        self._update_metrics()

        # Check breakers
        self._check_breakers()

    def _update_metrics(self) -> None:
        """Update all risk metrics."""
        equity = self.state.current_equity

        # Daily P&L
        if self._day_start_equity > 0:
            self.state.daily_pnl = equity - self._day_start_equity
            self.state.daily_return = self.state.daily_pnl / self._day_start_equity
        else:
            self.state.daily_pnl = 0.0
            self.state.daily_return = 0.0

        # Weekly P&L
        if self._week_start_equity > 0:
            self.state.weekly_pnl = equity - self._week_start_equity
            self.state.weekly_return = self.state.weekly_pnl / self._week_start_equity
        else:
            self.state.weekly_pnl = 0.0
            self.state.weekly_return = 0.0

        # Drawdown
        if self.state.peak_equity > 0:
            self.state.drawdown = (equity - self.state.peak_equity) / self.state.peak_equity
        else:
            self.state.drawdown = 0.0

    def _check_breakers(self) -> None:
        """Check all circuit breaker conditions."""
        if self.state.is_halted:
            return  # Already halted

        # Daily loss check
        if self.state.daily_return < self.daily_loss_limit:
            self._trigger_halt(
                CircuitBreakerType.DAILY_LOSS,
                TradingHaltReason.DAILY_LOSS_EXCEEDED,
                f"Daily return: {self.state.daily_return:.2%} < {self.daily_loss_limit:.2%}"
            )
            return

        # Weekly loss check
        if self.state.weekly_return < self.weekly_loss_limit:
            self._trigger_halt(
                CircuitBreakerType.WEEKLY_LOSS,
                TradingHaltReason.WEEKLY_LOSS_EXCEEDED,
                f"Weekly return: {self.state.weekly_return:.2%} < {self.weekly_loss_limit:.2%}"
            )
            return

        # Drawdown check
        if self.state.drawdown < self.max_drawdown_limit:
            self._trigger_halt(
                CircuitBreakerType.MAX_DRAWDOWN,
                TradingHaltReason.MAX_DRAWDOWN_EXCEEDED,
                f"Drawdown: {self.state.drawdown:.2%} < {self.max_drawdown_limit:.2%}"
            )
            return

    def _trigger_halt(
        self,
        breaker_type: CircuitBreakerType,
        reason: TradingHaltReason,
        details: str
    ) -> None:
        """Trigger a trading halt."""
        now = datetime.now()

        self.state.is_halted = True
        self.state.breaker_type = breaker_type
        self.state.halt_reason = reason
        self.state.halt_time = now

        # Set resume time based on breaker type
        if breaker_type == CircuitBreakerType.DAILY_LOSS:
            # Resume next trading day
            self.state.resume_time = self._next_trading_day(now)
        elif breaker_type == CircuitBreakerType.WEEKLY_LOSS:
            # Resume next week
            days_until_monday = (7 - now.weekday()) % 7 or 7
            self.state.resume_time = datetime.combine(
                now.date() + timedelta(days=days_until_monday),
                datetime.min.time()
            ).replace(hour=9, minute=30)
        else:
            # Manual review required for max drawdown
            self.state.resume_time = None

        # Record in history
        self.state.halt_history.append({
            "type": breaker_type.value,
            "reason": reason.value,
            "details": details,
            "halt_time": now.isoformat(),
            "equity": self.state.current_equity,
            "daily_return": self.state.daily_return,
            "weekly_return": self.state.weekly_return,
            "drawdown": self.state.drawdown
        })

        logger.critical(
            "CIRCUIT BREAKER TRIGGERED",
            extra={
                "breaker_type": breaker_type.value,
                "reason": reason.value,
                "details": details,
                "equity": self.state.current_equity,
                "resume_time": self.state.resume_time
            }
        )

    def _next_trading_day(self, dt: datetime) -> datetime:
        """Get next trading day (skip weekends)."""
        next_day = dt.date() + timedelta(days=1)
        while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
            next_day += timedelta(days=1)
        return datetime.combine(next_day, datetime.min.time()).replace(hour=9, minute=30)

    def _reset_halt(self, reason: str) -> None:
        """Reset halt state."""
        logger.info(f"Trading halt reset: {reason}")
        self.state.is_halted = False
        self.state.halt_reason = None
        self.state.halt_time = None
        self.state.resume_time = None
        self.state.breaker_type = None

    def manual_halt(self, reason: str = "Manual halt requested") -> None:
        """Manually halt trading."""
        self._trigger_halt(
            CircuitBreakerType.MANUAL,
            TradingHaltReason.MANUAL_HALT,
            reason
        )

    def manual_resume(self, confirmation: str) -> bool:
        """
        Manually resume trading after halt.

        Args:
            confirmation: Must be "CONFIRM_RESUME" to proceed

        Returns:
            True if resumed, False if confirmation invalid
        """
        if confirmation != "CONFIRM_RESUME":
            logger.warning("Invalid resume confirmation")
            return False

        self._reset_halt("Manual resume")
        return True

    def can_trade(self) -> tuple[bool, Optional[str]]:
        """
        Check if trading is currently allowed.

        Returns:
            Tuple of (can_trade, reason_if_not)
        """
        if not self.state.is_halted:
            return True, None

        return False, self.state.halt_reason.value if self.state.halt_reason else "Unknown"

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get current risk metrics summary."""
        can_trade, halt_reason = self.can_trade()

        return {
            "can_trade": can_trade,
            "halt_reason": halt_reason,
            "daily_return": f"{self.state.daily_return:.2%}",
            "daily_limit": f"{self.daily_loss_limit:.2%}",
            "daily_headroom": f"{self.state.daily_return - self.daily_loss_limit:.2%}",
            "weekly_return": f"{self.state.weekly_return:.2%}",
            "weekly_limit": f"{self.weekly_loss_limit:.2%}",
            "weekly_headroom": f"{self.state.weekly_return - self.weekly_loss_limit:.2%}",
            "drawdown": f"{self.state.drawdown:.2%}",
            "drawdown_limit": f"{self.max_drawdown_limit:.2%}",
            "drawdown_headroom": f"{self.state.drawdown - self.max_drawdown_limit:.2%}",
            "current_equity": f"${self.state.current_equity:,.2f}",
            "peak_equity": f"${self.state.peak_equity:,.2f}",
        }


class RiskManager:
    """
    Unified risk management interface.

    Combines position sizing and circuit breakers into a single
    interface for order validation.
    """

    def __init__(
        self,
        position_sizer: "PositionSizer",
        circuit_breaker: CircuitBreaker
    ):
        """
        Initialize risk manager.

        Args:
            position_sizer: Position sizing instance
            circuit_breaker: Circuit breaker instance
        """
        from risk.position_sizing import PositionSizer
        self.position_sizer = position_sizer
        self.circuit_breaker = circuit_breaker

    def validate_order(
        self,
        symbol: str,
        order_value: float,
        portfolio_value: float,
        current_positions: Dict[str, float],
        sector_map: Optional[Dict[str, str]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate an order against all risk checks.

        Args:
            symbol: Symbol to trade
            order_value: Proposed order value
            portfolio_value: Total portfolio value
            current_positions: Current positions
            sector_map: Optional sector mapping

        Returns:
            Tuple of (is_valid, rejection_reason)
        """
        # Check circuit breakers first
        can_trade, halt_reason = self.circuit_breaker.can_trade()
        if not can_trade:
            return False, f"Trading halted: {halt_reason}"

        # Check position limits
        return self.position_sizer.validate_order(
            symbol, order_value, portfolio_value, current_positions, sector_map
        )

    def get_violation_reason(self) -> str:
        """Get the most recent validation failure reason."""
        can_trade, reason = self.circuit_breaker.can_trade()
        if not can_trade:
            return reason or "Unknown circuit breaker violation"
        return "Unknown violation"
