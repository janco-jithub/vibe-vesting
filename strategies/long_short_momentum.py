"""
Long/Short Momentum Strategy with Options Hedging

This strategy extends traditional momentum by:
1. Going LONG stocks with positive momentum
2. Going SHORT stocks with negative momentum (market-neutral extension)
3. Using protective puts for tail risk hedging
4. Using covered calls for income generation on long positions

Academic Foundation:
- Jegadeesh & Titman (1993): "Returns to Buying Winners and Selling Losers"
- Asness, Moskowitz & Pedersen (2013): "Value and Momentum Everywhere"
- Israel & Moskowitz (2013): "The Role of Shorting, Firm Size, and Time on Market Anomalies"

Key Findings:
- Long/short momentum delivers higher Sharpe ratios than long-only
- Short side contributes ~40% of total returns
- Options hedging reduces tail risk during market crashes

Risk Management:
- Maximum 25% net short exposure
- Stop loss: 15% on individual shorts
- Protective puts during high volatility regimes
- Covered calls during low volatility / range-bound markets
"""

from datetime import date, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

import pandas as pd
import numpy as np

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams
from execution.broker.alpaca_advanced import (
    AlpacaAdvancedTrading,
    PositionType,
    ShortPositionRiskManager
)


@dataclass
class LongShortSignal(Signal):
    """Extended signal with position type."""
    position_type: PositionType = PositionType.LONG
    hedge_with_options: bool = False
    options_strategy: Optional[str] = None  # 'protective_put' or 'covered_call'


class LongShortMomentumStrategy(BaseStrategy):
    """
    Long/Short Momentum Strategy with Options Hedging.

    Strategy Logic:
    1. Calculate 12-month momentum for universe
    2. Go LONG top decile (strongest momentum)
    3. Go SHORT bottom decile (weakest momentum)
    4. Rebalance monthly
    5. Add protective puts during high volatility
    6. Add covered calls during low volatility

    Parameters:
        lookback_months: Momentum lookback period (default: 12)
        skip_month: Skip most recent month to avoid reversal (default: True)
        enable_shorting: Enable short positions (default: True)
        max_short_pct: Maximum short exposure (default: 0.25 = 25%)
        long_positions: Number of long positions (default: 10)
        short_positions: Number of short positions (default: 10)
        use_protective_puts: Enable protective puts (default: False)
        use_covered_calls: Enable covered calls (default: False)
        vix_threshold_puts: VIX level to trigger protective puts (default: 25)
        vix_threshold_calls: VIX level below which to sell covered calls (default: 15)
    """

    def __init__(
        self,
        universe: List[str],
        lookback_months: int = 12,
        skip_month: bool = True,
        enable_shorting: bool = True,
        max_short_pct: float = 0.25,
        long_positions: int = 10,
        short_positions: int = 10,
        use_protective_puts: bool = False,
        use_covered_calls: bool = False,
        vix_threshold_puts: float = 25.0,
        vix_threshold_calls: float = 15.0
    ):
        super().__init__(
            name="LongShortMomentum",
            universe=universe
        )

        self.lookback_months = lookback_months
        self.skip_month = skip_month
        self.enable_shorting = enable_shorting
        self.max_short_pct = max_short_pct
        self.long_positions = long_positions
        self.short_positions = short_positions
        self.use_protective_puts = use_protective_puts
        self.use_covered_calls = use_covered_calls
        self.vix_threshold_puts = vix_threshold_puts
        self.vix_threshold_calls = vix_threshold_calls

        # Risk manager for shorts
        self.risk_manager = ShortPositionRiskManager(
            max_short_exposure_pct=max_short_pct
        )

    def calculate_momentum(
        self,
        data: Dict[str, pd.DataFrame],
        current_date: date
    ) -> pd.Series:
        """
        Calculate momentum scores for all symbols.

        Momentum = (Price_t / Price_{t-lookback}) - 1

        Args:
            data: Price data dict
            current_date: Current date

        Returns:
            Series of momentum scores indexed by symbol
        """
        momentum_scores = {}

        lookback_days = self.lookback_months * 21  # ~21 trading days per month
        skip_days = 21 if self.skip_month else 0

        for symbol, df in data.items():
            df = df[df.index <= current_date].copy()

            if len(df) < lookback_days + skip_days:
                continue

            # Get prices
            current_price = df['close'].iloc[-1 - skip_days] if skip_days > 0 else df['close'].iloc[-1]
            lookback_price = df['close'].iloc[-lookback_days - skip_days]

            if pd.isna(current_price) or pd.isna(lookback_price) or lookback_price == 0:
                continue

            # Calculate momentum
            momentum = (current_price / lookback_price) - 1
            momentum_scores[symbol] = momentum

        return pd.Series(momentum_scores).sort_values(ascending=False)

    def get_vix_level(self, data: Dict[str, pd.DataFrame], current_date: date) -> float:
        """
        Get current VIX level for options hedging decisions.

        Args:
            data: Price data dict (should include 'VIX' if available)
            current_date: Current date

        Returns:
            VIX level or default 20.0 if not available
        """
        if 'VIX' in data:
            vix_df = data['VIX']
            vix_df = vix_df[vix_df.index <= current_date]
            if len(vix_df) > 0:
                return float(vix_df['close'].iloc[-1])

        return 20.0  # Default VIX if not available

    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_date: Optional[date] = None
    ) -> List[LongShortSignal]:
        """
        Generate long/short momentum signals.

        Args:
            data: Price data dict
            current_date: Date for signal generation (defaults to latest)

        Returns:
            List of LongShortSignal objects
        """
        if current_date is None:
            current_date = max(df.index.max() for df in data.values() if len(df) > 0)

        # Calculate momentum for all stocks
        momentum_scores = self.calculate_momentum(data, current_date)

        if len(momentum_scores) == 0:
            return []

        # Get VIX level for options decisions
        vix = self.get_vix_level(data, current_date)

        signals = []

        # === LONG SIGNALS (Top Decile) ===
        top_decile = momentum_scores.head(self.long_positions)

        for symbol, momentum in top_decile.items():
            if momentum > 0:  # Only long positive momentum
                # Determine if we should use options hedging
                hedge_with_puts = self.use_protective_puts and vix > self.vix_threshold_puts
                use_covered_call = self.use_covered_calls and vix < self.vix_threshold_calls

                options_strategy = None
                if hedge_with_puts:
                    options_strategy = 'protective_put'
                elif use_covered_call:
                    options_strategy = 'covered_call'

                signal = LongShortSignal(
                    date=current_date,
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    strength=min(abs(momentum), 1.0),
                    position_type=PositionType.LONG,
                    hedge_with_options=hedge_with_puts or use_covered_call,
                    options_strategy=options_strategy,
                    metadata={
                        'momentum': momentum,
                        'rank': list(momentum_scores.index).index(symbol) + 1,
                        'vix': vix
                    }
                )
                signals.append(signal)

        # === SHORT SIGNALS (Bottom Decile) ===
        if self.enable_shorting:
            bottom_decile = momentum_scores.tail(self.short_positions)

            for symbol, momentum in bottom_decile.items():
                if momentum < 0:  # Only short negative momentum
                    signal = LongShortSignal(
                        date=current_date,
                        symbol=symbol,
                        signal_type=SignalType.SELL,
                        strength=min(abs(momentum), 1.0),
                        position_type=PositionType.SHORT,
                        hedge_with_options=False,
                        metadata={
                            'momentum': momentum,
                            'rank': list(momentum_scores.index).index(symbol) + 1,
                            'vix': vix
                        }
                    )
                    signals.append(signal)

        return signals

    def calculate_position_size(
        self,
        signal: LongShortSignal,
        portfolio_value: float,
        current_positions: Dict[str, float]
    ) -> float:
        """
        Calculate position size for long/short strategy.

        Position Sizing:
        - Equal weight within long/short portfolios
        - Long side: 100% / long_positions
        - Short side: max_short_pct / short_positions

        Args:
            signal: Trading signal
            portfolio_value: Current portfolio value
            current_positions: Dict of symbol -> position_value

        Returns:
            Position size in dollars
        """
        if signal.position_type == PositionType.LONG:
            # Equal weight long positions
            target_weight = 1.0 / self.long_positions
            position_size = portfolio_value * target_weight * signal.strength

        else:  # SHORT
            # Equal weight short positions within max_short_pct
            target_weight = self.max_short_pct / self.short_positions
            position_size = portfolio_value * target_weight * signal.strength

        return position_size

    def get_backtest_params(self) -> BacktestParams:
        """Return backtesting parameters."""
        return BacktestParams(
            start_date="2010-01-01",
            end_date="2024-12-31",
            initial_capital=100000.0,
            rebalance_frequency="monthly",
            transaction_cost_bps=10,
            slippage_bps=15  # Higher slippage for shorts
        )


class LongShortMomentumExecutor:
    """
    Executor for long/short momentum strategy with Alpaca.

    This class handles:
    1. Converting signals to orders
    2. Executing long positions
    3. Executing short positions (with margin checks)
    4. Adding options hedges (protective puts, covered calls)
    5. Position monitoring and risk management
    """

    def __init__(
        self,
        alpaca_trader: AlpacaAdvancedTrading,
        strategy: LongShortMomentumStrategy
    ):
        """
        Initialize executor.

        Args:
            alpaca_trader: AlpacaAdvancedTrading instance
            strategy: LongShortMomentumStrategy instance
        """
        self.trader = alpaca_trader
        self.strategy = strategy

    def execute_signals(self, signals: List[LongShortSignal]) -> Dict[str, any]:
        """
        Execute trading signals.

        Args:
            signals: List of signals to execute

        Returns:
            Execution summary
        """
        account_info = self.trader.check_short_eligibility()
        portfolio_value = account_info['equity']

        # Get current positions
        all_positions = self.trader.trading_client.get_all_positions()
        current_positions = {
            pos.symbol: float(pos.market_value)
            for pos in all_positions
        }

        results = {
            'long_orders': [],
            'short_orders': [],
            'options_orders': [],
            'errors': []
        }

        # Separate long and short signals
        long_signals = [s for s in signals if s.position_type == PositionType.LONG]
        short_signals = [s for s in signals if s.position_type == PositionType.SHORT]

        # Execute long positions
        for signal in long_signals:
            try:
                position_size = self.strategy.calculate_position_size(
                    signal, portfolio_value, current_positions
                )

                # Get current price and calculate shares
                price = self.trader.get_current_price(signal.symbol)
                shares = int(position_size / price)

                if shares == 0:
                    continue

                # Submit buy order
                order_result = self.trader.trading_client.submit_order(
                    MarketOrderRequest(
                        symbol=signal.symbol,
                        qty=shares,
                        side=OrderSide.BUY,
                        type=OrderType.MARKET,
                        time_in_force=TimeInForce.DAY
                    )
                )

                results['long_orders'].append({
                    'symbol': signal.symbol,
                    'shares': shares,
                    'order_id': order_result.id
                })

                # Add options hedge if requested
                if signal.hedge_with_options:
                    options_result = self._add_options_hedge(
                        signal, shares
                    )
                    if options_result:
                        results['options_orders'].append(options_result)

            except Exception as e:
                results['errors'].append({
                    'symbol': signal.symbol,
                    'type': 'long',
                    'error': str(e)
                })

        # Execute short positions
        current_short_value = abs(account_info['short_market_value'])

        for signal in short_signals:
            try:
                position_size = self.strategy.calculate_position_size(
                    signal, portfolio_value, current_positions
                )

                # Check short exposure limits
                allowed, reason = self.strategy.risk_manager.check_short_exposure(
                    portfolio_value,
                    current_short_value,
                    position_size
                )

                if not allowed:
                    results['errors'].append({
                        'symbol': signal.symbol,
                        'type': 'short',
                        'error': reason
                    })
                    continue

                # Calculate shares
                price = self.trader.get_current_price(signal.symbol)
                shares = int(position_size / price)

                if shares == 0:
                    continue

                # Submit short order
                order_result = self.trader.submit_short_order(
                    symbol=signal.symbol,
                    quantity=shares,
                    order_type="market",
                    check_margin=True
                )

                if order_result:
                    results['short_orders'].append(order_result)
                    current_short_value += position_size

            except Exception as e:
                results['errors'].append({
                    'symbol': signal.symbol,
                    'type': 'short',
                    'error': str(e)
                })

        return results

    def _add_options_hedge(
        self,
        signal: LongShortSignal,
        shares: int
    ) -> Optional[Dict]:
        """
        Add options hedge to long position.

        Args:
            signal: Trading signal with options strategy
            shares: Number of shares owned

        Returns:
            Options order result or None
        """
        try:
            if signal.options_strategy == 'protective_put':
                # Add protective put (5% OTM, 60 days)
                result = self.trader.execute_protective_put(
                    underlying_symbol=signal.symbol,
                    shares_owned=shares,
                    strike_price=None,  # Auto: 5% below current
                    expiration_days=60
                )
                return result

            elif signal.options_strategy == 'covered_call':
                # Sell covered call (5% OTM, 30 days)
                result = self.trader.execute_covered_call(
                    underlying_symbol=signal.symbol,
                    shares_owned=shares,
                    strike_price=None,  # Auto: 5% above current
                    expiration_days=30
                )
                return result

        except Exception as e:
            print(f"Error adding options hedge for {signal.symbol}: {e}")

        return None

    def monitor_short_positions(self) -> List[str]:
        """
        Monitor short positions and identify those needing attention.

        Returns:
            List of symbols that should be covered
        """
        short_positions = self.trader.get_short_positions()
        symbols_to_cover = []

        for position in short_positions:
            symbol = position['symbol']
            entry_price = position['avg_entry_price']
            current_price = position['current_price']

            # Check stop loss and take profit
            should_cover, reason = self.strategy.risk_manager.should_cover_short(
                entry_price=abs(entry_price),  # Entry price is negative for shorts
                current_price=current_price,
                stop_loss_pct=0.15,  # 15% stop loss
                take_profit_pct=0.20  # 20% take profit
            )

            if should_cover:
                print(f"{symbol}: {reason}")
                symbols_to_cover.append(symbol)

        return symbols_to_cover

    def auto_cover_positions(self, symbols: List[str]) -> Dict[str, any]:
        """
        Automatically cover short positions.

        Args:
            symbols: List of symbols to cover

        Returns:
            Cover results
        """
        results = {'covered': [], 'errors': []}

        for symbol in symbols:
            try:
                result = self.trader.cover_short_position(
                    symbol=symbol,
                    quantity=None,  # Cover entire position
                    order_type="market"
                )

                if result:
                    results['covered'].append(result)

            except Exception as e:
                results['errors'].append({
                    'symbol': symbol,
                    'error': str(e)
                })

        return results


if __name__ == "__main__":
    # Example usage
    print("Long/Short Momentum Strategy with Options Hedging")
    print("=" * 70)

    # Universe: S&P 500 or liquid large caps
    universe = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'JPM',
        'BAC', 'WMT', 'XOM', 'CVX', 'JNJ', 'PFE', 'UNH', 'HD'
    ]

    # Initialize strategy
    strategy = LongShortMomentumStrategy(
        universe=universe,
        lookback_months=12,
        skip_month=True,
        enable_shorting=True,
        max_short_pct=0.25,
        long_positions=8,
        short_positions=8,
        use_protective_puts=True,
        use_covered_calls=True,
        vix_threshold_puts=25.0,
        vix_threshold_calls=15.0
    )

    print(f"\nStrategy Configuration:")
    print(f"  Lookback: {strategy.lookback_months} months")
    print(f"  Long Positions: {strategy.long_positions}")
    print(f"  Short Positions: {strategy.short_positions}")
    print(f"  Max Short Exposure: {strategy.max_short_pct:.0%}")
    print(f"  Protective Puts: {strategy.use_protective_puts} (VIX > {strategy.vix_threshold_puts})")
    print(f"  Covered Calls: {strategy.use_covered_calls} (VIX < {strategy.vix_threshold_calls})")

    # Initialize Alpaca trader (paper trading)
    trader = AlpacaAdvancedTrading(paper=True)

    # Initialize executor
    executor = LongShortMomentumExecutor(trader, strategy)

    print("\n" + "=" * 70)
    print("Strategy ready. Use executor.execute_signals() to trade.")
    print("\nExample workflow:")
    print("  1. Load price data")
    print("  2. signals = strategy.generate_signals(data)")
    print("  3. results = executor.execute_signals(signals)")
    print("  4. symbols_to_cover = executor.monitor_short_positions()")
    print("  5. executor.auto_cover_positions(symbols_to_cover)")
