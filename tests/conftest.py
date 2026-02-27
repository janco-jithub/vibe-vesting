"""
Pytest configuration and shared fixtures.
"""

import pytest
import tempfile
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import numpy as np


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    os.unlink(f.name)


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    dates = pd.date_range("2020-01-01", "2024-12-31", freq="B")
    n = len(dates)

    def make_prices(trend=0.0001, volatility=0.01):
        returns = np.random.randn(n) * volatility + trend
        prices = 100 * np.exp(np.cumsum(returns))
        return prices

    def make_df(prices):
        return pd.DataFrame({
            "open": prices * (1 + np.random.randn(n) * 0.001),
            "high": prices * (1 + abs(np.random.randn(n)) * 0.01),
            "low": prices * (1 - abs(np.random.randn(n)) * 0.01),
            "close": prices,
            "volume": np.random.randint(1000000, 50000000, n)
        }, index=dates)

    return {
        "SPY": make_df(make_prices(0.0004, 0.01)),
        "QQQ": make_df(make_prices(0.0006, 0.012)),
        "TLT": make_df(make_prices(-0.0001, 0.008))
    }


@pytest.fixture
def mock_alpaca_client():
    """Create a mock Alpaca client for testing."""
    mock = MagicMock()

    # Mock account
    mock.get_account.return_value = {
        "account_number": "TEST123",
        "status": "ACTIVE",
        "equity": 100000.0,
        "cash": 50000.0,
        "buying_power": 100000.0,
        "portfolio_value": 50000.0,
        "currency": "USD",
        "pattern_day_trader": False,
        "trading_blocked": False,
        "account_blocked": False
    }

    # Mock positions
    mock.get_positions.return_value = {
        "SPY": {
            "symbol": "SPY",
            "qty": 100,
            "market_value": 47500.0,
            "cost_basis": 45000.0,
            "unrealized_pl": 2500.0,
            "unrealized_plpc": 0.0556,
            "current_price": 475.0,
            "avg_entry_price": 450.0,
            "side": "long"
        }
    }

    # Mock quote
    mock.get_latest_quote.return_value = {
        "symbol": "SPY",
        "bid_price": 474.50,
        "bid_size": 100,
        "ask_price": 475.50,
        "ask_size": 150,
        "timestamp": "2024-01-15T10:30:00Z"
    }

    mock.get_latest_price.return_value = 475.0

    # Mock order submission
    mock.submit_limit_order.return_value = {
        "id": "ORDER-123",
        "client_order_id": "CLIENT-123",
        "symbol": "SPY",
        "qty": "100",
        "filled_qty": "0",
        "side": "buy",
        "type": "limit",
        "status": "new",
        "limit_price": "476.00",
        "filled_avg_price": None,
        "created_at": "2024-01-15T10:30:00Z",
        "filled_at": None,
        "time_in_force": "day"
    }

    # Mock market status
    mock.is_market_open.return_value = True
    mock.get_market_hours.return_value = {
        "is_open": True,
        "next_open": None,
        "next_close": "2024-01-15T16:00:00-05:00"
    }

    return mock


@pytest.fixture
def mock_polygon_client():
    """Create a mock Polygon client for testing."""
    mock = MagicMock()

    def mock_get_daily_bars(symbol, start_date, end_date):
        dates = pd.date_range(start_date, end_date, freq="B")
        return [
            {
                "symbol": symbol,
                "date": d.date(),
                "open": 100.0 + i * 0.1,
                "high": 101.0 + i * 0.1,
                "low": 99.0 + i * 0.1,
                "close": 100.5 + i * 0.1,
                "volume": 1000000
            }
            for i, d in enumerate(dates)
        ]

    mock.get_daily_bars.side_effect = mock_get_daily_bars
    mock.get_latest_price.return_value = 475.0

    return mock
