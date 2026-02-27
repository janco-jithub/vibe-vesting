#!/usr/bin/env python3
"""
Deep dive analysis into why strategies are failing.
Check signal generation, position sizing, and execution logic.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta
import pandas as pd
from data.storage import TradingDatabase
from strategies.simple_momentum import SimpleMomentumStrategy

def main():
    print("="*80)
    print("SIGNAL GENERATION ANALYSIS")
    print("="*80)

    # Load data
    db = TradingDatabase('data/quant.db')
    start = date(2024, 1, 1)

    universe = ["SPY", "QQQ", "IWM", "XLK", "XLE", "XLF"]
    data = {}

    for symbol in universe:
        df = db.get_daily_bars(symbol, start)
        if not df.empty:
            data[symbol] = df

    # Test Simple Momentum
    strategy = SimpleMomentumStrategy(
        sma_period=50,
        momentum_period=20,
        max_positions=3,
        position_size_pct=0.15,
        universe=list(data.keys())
    )

    print(f"\nStrategy: {strategy.name}")
    print(f"Universe: {strategy.universe}")
    print(f"Parameters: sma_period={strategy.sma_period}, momentum_period={strategy.momentum_period}")

    # Get current signals
    current_signals = strategy.get_current_signal(data)

    print(f"\nCurrent Signals ({len(current_signals)} total):")
    for sig in current_signals:
        print(f"  {sig.symbol}: {sig.signal_type.value} (strength={sig.strength:.2f})")
        if sig.metadata:
            print(f"    Metadata: {sig.metadata}")

    # Analyze each symbol
    print("\n" + "="*80)
    print("PER-SYMBOL ANALYSIS")
    print("="*80)

    for symbol in universe:
        if symbol not in data:
            continue

        df = data[symbol]
        if len(df) < strategy.sma_period + 10:
            print(f"\n{symbol}: Insufficient data ({len(df)} days)")
            continue

        # Calculate indicators
        close = df['close']
        sma = close.rolling(strategy.sma_period).mean()
        momentum = close.pct_change(strategy.momentum_period) * 100

        latest_close = close.iloc[-1]
        latest_sma = sma.iloc[-1]
        latest_momentum = momentum.iloc[-1]

        above_sma = latest_close > latest_sma
        pct_from_sma = ((latest_close - latest_sma) / latest_sma) * 100

        print(f"\n{symbol}:")
        print(f"  Current Price:     ${latest_close:.2f}")
        print(f"  50-day SMA:        ${latest_sma:.2f}")
        print(f"  % from SMA:        {pct_from_sma:+.2f}%")
        print(f"  20-day Momentum:   {latest_momentum:+.2f}%")
        print(f"  Above Trend:       {'YES' if above_sma else 'NO'}")
        print(f"  Should Trade:      {'YES' if above_sma and latest_momentum > 0 else 'NO'}")

    # Check all generated signals for backtesting
    print("\n" + "="*80)
    print("BACKTEST SIGNAL GENERATION")
    print("="*80)

    all_signals = strategy.generate_signals(data)
    print(f"\nTotal signals generated: {len(all_signals)}")

    # Group by signal type
    buy_signals = [s for s in all_signals if s.signal_type.value == 'BUY']
    sell_signals = [s for s in all_signals if s.signal_type.value == 'SELL']

    print(f"  BUY signals:  {len(buy_signals)}")
    print(f"  SELL signals: {len(sell_signals)}")

    # Show sample signals
    print("\nFirst 10 BUY signals:")
    for sig in buy_signals[:10]:
        print(f"  {sig.date}: {sig.symbol} strength={sig.strength:.2f}")

    print("\nFirst 10 SELL signals:")
    for sig in sell_signals[:10]:
        print(f"  {sig.date}: {sig.symbol} strength={sig.strength:.2f}")

    # Check signal distribution by symbol
    print("\nSignals per symbol:")
    symbol_counts = {}
    for sig in all_signals:
        symbol_counts[sig.symbol] = symbol_counts.get(sig.symbol, 0) + 1

    for symbol, count in sorted(symbol_counts.items(), key=lambda x: x[1], reverse=True):
        print(f"  {symbol}: {count} signals")

if __name__ == "__main__":
    main()
