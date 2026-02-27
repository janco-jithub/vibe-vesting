"""
SQLite storage layer for market data and trades.

Provides persistent storage for:
- Daily OHLCV bars
- Trade records
- Portfolio snapshots

Optimized for long-running operation with:
- WAL mode for better concurrency
- Connection pooling
- Busy timeout to prevent hangs
"""

import sqlite3
import json
import os
import threading
from typing import List, Dict, Optional, Any
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from contextlib import contextmanager
import logging
import time

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


class TradingDatabase:
    """
    SQLite database for market data and trading records.

    Tables:
        - daily_bars: OHLCV price data
        - trades: Executed trade records
        - portfolio_snapshots: Daily portfolio state
        - signals: Strategy signal history

    Attributes:
        db_path: Path to SQLite database file
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database connection and schema.

        Args:
            db_path: Path to SQLite database. If None, uses DATABASE_PATH env var.
        """
        self.db_path = db_path or os.getenv("DATABASE_PATH", "data/quant.db")

        # Ensure parent directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # Thread-local storage for connections (connection pooling)
        self._local = threading.local()

        # Track all connections for cleanup
        self._all_connections: List[sqlite3.Connection] = []
        self._connections_lock = threading.Lock()

        self._init_schema()
        self._enable_wal_mode()
        logger.info("Database initialized", extra={"path": self.db_path})

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get a database connection with row factory.

        Uses thread-local storage to reuse connections within the same thread,
        preventing connection exhaustion during long-running operation.
        Tracks all connections for proper cleanup.
        """
        # Check if we have a connection for this thread
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,  # Wait up to 30 seconds for locks
                check_same_thread=False,
                isolation_level=None  # Autocommit mode - prevents lock accumulation
            )
            conn.row_factory = sqlite3.Row
            # Set busy timeout to prevent "database is locked" errors
            conn.execute("PRAGMA busy_timeout = 30000")
            self._local.conn = conn

            # Track this connection for cleanup
            with self._connections_lock:
                self._all_connections.append(conn)

        return self._local.conn

    def _enable_wal_mode(self) -> None:
        """Enable WAL mode for better concurrency and crash recovery."""
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.close()
            logger.info("WAL mode enabled for database")
        except Exception as e:
            logger.warning(f"Failed to enable WAL mode: {e}")

    @contextmanager
    def get_connection(self):
        """Context manager for database connections (for external use)."""
        conn = self._get_connection()
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise
        finally:
            # Don't close - we're reusing connections
            pass

    def close(self) -> None:
        """Close the database connection for this thread."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def close_all_connections(self) -> None:
        """
        Close ALL database connections from all threads.

        Call this during periodic cleanup to prevent connection leaks
        and "database is locked" errors in long-running processes.
        """
        with self._connections_lock:
            closed_count = 0
            for conn in self._all_connections:
                try:
                    conn.close()
                    closed_count += 1
                except Exception:
                    pass
            self._all_connections.clear()

            # Also clear thread-local connection
            if hasattr(self._local, 'conn'):
                self._local.conn = None

            if closed_count > 0:
                logger.info(f"Closed {closed_count} database connections during cleanup")

    def _init_schema(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Daily OHLCV bars
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_bars (
                    symbol TEXT NOT NULL,
                    date DATE NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, date)
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_bars_symbol_date
                ON daily_bars(symbol, date)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_bars_date
                ON daily_bars(date)
            """)

            # Trade records
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL CHECK(action IN ('BUY', 'SELL')),
                    quantity REAL NOT NULL,
                    price REAL NOT NULL,
                    commission REAL DEFAULT 0,
                    order_id TEXT,
                    strategy TEXT,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_timestamp
                ON trades(timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_symbol
                ON trades(symbol)
            """)

            # Portfolio snapshots
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    date DATE PRIMARY KEY,
                    equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    positions TEXT,
                    daily_pnl REAL,
                    daily_return REAL,
                    drawdown REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Strategy signals
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL,
                    strategy TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    signal_value REAL,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_date_strategy
                ON signals(date, strategy)
            """)

            # Position tracker state persistence
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_tracker (
                    symbol TEXT PRIMARY KEY,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('long', 'short')),
                    stop_loss REAL,
                    take_profit REAL,
                    highest_price REAL,
                    lowest_price REAL,
                    scale_ins INTEGER DEFAULT 0,
                    scale_outs INTEGER DEFAULT 0,
                    strategy TEXT,
                    atr REAL,
                    signal_strength REAL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_position_tracker_updated
                ON position_tracker(updated_at)
            """)

            # Daily performance journal for manual tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL UNIQUE,
                    starting_equity REAL NOT NULL,
                    ending_equity REAL NOT NULL,
                    daily_pnl REAL NOT NULL,
                    daily_pnl_pct REAL NOT NULL,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_journal_date
                ON daily_journal(date)
            """)

            conn.commit()

    # ==================== Daily Bars ====================

    def insert_daily_bars(self, bars: List[Dict]) -> int:
        """
        Insert or update daily bar data.

        Args:
            bars: List of dicts with keys: symbol, date, open, high, low, close, volume

        Returns:
            Number of rows inserted/updated
        """
        if not bars:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Convert date objects to strings for SQLite
            processed_bars = []
            for bar in bars:
                processed_bar = bar.copy()
                if isinstance(processed_bar.get("date"), date):
                    processed_bar["date"] = processed_bar["date"].isoformat()
                processed_bars.append(processed_bar)

            cursor.executemany("""
                INSERT OR REPLACE INTO daily_bars
                (symbol, date, open, high, low, close, volume)
                VALUES (:symbol, :date, :open, :high, :low, :close, :volume)
            """, processed_bars)

            conn.commit()

            logger.info("Inserted daily bars", extra={"count": len(bars)})
            return len(bars)

    def get_daily_bars(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Retrieve daily bars as a pandas DataFrame.

        Args:
            symbol: Ticker symbol
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            DataFrame with DatetimeIndex and columns: open, high, low, close, volume
        """
        query = "SELECT date, open, high, low, close, volume FROM daily_bars WHERE symbol = ?"
        params: List[Any] = [symbol.upper()]

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat() if isinstance(start_date, date) else start_date)

        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat() if isinstance(end_date, date) else end_date)

        query += " ORDER BY date"

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params, parse_dates=["date"])
            if not df.empty:
                df.set_index("date", inplace=True)

        logger.debug("Retrieved daily bars", extra={"symbol": symbol, "rows": len(df)})
        return df

    def get_multiple_symbols(
        self,
        symbols: List[str],
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Retrieve daily bars for multiple symbols.

        Args:
            symbols: List of ticker symbols
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dict mapping symbol to DataFrame
        """
        return {
            symbol: self.get_daily_bars(symbol, start_date, end_date)
            for symbol in symbols
        }

    def get_latest_date(self, symbol: str) -> Optional[date]:
        """Get the most recent date with data for a symbol."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT MAX(date) FROM daily_bars WHERE symbol = ?",
                (symbol.upper(),)
            )
            result = cursor.fetchone()[0]
            if result:
                return datetime.strptime(result, "%Y-%m-%d").date()
            return None

    def get_symbols(self) -> List[str]:
        """Get list of all symbols in database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT symbol FROM daily_bars ORDER BY symbol")
            return [row[0] for row in cursor.fetchall()]

    # ==================== Trades ====================

    def insert_trade(
        self,
        timestamp: datetime,
        symbol: str,
        action: str,
        quantity: float,
        price: float,
        commission: float = 0.0,
        order_id: Optional[str] = None,
        strategy: Optional[str] = None,
        notes: Optional[str] = None
    ) -> int:
        """
        Record a trade execution.

        Args:
            timestamp: Trade execution time
            symbol: Ticker symbol
            action: 'BUY' or 'SELL'
            quantity: Number of shares
            price: Execution price
            commission: Commission paid
            order_id: Broker order ID
            strategy: Strategy that generated the trade
            notes: Additional notes

        Returns:
            Trade ID
        """
        if action not in ("BUY", "SELL"):
            raise ValueError(f"Invalid action: {action}. Must be 'BUY' or 'SELL'.")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO trades
                (timestamp, symbol, action, quantity, price, commission, order_id, strategy, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, symbol.upper(), action, quantity, price, commission, order_id, strategy, notes))

            conn.commit()
            trade_id = cursor.lastrowid

            logger.info(
                "Trade recorded",
                extra={
                    "trade_id": trade_id,
                    "symbol": symbol,
                    "action": action,
                    "quantity": quantity,
                    "price": price
                }
            )
            return trade_id

    def get_trades(
        self,
        symbol: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        strategy: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Retrieve trade records.

        Args:
            symbol: Optional symbol filter
            start_date: Optional start date filter
            end_date: Optional end date filter
            strategy: Optional strategy filter

        Returns:
            DataFrame with trade records
        """
        query = "SELECT * FROM trades WHERE 1=1"
        params: List[Any] = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())

        if start_date:
            query += " AND date(timestamp) >= ?"
            params.append(start_date.isoformat() if isinstance(start_date, date) else start_date)

        if end_date:
            query += " AND date(timestamp) <= ?"
            params.append(end_date.isoformat() if isinstance(end_date, date) else end_date)

        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)

        query += " ORDER BY timestamp"

        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params, parse_dates=["timestamp"])

    # ==================== Portfolio Snapshots ====================

    def save_portfolio_snapshot(
        self,
        snapshot_date: date,
        equity: float,
        cash: float,
        positions: Dict[str, float],
        daily_pnl: Optional[float] = None,
        daily_return: Optional[float] = None,
        drawdown: Optional[float] = None
    ) -> None:
        """
        Save a daily portfolio snapshot.

        Args:
            snapshot_date: Date of snapshot
            equity: Total portfolio value
            cash: Cash balance
            positions: Dict mapping symbol to quantity
            daily_pnl: Daily profit/loss in dollars
            daily_return: Daily return as decimal
            drawdown: Current drawdown from peak as decimal
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO portfolio_snapshots
                (date, equity, cash, positions, daily_pnl, daily_return, drawdown)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_date.isoformat() if isinstance(snapshot_date, date) else snapshot_date,
                equity,
                cash,
                json.dumps(positions),
                daily_pnl,
                daily_return,
                drawdown
            ))
            conn.commit()

            logger.debug(
                "Portfolio snapshot saved",
                extra={"date": snapshot_date, "equity": equity}
            )

    def get_portfolio_history(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Retrieve portfolio snapshot history.

        Returns:
            DataFrame with portfolio history indexed by date
        """
        query = "SELECT * FROM portfolio_snapshots WHERE 1=1"
        params: List[Any] = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat() if isinstance(start_date, date) else start_date)

        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat() if isinstance(end_date, date) else end_date)

        query += " ORDER BY date"

        with self._get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params, parse_dates=["date"])
            if not df.empty:
                df.set_index("date", inplace=True)
                # Parse positions JSON
                if "positions" in df.columns:
                    df["positions"] = df["positions"].apply(
                        lambda x: json.loads(x) if x else {}
                    )
            return df

    # ==================== Signals ====================

    def save_signal(
        self,
        signal_date: date,
        strategy: str,
        symbol: str,
        signal_type: str,
        signal_value: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Record a strategy signal.

        Args:
            signal_date: Date signal was generated
            strategy: Strategy name
            symbol: Target symbol
            signal_type: Type of signal (e.g., 'BUY', 'SELL', 'HOLD')
            signal_value: Numeric signal value
            metadata: Additional signal metadata

        Returns:
            Signal ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signals
                (date, strategy, symbol, signal_type, signal_value, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                signal_date.isoformat() if isinstance(signal_date, date) else signal_date,
                strategy,
                symbol.upper(),
                signal_type,
                signal_value,
                json.dumps(metadata) if metadata else None
            ))
            conn.commit()
            return cursor.lastrowid

    def get_signals(
        self,
        strategy: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """Retrieve signal history."""
        query = "SELECT * FROM signals WHERE 1=1"
        params: List[Any] = []

        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat() if isinstance(start_date, date) else start_date)

        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat() if isinstance(end_date, date) else end_date)

        query += " ORDER BY date, strategy"

        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params, parse_dates=["date"])

    # ==================== Position Tracker State ====================

    def save_position_tracker_state(self, positions: Dict[str, Any]) -> None:
        """
        Save position tracker state to database.

        Args:
            positions: Dict mapping symbol to position state dict with keys:
                - entry_price, entry_time, quantity, side, stop_loss, take_profit,
                  highest_price, lowest_price, scale_ins, scale_outs, strategy,
                  atr, signal_strength
        """
        if not positions:
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()

            for symbol, pos in positions.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO position_tracker
                    (symbol, entry_price, entry_time, quantity, side, stop_loss, take_profit,
                     highest_price, lowest_price, scale_ins, scale_outs, strategy, atr,
                     signal_strength, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    symbol,
                    pos.get('entry_price'),
                    pos.get('entry_time'),
                    pos.get('quantity'),
                    pos.get('side'),
                    pos.get('stop_loss'),
                    pos.get('take_profit'),
                    pos.get('highest_price'),
                    pos.get('lowest_price'),
                    pos.get('scale_ins', 0),
                    pos.get('scale_outs', 0),
                    pos.get('strategy'),
                    pos.get('atr'),
                    pos.get('signal_strength')
                ))

            conn.commit()
            logger.debug(f"Saved position tracker state: {len(positions)} positions")

    def load_position_tracker_state(self) -> Dict[str, Dict[str, Any]]:
        """
        Load position tracker state from database.

        Returns:
            Dict mapping symbol to position state dict
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, entry_price, entry_time, quantity, side, stop_loss, take_profit,
                       highest_price, lowest_price, scale_ins, scale_outs, strategy, atr,
                       signal_strength, updated_at
                FROM position_tracker
                ORDER BY updated_at DESC
            """)

            positions = {}
            for row in cursor.fetchall():
                positions[row[0]] = {
                    'entry_price': row[1],
                    'entry_time': row[2],
                    'quantity': row[3],
                    'side': row[4],
                    'stop_loss': row[5],
                    'take_profit': row[6],
                    'highest_price': row[7],
                    'lowest_price': row[8],
                    'scale_ins': row[9],
                    'scale_outs': row[10],
                    'strategy': row[11],
                    'atr': row[12],
                    'signal_strength': row[13],
                    'updated_at': row[14]
                }

            logger.info(f"Loaded position tracker state: {len(positions)} positions")
            return positions

    def remove_position_tracker_state(self, symbol: str) -> None:
        """
        Remove a position from tracker state (after close).

        Args:
            symbol: Symbol to remove
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM position_tracker WHERE symbol = ?", (symbol,))
            conn.commit()
            logger.debug(f"Removed position tracker state: {symbol}")

    def clear_position_tracker_state(self) -> None:
        """Clear all position tracker state (use with caution)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM position_tracker")
            conn.commit()
            logger.info("Cleared all position tracker state")

    # ==================== Utilities ====================

    def validate_data(self, symbol: str) -> Dict[str, Any]:
        """
        Validate data quality for a symbol.

        Checks:
        - Missing dates (gaps in trading days)
        - Price continuity (no >20% jumps without splits)
        - Data range

        Returns:
            Dict with validation results
        """
        df = self.get_daily_bars(symbol)

        if df.empty:
            return {"valid": False, "error": "No data found"}

        results = {
            "valid": True,
            "symbol": symbol,
            "start_date": df.index.min(),
            "end_date": df.index.max(),
            "row_count": len(df),
            "missing_values": df.isnull().sum().to_dict(),
            "issues": []
        }

        # Check for large price gaps (>20%)
        returns = df["close"].pct_change().abs()
        large_gaps = returns[returns > 0.20]
        if not large_gaps.empty:
            results["issues"].append({
                "type": "large_price_gap",
                "dates": large_gaps.index.tolist(),
                "values": large_gaps.tolist()
            })

        # Check for missing values
        if df.isnull().any().any():
            results["valid"] = False
            results["issues"].append({
                "type": "missing_values",
                "columns": df.columns[df.isnull().any()].tolist()
            })

        return results

    # ==================== Daily Journal ====================

    def save_daily_journal(
        self,
        journal_date: date,
        starting_equity: float,
        ending_equity: float,
        notes: Optional[str] = None
    ) -> int:
        """
        Save or update a daily journal entry.

        Args:
            journal_date: Date of the entry
            starting_equity: Portfolio value at start of day
            ending_equity: Portfolio value at end of day
            notes: Optional notes about the day

        Returns:
            Journal entry ID
        """
        daily_pnl = ending_equity - starting_equity
        daily_pnl_pct = (daily_pnl / starting_equity * 100) if starting_equity > 0 else 0

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO daily_journal
                (date, starting_equity, ending_equity, daily_pnl, daily_pnl_pct, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date) DO UPDATE SET
                    starting_equity = excluded.starting_equity,
                    ending_equity = excluded.ending_equity,
                    daily_pnl = excluded.daily_pnl,
                    daily_pnl_pct = excluded.daily_pnl_pct,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                journal_date.isoformat() if isinstance(journal_date, date) else journal_date,
                starting_equity,
                ending_equity,
                daily_pnl,
                daily_pnl_pct,
                notes
            ))
            conn.commit()
            logger.info(f"Saved daily journal entry for {journal_date}: ${daily_pnl:+.2f} ({daily_pnl_pct:+.2f}%)")
            return cursor.lastrowid

    def get_daily_journal(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Retrieve daily journal entries.

        Args:
            start_date: Filter entries from this date
            end_date: Filter entries until this date
            limit: Maximum entries to return

        Returns:
            DataFrame with journal entries
        """
        query = "SELECT * FROM daily_journal WHERE 1=1"
        params: List[Any] = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date.isoformat() if isinstance(start_date, date) else start_date)

        if end_date:
            query += " AND date <= ?"
            params.append(end_date.isoformat() if isinstance(end_date, date) else end_date)

        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def delete_daily_journal(self, journal_date: date) -> bool:
        """
        Delete a daily journal entry.

        Args:
            journal_date: Date of entry to delete

        Returns:
            True if entry was deleted
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM daily_journal WHERE date = ?",
                (journal_date.isoformat() if isinstance(journal_date, date) else journal_date,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted daily journal entry for {journal_date}")
            return deleted
