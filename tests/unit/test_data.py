"""
Unit tests for data layer components.
"""

import pytest
import tempfile
import os
from datetime import date, datetime

import pandas as pd
import numpy as np

from data.storage import TradingDatabase, DatabaseError


class TestTradingDatabase:
    """Tests for TradingDatabase."""

    @pytest.fixture
    def db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        db = TradingDatabase(db_path)
        yield db

        # Cleanup
        os.unlink(db_path)

    @pytest.fixture
    def sample_bars(self):
        """Create sample bar data."""
        return [
            {
                "symbol": "SPY",
                "date": date(2024, 1, 2),
                "open": 470.0,
                "high": 475.0,
                "low": 468.0,
                "close": 473.0,
                "volume": 50000000
            },
            {
                "symbol": "SPY",
                "date": date(2024, 1, 3),
                "open": 473.0,
                "high": 478.0,
                "low": 472.0,
                "close": 476.0,
                "volume": 45000000
            },
            {
                "symbol": "QQQ",
                "date": date(2024, 1, 2),
                "open": 400.0,
                "high": 405.0,
                "low": 398.0,
                "close": 403.0,
                "volume": 30000000
            }
        ]

    def test_insert_and_get_daily_bars(self, db, sample_bars):
        # Insert
        count = db.insert_daily_bars(sample_bars)
        assert count == 3

        # Get
        df = db.get_daily_bars("SPY")
        assert len(df) == 2
        assert "close" in df.columns
        assert df["close"].iloc[0] == 473.0

    def test_get_daily_bars_date_filter(self, db, sample_bars):
        db.insert_daily_bars(sample_bars)

        df = db.get_daily_bars(
            "SPY",
            start_date=date(2024, 1, 3)
        )
        assert len(df) == 1
        assert df["close"].iloc[0] == 476.0

    def test_get_multiple_symbols(self, db, sample_bars):
        db.insert_daily_bars(sample_bars)

        data = db.get_multiple_symbols(["SPY", "QQQ"])
        assert "SPY" in data
        assert "QQQ" in data
        assert len(data["SPY"]) == 2
        assert len(data["QQQ"]) == 1

    def test_get_latest_date(self, db, sample_bars):
        db.insert_daily_bars(sample_bars)

        latest = db.get_latest_date("SPY")
        assert latest == date(2024, 1, 3)

    def test_get_latest_date_no_data(self, db):
        latest = db.get_latest_date("AAPL")
        assert latest is None

    def test_get_symbols(self, db, sample_bars):
        db.insert_daily_bars(sample_bars)

        symbols = db.get_symbols()
        assert "SPY" in symbols
        assert "QQQ" in symbols

    def test_insert_trade(self, db):
        trade_id = db.insert_trade(
            timestamp=datetime(2024, 1, 15, 10, 30),
            symbol="SPY",
            action="BUY",
            quantity=100,
            price=475.50,
            commission=0.0,
            order_id="ORD-001",
            strategy="dual_momentum"
        )

        assert trade_id == 1

        trades = db.get_trades()
        assert len(trades) == 1
        assert trades.iloc[0]["symbol"] == "SPY"
        assert trades.iloc[0]["quantity"] == 100

    def test_insert_trade_invalid_action(self, db):
        with pytest.raises(ValueError):
            db.insert_trade(
                timestamp=datetime.now(),
                symbol="SPY",
                action="INVALID",  # Should be BUY or SELL
                quantity=100,
                price=475.0
            )

    def test_get_trades_filtered(self, db):
        # Insert multiple trades
        db.insert_trade(datetime(2024, 1, 15, 10, 0), "SPY", "BUY", 100, 475.0)
        db.insert_trade(datetime(2024, 1, 16, 10, 0), "QQQ", "BUY", 50, 400.0)
        db.insert_trade(datetime(2024, 1, 17, 10, 0), "SPY", "SELL", 100, 480.0)

        # Filter by symbol
        spy_trades = db.get_trades(symbol="SPY")
        assert len(spy_trades) == 2

        # Filter by date
        recent_trades = db.get_trades(start_date=date(2024, 1, 16))
        assert len(recent_trades) == 2

    def test_save_and_get_portfolio_snapshot(self, db):
        db.save_portfolio_snapshot(
            snapshot_date=date(2024, 1, 15),
            equity=100500.0,
            cash=5000.0,
            positions={"SPY": 100, "QQQ": 50},
            daily_pnl=500.0,
            daily_return=0.005,
            drawdown=-0.02
        )

        history = db.get_portfolio_history()
        assert len(history) == 1
        assert history.iloc[0]["equity"] == 100500.0
        assert history.iloc[0]["positions"] == {"SPY": 100, "QQQ": 50}

    def test_save_signal(self, db):
        signal_id = db.save_signal(
            signal_date=date(2024, 1, 31),
            strategy="dual_momentum",
            symbol="SPY",
            signal_type="BUY",
            signal_value=0.15,
            metadata={"momentum": 0.15}
        )

        assert signal_id == 1

        signals = db.get_signals()
        assert len(signals) == 1
        assert signals.iloc[0]["symbol"] == "SPY"

    def test_validate_data(self, db, sample_bars):
        db.insert_daily_bars(sample_bars)

        validation = db.validate_data("SPY")
        assert validation["valid"] is True
        assert validation["row_count"] == 2

    def test_validate_data_no_data(self, db):
        validation = db.validate_data("UNKNOWN")
        assert validation["valid"] is False
        assert "No data found" in validation["error"]

    def test_upsert_bars(self, db, sample_bars):
        # Insert initial
        db.insert_daily_bars(sample_bars)

        # Update with new data
        updated_bars = [{
            "symbol": "SPY",
            "date": date(2024, 1, 2),
            "open": 470.0,
            "high": 480.0,  # Updated
            "low": 468.0,
            "close": 478.0,  # Updated
            "volume": 55000000
        }]
        db.insert_daily_bars(updated_bars)

        df = db.get_daily_bars("SPY")
        assert len(df) == 2  # Still 2 rows
        assert df.loc[df.index[0], "close"] == 478.0  # Updated value
