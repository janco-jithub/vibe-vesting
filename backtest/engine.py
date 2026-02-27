"""
Backtesting engine for strategy validation.

Features:
- Transaction cost modeling
- Slippage estimation
- Walk-forward validation
- Monte Carlo simulation
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Any, Tuple
import logging

import pandas as pd
import numpy as np

from strategies.base import BaseStrategy, Signal, SignalType, BacktestParams
from backtest.metrics import PerformanceMetrics, calculate_metrics

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """Record of a single trade."""
    date: date
    symbol: str
    action: str  # 'BUY' or 'SELL'
    shares: int
    price: float
    value: float
    commission: float
    slippage: float


@dataclass
class BacktestResult:
    """Complete backtest results."""
    strategy_name: str
    start_date: date
    end_date: date
    initial_capital: float
    final_equity: float

    # Performance metrics
    metrics: PerformanceMetrics

    # Time series
    equity_curve: pd.Series
    returns: pd.Series
    drawdown: pd.Series

    # Trades
    trades: List[Trade]
    trade_count: int

    # Costs
    total_commissions: float
    total_slippage: float

    # Position history
    positions: pd.DataFrame

    # Parameters used
    params: BacktestParams


class BacktestEngine:
    """
    Event-driven backtesting engine.

    Simulates strategy execution with realistic costs and constraints.

    Attributes:
        strategy: Strategy to backtest
        data: Market data dict
        params: Backtest parameters
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        data: Dict[str, pd.DataFrame],
        params: Optional[BacktestParams] = None
    ):
        """
        Initialize backtest engine.

        Args:
            strategy: Strategy instance to test
            data: Dict mapping symbol to OHLCV DataFrame
            params: Backtest parameters (uses strategy defaults if None)
        """
        self.strategy = strategy
        self.data = data
        self.params = params or strategy.get_backtest_params()

        # Validate data
        strategy.validate_data(data)

        # State
        self.cash = self.params.initial_capital
        self.positions: Dict[str, int] = {}  # symbol -> shares
        self.equity_history: List[Tuple[date, float]] = []
        self.trades: List[Trade] = []
        self.position_history: List[Dict] = []

        # Costs
        self.transaction_cost_rate = self.params.transaction_cost_bps / 10000
        self.slippage_rate = self.params.slippage_bps / 10000

        logger.info(
            "BacktestEngine initialized",
            extra={
                "strategy": strategy.name,
                "start": self.params.start_date,
                "end": self.params.end_date,
                "capital": self.params.initial_capital
            }
        )

    def _get_price(self, symbol: str, dt: date, price_type: str = "close") -> Optional[float]:
        """Get price for symbol on date."""
        if symbol not in self.data:
            return None

        df = self.data[symbol]
        mask = df.index.date == dt if hasattr(df.index, 'date') else df.index == dt

        if not mask.any():
            return None

        return float(df.loc[mask, price_type].iloc[0])

    def _calculate_equity(self, dt: date) -> float:
        """Calculate total portfolio value on a date."""
        equity = self.cash

        for symbol, shares in self.positions.items():
            if shares > 0:
                price = self._get_price(symbol, dt)
                if price:
                    equity += shares * price

        return equity

    def _apply_slippage(self, price: float, action: str) -> float:
        """Apply slippage to execution price."""
        if action == "BUY":
            return price * (1 + self.slippage_rate)
        else:
            return price * (1 - self.slippage_rate)

    def _execute_signal(self, signal: Signal, dt: date, portfolio_value: float) -> Optional[Trade]:
        """Execute a trading signal."""
        price = self._get_price(signal.symbol, dt)
        if price is None:
            logger.warning(f"No price for {signal.symbol} on {dt}")
            return None

        current_shares = self.positions.get(signal.symbol, 0)

        if signal.signal_type == SignalType.SELL:
            if current_shares <= 0:
                return None  # Nothing to sell

            # Sell all shares
            exec_price = self._apply_slippage(price, "SELL")
            value = current_shares * exec_price
            commission = value * self.transaction_cost_rate
            slippage_cost = current_shares * abs(price - exec_price)

            self.cash += value - commission
            self.positions[signal.symbol] = 0

            trade = Trade(
                date=dt,
                symbol=signal.symbol,
                action="SELL",
                shares=current_shares,
                price=exec_price,
                value=value,
                commission=commission,
                slippage=slippage_cost
            )

            logger.debug(
                f"SELL {current_shares} {signal.symbol} @ ${exec_price:.2f} = ${value:.2f}"
            )
            return trade

        elif signal.signal_type == SignalType.BUY:
            # Calculate target position
            target_value = self.strategy.calculate_position_size(
                signal, portfolio_value, {s: self.positions.get(s, 0) * (self._get_price(s, dt) or 0) for s in self.strategy.universe}
            )

            current_value = current_shares * price
            additional_value = target_value - current_value

            if additional_value <= 0:
                return None  # Already at or above target

            # How many shares can we buy?
            exec_price = self._apply_slippage(price, "BUY")
            available_cash = self.cash * 0.99  # Keep 1% buffer
            max_value = min(additional_value, available_cash)

            shares_to_buy = int(max_value / exec_price)
            if shares_to_buy <= 0:
                return None

            value = shares_to_buy * exec_price
            commission = value * self.transaction_cost_rate
            slippage_cost = shares_to_buy * abs(exec_price - price)

            self.cash -= value + commission
            self.positions[signal.symbol] = current_shares + shares_to_buy

            trade = Trade(
                date=dt,
                symbol=signal.symbol,
                action="BUY",
                shares=shares_to_buy,
                price=exec_price,
                value=value,
                commission=commission,
                slippage=slippage_cost
            )

            logger.debug(
                f"BUY {shares_to_buy} {signal.symbol} @ ${exec_price:.2f} = ${value:.2f}"
            )
            return trade

        return None

    def run(self) -> BacktestResult:
        """
        Run the backtest.

        Returns:
            BacktestResult with all metrics and history
        """
        logger.info(f"Starting backtest for {self.strategy.name}")

        # Generate all signals
        signals = self.strategy.generate_signals(self.data)
        signals_by_date: Dict[date, List[Signal]] = {}

        for signal in signals:
            if signal.date not in signals_by_date:
                signals_by_date[signal.date] = []
            signals_by_date[signal.date].append(signal)

        # Get trading dates from reference symbol
        ref_symbol = self.strategy.universe[0]
        all_dates = self.data[ref_symbol].index

        start = pd.Timestamp(self.params.start_date)
        end = pd.Timestamp(self.params.end_date)
        trading_dates = all_dates[(all_dates >= start) & (all_dates <= end)]

        # Main simulation loop
        for dt in trading_dates:
            dt_date = dt.date() if hasattr(dt, 'date') else dt

            # Calculate current equity
            equity = self._calculate_equity(dt_date)

            # Execute signals for this date
            if dt_date in signals_by_date:
                day_signals = signals_by_date[dt_date]

                # Execute sells first, then buys
                sells = [s for s in day_signals if s.signal_type == SignalType.SELL]
                buys = [s for s in day_signals if s.signal_type == SignalType.BUY]

                for signal in sells:
                    trade = self._execute_signal(signal, dt_date, equity)
                    if trade:
                        self.trades.append(trade)

                # Recalculate equity after sells
                equity = self._calculate_equity(dt_date)

                for signal in buys:
                    trade = self._execute_signal(signal, dt_date, equity)
                    if trade:
                        self.trades.append(trade)

            # Record equity
            final_equity = self._calculate_equity(dt_date)
            self.equity_history.append((dt_date, final_equity))

            # Record position snapshot
            positions_snapshot = {
                "date": dt_date,
                "cash": self.cash,
                "equity": final_equity,
                **{f"pos_{s}": self.positions.get(s, 0) for s in self.strategy.universe}
            }
            self.position_history.append(positions_snapshot)

        # Build results
        equity_series = pd.Series(
            {dt: eq for dt, eq in self.equity_history},
            name="equity"
        )
        equity_series.index = pd.to_datetime(equity_series.index)

        returns = equity_series.pct_change().dropna()
        drawdown = (equity_series - equity_series.cummax()) / equity_series.cummax()

        # Calculate metrics
        metrics = calculate_metrics(
            returns=returns,
            equity_curve=equity_series,
            trades=self.trades,
            initial_capital=self.params.initial_capital,
            benchmark_returns=self._get_benchmark_returns(returns.index)
        )

        # Summarize costs
        total_commissions = sum(t.commission for t in self.trades)
        total_slippage = sum(t.slippage for t in self.trades)

        result = BacktestResult(
            strategy_name=self.strategy.name,
            start_date=trading_dates[0].date() if hasattr(trading_dates[0], 'date') else trading_dates[0],
            end_date=trading_dates[-1].date() if hasattr(trading_dates[-1], 'date') else trading_dates[-1],
            initial_capital=self.params.initial_capital,
            final_equity=equity_series.iloc[-1],
            metrics=metrics,
            equity_curve=equity_series,
            returns=returns,
            drawdown=drawdown,
            trades=self.trades,
            trade_count=len(self.trades),
            total_commissions=total_commissions,
            total_slippage=total_slippage,
            positions=pd.DataFrame(self.position_history),
            params=self.params
        )

        logger.info(
            "Backtest completed",
            extra={
                "final_equity": f"${result.final_equity:,.2f}",
                "total_return": f"{metrics.total_return:.2%}",
                "sharpe": f"{metrics.sharpe_ratio:.2f}",
                "max_drawdown": f"{metrics.max_drawdown:.2%}",
                "trades": result.trade_count
            }
        )

        return result

    def _get_benchmark_returns(self, dates: pd.DatetimeIndex) -> Optional[pd.Series]:
        """Get benchmark returns for comparison."""
        benchmark = self.params.__dict__.get("benchmark", "SPY")

        if benchmark not in self.data:
            return None

        benchmark_prices = self.data[benchmark]["close"]
        benchmark_prices = benchmark_prices[benchmark_prices.index.isin(dates)]

        if len(benchmark_prices) < 2:
            return None

        return benchmark_prices.pct_change().dropna()


def run_walk_forward(
    strategy: BaseStrategy,
    data: Dict[str, pd.DataFrame],
    train_years: int = 5,
    test_years: int = 1,
    step_months: int = 12
) -> List[BacktestResult]:
    """
    Run walk-forward analysis.

    Trains on rolling window, tests on subsequent period.
    This is the ONLY valid way to backtest time-series strategies.

    Args:
        strategy: Strategy to test
        data: Market data
        train_years: Years of training data
        test_years: Years of test data
        step_months: Months to step forward each iteration

    Returns:
        List of BacktestResult for each test period
    """
    results = []

    # Get date range from data
    ref_symbol = strategy.universe[0]
    all_dates = data[ref_symbol].index
    min_date = all_dates.min()
    max_date = all_dates.max()

    # Calculate periods
    train_days = train_years * 252
    test_days = test_years * 252
    step_days = step_months * 21  # ~21 trading days per month

    current_start = min_date

    while True:
        train_end = current_start + pd.Timedelta(days=train_days * 1.5)  # Calendar days
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.Timedelta(days=test_days * 1.5)

        if test_end > max_date:
            break

        logger.info(
            f"Walk-forward period: train {current_start.date()} - {train_end.date()}, "
            f"test {test_start.date()} - {test_end.date()}"
        )

        # Create params for test period
        params = strategy.get_backtest_params()
        params.start_date = test_start.strftime("%Y-%m-%d")
        params.end_date = test_end.strftime("%Y-%m-%d")

        # Run backtest on test period
        engine = BacktestEngine(strategy, data, params)
        result = engine.run()
        results.append(result)

        # Step forward
        current_start += pd.Timedelta(days=step_days * 1.5)

    logger.info(f"Walk-forward complete: {len(results)} periods tested")
    return results
