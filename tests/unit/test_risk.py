"""
Unit tests for risk management components.
"""

import pytest
from datetime import date, datetime

from risk.position_sizing import PositionSizer, PositionSizeResult
from risk.circuit_breakers import (
    CircuitBreaker,
    CircuitBreakerState,
    CircuitBreakerType,
    TradingHaltReason,
    RiskManager
)


class TestPositionSizer:
    """Tests for PositionSizer."""

    @pytest.fixture
    def sizer(self):
        return PositionSizer(
            max_position_pct=0.05,  # 5%
            max_sector_pct=0.25,    # 25%
            method="fixed"
        )

    def test_fixed_sizing(self, sizer):
        size = sizer.calculate_fixed_size(
            target_pct=0.10,  # 10% target
            portfolio_value=100000
        )
        # Should be capped at max_position_pct (5%)
        assert size == 5000  # 5% of 100000

    def test_fixed_sizing_below_max(self, sizer):
        size = sizer.calculate_fixed_size(
            target_pct=0.03,  # 3% target
            portfolio_value=100000
        )
        assert size == 3000  # 3% of 100000

    def test_kelly_sizing_positive_edge(self, sizer):
        sizer.method = "kelly"
        size = sizer.calculate_kelly_size(
            win_rate=0.60,
            avg_win=0.02,
            avg_loss=0.01,
            portfolio_value=100000
        )
        # Kelly = (2*0.6 - 0.4) / 2 = 0.4
        # Quarter Kelly = 0.1
        # Capped at 5%
        assert size == 5000

    def test_kelly_sizing_negative_edge(self, sizer):
        sizer.method = "kelly"
        size = sizer.calculate_kelly_size(
            win_rate=0.30,  # Low win rate
            avg_win=0.01,
            avg_loss=0.02,
            portfolio_value=100000
        )
        # Negative edge should return 0
        assert size == 0

    def test_calculate_position_size_result(self, sizer):
        result = sizer.calculate_position_size(
            symbol="SPY",
            portfolio_value=100000,
            current_price=450.0,
            current_positions={},
            target_pct=0.10
        )

        assert isinstance(result, PositionSizeResult)
        assert result.symbol == "SPY"
        assert result.target_value == 5000  # Capped at 5%
        assert result.target_shares == 11  # int(5000/450)
        assert result.method == "fixed"
        # limited_by is set when the limit actively constrains the target
        # Here target was 10000 but capped to 5000

    def test_sector_limit(self, sizer):
        # Use a sizer with higher position limit to test sector limit
        sector_sizer = PositionSizer(
            max_position_pct=0.15,  # 15% position limit
            max_sector_pct=0.25,    # 25% sector limit
            method="fixed"
        )
        sector_map = {
            "SPY": "equity",
            "QQQ": "equity",
            "TLT": "bonds"
        }
        current_positions = {
            "QQQ": 20000  # Already 20% in equity sector
        }

        result = sector_sizer.calculate_position_size(
            symbol="SPY",
            portfolio_value=100000,
            current_price=450.0,
            current_positions=current_positions,
            sector_map=sector_map,
            target_pct=0.10  # 10% target
        )

        # Max sector is 25%, already have 20%, so max additional is 5%
        # This should be limited by sector, not position
        assert result.target_value == 5000
        assert result.limited_by == "max_sector"

    def test_validate_order_pass(self, sizer):
        is_valid, reason = sizer.validate_order(
            symbol="SPY",
            order_value=3000,  # 3% of portfolio
            portfolio_value=100000,
            current_positions={}
        )
        assert is_valid is True
        assert reason is None

    def test_validate_order_exceeds_position_limit(self, sizer):
        is_valid, reason = sizer.validate_order(
            symbol="SPY",
            order_value=10000,  # 10% of portfolio
            portfolio_value=100000,
            current_positions={}
        )
        assert is_valid is False
        assert "max position size" in reason.lower()


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.fixture
    def breaker(self):
        return CircuitBreaker(
            daily_loss_limit=-0.02,
            weekly_loss_limit=-0.05,
            max_drawdown_limit=-0.15,
            initial_equity=100000
        )

    def test_initialization(self, breaker):
        assert breaker.state.is_halted is False
        assert breaker.state.peak_equity == 100000
        assert breaker.state.current_equity == 100000

    def test_update_equity_increase(self, breaker):
        breaker.update(105000)

        assert breaker.state.current_equity == 105000
        assert breaker.state.peak_equity == 105000
        assert breaker.state.is_halted is False

    def test_daily_loss_trigger(self, breaker):
        # Simulate 3% daily loss (exceeds 2% limit)
        breaker.update(97000)

        assert breaker.state.is_halted is True
        assert breaker.state.breaker_type == CircuitBreakerType.DAILY_LOSS
        assert breaker.state.halt_reason == TradingHaltReason.DAILY_LOSS_EXCEEDED

    def test_weekly_loss_trigger(self, breaker):
        # Simulate 6% weekly loss
        breaker.update(94000)

        # Should trigger both daily and weekly, but daily triggers first
        assert breaker.state.is_halted is True

    def test_max_drawdown_trigger(self, breaker):
        # Build up equity over multiple days to avoid daily loss trigger
        from datetime import timedelta

        # Start fresh with higher initial equity
        dd_breaker = CircuitBreaker(
            daily_loss_limit=-0.25,   # High daily limit so it doesn't trigger
            weekly_loss_limit=-0.25,  # High weekly limit
            max_drawdown_limit=-0.15, # 15% drawdown limit
            initial_equity=100000
        )

        # Reach peak
        dd_breaker.update(120000)
        assert dd_breaker.state.peak_equity == 120000

        # Now simulate drawdown that exceeds 15% but not daily limit
        dd_breaker.update(96000)  # 20% below peak

        assert dd_breaker.state.is_halted is True
        assert dd_breaker.state.breaker_type == CircuitBreakerType.MAX_DRAWDOWN

    def test_can_trade_when_not_halted(self, breaker):
        can_trade, reason = breaker.can_trade()
        assert can_trade is True
        assert reason is None

    def test_can_trade_when_halted(self, breaker):
        breaker.update(97000)  # Trigger daily loss

        can_trade, reason = breaker.can_trade()
        assert can_trade is False
        assert reason is not None

    def test_manual_halt(self, breaker):
        breaker.manual_halt("Testing")

        assert breaker.state.is_halted is True
        assert breaker.state.breaker_type == CircuitBreakerType.MANUAL

    def test_manual_resume_invalid(self, breaker):
        breaker.manual_halt("Testing")
        resumed = breaker.manual_resume("wrong_code")

        assert resumed is False
        assert breaker.state.is_halted is True

    def test_manual_resume_valid(self, breaker):
        breaker.manual_halt("Testing")
        resumed = breaker.manual_resume("CONFIRM_RESUME")

        assert resumed is True
        assert breaker.state.is_halted is False

    def test_risk_summary(self, breaker):
        summary = breaker.get_risk_summary()

        assert "can_trade" in summary
        assert "daily_return" in summary
        assert "drawdown" in summary
        assert summary["can_trade"] is True

    def test_halt_history(self, breaker):
        breaker.update(97000)  # Trigger halt

        assert len(breaker.state.halt_history) == 1
        assert breaker.state.halt_history[0]["type"] == "daily_loss"


class TestRiskManager:
    """Tests for unified RiskManager."""

    @pytest.fixture
    def risk_manager(self):
        sizer = PositionSizer(max_position_pct=0.05)
        breaker = CircuitBreaker(initial_equity=100000)
        return RiskManager(sizer, breaker)

    def test_validate_order_passes_all_checks(self, risk_manager):
        is_valid, reason = risk_manager.validate_order(
            symbol="SPY",
            order_value=3000,
            portfolio_value=100000,
            current_positions={}
        )
        assert is_valid is True

    def test_validate_order_fails_circuit_breaker(self, risk_manager):
        # Trigger circuit breaker
        risk_manager.circuit_breaker.update(97000)

        is_valid, reason = risk_manager.validate_order(
            symbol="SPY",
            order_value=3000,
            portfolio_value=97000,
            current_positions={}
        )
        assert is_valid is False
        assert "halted" in reason.lower()

    def test_validate_order_fails_position_limit(self, risk_manager):
        is_valid, reason = risk_manager.validate_order(
            symbol="SPY",
            order_value=10000,  # 10% exceeds 5% limit
            portfolio_value=100000,
            current_positions={}
        )
        assert is_valid is False
        assert "position size" in reason.lower()
