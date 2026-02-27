"""
Alpaca Market Data API client for historical and real-time data.

Benefits over Polygon:
- 200 calls/minute (vs 5 for Polygon free tier) = 40x faster
- Same credentials as trading API
- Real-time quotes included
- No extra cost

Supports:
- Daily bars (OHLCV)
- Minute bars
- Real-time quotes
- Multi-symbol fetching
"""

import os
import time
import threading
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Any
from pathlib import Path
import logging

from requests.adapters import HTTPAdapter
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestBarRequest
)


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
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed
from dotenv import load_dotenv

# Load .env from project root explicitly
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / ".env")

logger = logging.getLogger(__name__)


class AlpacaDataClientError(Exception):
    """Custom exception for Alpaca Data API errors."""
    pass


class AlpacaDataClient:
    """
    Alpaca Market Data client with rate limiting.

    Free tier: 200 calls/minute (40x faster than Polygon!)

    Attributes:
        api_key: Alpaca API key
        secret_key: Alpaca secret key
        calls_per_minute: Rate limit (default: 200)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        calls_per_minute: int = 200,
        retry_attempts: int = 3,
        retry_delay: float = 5.0
    ):
        """
        Initialize Alpaca data client.

        Args:
            api_key: API key (defaults to env var)
            secret_key: Secret key (defaults to env var)
            calls_per_minute: Rate limit (default: 200 for free tier)
            retry_attempts: Number of retries on failure
            retry_delay: Seconds between retries
        """
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY")

        if not self.api_key or not self.secret_key:
            raise AlpacaDataClientError(
                "ALPACA_API_KEY and ALPACA_SECRET_KEY must be set"
            )

        self.calls_per_minute = calls_per_minute
        self.min_interval = 60.0 / calls_per_minute  # 0.3 seconds for 200/min
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay

        # Rate limiting state
        self.last_call_time = 0.0
        self._lock = threading.Lock()

        # Circuit breaker state
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._max_failures = 5
        self._circuit_timeout = 60.0

        # Initialize client
        self.client = StockHistoricalDataClient(
            api_key=self.api_key,
            secret_key=self.secret_key
        )

        # Set 30-second timeout to prevent indefinite hangs on network issues
        timeout_adapter = TimeoutHTTPAdapter(timeout=30)
        if hasattr(self.client, '_session'):
            self.client._session.mount('https://', timeout_adapter)
            self.client._session.mount('http://', timeout_adapter)

        logger.info(
            "Initialized Alpaca Data client",
            extra={"rate_limit": calls_per_minute}
        )

    def _rate_limit(self) -> None:
        """Enforce rate limiting between API calls."""
        with self._lock:
            elapsed = time.time() - self.last_call_time
            sleep_time = max(0, self.min_interval - elapsed)

        if sleep_time > 0:
            time.sleep(sleep_time)

        with self._lock:
            self.last_call_time = time.time()

    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows the call."""
        with self._lock:
            if self._consecutive_failures >= self._max_failures:
                if time.time() < self._circuit_open_until:
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
                logger.warning(f"Circuit breaker OPEN for {self._circuit_timeout}s")

    def get_daily_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """
        Fetch daily OHLCV bars for a symbol.

        Args:
            symbol: Ticker symbol (e.g., "SPY")
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            List of dicts with keys: symbol, date, open, high, low, close, volume
        """
        if not self._check_circuit_breaker():
            logger.warning(f"Circuit breaker OPEN - skipping {symbol}")
            return []

        symbol = symbol.upper().strip()

        for attempt in range(self.retry_attempts):
            self._rate_limit()

            logger.info(
                "Fetching daily bars",
                extra={"symbol": symbol, "start_date": start_date, "end_date": end_date}
            )

            try:
                request = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame.Day,
                    start=datetime.strptime(start_date, "%Y-%m-%d"),
                    end=datetime.strptime(end_date, "%Y-%m-%d"),
                    feed=DataFeed.IEX  # Use IEX for free tier
                )

                bars_response = self.client.get_stock_bars(request)

                bars = []
                for bar in bars_response.data.get(symbol, []):
                    bars.append({
                        "symbol": symbol,
                        "date": bar.timestamp.date(),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                    })

                logger.info(
                    "Retrieved daily bars",
                    extra={"symbol": symbol, "bar_count": len(bars)}
                )
                self._record_success()
                return bars

            except Exception as e:
                self._record_failure()
                logger.warning(f"API call failed for {symbol}: {e}")

                if attempt < self.retry_attempts - 1:
                    logger.info(f"Retrying in {self.retry_delay}s...")
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed to fetch {symbol} after {self.retry_attempts} attempts")

        return []

    def get_multiple_symbols(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str
    ) -> Dict[str, List[Dict]]:
        """
        Fetch daily bars for multiple symbols efficiently.

        Can batch up to 100 symbols in a single API call!

        Args:
            symbols: List of ticker symbols
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format

        Returns:
            Dict mapping symbol to list of bar dicts
        """
        if not self._check_circuit_breaker():
            logger.warning("Circuit breaker OPEN - skipping batch request")
            return {s: [] for s in symbols}

        self._rate_limit()

        # Alpaca allows batching up to 100 symbols
        symbols = [s.upper().strip() for s in symbols]

        logger.info(
            "Fetching bars for multiple symbols",
            extra={"symbol_count": len(symbols), "start_date": start_date}
        )

        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Day,
                start=datetime.strptime(start_date, "%Y-%m-%d"),
                end=datetime.strptime(end_date, "%Y-%m-%d"),
                feed=DataFeed.IEX  # Use IEX for free tier
            )

            bars_response = self.client.get_stock_bars(request)

            results = {}
            for symbol in symbols:
                results[symbol] = [
                    {
                        "symbol": symbol,
                        "date": bar.timestamp.date(),
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                    }
                    for bar in bars_response.data.get(symbol, [])
                ]

            success_count = sum(1 for v in results.values() if v)
            logger.info(f"Retrieved bars for {success_count}/{len(symbols)} symbols")

            self._record_success()
            return results

        except Exception as e:
            self._record_failure()
            logger.error(f"Batch request failed: {e}")
            return {s: [] for s in symbols}

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest price for a symbol.

        Uses real-time quote data from Alpaca.

        Args:
            symbol: Ticker symbol

        Returns:
            Latest mid price or None if unavailable
        """
        if not self._check_circuit_breaker():
            return None

        self._rate_limit()

        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
            quotes = self.client.get_stock_latest_quote(request)

            if symbol.upper() in quotes:
                quote = quotes[symbol.upper()]
                bid = float(quote.bid_price) if quote.bid_price else 0
                ask = float(quote.ask_price) if quote.ask_price else 0

                if bid and ask:
                    return (bid + ask) / 2
                return ask or bid

            return None

        except Exception as e:
            logger.error(f"Failed to get latest price for {symbol}: {e}")
            return None

    def get_latest_bar(self, symbol: str) -> Optional[Dict]:
        """
        Get the latest bar for a symbol.

        Args:
            symbol: Ticker symbol

        Returns:
            Latest bar dict or None
        """
        if not self._check_circuit_breaker():
            return None

        self._rate_limit()

        try:
            request = StockLatestBarRequest(symbol_or_symbols=symbol.upper())
            bars = self.client.get_stock_latest_bar(request)

            if symbol.upper() in bars:
                bar = bars[symbol.upper()]
                return {
                    "symbol": symbol.upper(),
                    "date": bar.timestamp.date(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get latest bar for {symbol}: {e}")
            return None

    def get_minute_bars(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        timeframe_minutes: int = 1
    ) -> List[Dict]:
        """
        Fetch minute-level bars for intraday analysis.

        Args:
            symbol: Ticker symbol
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            timeframe_minutes: Bar size in minutes (1, 5, 15, 30, 60)

        Returns:
            List of bar dicts
        """
        if not self._check_circuit_breaker():
            return []

        self._rate_limit()

        try:
            # Map minutes to TimeFrame
            if timeframe_minutes == 1:
                tf = TimeFrame.Minute
            elif timeframe_minutes == 5:
                tf = TimeFrame(5, TimeFrameUnit.Minute)
            elif timeframe_minutes == 15:
                tf = TimeFrame(15, TimeFrameUnit.Minute)
            elif timeframe_minutes == 30:
                tf = TimeFrame(30, TimeFrameUnit.Minute)
            elif timeframe_minutes == 60:
                tf = TimeFrame.Hour
            else:
                tf = TimeFrame.Minute

            request = StockBarsRequest(
                symbol_or_symbols=symbol.upper(),
                timeframe=tf,
                start=datetime.strptime(start_date, "%Y-%m-%d"),
                end=datetime.strptime(end_date, "%Y-%m-%d"),
                feed=DataFeed.IEX  # Use IEX for free tier
            )

            bars_response = self.client.get_stock_bars(request)

            bars = []
            for bar in bars_response.data.get(symbol.upper(), []):
                bars.append({
                    "symbol": symbol.upper(),
                    "timestamp": bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                })

            self._record_success()
            return bars

        except Exception as e:
            self._record_failure()
            logger.error(f"Failed to get minute bars for {symbol}: {e}")
            return []
