"""
Unit tests for CashManager.

Tests cash calculation, validation, and pending order tracking.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from execution.cash_manager import CashManager, CashManagerError


@pytest.fixture
def mock_alpaca_client():
    """Create a mock Alpaca client."""
    client = Mock()

    # Mock account data
    client.get_account.return_value = {
        'cash': 10000.0,
        'buying_power': 20000.0,
        'equity': 50000.0,
        'portfolio_value': 40000.0
    }

    # Mock empty orders by default
    client.get_orders.return_value = []

    return client


@pytest.fixture
def cash_manager(mock_alpaca_client):
    """Create a CashManager instance with mocked client."""
    return CashManager(mock_alpaca_client)


def test_initialization(cash_manager):
    """Test CashManager initializes correctly."""
    assert cash_manager is not None
    assert cash_manager.config is not None
    assert cash_manager.config['cash_buffer']['minimum_reserve'] == 2000.0


def test_get_available_cash_no_pending_orders(cash_manager, mock_alpaca_client):
    """Test available cash calculation with no pending orders."""
    mock_alpaca_client.get_orders.return_value = []

    available = cash_manager.get_available_cash()

    # $10,000 cash - $0 locked - $2,000 buffer = $8,000
    assert available == 8000.0


def test_get_available_cash_with_pending_orders(cash_manager, mock_alpaca_client):
    """Test available cash calculation with pending buy orders."""
    mock_alpaca_client.get_orders.return_value = [
        {
            'symbol': 'SPY',
            'side': 'buy',
            'qty': 10,
            'limit_price': 450.0
        },
        {
            'symbol': 'QQQ',
            'side': 'buy',
            'qty': 5,
            'limit_price': 400.0
        }
    ]

    available = cash_manager.get_available_cash()

    # $10,000 cash - $6,500 locked (10*450 + 5*400) - $2,000 buffer = $1,500
    assert available == 1500.0


def test_get_available_cash_ignores_sell_orders(cash_manager, mock_alpaca_client):
    """Test that sell orders don't lock cash."""
    mock_alpaca_client.get_orders.return_value = [
        {
            'symbol': 'SPY',
            'side': 'sell',
            'qty': 10,
            'limit_price': 450.0
        }
    ]

    available = cash_manager.get_available_cash()

    # Sell orders don't lock cash
    # $10,000 cash - $0 locked - $2,000 buffer = $8,000
    assert available == 8000.0


def test_validate_cash_for_order_sufficient(cash_manager, mock_alpaca_client):
    """Test validation passes when sufficient cash available."""
    mock_alpaca_client.get_orders.return_value = []

    # Try to buy $5,000 worth (should pass, available is $8,000)
    is_valid, reason = cash_manager.validate_cash_for_order(
        symbol='SPY',
        qty=10,
        limit_price=500.0
    )

    assert is_valid is True
    assert reason is None


def test_validate_cash_for_order_insufficient(cash_manager, mock_alpaca_client):
    """Test validation fails when insufficient cash."""
    mock_alpaca_client.get_orders.return_value = []

    # Try to buy $9,000 worth (should fail, available is $8,000)
    is_valid, reason = cash_manager.validate_cash_for_order(
        symbol='SPY',
        qty=20,
        limit_price=450.0
    )

    assert is_valid is False
    assert reason is not None
    assert 'Insufficient cash' in reason


def test_validate_cash_with_buffer(cash_manager, mock_alpaca_client):
    """Test that minimum buffer is maintained."""
    mock_alpaca_client.get_orders.return_value = []

    # Total cash: $10,000
    # Buffer: $2,000
    # Available: $8,000

    # Try to buy $8,500 worth (should fail due to buffer)
    is_valid, reason = cash_manager.validate_cash_for_order(
        symbol='SPY',
        qty=17,
        limit_price=500.0
    )

    assert is_valid is False
    assert 'Insufficient cash' in reason


def test_validate_cash_max_usage_per_order(cash_manager, mock_alpaca_client):
    """Test max usage per order limit (95%)."""
    mock_alpaca_client.get_orders.return_value = []

    # Available: $8,000
    # Max usage (95%): $7,600

    # Try to buy $7,700 worth (should fail, exceeds 95%)
    is_valid, reason = cash_manager.validate_cash_for_order(
        symbol='SPY',
        qty=15,
        limit_price=513.34  # 15 * 513.34 = $7,700
    )

    assert is_valid is False
    assert 'exceeds max usage' in reason


def test_get_pending_order_cash_requirements(cash_manager, mock_alpaca_client):
    """Test getting cash requirements by symbol."""
    mock_alpaca_client.get_orders.return_value = [
        {
            'symbol': 'SPY',
            'side': 'buy',
            'qty': 10,
            'limit_price': 450.0
        },
        {
            'symbol': 'QQQ',
            'side': 'buy',
            'qty': 5,
            'limit_price': 400.0
        },
        {
            'symbol': 'SPY',  # Another SPY order
            'side': 'buy',
            'qty': 5,
            'limit_price': 450.0
        }
    ]

    requirements = cash_manager.get_pending_order_cash_requirements()

    assert 'SPY' in requirements
    assert 'QQQ' in requirements
    assert requirements['SPY'] == 6750.0  # 10*450 + 5*450
    assert requirements['QQQ'] == 2000.0  # 5*400


def test_get_pending_order_cash_requirements_filter_by_symbol(cash_manager, mock_alpaca_client):
    """Test filtering cash requirements by symbol."""
    mock_alpaca_client.get_orders.return_value = [
        {'symbol': 'SPY', 'side': 'buy', 'qty': 10, 'limit_price': 450.0},
        {'symbol': 'QQQ', 'side': 'buy', 'qty': 5, 'limit_price': 400.0}
    ]

    requirements = cash_manager.get_pending_order_cash_requirements(symbol='SPY')

    assert 'SPY' in requirements
    assert 'QQQ' not in requirements


def test_get_cash_status(cash_manager, mock_alpaca_client):
    """Test getting comprehensive cash status."""
    mock_alpaca_client.get_orders.return_value = [
        {'symbol': 'SPY', 'side': 'buy', 'qty': 10, 'limit_price': 450.0}
    ]

    status = cash_manager.get_cash_status()

    assert status['total_cash'] == 10000.0
    assert status['locked_cash'] == 4500.0
    assert status['minimum_reserve'] == 2000.0
    assert status['available_cash'] == 3500.0
    assert status['pending_buy_orders'] == 1
    assert 'details_by_symbol' in status
    assert 'timestamp' in status


def test_cache_ttl(cash_manager, mock_alpaca_client):
    """Test that account data is cached."""
    # First call
    cash_manager.get_available_cash()
    assert mock_alpaca_client.get_account.call_count == 1

    # Second call within cache TTL
    cash_manager.get_available_cash()
    # Should still be 1 (cached)
    assert mock_alpaca_client.get_account.call_count == 1


def test_invalidate_cache(cash_manager, mock_alpaca_client):
    """Test cache invalidation."""
    # First call
    cash_manager.get_available_cash()
    assert mock_alpaca_client.get_account.call_count == 1

    # Invalidate cache
    cash_manager.invalidate_cache()

    # Next call should fetch fresh data
    cash_manager.get_available_cash()
    assert mock_alpaca_client.get_account.call_count == 2


def test_never_uses_buying_power(cash_manager, mock_alpaca_client):
    """Test that only cash is used, never buying_power."""
    # Account has $10k cash but $20k buying power
    mock_alpaca_client.get_account.return_value = {
        'cash': 10000.0,
        'buying_power': 20000.0,  # Should be ignored
        'equity': 50000.0
    }

    available = cash_manager.get_available_cash()

    # Should be based on cash ($10k) not buying_power ($20k)
    # $10,000 - $0 locked - $2,000 buffer = $8,000
    assert available == 8000.0


def test_error_handling_on_api_failure(cash_manager, mock_alpaca_client):
    """Test error handling when Alpaca API fails."""
    mock_alpaca_client.get_account.side_effect = Exception("API Error")

    with pytest.raises(CashManagerError):
        cash_manager.get_available_cash()


def test_available_cash_never_negative(cash_manager, mock_alpaca_client):
    """Test that available cash is never negative."""
    # Set up scenario where locked + buffer > total cash
    mock_alpaca_client.get_account.return_value = {
        'cash': 5000.0,
        'buying_power': 10000.0,
        'equity': 50000.0
    }

    mock_alpaca_client.get_orders.return_value = [
        {'symbol': 'SPY', 'side': 'buy', 'qty': 20, 'limit_price': 450.0}  # $9,000 locked
    ]

    available = cash_manager.get_available_cash()

    # $5,000 cash - $9,000 locked - $2,000 buffer = -$6,000, but should return 0
    assert available == 0.0
    assert available >= 0
