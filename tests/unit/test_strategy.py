"""
Unit tests for trading strategies.
"""

import pytest
from datetime import date
import pandas as pd
import numpy as np

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams
from strategies.dual_momentum import DualMomentumStrategy, MomentumScore


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self):
        signal = Signal(
            date=date(2024, 1, 15),
            symbol="SPY",
            signal_type=SignalType.BUY,
            strength=0.8
        )
        assert signal.symbol == "SPY"
        assert signal.signal_type == SignalType.BUY
        assert signal.strength == 0.8

    def test_signal_strength_validation(self):
        with pytest.raises(ValueError):
            Signal(
                date=date(2024, 1, 15),
                symbol="SPY",
                signal_type=SignalType.BUY,
                strength=1.5  # Invalid: > 1
            )

    def test_signal_default_strength(self):
        signal = Signal(
            date=date(2024, 1, 15),
            symbol="SPY",
            signal_type=SignalType.SELL
        )
        assert signal.strength == 1.0


class TestDualMomentumStrategy:
    """Tests for Dual Momentum strategy."""

    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data for testing."""
        dates = pd.date_range("2023-01-01", "2024-12-31", freq="B")
        n = len(dates)

        # Create trending data for SPY (uptrend)
        spy_prices = 100 * np.exp(np.cumsum(np.random.randn(n) * 0.01 + 0.0005))

        # Create trending data for QQQ (stronger uptrend)
        qqq_prices = 100 * np.exp(np.cumsum(np.random.randn(n) * 0.012 + 0.0008))

        # Create stable data for TLT (slight downtrend)
        tlt_prices = 100 * np.exp(np.cumsum(np.random.randn(n) * 0.005 - 0.0001))

        def make_df(prices):
            return pd.DataFrame({
                "open": prices * 0.999,
                "high": prices * 1.01,
                "low": prices * 0.99,
                "close": prices,
                "volume": np.random.randint(1000000, 10000000, n)
            }, index=dates)

        return {
            "SPY": make_df(spy_prices),
            "QQQ": make_df(qqq_prices),
            "TLT": make_df(tlt_prices)
        }

    @pytest.fixture
    def strategy(self):
        """Create strategy instance."""
        return DualMomentumStrategy()

    def test_initialization(self, strategy):
        assert strategy.name == "dual_momentum"
        assert "SPY" in strategy.universe
        assert "QQQ" in strategy.universe
        assert "TLT" in strategy.universe
        assert strategy.lookback_days == 252

    def test_custom_initialization(self):
        strategy = DualMomentumStrategy(
            lookback_days=200,
            risk_assets=["SPY", "IWM"],
            safe_haven="SHY"
        )
        assert strategy.lookback_days == 200
        assert strategy.risk_assets == ["SPY", "IWM"]
        assert strategy.safe_haven == "SHY"

    def test_validate_data_success(self, strategy, sample_data):
        assert strategy.validate_data(sample_data) is True

    def test_validate_data_missing_symbol(self, strategy, sample_data):
        del sample_data["TLT"]
        with pytest.raises(ValueError, match="Missing data"):
            strategy.validate_data(sample_data)

    def test_validate_data_empty_df(self, strategy, sample_data):
        sample_data["SPY"] = pd.DataFrame()
        with pytest.raises(ValueError, match="Empty DataFrame"):
            strategy.validate_data(sample_data)

    def test_generate_signals(self, strategy, sample_data):
        signals = strategy.generate_signals(sample_data)

        # Should generate signals
        assert len(signals) > 0

        # All signals should be valid
        for signal in signals:
            assert isinstance(signal, Signal)
            assert signal.symbol in strategy.universe
            assert signal.signal_type in SignalType

    def test_generate_signals_buy_signals(self, strategy, sample_data):
        signals = strategy.generate_signals(sample_data)
        buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]

        # Should have buy signals
        assert len(buy_signals) > 0

        # Buy signals should have metadata
        for signal in buy_signals:
            assert signal.metadata is not None
            assert "strategy" in signal.metadata
            assert "momentum_scores" in signal.metadata

    def test_calculate_position_size_buy(self, strategy):
        signal = Signal(
            date=date(2024, 1, 15),
            symbol="SPY",
            signal_type=SignalType.BUY,
            strength=1.0
        )

        portfolio_value = 100000
        current_positions = {}

        size = strategy.calculate_position_size(signal, portfolio_value, current_positions)

        # For dual momentum, should be 100% allocation
        assert size == portfolio_value

    def test_calculate_position_size_sell(self, strategy):
        signal = Signal(
            date=date(2024, 1, 15),
            symbol="SPY",
            signal_type=SignalType.SELL,
            strength=1.0
        )

        size = strategy.calculate_position_size(signal, 100000, {"SPY": 50000})

        # Sell should return 0
        assert size == 0.0

    def test_calculate_position_size_with_strength(self, strategy):
        signal = Signal(
            date=date(2024, 1, 15),
            symbol="SPY",
            signal_type=SignalType.BUY,
            strength=0.5
        )

        portfolio_value = 100000
        size = strategy.calculate_position_size(signal, portfolio_value, {})

        # Should scale with strength
        assert size == portfolio_value * 0.5

    def test_get_backtest_params(self, strategy):
        params = strategy.get_backtest_params()

        assert isinstance(params, BacktestParams)
        assert params.rebalance_frequency == "monthly"
        assert params.transaction_cost_bps == 10

    def test_get_required_history(self, strategy):
        required = strategy.get_required_history()

        # Should be at least lookback period
        assert required >= strategy.lookback_days

    def test_get_current_signal(self, strategy, sample_data):
        signal = strategy.get_current_signal(sample_data)

        if signal:
            assert signal.signal_type == SignalType.BUY
            assert signal.symbol in strategy.universe


class TestMomentumScore:
    """Tests for MomentumScore dataclass."""

    def test_momentum_score_creation(self):
        score = MomentumScore(
            symbol="SPY",
            return_12m=0.15,
            is_positive=True,
            rank=1
        )
        assert score.symbol == "SPY"
        assert score.return_12m == 0.15
        assert score.is_positive is True
        assert score.rank == 1

    def test_momentum_score_negative(self):
        score = MomentumScore(
            symbol="SPY",
            return_12m=-0.10,
            is_positive=False,
            rank=2
        )
        assert score.is_positive is False
