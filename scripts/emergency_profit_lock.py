#!/usr/bin/env python3
"""
Emergency profit locking script.

Immediately takes partial profits on winning positions and exits losers.
Use when system is giving back gains.

Usage:
    python -m scripts.emergency_profit_lock --execute
    python -m scripts.emergency_profit_lock --dry-run  # Preview only
"""

import argparse
import logging
from datetime import datetime
from typing import Dict, List
from execution.alpaca_client import AlpacaClient, AlpacaClientError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class EmergencyProfitLocker:
    """Emergency profit protection for current positions."""

    def __init__(self, dry_run: bool = True):
        self.alpaca = AlpacaClient(paper=True)
        self.dry_run = dry_run
        self.actions_planned = []

    def analyze_positions(self) -> List[Dict]:
        """
        Analyze all positions and determine emergency actions.

        Returns:
            List of recommended actions
        """
        positions = self.alpaca.get_positions()
        actions = []

        logger.info(f"\n{'='*70}")
        logger.info("EMERGENCY PROFIT PROTECTION ANALYSIS")
        logger.info(f"{'='*70}\n")

        for symbol, pos in positions.items():
            qty = int(pos['qty'])
            current_price = float(pos['current_price'])
            entry_price = float(pos['avg_entry_price'])
            unrealized_pnl_pct = float(pos['unrealized_plpc']) * 100

            logger.info(f"\n{symbol}:")
            logger.info(f"  Position: {qty} shares @ ${current_price:.2f}")
            logger.info(f"  Entry: ${entry_price:.2f}")
            logger.info(f"  P&L: {unrealized_pnl_pct:+.2f}%")

            # Determine action based on P&L
            action = self._determine_action(
                symbol, qty, current_price, entry_price, unrealized_pnl_pct
            )

            if action:
                actions.append(action)
                logger.info(f"  → ACTION: {action['action']}")
                if action['action'] == 'TAKE_PROFIT':
                    logger.info(f"    Sell {action['qty']} shares ({action['pct']:.0f}%)")
                    logger.info(f"    Lock profit: ${action['profit_locked']:.2f}")
            else:
                logger.info(f"  → No action needed")

        return actions

    def _determine_action(
        self,
        symbol: str,
        qty: int,
        current_price: float,
        entry_price: float,
        pnl_pct: float
    ) -> Dict:
        """Determine emergency action for position."""

        # STRONG WINNERS (>6%): Take 50% profit
        if pnl_pct >= 6.0:
            qty_to_sell = int(qty * 0.50)
            profit_locked = qty_to_sell * (current_price - entry_price)
            return {
                'symbol': symbol,
                'action': 'TAKE_PROFIT',
                'qty': qty_to_sell,
                'pct': 50,
                'reason': f'Strong winner (+{pnl_pct:.1f}%), protect gains',
                'profit_locked': profit_locked,
                'new_stop': entry_price,  # Move to breakeven
                'order_type': 'limit',
                'limit_price': current_price * 0.999  # Slightly below market
            }

        # GOOD WINNERS (3-6%): Take 33% profit
        elif pnl_pct >= 3.0:
            qty_to_sell = int(qty * 0.33)
            profit_locked = qty_to_sell * (current_price - entry_price)
            return {
                'symbol': symbol,
                'action': 'TAKE_PROFIT',
                'qty': qty_to_sell,
                'pct': 33,
                'reason': f'Good winner (+{pnl_pct:.1f}%), lock some profit',
                'profit_locked': profit_locked,
                'new_stop': entry_price,  # Move to breakeven
                'order_type': 'limit',
                'limit_price': current_price * 0.999
            }

        # SMALL WINNERS (1-3%): Move stop to breakeven only
        elif pnl_pct >= 1.0:
            return {
                'symbol': symbol,
                'action': 'MOVE_STOP',
                'new_stop': entry_price,
                'reason': f'Small winner (+{pnl_pct:.1f}%), protect breakeven',
                'qty': 0,
                'pct': 0,
                'profit_locked': 0
            }

        # LOSERS (<-1%): Exit immediately
        elif pnl_pct <= -1.0:
            profit_locked = qty * (current_price - entry_price)  # Negative
            return {
                'symbol': symbol,
                'action': 'EXIT_LOSER',
                'qty': qty,
                'pct': 100,
                'reason': f'Loser ({pnl_pct:.1f}%), cut loss',
                'profit_locked': profit_locked,
                'order_type': 'market',  # Use market order to exit fast
                'new_stop': None
            }

        # NEAR BREAKEVEN (-1% to +1%): Tighten stop
        else:
            return {
                'symbol': symbol,
                'action': 'TIGHTEN_STOP',
                'new_stop': entry_price * 0.99,  # 1% below entry
                'reason': f'Near breakeven ({pnl_pct:.1f}%), tighten stop',
                'qty': 0,
                'pct': 0,
                'profit_locked': 0
            }

    def execute_actions(self, actions: List[Dict]) -> Dict:
        """
        Execute emergency actions.

        Returns:
            Summary of executed actions
        """
        if self.dry_run:
            logger.info(f"\n{'='*70}")
            logger.info("DRY RUN MODE - No orders will be submitted")
            logger.info(f"{'='*70}\n")
            return self._summarize_actions(actions)

        logger.info(f"\n{'='*70}")
        logger.info("EXECUTING EMERGENCY ACTIONS")
        logger.info(f"{'='*70}\n")

        executed = []
        failed = []

        for action in actions:
            symbol = action['symbol']

            try:
                if action['action'] == 'TAKE_PROFIT':
                    # Submit sell order
                    order = self.alpaca.submit_limit_order(
                        symbol=symbol,
                        qty=action['qty'],
                        side='sell',
                        limit_price=action['limit_price']
                    )
                    logger.info(
                        f"✓ {symbol}: Sold {action['qty']} shares @ ${action['limit_price']:.2f} "
                        f"(locked ${action['profit_locked']:.2f})"
                    )
                    executed.append(action)

                    # Cancel existing stops and set new breakeven stop
                    if action.get('new_stop'):
                        self._update_stop(symbol, action['new_stop'])

                elif action['action'] == 'EXIT_LOSER':
                    # Exit entire position with market order
                    order = self.alpaca.submit_market_order(
                        symbol=symbol,
                        qty=action['qty'],
                        side='sell'
                    )
                    logger.info(
                        f"✓ {symbol}: Exited {action['qty']} shares (loss: ${action['profit_locked']:.2f})"
                    )
                    executed.append(action)

                elif action['action'] in ['MOVE_STOP', 'TIGHTEN_STOP']:
                    # Update stop loss
                    self._update_stop(symbol, action['new_stop'])
                    logger.info(
                        f"✓ {symbol}: Stop moved to ${action['new_stop']:.2f}"
                    )
                    executed.append(action)

            except AlpacaClientError as e:
                logger.error(f"✗ {symbol}: Failed - {e}")
                failed.append({'symbol': symbol, 'error': str(e)})

        return self._summarize_actions(actions, executed, failed)

    def _update_stop(self, symbol: str, stop_price: float):
        """Update stop loss for position."""
        try:
            # Cancel existing stop orders
            open_orders = self.alpaca.get_open_orders_for_symbol(symbol)
            for order in open_orders:
                if order.get('type') in ['stop', 'trailing_stop', 'stop_limit']:
                    self.alpaca.cancel_order(order['id'])

            # Get position size
            positions = self.alpaca.get_positions()
            if symbol not in positions:
                return

            qty = int(positions[symbol]['qty'])

            # Submit new stop order
            order = self.alpaca.submit_stop_order(
                symbol=symbol,
                qty=qty,
                side='sell',
                stop_price=stop_price
            )

            logger.debug(f"Stop order placed for {symbol} at ${stop_price:.2f}")

        except Exception as e:
            logger.warning(f"Could not update stop for {symbol}: {e}")

    def _summarize_actions(
        self,
        planned: List[Dict],
        executed: List[Dict] = None,
        failed: List[Dict] = None
    ) -> Dict:
        """Summarize emergency actions."""
        executed = executed or []
        failed = failed or []

        total_profit_locked = sum(
            a.get('profit_locked', 0) for a in (executed if executed else planned)
            if a['action'] in ['TAKE_PROFIT', 'EXIT_LOSER']
        )

        summary = {
            'timestamp': datetime.now().isoformat(),
            'dry_run': self.dry_run,
            'total_actions_planned': len(planned),
            'actions_executed': len(executed),
            'actions_failed': len(failed),
            'total_profit_locked': total_profit_locked,
            'actions': planned
        }

        logger.info(f"\n{'='*70}")
        logger.info("SUMMARY")
        logger.info(f"{'='*70}")
        logger.info(f"Total actions planned: {len(planned)}")
        if not self.dry_run:
            logger.info(f"Successfully executed: {len(executed)}")
            logger.info(f"Failed: {len(failed)}")
        logger.info(f"Total profit locked: ${total_profit_locked:.2f}")
        logger.info(f"{'='*70}\n")

        return summary


def main():
    parser = argparse.ArgumentParser(
        description="Emergency profit locking for positions giving back gains"
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Execute actions (default is dry-run)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview actions without executing (default)'
    )

    args = parser.parse_args()

    # If --execute is specified, turn off dry-run
    dry_run = not args.execute

    logger.info("Emergency Profit Locker")
    logger.info(f"Mode: {'DRY RUN' if dry_run else 'LIVE EXECUTION'}")
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    try:
        locker = EmergencyProfitLocker(dry_run=dry_run)

        # Analyze positions
        actions = locker.analyze_positions()

        if not actions:
            logger.info("No emergency actions needed. All positions look good!")
            return

        # Ask for confirmation if executing
        if not dry_run:
            logger.info(f"\n⚠️  READY TO EXECUTE {len(actions)} ACTIONS ⚠️")
            response = input("\nType 'YES' to confirm: ")
            if response != 'YES':
                logger.info("Cancelled by user")
                return

        # Execute
        summary = locker.execute_actions(actions)

        if not dry_run:
            logger.info("\n✅ Emergency profit locking complete!")
            logger.info(f"Locked ${summary['total_profit_locked']:.2f} in profits")

    except Exception as e:
        logger.error(f"Emergency profit locking failed: {e}")
        raise


if __name__ == "__main__":
    main()
