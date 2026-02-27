"""
Performance metrics calculation for backtesting.

Implements standard quantitative finance metrics:
- Sharpe Ratio
- Sortino Ratio
- Calmar Ratio
- Maximum Drawdown
- Win Rate
- Profit Factor
"""

from dataclasses import dataclass
from typing import List, Optional, Any
import logging

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.04  # 4% annual risk-free rate


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a strategy."""

    # Returns
    total_return: float
    cagr: float  # Compound Annual Growth Rate
    annual_volatility: float

    # Risk-adjusted
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown
    max_drawdown: float
    avg_drawdown: float
    max_drawdown_duration_days: int

    # Trading
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    trade_count: int

    # vs Benchmark
    alpha: Optional[float] = None
    beta: Optional[float] = None
    information_ratio: Optional[float] = None

    # Additional
    skewness: float = 0.0
    kurtosis: float = 0.0
    var_95: float = 0.0  # Value at Risk 95%
    cvar_95: float = 0.0  # Conditional VaR (Expected Shortfall)


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE
) -> float:
    """
    Calculate annualized Sharpe Ratio.

    Sharpe = (Mean Return - Risk Free Rate) / Std Dev

    Args:
        returns: Daily returns series
        risk_free_rate: Annual risk-free rate

    Returns:
        Annualized Sharpe Ratio
    """
    if len(returns) < 2 or returns.std() == 0:
        return 0.0

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess_returns = returns - daily_rf

    sharpe = excess_returns.mean() / excess_returns.std()
    return float(sharpe * np.sqrt(TRADING_DAYS_PER_YEAR))


def calculate_sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE,
    target_return: float = 0.0
) -> float:
    """
    Calculate annualized Sortino Ratio.

    Like Sharpe but only penalizes downside volatility.

    Args:
        returns: Daily returns series
        risk_free_rate: Annual risk-free rate
        target_return: Target daily return

    Returns:
        Annualized Sortino Ratio
    """
    if len(returns) < 2:
        return 0.0

    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess_returns = returns - daily_rf

    downside_returns = returns[returns < target_return]
    if len(downside_returns) == 0 or downside_returns.std() == 0:
        return float('inf') if excess_returns.mean() > 0 else 0.0

    downside_std = downside_returns.std()
    sortino = excess_returns.mean() / downside_std

    return float(sortino * np.sqrt(TRADING_DAYS_PER_YEAR))


def calculate_max_drawdown(equity_curve: pd.Series) -> tuple[float, int]:
    """
    Calculate maximum drawdown and duration.

    Args:
        equity_curve: Portfolio value over time

    Returns:
        Tuple of (max_drawdown, duration_in_days)
    """
    if len(equity_curve) < 2:
        return 0.0, 0

    running_max = equity_curve.cummax()
    drawdown = (equity_curve - running_max) / running_max

    max_dd = float(drawdown.min())

    # Calculate duration
    in_drawdown = drawdown < 0
    if not in_drawdown.any():
        return max_dd, 0

    # Find longest drawdown period
    drawdown_periods = []
    start_idx = None

    for i, is_dd in enumerate(in_drawdown):
        if is_dd and start_idx is None:
            start_idx = i
        elif not is_dd and start_idx is not None:
            drawdown_periods.append(i - start_idx)
            start_idx = None

    if start_idx is not None:
        drawdown_periods.append(len(in_drawdown) - start_idx)

    max_duration = max(drawdown_periods) if drawdown_periods else 0

    return max_dd, max_duration


def calculate_calmar_ratio(cagr: float, max_drawdown: float) -> float:
    """
    Calculate Calmar Ratio.

    Calmar = CAGR / |Max Drawdown|

    Args:
        cagr: Compound Annual Growth Rate
        max_drawdown: Maximum drawdown (negative number)

    Returns:
        Calmar Ratio
    """
    if max_drawdown >= 0:
        return float('inf') if cagr > 0 else 0.0

    return float(cagr / abs(max_drawdown))


def calculate_trade_stats(trades: List[Any]) -> dict:
    """
    Calculate trading statistics.

    Args:
        trades: List of Trade objects

    Returns:
        Dict with win_rate, profit_factor, avg_win, avg_loss
    """
    if not trades:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "trade_count": 0
        }

    # Group trades into round trips (buy -> sell pairs)
    # For simplicity, calculate based on individual trade P&L
    pnls = []
    position_cost = {}

    for trade in trades:
        if trade.action == "BUY":
            position_cost[trade.symbol] = position_cost.get(trade.symbol, 0) + trade.value
        else:  # SELL
            cost = position_cost.get(trade.symbol, 0)
            if cost > 0:
                pnl = trade.value - cost - trade.commission
                pnls.append(pnl)
                position_cost[trade.symbol] = 0

    if not pnls:
        return {
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "trade_count": len(trades)
        }

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = len(wins) / len(pnls) if pnls else 0
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0

    total_wins = sum(wins) if wins else 0
    total_losses = abs(sum(losses)) if losses else 0
    profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

    return {
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
        "avg_win": float(avg_win),
        "avg_loss": float(avg_loss),
        "trade_count": len(trades)
    }


def calculate_alpha_beta(
    returns: pd.Series,
    benchmark_returns: pd.Series
) -> tuple[float, float]:
    """
    Calculate alpha and beta vs benchmark.

    Args:
        returns: Strategy returns
        benchmark_returns: Benchmark returns

    Returns:
        Tuple of (alpha, beta)
    """
    # Align the series
    aligned = pd.concat([returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 30:
        return 0.0, 1.0

    strategy_ret = aligned.iloc[:, 0]
    benchmark_ret = aligned.iloc[:, 1]

    # Calculate beta
    covariance = strategy_ret.cov(benchmark_ret)
    benchmark_var = benchmark_ret.var()

    if benchmark_var == 0:
        return 0.0, 0.0

    beta = covariance / benchmark_var

    # Calculate alpha (annualized)
    alpha = (strategy_ret.mean() - beta * benchmark_ret.mean()) * TRADING_DAYS_PER_YEAR

    return float(alpha), float(beta)


def calculate_var_cvar(returns: pd.Series, confidence: float = 0.95) -> tuple[float, float]:
    """
    Calculate Value at Risk and Conditional VaR.

    Args:
        returns: Daily returns
        confidence: Confidence level (default 95%)

    Returns:
        Tuple of (VaR, CVaR) as positive numbers representing potential loss
    """
    if len(returns) < 30:
        return 0.0, 0.0

    sorted_returns = returns.sort_values()
    index = int((1 - confidence) * len(sorted_returns))

    var = abs(sorted_returns.iloc[index])
    cvar = abs(sorted_returns.iloc[:index + 1].mean())

    return float(var), float(cvar)


def calculate_metrics(
    returns: pd.Series,
    equity_curve: pd.Series,
    trades: List[Any],
    initial_capital: float,
    benchmark_returns: Optional[pd.Series] = None
) -> PerformanceMetrics:
    """
    Calculate all performance metrics.

    Args:
        returns: Daily returns series
        equity_curve: Portfolio value series
        trades: List of Trade objects
        initial_capital: Starting capital
        benchmark_returns: Optional benchmark returns for alpha/beta

    Returns:
        PerformanceMetrics dataclass
    """
    # Basic returns
    total_return = (equity_curve.iloc[-1] - initial_capital) / initial_capital
    years = len(returns) / TRADING_DAYS_PER_YEAR
    cagr = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0

    annual_vol = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    # Risk-adjusted metrics
    sharpe = calculate_sharpe_ratio(returns)
    sortino = calculate_sortino_ratio(returns)
    max_dd, max_dd_duration = calculate_max_drawdown(equity_curve)
    calmar = calculate_calmar_ratio(cagr, max_dd)

    # Drawdown stats
    drawdown = (equity_curve - equity_curve.cummax()) / equity_curve.cummax()
    avg_dd = float(drawdown[drawdown < 0].mean()) if (drawdown < 0).any() else 0.0

    # Trade stats
    trade_stats = calculate_trade_stats(trades)

    # Risk metrics
    var_95, cvar_95 = calculate_var_cvar(returns)

    # Distribution stats
    skewness = float(returns.skew()) if len(returns) > 2 else 0.0
    kurtosis = float(returns.kurtosis()) if len(returns) > 2 else 0.0

    # Alpha/Beta
    alpha, beta, info_ratio = None, None, None
    if benchmark_returns is not None and len(benchmark_returns) > 30:
        alpha, beta = calculate_alpha_beta(returns, benchmark_returns)

        # Information ratio
        active_returns = returns - benchmark_returns.reindex(returns.index).fillna(0)
        tracking_error = active_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
        if tracking_error > 0:
            info_ratio = float(active_returns.mean() * TRADING_DAYS_PER_YEAR / tracking_error)

    return PerformanceMetrics(
        total_return=float(total_return),
        cagr=float(cagr),
        annual_volatility=float(annual_vol),
        sharpe_ratio=float(sharpe),
        sortino_ratio=float(sortino),
        calmar_ratio=float(calmar),
        max_drawdown=float(max_dd),
        avg_drawdown=float(avg_dd),
        max_drawdown_duration_days=max_dd_duration,
        win_rate=trade_stats["win_rate"],
        profit_factor=trade_stats["profit_factor"],
        avg_win=trade_stats["avg_win"],
        avg_loss=trade_stats["avg_loss"],
        trade_count=trade_stats["trade_count"],
        alpha=alpha,
        beta=beta,
        information_ratio=info_ratio,
        skewness=skewness,
        kurtosis=kurtosis,
        var_95=var_95,
        cvar_95=cvar_95
    )


def print_metrics(metrics: PerformanceMetrics, title: str = "Performance Metrics") -> str:
    """Format metrics for display."""
    lines = [
        f"\n{'=' * 50}",
        f"  {title}",
        f"{'=' * 50}",
        "",
        "RETURNS",
        f"  Total Return:      {metrics.total_return:>10.2%}",
        f"  CAGR:              {metrics.cagr:>10.2%}",
        f"  Annual Volatility: {metrics.annual_volatility:>10.2%}",
        "",
        "RISK-ADJUSTED",
        f"  Sharpe Ratio:      {metrics.sharpe_ratio:>10.2f}",
        f"  Sortino Ratio:     {metrics.sortino_ratio:>10.2f}",
        f"  Calmar Ratio:      {metrics.calmar_ratio:>10.2f}",
        "",
        "DRAWDOWN",
        f"  Max Drawdown:      {metrics.max_drawdown:>10.2%}",
        f"  Avg Drawdown:      {metrics.avg_drawdown:>10.2%}",
        f"  Max DD Duration:   {metrics.max_drawdown_duration_days:>10d} days",
        "",
        "TRADING",
        f"  Trade Count:       {metrics.trade_count:>10d}",
        f"  Win Rate:          {metrics.win_rate:>10.2%}",
        f"  Profit Factor:     {metrics.profit_factor:>10.2f}",
        f"  Avg Win:           ${metrics.avg_win:>9.2f}",
        f"  Avg Loss:          ${metrics.avg_loss:>9.2f}",
        "",
        "RISK",
        f"  VaR (95%):         {metrics.var_95:>10.2%}",
        f"  CVaR (95%):        {metrics.cvar_95:>10.2%}",
        f"  Skewness:          {metrics.skewness:>10.2f}",
        f"  Kurtosis:          {metrics.kurtosis:>10.2f}",
    ]

    if metrics.alpha is not None:
        lines.extend([
            "",
            "VS BENCHMARK",
            f"  Alpha (annual):    {metrics.alpha:>10.2%}",
            f"  Beta:              {metrics.beta:>10.2f}",
        ])
        if metrics.information_ratio is not None:
            lines.append(f"  Information Ratio: {metrics.information_ratio:>10.2f}")

    lines.append(f"{'=' * 50}\n")

    return "\n".join(lines)
