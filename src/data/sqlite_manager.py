"""SQLite database manager with async support."""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import aiosqlite
from loguru import logger

from config.settings import settings


class SQLiteManager:
    """Async SQLite database manager with connection pooling."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path or settings.sqlite_db_path)
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrency
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")

        # Create tables
        await self._create_tables()
        logger.info(f"SQLite database initialized at {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("SQLite database connection closed")

    @asynccontextmanager
    async def get_connection(self):
        """Get database connection context manager."""
        if not self._connection:
            await self.initialize()
        async with self._lock:
            yield self._connection

    async def _create_tables(self) -> None:
        """Create all required tables."""
        tables = [
            # Stock metadata
            """
            CREATE TABLE IF NOT EXISTS stocks (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                exchange TEXT NOT NULL,
                market TEXT NOT NULL,
                sector TEXT,
                industry TEXT,
                listing_date DATE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Market data (OHLCV)
            """
            CREATE TABLE IF NOT EXISTS market_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TIMESTAMP NOT NULL,
                symbol TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                amount REAL,
                turnover_rate REAL,
                pct_change REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(time, symbol)
            )
            """,
            # Technical indicators
            """
            CREATE TABLE IF NOT EXISTS technical_indicators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time TIMESTAMP NOT NULL,
                symbol TEXT NOT NULL,
                indicator_type TEXT NOT NULL,
                value REAL NOT NULL,
                parameters TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Trading signals
            """
            CREATE TABLE IF NOT EXISTS trading_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                signal_value TEXT NOT NULL,
                confidence REAL,
                price_at_signal REAL,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                strategy_name TEXT,
                parameters TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Backtest results
            """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_name TEXT NOT NULL,
                symbol TEXT,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                initial_capital REAL NOT NULL,
                final_capital REAL NOT NULL,
                total_return REAL,
                annual_return REAL,
                sharpe_ratio REAL,
                max_drawdown REAL,
                win_rate REAL,
                profit_factor REAL,
                total_trades INTEGER,
                parameters TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Trades
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backtest_run_id INTEGER,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                price REAL NOT NULL,
                commission REAL,
                executed_at TIMESTAMP NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (backtest_run_id) REFERENCES backtest_runs(id)
            )
            """,
            # Daily reports
            """
            CREATE TABLE IF NOT EXISTS daily_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date DATE UNIQUE NOT NULL,
                report_type TEXT DEFAULT 'daily',
                title TEXT,
                content TEXT,
                summary TEXT,
                market_overview TEXT,
                top_gainers TEXT,
                top_losers TEXT,
                sector_performance TEXT,
                ai_analysis TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # News
            """
            CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                title TEXT NOT NULL,
                content TEXT,
                source TEXT,
                url TEXT,
                publish_time TIMESTAMP,
                sentiment_score REAL,
                sentiment_label TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Task logs
            """
            CREATE TABLE IF NOT EXISTS task_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # Feishu messages (for tracking)
            """
            CREATE TABLE IF NOT EXISTS feishu_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                chat_id TEXT,
                user_id TEXT,
                message_type TEXT,
                content TEXT,
                processed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            # OAuth2 tokens
            """
            CREATE TABLE IF NOT EXISTS oauth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(provider)
            )
            """,
        ]

        async with self.get_connection() as conn:
            for table_sql in tables:
                await conn.execute(table_sql)

            # Create indexes for better query performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_market_data_symbol ON market_data(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_market_data_time ON market_data(time)",
                "CREATE INDEX IF NOT EXISTS idx_market_data_symbol_time ON market_data(symbol, time)",
                "CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol ON trading_signals(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_trading_signals_time ON trading_signals(generated_at)",
                "CREATE INDEX IF NOT EXISTS idx_news_symbol ON news(symbol)",
                "CREATE INDEX IF NOT EXISTS idx_news_time ON news(publish_time)",
                "CREATE INDEX IF NOT EXISTS idx_task_logs_status ON task_logs(status)",
                "CREATE INDEX IF NOT EXISTS idx_feishu_messages_chat ON feishu_messages(chat_id)",
            ]

            for index_sql in indexes:
                await conn.execute(index_sql)

            await conn.commit()

        logger.info("Database tables and indexes created")

    async def execute(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Execute a query without returning results.

        Args:
            query: SQL query
            params: Query parameters
        """
        async with self.get_connection() as conn:
            await conn.execute(query, params or {})
            await conn.commit()

    async def execute_many(
        self,
        query: str,
        params_list: list[dict[str, Any]],
    ) -> None:
        """
        Execute a query with multiple parameter sets.

        Args:
            query: SQL query
            params_list: List of parameter dictionaries
        """
        async with self.get_connection() as conn:
            await conn.executemany(query, params_list)
            await conn.commit()

    async def fetch_one(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """
        Fetch a single row.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            Dictionary with row data or None
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params or {})
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def fetch_all(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch all rows.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            List of dictionaries with row data
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params or {})
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def fetch_value(
        self,
        query: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Any:
        """
        Fetch a single value.

        Args:
            query: SQL query
            params: Query parameters

        Returns:
            Single value or None
        """
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params or {})
            row = await cursor.fetchone()
            return row[0] if row else None


# Global instance
_sqlite_manager: Optional[SQLiteManager] = None


async def get_sqlite_manager() -> SQLiteManager:
    """Get or create the global SQLite manager instance."""
    global _sqlite_manager
    if _sqlite_manager is None:
        _sqlite_manager = SQLiteManager()
        await _sqlite_manager.initialize()
    return _sqlite_manager