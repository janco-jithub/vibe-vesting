#!/usr/bin/env python3
"""
Comprehensive Strategy Optimization & Backtest

Compares CURRENT strategies vs. OPTIMIZED strategies using academic best practices.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta
import pandas as pd
import numpy as np
from data.storage import TradingDatabase
from strategies.simple_momentum import SimpleMomentumStrategy
from strategies.dual_momentum import DualMomentumStrategy
from strategies.swing_momentum import SwingMomentumStrategy
from backtest.engine import BacktestEngine
from strategies.base import BacktestParams

# Results storage
results = {}

def print_header(text):
    print("\n" + "="*80)
    print(text.center(80))
    print("="*80)

def print_metrics(name, metrics):
    """Print backtest metrics in a clean format."""
    print(f"\n{name}")
    print("-" * 60)
    print(f"  Total Return:      {metrics.total_return:>8.2%}")
    print(f"  CAGR:              {metrics.cagr:>8.2%}")
    print(f"  Sharpe Ratio:      {metrics.sharpe_ratio:>8.2f}")
    print(f"  Sortino Ratio:     {metrics.sortino_ratio:>8.2f}")
    print(f"  Max Drawdown:      {metrics.max_drawdown:>8.2%}")
    print(f"  Win Rate:          {metrics.win_rate:>8.2%}")
    print(f"  Avg Win:           ${metrics.avg_win:>7.2f}")
    print(f"  Avg Loss:          ${metrics.avg_loss:>7.2f}")
    print(f"  Profit Factor:     {metrics.profit_factor:>8.2f}")
    print(f"  Total Trades:      {metrics.trade_count:>8}")

    # Store for comparison
    results[name] = {
        'sharpe': metrics.sharpe_ratio,
        'return': metrics.total_return,
        'drawdown': metrics.max_drawdown,
        'win_rate': metrics.win_rate
    }

def run_strategy_backtest(strategy, data, name):
    """Run backtest for a strategy."""
    print(f"\n>>> Running backtest for {name}...")

    params = strategy.get_backtest_params()
    # Override dates to use available data
    params.start_date = "2024-03-01"
    params.end_date = "2026-02-01"

    engine = BacktestEngine(strategy, data, params)
    result = engine.run()

    print_metrics(name, result.metrics)
    return result

def main():
    print_header("QUANTITATIVE TRADING SYSTEM - OPTIMIZATION ANALYSIS")

    # Load data
    print("\n>>> Loading market data...")
    db = TradingDatabase('data/quant.db')
    start = date(2024, 1, 1)

    # Load core universe
    universe = ["SPY", "QQQ", "IWM", "XLK", "XLE", "XLF", "XLV", "TLT"]
    data = {}

    for symbol in universe:
        df = db.get_daily_bars(symbol, start)
        if not df.empty:
            data[symbol] = df
            print(f"  {symbol}: {len(df)} days")

    if not data:
        print("ERROR: No data available")
        return

    print_header("PHASE 1: CURRENT STRATEGIES (BASELINE)")

    # Test 1: Current Simple Momentum (50-day SMA, 20-day momentum)
    current_simple = SimpleMomentumStrategy(
        sma_period=50,
        momentum_period=20,
        max_positions=3,
        position_size_pct=0.15,
        universe=list(data.keys()),
        name="current_simple_momentum"
    )
    r1 = run_strategy_backtest(current_simple, data, "CURRENT: Simple Momentum (50/20)")

    # Test 2: Current Dual Momentum (63-day = 3 months)
    current_dual = DualMomentumStrategy(
        lookback_days=63,
        skip_days=5,
        risk_assets=["SPY", "QQQ", "IWM"],
        safe_haven="TLT",
        name="current_dual_momentum"
    )
    r2 = run_strategy_backtest(current_dual, data, "CURRENT: Dual Momentum (3-month)")

    # Test 3: Current Swing Momentum
    current_swing = SwingMomentumStrategy(
        rsi_period=14,
        rsi_oversold=35.0,
        rsi_overbought=65.0,
        short_ma=20,
        long_ma=50,
        momentum_period=63,
        skip_days=5,
        min_signal_strength=0.3,
        universe=list(data.keys()),
        name="current_swing_momentum"
    )
    r3 = run_strategy_backtest(current_swing, data, "CURRENT: Swing Momentum (50MA)")

    print_header("PHASE 2: OPTIMIZED STRATEGIES (ACADEMIC BEST PRACTICES)")

    # Test 4: OPTIMIZED Simple Momentum (200-day SMA, 12-1 month momentum)
    optimized_simple = SimpleMomentumStrategy(
        sma_period=200,  # Faber 2007: 200-day MA trend filter
        momentum_period=252,  # Jegadeesh & Titman 1993: 12-month momentum
        max_positions=3,
        position_size_pct=0.20,  # Slightly larger per Fama & French
        universe=list(data.keys()),
        name="optimized_simple_momentum"
    )
    r4 = run_strategy_backtest(optimized_simple, data, "OPTIMIZED: Simple Momentum (200/252)")

    # Test 5: OPTIMIZED Dual Momentum (252-day = 12 months)
    optimized_dual = DualMomentumStrategy(
        lookback_days=252,  # Antonacci 2013: 12-month momentum
        skip_days=21,  # Jegadeesh & Titman: skip recent month
        risk_assets=["SPY", "QQQ", "IWM"],
        safe_haven="TLT",
        use_trend_filter=True,
        trend_ma_days=200,  # Faber 2007: 200-day MA filter
        name="optimized_dual_momentum"
    )
    r5 = run_strategy_backtest(optimized_dual, data, "OPTIMIZED: Dual Momentum (12-1 month)")

    # Test 6: OPTIMIZED Swing Momentum (200-day MA, 12-month momentum)
    optimized_swing = SwingMomentumStrategy(
        rsi_period=14,
        rsi_oversold=40.0,  # Relaxed
        rsi_overbought=60.0,  # Relaxed
        short_ma=50,
        long_ma=200,  # Faber 2007: 200-day MA
        momentum_period=252,  # 12-month momentum
        skip_days=21,  # Skip recent month
        min_signal_strength=0.5,  # Higher threshold
        universe=list(data.keys()),
        name="optimized_swing_momentum"
    )
    r6 = run_strategy_backtest(optimized_swing, data, "OPTIMIZED: Swing Momentum (200MA)")

    print_header("COMPARISON SUMMARY")

    print("\nStrategy                                   Sharpe  Return   MaxDD   WinRate")
    print("-" * 78)
    for name, metrics in results.items():
        print(f"{name:40s} {metrics['sharpe']:>6.2f}  {metrics['return']:>6.1%}  {metrics['drawdown']:>6.1%}  {metrics['win_rate']:>6.1%}")

    print_header("RECOMMENDATIONS")

    # Find best performing strategies
    best_sharpe = max(results.items(), key=lambda x: x[1]['sharpe'])
    best_return = max(results.items(), key=lambda x: x[1]['return'])
    best_drawdown = min(results.items(), key=lambda x: abs(x[1]['drawdown']))

    print(f"\nBest Sharpe Ratio:  {best_sharpe[0]} ({best_sharpe[1]['sharpe']:.2f})")
    print(f"Best Total Return:  {best_return[0]} ({best_return[1]['return']:.1%})")
    print(f"Best Max Drawdown:  {best_drawdown[0]} ({best_drawdown[1]['drawdown']:.1%})")

    print("\nKEY FINDINGS:")

    # Calculate improvements
    for opt_name in results.keys():
        if 'OPTIMIZED' in opt_name:
            base_name = opt_name.replace('OPTIMIZED:', 'CURRENT:')
            if base_name in results:
                sharpe_improve = results[opt_name]['sharpe'] - results[base_name]['sharpe']
                return_improve = results[opt_name]['return'] - results[base_name]['return']
                dd_improve = results[opt_name]['drawdown'] - results[base_name]['drawdown']

                print(f"\n{opt_name}:")
                print(f"  Sharpe improvement: {sharpe_improve:+.2f}")
                print(f"  Return improvement: {return_improve:+.1%}")
                print(f"  Drawdown change:    {dd_improve:+.1%} ({'better' if dd_improve > 0 else 'worse'})")

    print("\nRECOMMENDED CHANGES:")
    print("1. Use 200-day MA instead of 50-day MA (Faber 2007)")
    print("2. Use 12-month momentum formation period (Jegadeesh & Titman 1993)")
    print("3. Skip most recent month to avoid reversal (J&T 1993)")
    print("4. Increase minimum signal strength to reduce false signals")
    print("5. Use larger position sizes for high-conviction signals (20% vs 15%)")

if __name__ == "__main__":
    main()
