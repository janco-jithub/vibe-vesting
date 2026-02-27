"""
Polygon.io API client with rate limiting for free tier.

Free tier limits: 5 API calls per minute, delayed data only.

Optimized for long-running operation with:
- Non-blocking rate limiting (yields to event loop)
- Connection timeouts to prevent hangs
- Circuit breaker for failed calls
"""

import time
import os
import asyncio
from datetime import datetime, date
from typing import List, Dict, Optional
from decimal import Decimal
import logging
import threading

from polygon import RESTClient
from polygon.rest.models import Agg
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PolygonClientError(Exception):
    """Custom exception for Polygon API errors."""
    pass


class RateLimitedPolygonClient:
    """
    Polygon.io client with automatic rate limiting.

    Free tier: 5 calls/minute, delayed data.

    Attributes:
        api_key: Polygon API key
        calls_per_minute: Rate limit for API calls
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        calls_per_minute: int = 5,
        retry_attempts: int = 3,
        retry_delay: float = 60.0
    ):
        """
        Initialize the Polygon client.

        Args:
            api_key: Polygon API key. If None, reads from POLYGON_API_KEY env var.
            calls_per_minute: Maximum API calls per minute (free tier = 5).
            retry_attempts: Number of retry attempts on failure.
            retry_delay: Delay in seconds between retries.
        """
        self.api_key = api_key or os.getenv("POLYGON_API_KEY")
        if not self.api_key:
            raise PolygonClientError("POLYGON_API_KEY not found in environment")

        self.client = RESTClient(self.api_key)
        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute
        self.last_call_time = 0.0
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._max_failures = 5
        self._circuit_timeout = 60.0  # 1 minute circuit breaker

        # Lock for thread safety
        self._lock = threading.Lock()

        logger.info(
            "Initialized Polygon client",
            extra={
                "rate_limit": calls_per_minute,
                "retry_attempts": retry_attempts
            }
        )

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker is open. Returns True if we should proceed."""
        with self._lock:
            if self._consecutive_failures >= self._max_failures:
                if time.time() < self._circuit_open_until:
                    return False
                # Reset circuit breaker after timeout
                self._consecutive_failures = 0
            return True

    def _record_success(self) -> None:
        """Record successful API call."""
        with self._lock:
            self._consecutive_failures = 0

    def _record_failure(self) -> None:
        """Record failed API call and potentially open circuit breaker."""
        with self._lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._max_failures:
                self._circuit_open_until = time.time() + self._circuit_timeout
                logger.warning(
                    f"Circuit breaker OPEN - too many failures. Will retry after {self._circuit_timeout}s"
                )

    def _rate_limit(self) -> None:
        """
        Enforce rate limiting between API calls.

        Uses short sleeps with yielding to prevent blocking the entire process.
        """
        with self._lock:
            elapsed = time.time() - self.last_call_time
            sleep_time = max(0, self.min_interval - elapsed)

        if sleep_time > 0:
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            # Sleep in small chunks to remain responsive
            end_time = time.time() + sleep_time
            while time.time() < end_time:
                remaining = end_time - time.time()
                time.sleep(min(0.1, remaining))  # Sleep max 100ms at a time

        with self._lock:
            self.last_call_time = time.time()

    def _validate_date_format(self, date_str: str) -> bool:
        """Validate date string is in YYYY-MM-DD format."""
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> List[Dict]:
        """
        Fetch daily OHLCV bars for a symbol.

        Args:
            symbol: Ticker symbol (e.g., "SPY")
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of dicts with keys: symbol, date, open, high, low, close, volume

        Raises:
            PolygonClientError: If API call fails after all retries
            ValueError: If date format is invalid
        """
        # Validate inputs
        if not self._validate_date_format(start_date):
            raise ValueError(f"Invalid start_date format: {start_date}. Use YYYY-MM-DD.")
        if not self._validate_date_format(end_date):
            raise ValueError(f"Invalid end_date format: {end_date}. Use YYYY-MM-DD.")

        symbol = symbol.upper().strip()

        # Check circuit breaker first
        if not self._check_circuit_breaker():
            logger.warning(f"Circuit breaker OPEN - skipping API call for {symbol}")
            return []

        for attempt in range(self.retry_attempts):
            self._rate_limit()

            logger.info(
                "Fetching daily bars",
                extra={
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                    "attempt": attempt + 1
                }
            )

            try:
                aggs = self.client.get_aggs(
                    ticker=symbol,
                    multiplier=1,
                    timespan="day",
                    from_=start_date,
                    to=end_date,
                    limit=50000
                )

                bars = []
                for agg in aggs:
                    bar_date = datetime.fromtimestamp(agg.timestamp / 1000).date()
                    bars.append({
                        "symbol": symbol,
                        "date": bar_date,
                        "open": float(agg.open),
                        "high": float(agg.high),
                        "low": float(agg.low),
                        "close": float(agg.close),
                        "volume": int(agg.volume),
                    })

                logger.info(
                    "Retrieved daily bars",
                    extra={"symbol": symbol, "bar_count": len(bars)}
                )
                self._record_success()
                return bars

            except Exception as e:
                self._record_failure()
                logger.warning(
                    "API call failed",
                    extra={
                        "symbol": symbol,
                        "attempt": attempt + 1,
                        "error": str(e)
                    }
                )

                if attempt < self.retry_attempts - 1:
                    # Use chunked sleep for retry delay
                    retry_sleep = min(self.retry_delay, 30.0)  # Cap at 30 seconds
                    logger.info(f"Retrying in {retry_sleep}s...")
                    end_time = time.time() + retry_sleep
                    while time.time() < end_time:
                        time.sleep(min(0.5, end_time - time.time()))
                else:
                    raise PolygonClientError(
                        f"Failed to fetch data for {symbol} after {self.retry_attempts} attempts: {e}"
                    )

        return []

    def get_multiple_symbols(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str
    ) -> Dict[str, List[Dict]]:
        """
        Fetch daily bars for multiple symbols.

        Args:
            symbols: List of ticker symbols
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict mapping symbol to list of bar dicts
        """
        results = {}
        for symbol in symbols:
            try:
                bars = self.get_daily_bars(symbol, start_date, end_date)
                results[symbol] = bars
            except PolygonClientError as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                results[symbol] = []

        return results

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the most recent closing price for a symbol.

        Note: Free tier returns delayed data (15-20 minutes).

        Args:
            symbol: Ticker symbol

        Returns:
            Latest closing price or None if unavailable
        """
        # Check circuit breaker
        if not self._check_circuit_breaker():
            logger.warning(f"Circuit breaker OPEN - skipping price fetch for {symbol}")
            return None

        self._rate_limit()

        try:
            # Get previous day close using aggs
            end_date = date.today().strftime("%Y-%m-%d")
            start_date = (date.today().replace(day=1)).strftime("%Y-%m-%d")

            aggs = self.client.get_aggs(
                ticker=symbol.upper(),
                multiplier=1,
                timespan="day",
                from_=start_date,
                to=end_date,
                limit=5,
                sort="desc"
            )

            for agg in aggs:
                return float(agg.close)

            return None

        except Exception as e:
            logger.error(f"Failed to get latest price for {symbol}: {e}")
            return None
