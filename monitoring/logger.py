"""
Structured logging configuration for trading system.

Provides consistent, parseable log output for all trading activity.
"""

import logging
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

import structlog


def setup_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    json_format: bool = False
) -> None:
    """
    Configure structured logging for the trading system.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_dir: Directory for log files
        json_format: Use JSON format for logs (good for parsing)
    """
    # Create log directory
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Configure structlog
    processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level))
    console_handler.setFormatter(logging.Formatter(log_format))

    # File handler for all logs
    file_handler = logging.FileHandler(f"{log_dir}/trading.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))

    # File handler for trades only
    trade_handler = logging.FileHandler(f"{log_dir}/trades.log")
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(logging.Formatter(log_format))
    trade_handler.addFilter(lambda record: "trade" in record.getMessage().lower() or
                           "order" in record.getMessage().lower())

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # Add trade handler to execution logger
    execution_logger = logging.getLogger("execution")
    execution_logger.addHandler(trade_handler)


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a structured logger instance."""
    return structlog.get_logger(name)


class TradingLogger:
    """
    Specialized logger for trading events.

    Provides consistent logging for:
    - Order events
    - Trade executions
    - Risk events
    - Strategy signals
    """

    def __init__(self, name: str = "trading"):
        self.logger = get_logger(name)

    def log_order(
        self,
        event: str,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        **kwargs
    ) -> None:
        """Log an order event."""
        self.logger.info(
            event,
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            **kwargs
        )

    def log_trade(
        self,
        symbol: str,
        side: str,
        quantity: int,
        price: float,
        order_id: Optional[str] = None,
        **kwargs
    ) -> None:
        """Log a trade execution."""
        self.logger.info(
            "trade_executed",
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            value=quantity * price,
            order_id=order_id,
            **kwargs
        )

    def log_signal(
        self,
        strategy: str,
        symbol: str,
        signal_type: str,
        **kwargs
    ) -> None:
        """Log a strategy signal."""
        self.logger.info(
            "signal_generated",
            strategy=strategy,
            symbol=symbol,
            signal_type=signal_type,
            **kwargs
        )

    def log_risk_event(
        self,
        event: str,
        **kwargs
    ) -> None:
        """Log a risk management event."""
        self.logger.warning(
            event,
            category="risk",
            **kwargs
        )

    def log_circuit_breaker(
        self,
        event: str,
        breaker_type: str,
        **kwargs
    ) -> None:
        """Log a circuit breaker event."""
        self.logger.critical(
            event,
            category="circuit_breaker",
            breaker_type=breaker_type,
            **kwargs
        )


def log_performance_snapshot(
    equity: float,
    daily_return: float,
    drawdown: float,
    positions: Dict[str, Any],
    log_file: str = "logs/performance.jsonl"
) -> None:
    """
    Log a performance snapshot to JSONL file.

    Args:
        equity: Current portfolio equity
        daily_return: Daily return percentage
        drawdown: Current drawdown from peak
        positions: Current positions dict
        log_file: Path to log file
    """
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "equity": equity,
        "daily_return": daily_return,
        "drawdown": drawdown,
        "positions": positions
    }

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    with open(log_file, "a") as f:
        f.write(json.dumps(snapshot) + "\n")
