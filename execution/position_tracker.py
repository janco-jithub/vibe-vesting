"""
Position Tracker with Advanced Profit Optimization

Tracks open positions and applies profit optimization techniques:
- Maintains highest price since entry for trailing stops
- Tracks scale-in and scale-out history
- Calculates position metrics (P&L, holding period, etc.)
- Interfaces with ProfitOptimizer to generate trade actions

Used by auto_trader to monitor and optimize all active positions.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd

from risk.profit_optimizer import (
    ProfitOptimizer,
    PositionState,
    TradeAction
)

logger = logging.getLogger(__name__)

# Valid strategy names - prevents "unknown" from being stored
VALID_STRATEGIES = {
    'factor_composite',
    'simple_momentum',
    'pairs_trading',
    'swing_momentum',
    'ml_momentum',
    'dual_momentum',
    'volatility_breakout',
    'manual_review'  # Special flag for positions requiring manual review
}

# Import database for persistence
try:
    from data.storage import TradingDatabase
except ImportError:
    TradingDatabase = None
    logger.warning("TradingDatabase not available - position tracker will not persist state")


class PositionTracker:
    """
    Track and optimize open positions.

    Maintains state for each position and generates optimization actions
    by interfacing with ProfitOptimizer.
    """

    def __init__(
        self,
        profit_optimizer: Optional[ProfitOptimizer] = None,
        database: Optional['TradingDatabase'] = None,
        auto_persist: bool = True
    ):
        """
        Initialize position tracker.

        Args:
            profit_optimizer: ProfitOptimizer instance (creates default if None)
            database: TradingDatabase instance for persistence (optional)
            auto_persist: Automatically save state after changes (default: True)
        """
        self.optimizer = profit_optimizer or ProfitOptimizer()
        self.positions: Dict[str, PositionState] = {}
        self.highest_prices: Dict[str, float] = {}  # Track highest price since entry
        self.position_history: Dict[str, List[Dict]] = {}  # Track all actions per position

        # Database persistence
        self.database = database
        self.auto_persist = auto_persist

        logger.info("PositionTracker initialized")

    def add_position(
        self,
        symbol: str,
        entry_price: float,
        quantity: int,
        side: str,
        stop_loss: float,
        take_profit: Optional[float] = None,
        strategy: str = "",
        signal_strength: float = 0.0,
        atr: Optional[float] = None
    ) -> None:
        """
        Add a new position to track.

        Args:
            symbol: Symbol ticker
            entry_price: Entry price
            quantity: Number of shares
            side: 'long' or 'short'
            stop_loss: Initial stop loss price
            take_profit: Initial take profit price
            strategy: Strategy name that generated the signal (must be valid)
            signal_strength: Signal strength (0-1)
            atr: Average True Range for volatility-based stops

        Raises:
            ValueError: If strategy is invalid (empty, "unknown", or not in VALID_STRATEGIES)
        """
        # Validate strategy - NEVER allow "unknown"
        if not strategy or strategy == "unknown":
            raise ValueError(
                f"Invalid strategy '{strategy}' for {symbol}. "
                f"Strategy must be one of: {sorted(VALID_STRATEGIES)}"
            )

        if strategy not in VALID_STRATEGIES:
            logger.warning(
                f"Strategy '{strategy}' not in known strategies list. "
                f"Valid strategies: {sorted(VALID_STRATEGIES)}"
            )
            # Don't raise - allow new strategies, but log warning
        position = PositionState(
            symbol=symbol,
            entry_price=entry_price,
            entry_time=datetime.now(),
            quantity=quantity,
            side=side,
            current_price=entry_price,
            unrealized_pnl=0.0,
            unrealized_pnl_pct=0.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
            trailing_stop=None,
            scale_in_count=0,
            scale_out_count=0,
            strategy=strategy,
            signal_strength=signal_strength,
            atr=atr
        )

        self.positions[symbol] = position
        self.highest_prices[symbol] = entry_price
        self.position_history[symbol] = [{
            'timestamp': datetime.now(),
            'action': 'entry',
            'price': entry_price,
            'quantity': quantity,
            'total_quantity': quantity
        }]

        logger.info(
            f"Position added: {symbol} {side} {quantity} @ ${entry_price:.2f}, "
            f"stop=${stop_loss:.2f}, strategy={strategy}"
        )

        # Save to database
        self._save_to_database()

    def update_position(
        self,
        symbol: str,
        current_price: float,
        quantity: Optional[int] = None
    ) -> None:
        """
        Update position with current market price.

        Args:
            symbol: Symbol ticker
            current_price: Current market price
            quantity: Current quantity (if position size changed)
        """
        if symbol not in self.positions:
            logger.warning(f"Cannot update unknown position: {symbol}")
            return

        position = self.positions[symbol]
        position.current_price = current_price

        if quantity is not None:
            position.quantity = quantity

        # Update P&L
        if position.side == 'long':
            position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
            position.unrealized_pnl_pct = (current_price - position.entry_price) / position.entry_price
        else:
            # Short position
            position.unrealized_pnl = (position.entry_price - current_price) * position.quantity
            position.unrealized_pnl_pct = (position.entry_price - current_price) / position.entry_price

        # Update highest price for trailing stops
        if current_price > self.highest_prices.get(symbol, 0):
            self.highest_prices[symbol] = current_price

        logger.debug(
            f"Position updated: {symbol} @ ${current_price:.2f}, "
            f"P&L: ${position.unrealized_pnl:+.2f} ({position.unrealized_pnl_pct*100:+.2f}%)"
        )

        # Save to database
        self._save_to_database()

    def remove_position(self, symbol: str, reason: str = "") -> None:
        """
        Remove a position (after close/exit).

        Args:
            symbol: Symbol ticker
            reason: Reason for removal
        """
        if symbol in self.positions:
            position = self.positions[symbol]

            # Record final state
            if symbol in self.position_history:
                self.position_history[symbol].append({
                    'timestamp': datetime.now(),
                    'action': 'close',
                    'price': position.current_price,
                    'quantity': position.quantity,
                    'total_quantity': 0,
                    'pnl': position.unrealized_pnl,
                    'pnl_pct': position.unrealized_pnl_pct,
                    'reason': reason
                })

            del self.positions[symbol]
            if symbol in self.highest_prices:
                del self.highest_prices[symbol]

            logger.info(
                f"Position removed: {symbol}, "
                f"final P&L: ${position.unrealized_pnl:+.2f} ({position.unrealized_pnl_pct*100:+.2f}%), "
                f"reason: {reason}"
            )

            # Remove from database
            self._remove_from_database(symbol)

    def scale_in(
        self,
        symbol: str,
        add_quantity: int,
        add_price: float
    ) -> None:
        """
        Record a scale-in (add to position).

        Args:
            symbol: Symbol ticker
            add_quantity: Shares added
            add_price: Price of addition
        """
        if symbol not in self.positions:
            logger.warning(f"Cannot scale in to unknown position: {symbol}")
            return

        position = self.positions[symbol]

        # Update average entry price
        total_cost = (position.entry_price * position.quantity) + (add_price * add_quantity)
        new_quantity = position.quantity + add_quantity
        position.entry_price = total_cost / new_quantity
        position.quantity = new_quantity
        position.scale_in_count += 1

        # Record in history
        self.position_history[symbol].append({
            'timestamp': datetime.now(),
            'action': 'scale_in',
            'price': add_price,
            'quantity': add_quantity,
            'total_quantity': new_quantity,
            'avg_price': position.entry_price
        })

        logger.info(
            f"Scaled into {symbol}: +{add_quantity} @ ${add_price:.2f}, "
            f"new qty={new_quantity}, new avg=${position.entry_price:.2f}"
        )

        # Save to database
        self._save_to_database()

    def scale_out(
        self,
        symbol: str,
        reduce_quantity: int,
        exit_price: float
    ) -> float:
        """
        Record a scale-out (partial profit taking).

        Args:
            symbol: Symbol ticker
            reduce_quantity: Shares sold
            exit_price: Price of sale

        Returns:
            Realized P&L from the partial exit
        """
        if symbol not in self.positions:
            logger.warning(f"Cannot scale out of unknown position: {symbol}")
            return 0.0

        position = self.positions[symbol]

        # Calculate realized P&L on the portion sold
        if position.side == 'long':
            realized_pnl = (exit_price - position.entry_price) * reduce_quantity
        else:
            realized_pnl = (position.entry_price - exit_price) * reduce_quantity

        # Update position
        position.quantity -= reduce_quantity
        position.scale_out_count += 1

        # Record in history
        self.position_history[symbol].append({
            'timestamp': datetime.now(),
            'action': 'scale_out',
            'price': exit_price,
            'quantity': reduce_quantity,
            'total_quantity': position.quantity,
            'realized_pnl': realized_pnl
        })

        logger.info(
            f"Scaled out of {symbol}: -{reduce_quantity} @ ${exit_price:.2f}, "
            f"realized P&L: ${realized_pnl:+.2f}, remaining qty={position.quantity}"
        )

        # Save to database
        self._save_to_database()

        return realized_pnl

    def update_stop_loss(self, symbol: str, new_stop: float) -> None:
        """
        Update stop loss for a position.

        Args:
            symbol: Symbol ticker
            new_stop: New stop loss price
        """
        if symbol not in self.positions:
            logger.warning(f"Cannot update stop for unknown position: {symbol}")
            return

        position = self.positions[symbol]
        old_stop = position.stop_loss
        position.stop_loss = new_stop

        # Record in history
        self.position_history[symbol].append({
            'timestamp': datetime.now(),
            'action': 'update_stop',
            'old_stop': old_stop,
            'new_stop': new_stop
        })

        logger.info(f"Stop loss updated for {symbol}: ${old_stop:.2f} -> ${new_stop:.2f}")

        # Save to database
        self._save_to_database()

    def get_optimization_actions(
        self,
        symbol: str,
        vix: float = 20.0,
        signal_strength: float = 0.0
    ) -> List[TradeAction]:
        """
        Get recommended optimization actions for a position.

        Args:
            symbol: Symbol ticker
            vix: Current VIX level
            signal_strength: Current signal strength for the position

        Returns:
            List of TradeActions to execute
        """
        if symbol not in self.positions:
            return []

        position = self.positions[symbol]
        highest_price = self.highest_prices.get(symbol, position.entry_price)

        logger.debug(
            f"Optimizing {symbol}: entry=${position.entry_price:.2f}, "
            f"current=${position.current_price:.2f}, "
            f"highest=${highest_price:.2f}, "
            f"stop=${position.stop_loss:.2f}, "
            f"pnl={position.unrealized_pnl_pct*100:+.2f}%"
        )

        return self.optimizer.optimize_position(
            position=position,
            vix=vix,
            signal_strength=signal_strength,
            highest_price_since_entry=highest_price
        )

    def get_all_optimization_actions(
        self,
        vix: float = 20.0,
        signal_strengths: Optional[Dict[str, float]] = None
    ) -> List[TradeAction]:
        """
        Get optimization actions for all positions.

        Args:
            vix: Current VIX level
            signal_strengths: Dict mapping symbol to current signal strength

        Returns:
            List of all recommended TradeActions
        """
        signal_strengths = signal_strengths or {}
        all_actions = []

        for symbol in list(self.positions.keys()):
            signal_strength = signal_strengths.get(symbol, 0.0)
            actions = self.get_optimization_actions(symbol, vix, signal_strength)
            all_actions.extend(actions)

        return all_actions

    def get_position_summary(self) -> pd.DataFrame:
        """
        Get summary of all positions.

        Returns:
            DataFrame with position details
        """
        if not self.positions:
            return pd.DataFrame()

        data = []
        for symbol, pos in self.positions.items():
            holding_period = (datetime.now() - pos.entry_time).total_seconds() / 3600  # hours

            data.append({
                'symbol': symbol,
                'side': pos.side,
                'quantity': pos.quantity,
                'entry_price': pos.entry_price,
                'current_price': pos.current_price,
                'unrealized_pnl': pos.unrealized_pnl,
                'unrealized_pnl_pct': pos.unrealized_pnl_pct * 100,
                'stop_loss': pos.stop_loss,
                'take_profit': pos.take_profit,
                'scale_ins': pos.scale_in_count,
                'scale_outs': pos.scale_out_count,
                'holding_hours': holding_period,
                'strategy': pos.strategy
            })

        df = pd.DataFrame(data)
        return df.sort_values('unrealized_pnl_pct', ascending=False)

    def get_position_history(self, symbol: str) -> List[Dict]:
        """
        Get full history of actions for a position.

        Args:
            symbol: Symbol ticker

        Returns:
            List of historical actions
        """
        return self.position_history.get(symbol, [])

    def check_stop_hits(self) -> List[str]:
        """
        Check which positions have hit their stop losses.

        Returns:
            List of symbols that should be closed (stop hit)
        """
        stops_hit = []

        for symbol, position in self.positions.items():
            if position.side == 'long':
                if position.current_price <= position.stop_loss:
                    stops_hit.append(symbol)
                    logger.warning(
                        f"Stop loss HIT for {symbol}: "
                        f"${position.current_price:.2f} <= ${position.stop_loss:.2f}"
                    )
            else:
                # Short position
                if position.current_price >= position.stop_loss:
                    stops_hit.append(symbol)
                    logger.warning(
                        f"Stop loss HIT for {symbol} (short): "
                        f"${position.current_price:.2f} >= ${position.stop_loss:.2f}"
                    )

        return stops_hit

    def check_take_profit_hits(self) -> List[str]:
        """
        Check which positions have hit their take profit levels.

        Returns:
            List of symbols that should be closed (take profit hit)
        """
        tp_hits = []

        for symbol, position in self.positions.items():
            if position.take_profit is None:
                continue

            if position.side == 'long':
                if position.current_price >= position.take_profit:
                    tp_hits.append(symbol)
                    logger.info(
                        f"Take profit HIT for {symbol}: "
                        f"${position.current_price:.2f} >= ${position.take_profit:.2f}"
                    )
            else:
                # Short position
                if position.current_price <= position.take_profit:
                    tp_hits.append(symbol)
                    logger.info(
                        f"Take profit HIT for {symbol} (short): "
                        f"${position.current_price:.2f} <= ${position.take_profit:.2f}"
                    )

        return tp_hits

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized P&L across all positions."""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_position_count(self) -> int:
        """Get number of open positions."""
        return len(self.positions)

    def get_winning_positions(self) -> List[str]:
        """Get list of symbols with positive P&L."""
        return [
            symbol for symbol, pos in self.positions.items()
            if pos.unrealized_pnl > 0
        ]

    def get_losing_positions(self) -> List[str]:
        """Get list of symbols with negative P&L."""
        return [
            symbol for symbol, pos in self.positions.items()
            if pos.unrealized_pnl < 0
        ]

    # ==================== Persistence ====================

    def _save_to_database(self) -> None:
        """Save current positions to database."""
        if not self.auto_persist or not self.database:
            return

        try:
            # Convert positions to dict format for database
            positions_dict = {}
            for symbol, pos in self.positions.items():
                positions_dict[symbol] = {
                    'entry_price': pos.entry_price,
                    'entry_time': pos.entry_time.isoformat(),
                    'quantity': pos.quantity,
                    'side': pos.side,
                    'stop_loss': pos.stop_loss,
                    'take_profit': pos.take_profit,
                    'highest_price': self.highest_prices.get(symbol, pos.entry_price),
                    'lowest_price': pos.entry_price,  # Not tracked separately yet
                    'scale_ins': pos.scale_in_count,
                    'scale_outs': pos.scale_out_count,
                    'strategy': pos.strategy,
                    'atr': pos.atr,
                    'signal_strength': pos.signal_strength
                }

            self.database.save_position_tracker_state(positions_dict)
        except Exception as e:
            logger.error(f"Failed to save position tracker state: {e}")

    def _remove_from_database(self, symbol: str) -> None:
        """Remove position from database."""
        if not self.database:
            return

        try:
            self.database.remove_position_tracker_state(symbol)
        except Exception as e:
            logger.error(f"Failed to remove position tracker state for {symbol}: {e}")

    def load_state_from_database(self) -> int:
        """
        Load position tracker state from database.

        This should be called on startup to restore positions after a restart.

        Returns:
            Number of positions loaded
        """
        if not self.database:
            logger.warning("No database configured - cannot load position state")
            return 0

        try:
            positions_dict = self.database.load_position_tracker_state()

            # Restore positions
            for symbol, pos_data in positions_dict.items():
                # Parse entry time
                entry_time = datetime.fromisoformat(pos_data['entry_time'])

                # Create PositionState
                position = PositionState(
                    symbol=symbol,
                    entry_price=pos_data['entry_price'],
                    entry_time=entry_time,
                    quantity=pos_data['quantity'],
                    side=pos_data['side'],
                    current_price=pos_data['entry_price'],  # Will be updated on next sync
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                    stop_loss=pos_data['stop_loss'],
                    take_profit=pos_data['take_profit'],
                    trailing_stop=None,
                    scale_in_count=pos_data['scale_ins'],
                    scale_out_count=pos_data['scale_outs'],
                    strategy=pos_data['strategy'],
                    signal_strength=pos_data['signal_strength'],
                    atr=pos_data['atr']
                )

                self.positions[symbol] = position
                self.highest_prices[symbol] = pos_data['highest_price']

                # Initialize history
                self.position_history[symbol] = [{
                    'timestamp': entry_time,
                    'action': 'loaded_from_db',
                    'price': pos_data['entry_price'],
                    'quantity': pos_data['quantity'],
                    'total_quantity': pos_data['quantity']
                }]

            logger.info(f"Loaded {len(positions_dict)} positions from database")
            return len(positions_dict)

        except Exception as e:
            logger.error(f"Failed to load position tracker state: {e}")
            return 0

    def force_save(self) -> None:
        """Force save current state to database (even if auto_persist is False)."""
        if not self.database:
            logger.warning("No database configured - cannot save state")
            return

        # Temporarily enable auto_persist
        original_persist = self.auto_persist
        self.auto_persist = True
        self._save_to_database()
        self.auto_persist = original_persist

        logger.info("Forced save of position tracker state")
