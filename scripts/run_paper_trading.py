#!/usr/bin/env python3
"""
Paper trading runner for live strategy execution.

Usage:
    python -m scripts.run_paper_trading
    python -m scripts.run_paper_trading --strategy dual_momentum --check-only
"""

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from typing import Optional

from data.storage import TradingDatabase
from data.polygon_client import RateLimitedPolygonClient
from strategies.dual_momentum import DualMomentumStrategy
from strategies.base import Signal, SignalType
from risk.position_sizing import PositionSizer
from risk.circuit_breakers import CircuitBreaker
from execution.alpaca_client import AlpacaClient, AlpacaClientError
from execution.order_manager import OrderManager, RiskLimitExceeded
from execution.cash_manager import CashManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/paper_trading.log")
    ]
)
logger = logging.getLogger(__name__)


class PaperTradingRunner:
    """
    Automated paper trading execution.

    Runs the trading strategy and executes signals via Alpaca paper trading.
    """

    def __init__(
        self,
        strategy_name: str = "dual_momentum",
        db_path: str = "data/quant.db"
    ):
        """Initialize paper trading runner."""
        # Initialize components
        self.db = TradingDatabase(db_path)
        self.polygon = RateLimitedPolygonClient()

        # Initialize strategy
        if strategy_name == "dual_momentum":
            self.strategy = DualMomentumStrategy()
        else:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        # Initialize Alpaca (paper trading)
        self.alpaca = AlpacaClient(paper=True)

        # Get initial equity for circuit breaker
        account = self.alpaca.get_account()
        initial_equity = account["equity"]

        # Initialize risk components
        self.position_sizer = PositionSizer(
            max_position_pct=1.0,  # 100% for single-asset strategy
            method="fixed"
        )
        self.circuit_breaker = CircuitBreaker(initial_equity=initial_equity)

        # Initialize order manager
        self.order_manager = OrderManager(
            alpaca_client=self.alpaca,
            position_sizer=self.position_sizer,
            circuit_breaker=self.circuit_breaker,
            database=self.db
        )

        # Initialize cash manager
        self.cash_manager = CashManager(alpaca_client=self.alpaca)

        logger.info(
            "PaperTradingRunner initialized",
            extra={
                "strategy": strategy_name,
                "initial_equity": initial_equity,
                "paper": True
            }
        )

    def update_data(self) -> None:
        """Download latest market data."""
        logger.info("Updating market data...")

        end_date = date.today()
        start_date = end_date - timedelta(days=30)  # Last 30 days

        for symbol in self.strategy.universe:
            try:
                bars = self.polygon.get_daily_bars(
                    symbol=symbol,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat()
                )
                if bars:
                    self.db.insert_daily_bars(bars)
                    logger.info(f"Updated {symbol}: {len(bars)} bars")
            except Exception as e:
                logger.error(f"Failed to update {symbol}: {e}")

    def get_current_signal(self) -> Optional[Signal]:
        """Get current trading signal from strategy."""
        # Load historical data needed for signal generation
        required_history = self.strategy.get_required_history()
        start_date = date.today() - timedelta(days=int(required_history * 1.5))

        data = self.db.get_multiple_symbols(
            symbols=self.strategy.universe,
            start_date=start_date
        )

        # Generate current signal
        signal = self.strategy.get_current_signal(data, as_of_date=date.today())

        if signal:
            logger.info(
                "Current signal",
                extra={
                    "symbol": signal.symbol,
                    "type": signal.signal_type.value,
                    "date": signal.date
                }
            )

        return signal

    def get_current_state(self) -> dict:
        """Get current portfolio state."""
        account = self.alpaca.get_account()
        positions = self.alpaca.get_positions()

        return {
            "equity": account["equity"],
            "cash": account["cash"],
            "buying_power": account["buying_power"],
            "positions": positions
        }

    def execute_signal(self, signal: Signal) -> None:
        """Execute a trading signal."""
        if signal.signal_type == SignalType.HOLD:
            logger.info("Signal is HOLD, no action needed")
            return

        state = self.get_current_state()
        equity = state["equity"]
        positions = state["positions"]

        # Update circuit breaker
        self.circuit_breaker.update(equity)

        # Check if we can trade
        can_trade, halt_reason = self.circuit_breaker.can_trade()
        if not can_trade:
            logger.warning(f"Trading halted: {halt_reason}")
            return

        # Calculate target positions
        target_symbol = signal.symbol
        target_value = self.strategy.calculate_position_size(
            signal=signal,
            portfolio_value=equity,
            current_positions={s: p["market_value"] for s, p in positions.items()}
        )

        # Build target portfolio (100% in target, 0% elsewhere)
        target_positions = {target_symbol: target_value}
        for symbol in self.strategy.universe:
            if symbol != target_symbol:
                target_positions[symbol] = 0.0

        logger.info(
            "Executing rebalance",
            extra={
                "target_symbol": target_symbol,
                "target_value": target_value,
                "current_positions": list(positions.keys())
            }
        )

        # Execute rebalance
        try:
            orders = self.order_manager.execute_rebalance(
                target_positions=target_positions,
                strategy=self.strategy.name
            )

            for order in orders:
                logger.info(
                    "Order submitted",
                    extra={
                        "order_id": order.id,
                        "symbol": order.symbol,
                        "side": order.side,
                        "quantity": order.quantity
                    }
                )

        except RiskLimitExceeded as e:
            logger.error(f"Order rejected by risk manager: {e}")
        except AlpacaClientError as e:
            logger.error(f"Order execution failed: {e}")

    def check_and_trade(self) -> dict:
        """
        Check for signals and execute if needed.

        Returns:
            Status dict with actions taken
        """
        result = {
            "timestamp": datetime.now().isoformat(),
            "action": None,
            "signal": None,
            "error": None
        }

        try:
            # Log cash status
            cash_status = self.cash_manager.get_cash_status()
            logger.info(
                "Cash Status",
                extra={
                    "total_cash": f"${cash_status['total_cash']:,.2f}",
                    "available_cash": f"${cash_status['available_cash']:,.2f}",
                    "locked_cash": f"${cash_status['locked_cash']:,.2f}"
                }
            )

            # Update market data
            self.update_data()

            # Get current signal
            signal = self.get_current_signal()

            if signal:
                result["signal"] = {
                    "symbol": signal.symbol,
                    "type": signal.signal_type.value,
                    "date": signal.date.isoformat()
                }

                # Check if we need to trade
                state = self.get_current_state()
                current_positions = set(state["positions"].keys())
                target_symbol = signal.symbol if signal.signal_type == SignalType.BUY else None

                # Determine if rebalance needed
                if target_symbol:
                    if target_symbol not in current_positions or len(current_positions) > 1:
                        logger.info(f"Rebalance needed: target={target_symbol}, current={current_positions}")
                        self.execute_signal(signal)
                        result["action"] = "rebalanced"
                    else:
                        logger.info("Already in target position, no action needed")
                        result["action"] = "no_change"
                else:
                    result["action"] = "no_signal"

        except Exception as e:
            logger.error(f"Error during check_and_trade: {e}")
            result["error"] = str(e)

        return result

    def print_status(self) -> None:
        """Print current portfolio status."""
        state = self.get_current_state()
        risk_summary = self.circuit_breaker.get_risk_summary()

        print("\n" + "=" * 60)
        print("Paper Trading Status")
        print("=" * 60)

        print("\nAccount:")
        print(f"  Equity:       ${state['equity']:>12,.2f}")
        print(f"  Cash:         ${state['cash']:>12,.2f}")
        print(f"  Buying Power: ${state['buying_power']:>12,.2f}")

        print("\nPositions:")
        if state["positions"]:
            for symbol, pos in state["positions"].items():
                pnl_pct = pos["unrealized_plpc"] * 100
                print(f"  {symbol:6s}: {pos['qty']:>6d} shares @ ${pos['avg_entry_price']:>8.2f} "
                      f"(P&L: {pnl_pct:>+6.2f}%)")
        else:
            print("  No positions")

        print("\nRisk Status:")
        print(f"  Can Trade:        {risk_summary['can_trade']}")
        print(f"  Daily Return:     {risk_summary['daily_return']}")
        print(f"  Daily Headroom:   {risk_summary['daily_headroom']}")
        print(f"  Drawdown:         {risk_summary['drawdown']}")
        print(f"  Drawdown Headroom:{risk_summary['drawdown_headroom']}")

        print("\nCurrent Signal:")
        signal = self.get_current_signal()
        if signal:
            print(f"  {signal.signal_type.value} {signal.symbol} (as of {signal.date})")
        else:
            print("  No signal")

        print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Run paper trading")
    parser.add_argument(
        "--strategy",
        type=str,
        default="dual_momentum",
        help="Strategy to run"
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Only check status, don't execute trades"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/quant.db",
        help="Path to database"
    )

    args = parser.parse_args()

    try:
        runner = PaperTradingRunner(
            strategy_name=args.strategy,
            db_path=args.db
        )

        if args.check_only:
            runner.print_status()
        else:
            # Check market hours
            market = runner.alpaca.get_market_hours()
            if not market["is_open"]:
                logger.info(f"Market is closed. Next open: {market['next_open']}")

            # Execute trading logic
            result = runner.check_and_trade()

            print(f"\nResult: {result['action']}")
            if result["signal"]:
                print(f"Signal: {result['signal']}")
            if result["error"]:
                print(f"Error: {result['error']}")

            # Print final status
            runner.print_status()

    except Exception as e:
        logger.error(f"Paper trading failed: {e}")
        raise


if __name__ == "__main__":
    main()
