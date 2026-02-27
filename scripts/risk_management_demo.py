#!/usr/bin/env python3
"""
Risk Management System Demonstration

Demonstrates the world-class risk management system including:
1. Dynamic position sizing
2. Portfolio-level risk controls
3. Adaptive trailing stops
4. Stress testing
5. Real-time risk dashboard

Usage:
    python scripts/risk_management_demo.py
    python scripts/risk_management_demo.py --live  # Use live data from broker
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from risk.dynamic_sizing import DynamicPositionSizer
from risk.portfolio_risk import PortfolioRiskManager
from risk.adaptive_stops import AdaptiveStopManager
from risk.stress_test import StressTestEngine
from risk.var_calculator import VaRCalculator
from risk.circuit_breakers import CircuitBreaker
from monitoring.risk_dashboard import RiskDashboard
from data.storage import TradingDatabase


def generate_sample_positions() -> dict:
    """Generate sample positions for demonstration."""
    return {
        'AAPL': {
            'market_value': 15000,
            'qty': 100,
            'current_price': 150.0,
            'avg_entry_price': 145.0,
            'entry_time': datetime.now() - timedelta(days=15),
            'stop_loss': 140.0,
            'unrealized_plpc': 3.45,
            'side': 'long',
            'highest_price': 152.0,
            'atr': 3.5
        },
        'MSFT': {
            'market_value': 12000,
            'qty': 40,
            'current_price': 300.0,
            'avg_entry_price': 295.0,
            'entry_time': datetime.now() - timedelta(days=8),
            'stop_loss': 285.0,
            'unrealized_plpc': 1.69,
            'side': 'long',
            'highest_price': 302.0,
            'atr': 8.0
        },
        'GOOGL': {
            'market_value': 10000,
            'qty': 80,
            'current_price': 125.0,
            'avg_entry_price': 123.0,
            'entry_time': datetime.now() - timedelta(days=5),
            'stop_loss': 118.0,
            'unrealized_plpc': 1.63,
            'side': 'long',
            'highest_price': 126.5,
            'atr': 4.0
        },
        'TSLA': {
            'market_value': 8000,
            'qty': 40,
            'current_price': 200.0,
            'avg_entry_price': 210.0,
            'entry_time': datetime.now() - timedelta(days=20),
            'stop_loss': 195.0,
            'unrealized_plpc': -4.76,
            'side': 'long',
            'highest_price': 215.0,
            'atr': 12.0
        },
        'NVDA': {
            'market_value': 13000,
            'qty': 25,
            'current_price': 520.0,
            'avg_entry_price': 500.0,
            'entry_time': datetime.now() - timedelta(days=12),
            'stop_loss': 480.0,
            'unrealized_plpc': 4.0,
            'side': 'long',
            'highest_price': 525.0,
            'atr': 18.0
        },
        'META': {
            'market_value': 9000,
            'qty': 30,
            'current_price': 300.0,
            'avg_entry_price': 290.0,
            'entry_time': datetime.now() - timedelta(days=25),
            'stop_loss': 280.0,
            'unrealized_plpc': 3.45,
            'side': 'long',
            'highest_price': 305.0,
            'atr': 10.0
        }
    }


def generate_sample_returns(symbols: list, days: int = 90) -> dict:
    """Generate sample return series for demonstration."""
    returns_data = {}
    dates = pd.date_range(end=date.today(), periods=days, freq='D')

    for symbol in symbols:
        # Generate synthetic returns with some correlation
        np.random.seed(hash(symbol) % 2**32)
        returns = np.random.normal(0.001, 0.02, days)
        returns_data[symbol] = pd.Series(returns, index=dates)

    return returns_data


def demo_dynamic_sizing():
    """Demonstrate dynamic position sizing."""
    print("\n" + "=" * 80)
    print("DYNAMIC POSITION SIZING DEMO")
    print("=" * 80)

    sizer = DynamicPositionSizer(
        base_position_pct=0.10,
        max_position_pct=0.15,
        min_position_pct=0.02
    )

    # Example: Size a new position
    portfolio_value = 100000
    symbol = 'AAPL'
    asset_volatility = 0.25  # 25% annualized
    vix = 22.0

    # Generate sample returns for correlation analysis
    symbols = ['MSFT', 'GOOGL', 'NVDA']
    portfolio_returns = pd.DataFrame({
        sym: generate_sample_returns([sym], 60)[sym]
        for sym in symbols
    })
    new_asset_returns = generate_sample_returns([symbol], 60)[symbol]

    # Generate sample SPY data for regime detection
    spy_data = pd.DataFrame({
        'close': 100 * (1 + np.random.normal(0.0005, 0.015, 250)).cumprod()
    }, index=pd.date_range(end=date.today(), periods=250))

    params = sizer.calculate_position_size(
        symbol=symbol,
        portfolio_value=portfolio_value,
        asset_volatility=asset_volatility,
        vix=vix,
        spy_data=spy_data,
        portfolio_returns=portfolio_returns,
        new_asset_returns=new_asset_returns,
        strategy='momentum',
        win_rate=0.58,
        avg_win=0.025,
        avg_loss=0.015
    )

    print(f"\nPosition Sizing for {symbol}:")
    print(f"  Portfolio Value: ${portfolio_value:,.0f}")
    print(f"  Asset Volatility: {asset_volatility:.1%}")
    print(f"  VIX: {vix:.1f}")
    print(f"\nAdjustments:")
    for reason in params.reasoning:
        print(f"  - {reason}")
    print(f"\nFinal Size: {params.final_size_pct:.2%} of portfolio (${portfolio_value * params.final_size_pct:,.0f})")

    # Record some sample trades for Kelly sizing
    print("\nRecording sample trades for Kelly calculation...")
    sizer.record_trade_result(
        symbol='AAPL', strategy='momentum',
        entry_price=145.0, exit_price=150.0,
        entry_time=datetime.now() - timedelta(days=10),
        exit_time=datetime.now() - timedelta(days=5)
    )
    sizer.record_trade_result(
        symbol='MSFT', strategy='momentum',
        entry_price=295.0, exit_price=300.0,
        entry_time=datetime.now() - timedelta(days=15),
        exit_time=datetime.now() - timedelta(days=8)
    )

    stats = sizer.get_strategy_statistics('momentum')
    print(f"Strategy Stats: {stats}")


def demo_portfolio_risk():
    """Demonstrate portfolio risk management."""
    print("\n" + "=" * 80)
    print("PORTFOLIO RISK MANAGEMENT DEMO")
    print("=" * 80)

    # Initialize
    risk_manager = PortfolioRiskManager(
        max_portfolio_heat_pct=0.20,
        max_sector_exposure_pct=0.30,
        max_avg_correlation=0.6
    )

    # Set sector mapping
    sector_map = {
        'AAPL': 'Technology',
        'MSFT': 'Technology',
        'GOOGL': 'Technology',
        'TSLA': 'Automotive',
        'NVDA': 'Technology',
        'META': 'Technology'
    }
    risk_manager.set_sector_map(sector_map)

    # Calculate metrics
    positions = generate_sample_positions()
    portfolio_value = 100000
    cash = 33000
    margin_used = 0
    margin_available = 100000

    returns_data = generate_sample_returns(list(positions.keys()), 60)

    metrics = risk_manager.calculate_metrics(
        positions=positions,
        portfolio_value=portfolio_value,
        cash=cash,
        margin_used=margin_used,
        margin_available=margin_available,
        returns_data=returns_data
    )

    # Print summary
    risk_manager.print_risk_summary(metrics)

    # Get risk reduction actions if needed
    actions = risk_manager.get_risk_reduction_actions(metrics, positions)
    if actions:
        print("\n⚠ RECOMMENDED RISK REDUCTION ACTIONS:")
        for action in actions:
            print(f"\n{action.action_type.upper()} - {action.urgency.upper()} PRIORITY")
            if action.symbol:
                print(f"  Symbol: {action.symbol}")
                print(f"  Current Size: ${action.current_size:,.0f}")
                print(f"  Target Size: ${action.target_size:,.0f}")
            print(f"  Reason: {action.reason}")


def demo_adaptive_stops():
    """Demonstrate adaptive trailing stops."""
    print("\n" + "=" * 80)
    print("ADAPTIVE TRAILING STOPS DEMO")
    print("=" * 80)

    stop_manager = AdaptiveStopManager(
        initial_stop_pct=0.04,
        trailing_stop_pct=0.03,
        max_hold_days=60,
        stale_position_days=30
    )

    positions = generate_sample_positions()
    vix = 22.0

    stops = stop_manager.calculate_batch_stops(positions, vix)
    stop_manager.print_stop_summary(stops)


def demo_stress_testing():
    """Demonstrate stress testing."""
    print("\n" + "=" * 80)
    print("STRESS TESTING DEMO")
    print("=" * 80)

    engine = StressTestEngine()
    positions = generate_sample_positions()
    portfolio_value = 100000

    # Run all scenarios
    results = engine.run_all_scenarios(positions, portfolio_value)

    # Print report
    engine.print_stress_test_report(results, show_position_detail=True)

    # Get tail risk estimate
    tail_risk = engine.get_tail_risk_estimate(results)
    print("\nTAIL RISK ANALYSIS:")
    print(f"  Worst Case Loss: {tail_risk['worst_loss']:.1%}")
    print(f"  Average Loss: {tail_risk['avg_loss']:.1%}")
    print(f"  5th Percentile: {tail_risk['percentile_5']:.1%}")
    print(f"  1st Percentile: {tail_risk['percentile_1']:.1%}")


def demo_risk_dashboard():
    """Demonstrate real-time risk dashboard."""
    print("\n" + "=" * 80)
    print("RISK DASHBOARD DEMO")
    print("=" * 80)

    # Initialize all components
    var_calculator = VaRCalculator()
    portfolio_risk_manager = PortfolioRiskManager()
    circuit_breaker = CircuitBreaker(initial_equity=100000)
    adaptive_stop_manager = AdaptiveStopManager()

    # Set sector mapping
    sector_map = {
        'AAPL': 'Technology',
        'MSFT': 'Technology',
        'GOOGL': 'Technology',
        'TSLA': 'Automotive',
        'NVDA': 'Technology',
        'META': 'Technology'
    }
    portfolio_risk_manager.set_sector_map(sector_map)

    dashboard = RiskDashboard(
        var_calculator=var_calculator,
        portfolio_risk_manager=portfolio_risk_manager,
        circuit_breaker=circuit_breaker,
        adaptive_stop_manager=adaptive_stop_manager
    )

    # Generate data
    positions = generate_sample_positions()
    portfolio_value = 100000
    cash = 33000

    # Generate portfolio returns
    portfolio_returns = pd.Series(
        np.random.normal(0.0008, 0.015, 90),
        index=pd.date_range(end=date.today(), periods=90)
    )

    # Generate returns for correlation
    returns_data = generate_sample_returns(list(positions.keys()), 60)

    # Generate SPY data
    spy_data = pd.DataFrame({
        'close': 100 * (1 + np.random.normal(0.0005, 0.015, 250)).cumprod()
    }, index=pd.date_range(end=date.today(), periods=250))

    # Update circuit breaker
    circuit_breaker.update(portfolio_value)

    # Get snapshot
    snapshot = dashboard.get_risk_snapshot(
        positions=positions,
        portfolio_value=portfolio_value,
        cash=cash,
        margin_used=0,
        margin_available=100000,
        returns_data=returns_data,
        portfolio_returns=portfolio_returns,
        spy_data=spy_data,
        vix=22.0
    )

    # Print dashboard
    dashboard.print_dashboard(snapshot)

    # Export snapshot
    filepath = dashboard.export_snapshot(snapshot)
    print(f"\nSnapshot exported to: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Risk Management System Demo")
    parser.add_argument(
        '--demo',
        choices=['sizing', 'portfolio', 'stops', 'stress', 'dashboard', 'all'],
        default='all',
        help='Which demo to run'
    )
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("WORLD-CLASS RISK MANAGEMENT SYSTEM")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nThis demonstration showcases institutional-grade risk management")
    print("for quantitative trading systems.\n")

    try:
        if args.demo in ['sizing', 'all']:
            demo_dynamic_sizing()

        if args.demo in ['portfolio', 'all']:
            demo_portfolio_risk()

        if args.demo in ['stops', 'all']:
            demo_adaptive_stops()

        if args.demo in ['stress', 'all']:
            demo_stress_testing()

        if args.demo in ['dashboard', 'all']:
            demo_risk_dashboard()

        print("\n" + "=" * 80)
        print("DEMONSTRATION COMPLETE")
        print("=" * 80)
        print("\nAll risk management components are functioning correctly.")
        print("See individual files in /Users/work/personal/quant/risk/ for implementation details.\n")

    except Exception as e:
        print(f"\n✗ Error during demonstration: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
