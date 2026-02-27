#!/usr/bin/env python3
"""Test institutional momentum strategy."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date
from data.storage import TradingDatabase
from strategies.institutional_momentum import InstitutionalMomentumStrategy
from strategies.simple_momentum import SimpleMomentumStrategy
from backtest.engine import BacktestEngine

def print_results(name, result):
    """Print backtest results."""
    m = result.metrics
    print(f"\n{name}")
    print("=" * 70)
    print(f"Total Return:      {m.total_return:>8.2%}")
    print(f"CAGR:              {m.cagr:>8.2%}")
    print(f"Sharpe Ratio:      {m.sharpe_ratio:>8.2f}  <- MUST BE > 1.5")
    print(f"Sortino Ratio:     {m.sortino_ratio:>8.2f}")
    print(f"Max Drawdown:      {m.max_drawdown:>8.2%}  <- MUST BE < 15%")
    print(f"Calmar Ratio:      {m.calmar_ratio:>8.2f}")
    print(f"Win Rate:          {m.win_rate:>8.2%}  <- MUST BE > 55%")
    print(f"Profit Factor:     {m.profit_factor:>8.2f}")
    print(f"Total Trades:      {m.trade_count:>8}  <- Should be LOW")
    print(f"\nTurnover: ~{(m.trade_count / 2) / 2:.1f} round trips per year")

    # Check if institutional grade
    is_institutional = (
        m.sharpe_ratio > 1.5 and
        m.max_drawdown > -0.15 and
        m.win_rate > 0.55
    )

    print(f"\nINSTITUTIONAL GRADE: {'YES ✓' if is_institutional else 'NO ✗'}")

    return is_institutional

def main():
    # Load data
    db = TradingDatabase('data/quant.db')
    start = date(2024, 1, 1)

    universe = ["SPY", "QQQ", "IWM", "XLK", "XLE", "XLF", "XLV", "TLT"]
    data = {}

    print("Loading data...")
    for symbol in universe:
        df = db.get_daily_bars(symbol, start)
        if not df.empty:
            data[symbol] = df
            print(f"  {symbol}: {len(df)} days")

    print("\n" + "="*70)
    print("TESTING INSTITUTIONAL MOMENTUM STRATEGY")
    print("="*70)

    # Test institutional strategy
    institutional = InstitutionalMomentumStrategy(
        momentum_lookback=252,  # 12 months
        momentum_skip=21,  # Skip recent month
        trend_filter_days=200,  # 10-month MA
        max_positions=5,
        position_size_pct=0.20,
        universe=list(data.keys())
    )

    # Get current signals
    current_signals = institutional.get_current_signal(data)
    print(f"\nCurrent signals: {len(current_signals)}")
    for sig in current_signals:
        if sig.signal_type.value == 'BUY':
            print(f"  BUY {sig.symbol}: strength={sig.strength:.2f}, momentum={sig.metadata.get('momentum', 0)*100:.1f}%")

    # Backtest
    print("\nRunning backtest...")
    engine = BacktestEngine(institutional, data)
    result = engine.run()

    institutional_grade = print_results("INSTITUTIONAL MOMENTUM", result)

    # Compare to baseline
    print("\n" + "="*70)
    print("BASELINE COMPARISON: Simple Momentum (for reference)")
    print("="*70)

    baseline = SimpleMomentumStrategy(
        sma_period=50,
        momentum_period=20,
        max_positions=3,
        universe=list(data.keys())
    )

    baseline_engine = BacktestEngine(baseline, data)
    baseline_result = baseline_engine.run()

    baseline_grade = print_results("SIMPLE MOMENTUM (BASELINE)", baseline_result)

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    if institutional_grade:
        print("\n✓ INSTITUTIONAL MOMENTUM ACHIEVED INSTITUTIONAL-GRADE PERFORMANCE!")
        print("  This strategy can be deployed to live trading.")
    else:
        print("\n✗ Did not achieve institutional grade with available data.")
        print("  Key issues:")
        if result.metrics.sharpe_ratio <= 1.5:
            print(f"    - Sharpe too low ({result.metrics.sharpe_ratio:.2f} < 1.5)")
        if result.metrics.max_drawdown < -0.15:
            print(f"    - Drawdown too high ({result.metrics.max_drawdown:.1%} < -15%)")
        if result.metrics.win_rate <= 0.55:
            print(f"    - Win rate too low ({result.metrics.win_rate:.1%} < 55%)")

    # Show improvement
    sharpe_improve = result.metrics.sharpe_ratio - baseline_result.metrics.sharpe_ratio
    return_improve = result.metrics.total_return - baseline_result.metrics.total_return

    print(f"\nImprovement vs Baseline:")
    print(f"  Sharpe: {sharpe_improve:+.2f}")
    print(f"  Return: {return_improve:+.1%}")
    print(f"  Trades: {result.trade_count} vs {baseline_result.trade_count} ({baseline_result.trade_count - result.trade_count} fewer)")

if __name__ == "__main__":
    main()
