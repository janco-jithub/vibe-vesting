#!/usr/bin/env python3
"""
Test script for Volatility Breakout Strategy.

This script demonstrates:
1. Strategy initialization and configuration
2. Signal generation on historical data
3. Backtest performance metrics
4. Comparison with other strategies

Usage:
    python -m scripts.test_volatility_strategy
    python -m scripts.test_volatility_strategy --symbols NVDA TSLA AMD
    python -m scripts.test_volatility_strategy --backtest
"""

import sys
import os
import argparse
import logging
from datetime import date, timedelta
from typing import List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd

from data.storage import TradingDatabase
from data.polygon_client import RateLimitedPolygonClient
from strategies.volatility_breakout import VolatilityBreakoutStrategy
from backtest.engine import BacktestEngine
from backtest.metrics import print_metrics

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_strategy_signals(symbols: List[str] = None):
    """Test signal generation for the volatility breakout strategy."""
    print("\n" + "=" * 80)
    print("VOLATILITY BREAKOUT STRATEGY - SIGNAL GENERATION TEST")
    print("=" * 80)

    # Initialize strategy
    strategy = VolatilityBreakoutStrategy(universe=symbols)
    print(f"\nStrategy: {strategy.name}")
    print(f"Universe: {', '.join(strategy.universe)}")
    print(f"Entry Lookback: {strategy.entry_lookback} days")
    print(f"Volatility Threshold: {strategy.vol_threshold:.0%}")
    print(f"Max Positions: {strategy.max_positions}")

    # Load data
    print("\nLoading market data...")
    db = TradingDatabase()
    end_date = date.today()
    start_date = end_date - timedelta(days=180)

    data = db.get_multiple_symbols(strategy.universe, start_date=start_date)

    if not data or all(df.empty for df in data.values()):
        print("ERROR: No market data available")
        print("Please run: python -m scripts.update_data")
        return

    # Generate signals
    print("\nGenerating signals...")
    signals = strategy.generate_signals(data)

    if not signals:
        print("No signals generated")
        return

    # Analyze signals
    buy_signals = [s for s in signals if s.signal_type.value == "BUY"]
    sell_signals = [s for s in signals if s.signal_type.value == "SELL"]

    print(f"\nTotal Signals: {len(signals)}")
    print(f"  BUY signals:  {len(buy_signals)}")
    print(f"  SELL signals: {len(sell_signals)}")

    # Get most recent signals
    if buy_signals:
        recent_buys = sorted(buy_signals, key=lambda s: s.date, reverse=True)[:5]

        print("\n" + "-" * 80)
        print("MOST RECENT BUY SIGNALS")
        print("-" * 80)
        print(f"{'Date':<12} {'Symbol':<8} {'Strength':<10} {'Volatility':<12} {'Momentum':<10}")
        print("-" * 80)

        for signal in recent_buys:
            vol = signal.metadata.get('volatility', 0) if signal.metadata else 0
            momentum = signal.metadata.get('momentum_50d', 0) if signal.metadata else 0
            print(f"{signal.date} {signal.symbol:<8} {signal.strength:<10.2f} "
                  f"{vol*100:<12.1f}% {momentum*100:<10.1f}%")

    # Get current (live) signals
    print("\n" + "-" * 80)
    print("CURRENT LIVE SIGNALS (as of latest data)")
    print("-" * 80)

    current_signals = strategy.get_current_signal(data)

    if current_signals:
        print(f"{'Symbol':<8} {'Strength':<10} {'Volatility':<12} {'Momentum':<10} {'Price':<10}")
        print("-" * 80)

        for signal in current_signals:
            vol = signal.metadata.get('volatility', 0) if signal.metadata else 0
            momentum = signal.metadata.get('momentum_50d', 0) if signal.metadata else 0
            price = signal.metadata.get('current_price', 0) if signal.metadata else 0
            print(f"{signal.symbol:<8} {signal.strength:<10.2f} "
                  f"{vol*100:<12.1f}% {momentum*100:<10.1f}% ${price:<10.2f}")
    else:
        print("No current signals - market conditions not favorable")

    print("\n")


def run_backtest(symbols: List[str] = None):
    """Run a full backtest of the volatility breakout strategy."""
    print("\n" + "=" * 80)
    print("VOLATILITY BREAKOUT STRATEGY - BACKTEST")
    print("=" * 80)

    # Initialize strategy
    strategy = VolatilityBreakoutStrategy(universe=symbols)
    print(f"\nStrategy: {strategy.name}")
    print(f"Universe: {', '.join(strategy.universe)}")

    # Load data
    print("\nLoading market data...")
    db = TradingDatabase()

    # Get data for backtesting period
    data = db.get_multiple_symbols(strategy.universe)

    if not data or all(df.empty for df in data.values()):
        print("ERROR: No market data available")
        print("Please run: python -m scripts.update_data")
        return

    # Check data availability
    print("\nData Summary:")
    for symbol, df in data.items():
        if not df.empty:
            print(f"  {symbol}: {len(df)} bars ({df.index[0].date()} to {df.index[-1].date()})")

    # Set up backtest parameters
    params = strategy.get_backtest_params()
    print(f"\nBacktest Parameters:")
    print(f"  Period: {params.start_date} to {params.end_date}")
    print(f"  Initial Capital: ${params.initial_capital:,.2f}")
    print(f"  Rebalance Frequency: {params.rebalance_frequency}")
    print(f"  Transaction Cost: {params.transaction_cost_bps} bps")
    print(f"  Slippage: {params.slippage_bps} bps")

    # Run backtest
    print("\nRunning backtest...")
    engine = BacktestEngine(strategy, data, params)
    result = engine.run()

    # Print results
    print("\n" + "=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)
    print_metrics(result)

    # Print equity curve summary
    if not result.equity_curve.empty:
        print("\nEquity Curve Statistics:")
        equity = result.equity_curve
        print(f"  Starting Equity: ${equity.iloc[0]:,.2f}")
        print(f"  Ending Equity:   ${equity.iloc[-1]:,.2f}")
        print(f"  Peak Equity:     ${equity.max():,.2f}")
        print(f"  Trough Equity:   ${equity.min():,.2f}")

    # Print trade summary
    print(f"\nTrade Summary:")
    print(f"  Total Trades: {result.trade_count}")
    if result.trade_count > 0:
        print(f"  Win Rate: {result.metrics.win_rate:.1%}")
        print(f"  Avg Win:  {result.metrics.avg_win:.2%}")
        print(f"  Avg Loss: {result.metrics.avg_loss:.2%}")

    print("\n" + "=" * 80)
    print("\nBacktest complete!")


def compare_volatility_regimes(symbols: List[str] = None):
    """Analyze how the strategy performs in different volatility regimes."""
    print("\n" + "=" * 80)
    print("VOLATILITY REGIME ANALYSIS")
    print("=" * 80)

    strategy = VolatilityBreakoutStrategy(universe=symbols)
    db = TradingDatabase()

    data = db.get_multiple_symbols(strategy.universe)

    if not data or all(df.empty for df in data.values()):
        print("ERROR: No market data available")
        return

    # Analyze each symbol
    for symbol in strategy.universe:
        if symbol not in data or data[symbol].empty:
            continue

        df = data[symbol]
        print(f"\n{symbol}:")
        print("-" * 40)

        # Calculate rolling volatility
        returns = df['close'].pct_change().dropna()
        vol_20d = returns.rolling(20).std() * (252 ** 0.5)

        # Classify into regimes
        low_vol = vol_20d[vol_20d < 0.20].mean() if any(vol_20d < 0.20) else 0
        med_vol = vol_20d[(vol_20d >= 0.20) & (vol_20d < 0.40)].mean() if any((vol_20d >= 0.20) & (vol_20d < 0.40)) else 0
        high_vol = vol_20d[vol_20d >= 0.40].mean() if any(vol_20d >= 0.40) else 0

        print(f"  Current Volatility: {vol_20d.iloc[-1]*100:.1f}%")
        print(f"  Avg Low Vol (<20%):  {low_vol*100:.1f}%" if low_vol else "  Low vol: N/A")
        print(f"  Avg Med Vol (20-40%): {med_vol*100:.1f}%" if med_vol else "  Med vol: N/A")
        print(f"  Avg High Vol (>40%): {high_vol*100:.1f}%" if high_vol else "  High vol: N/A")

        # Count days in each regime
        total_days = len(vol_20d)
        low_days = sum(vol_20d < 0.20)
        med_days = sum((vol_20d >= 0.20) & (vol_20d < 0.40))
        high_days = sum(vol_20d >= 0.40)

        print(f"  Days in Low Vol:  {low_days} ({low_days/total_days*100:.1f}%)")
        print(f"  Days in Med Vol:  {med_days} ({med_days/total_days*100:.1f}%)")
        print(f"  Days in High Vol: {high_days} ({high_days/total_days*100:.1f}%)")

    print("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Test Volatility Breakout Strategy"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Symbols to test (default: strategy default universe)"
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run full backtest"
    )
    parser.add_argument(
        "--regime-analysis",
        action="store_true",
        help="Analyze volatility regimes"
    )

    args = parser.parse_args()

    # Run tests
    if args.backtest:
        run_backtest(symbols=args.symbols)
    elif args.regime_analysis:
        compare_volatility_regimes(symbols=args.symbols)
    else:
        # Default: test signal generation
        test_strategy_signals(symbols=args.symbols)


if __name__ == "__main__":
    main()
