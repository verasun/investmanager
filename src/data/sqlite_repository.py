"""SQLite-compatible repository layer for database operations."""

from datetime import date, datetime, timedelta
from typing import Any, Optional

import pandas as pd
from loguru import logger

from config.settings import settings
from src.data.models import (
    BacktestResult,
    DailyReport,
    News,
    OHLCV,
    Stock,
    TechnicalIndicator,
    Trade,
    TradingSignal,
)
from src.data.sqlite_manager import SQLiteManager, get_sqlite_manager


class SQLiteRepository:
    """
    Repository for SQLite database operations.

    Provides the same interface as DataRepository but uses SQLite.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SQLite repository.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path or settings.sqlite_db_path
        self._manager: Optional[SQLiteManager] = None

    async def initialize(self) -> None:
        """Initialize database connection."""
        self._manager = SQLiteManager(self.db_path)
        await self._manager.initialize()
        logger.info(f"SQLite repository initialized: {self.db_path}")

    async def close(self) -> None:
        """Close database connection."""
        if self._manager:
            await self._manager.close()

    async def save_market_data(self, df: pd.DataFrame) -> int:
        """
        Save market data to database.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Number of rows inserted
        """
        if df.empty:
            return 0

        records = []
        for _, row in df.iterrows():
            # Convert timestamp to string for SQLite
            time_val = row["time"]
            if hasattr(time_val, 'isoformat'):
                time_str = time_val.isoformat()
            else:
                time_str = str(time_val)

            records.append({
                "time": time_str,
                "symbol": row["symbol"],
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("volume"),
                "amount": row.get("amount"),
                "turnover_rate": row.get("turnover_rate"),
                "pct_change": row.get("pct_change"),
            })

        # Use INSERT OR REPLACE for upsert
        query = """
            INSERT OR REPLACE INTO market_data
            (time, symbol, open, high, low, close, volume, amount, turnover_rate, pct_change)
            VALUES (:time, :symbol, :open, :high, :low, :close, :volume, :amount, :turnover_rate, :pct_change)
        """

        await self._manager.execute_many(query, records)
        logger.info(f"Saved {len(records)} market data records")
        return len(records)

    async def get_market_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get market data from database.

        Args:
            symbol: Stock symbol
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with OHLCV data
        """
        query = """
            SELECT time, symbol, open, high, low, close, volume, amount,
                   turnover_rate, pct_change
            FROM market_data
            WHERE symbol = :symbol
            AND time >= :start
            AND time <= :end
            ORDER BY time ASC
        """

        rows = await self._manager.fetch_all(
            query,
            {"symbol": symbol, "start": start.isoformat(), "end": end.isoformat()},
        )

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["time"] = pd.to_datetime(df["time"])
        return df

    async def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        Get the latest price for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Latest close price or None
        """
        query = """
            SELECT close
            FROM market_data
            WHERE symbol = :symbol
            ORDER BY time DESC
            LIMIT 1
        """

        result = await self._manager.fetch_value(query, {"symbol": symbol})
        return float(result) if result is not None else None

    async def save_stock(self, stock: Stock) -> None:
        """Save stock metadata to database."""
        query = """
            INSERT OR REPLACE INTO stocks
            (symbol, name, exchange, market, sector, industry, listing_date, is_active)
            VALUES (:symbol, :name, :exchange, :market, :sector, :industry, :listing_date, :is_active)
        """

        await self._manager.execute(
            query,
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "exchange": stock.exchange,
                "market": stock.market,
                "sector": stock.sector,
                "industry": stock.industry,
                "listing_date": stock.listing_date.isoformat() if stock.listing_date else None,
                "is_active": stock.is_active,
            },
        )

    async def get_stocks(self, market: Optional[str] = None) -> pd.DataFrame:
        """
        Get list of stocks from database.

        Args:
            market: Filter by market (optional)

        Returns:
            DataFrame with stock list
        """
        if market:
            query = """
                SELECT * FROM stocks
                WHERE market = :market AND is_active = TRUE
                ORDER BY symbol
            """
            rows = await self._manager.fetch_all(query, {"market": market})
        else:
            query = """
                SELECT * FROM stocks WHERE is_active = TRUE ORDER BY symbol
            """
            rows = await self._manager.fetch_all(query)

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    async def save_trading_signal(self, signal: TradingSignal) -> int:
        """
        Save a trading signal to database.

        Args:
            signal: TradingSignal model

        Returns:
            Signal ID
        """
        query = """
            INSERT INTO trading_signals
            (symbol, signal_type, signal_value, confidence, price_at_signal,
             generated_at, strategy_name, parameters, notes)
            VALUES (:symbol, :signal_type, :signal_value, :confidence, :price_at_signal,
                    :generated_at, :strategy_name, :parameters, :notes)
            RETURNING id
        """

        import json
        result = await self._manager.fetch_value(
            query,
            {
                "symbol": signal.symbol,
                "signal_type": signal.signal_type,
                "signal_value": signal.signal_value,
                "confidence": signal.confidence,
                "price_at_signal": signal.price_at_signal,
                "generated_at": signal.generated_at.isoformat(),
                "strategy_name": signal.strategy_name,
                "parameters": json.dumps(signal.parameters) if signal.parameters else None,
                "notes": signal.notes,
            },
        )
        return result

    async def get_recent_signals(
        self,
        symbol: Optional[str] = None,
        days: int = 7,
    ) -> pd.DataFrame:
        """
        Get recent trading signals.

        Args:
            symbol: Filter by symbol (optional)
            days: Number of days to look back

        Returns:
            DataFrame with signals
        """
        start_date = datetime.now() - timedelta(days=days)

        if symbol:
            query = """
                SELECT * FROM trading_signals
                WHERE symbol = :symbol AND generated_at >= :start
                ORDER BY generated_at DESC
            """
            rows = await self._manager.fetch_all(
                query,
                {"symbol": symbol, "start": start_date.isoformat()},
            )
        else:
            query = """
                SELECT * FROM trading_signals
                WHERE generated_at >= :start
                ORDER BY generated_at DESC
            """
            rows = await self._manager.fetch_all(
                query,
                {"start": start_date.isoformat()},
            )

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    async def save_backtest_result(self, result: BacktestResult) -> int:
        """
        Save backtest result to database.

        Args:
            result: BacktestResult model

        Returns:
            Backtest run ID
        """
        import json
        query = """
            INSERT INTO backtest_runs
            (strategy_name, symbol, start_date, end_date, initial_capital, final_capital,
             total_return, annual_return, sharpe_ratio, max_drawdown, win_rate, profit_factor,
             total_trades, parameters)
            VALUES (:strategy_name, :symbol, :start_date, :end_date, :initial_capital, :final_capital,
                    :total_return, :annual_return, :sharpe_ratio, :max_drawdown, :win_rate, :profit_factor,
                    :total_trades, :parameters)
            RETURNING id
        """

        run_id = await self._manager.fetch_value(
            query,
            {
                "strategy_name": result.strategy_name,
                "symbol": result.symbol,
                "start_date": result.start_date.isoformat(),
                "end_date": result.end_date.isoformat(),
                "initial_capital": result.initial_capital,
                "final_capital": result.final_capital,
                "total_return": result.total_return,
                "annual_return": result.annual_return,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "win_rate": result.win_rate,
                "profit_factor": result.profit_factor,
                "total_trades": result.total_trades,
                "parameters": json.dumps(result.parameters) if result.parameters else None,
            },
        )
        return run_id

    async def save_trade(self, trade: Trade) -> int:
        """Save a trade record."""
        query = """
            INSERT INTO trades
            (backtest_run_id, symbol, side, quantity, price, commission, executed_at, notes)
            VALUES (:backtest_run_id, :symbol, :side, :quantity, :price, :commission, :executed_at, :notes)
            RETURNING id
        """

        trade_id = await self._manager.fetch_value(
            query,
            {
                "backtest_run_id": trade.backtest_run_id,
                "symbol": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": trade.price,
                "commission": trade.commission,
                "executed_at": trade.executed_at.isoformat(),
                "notes": trade.notes,
            },
        )
        return trade_id

    async def save_daily_report(self, report: DailyReport) -> int:
        """Save a daily report."""
        import json
        query = """
            INSERT OR REPLACE INTO daily_reports
            (report_date, report_type, title, content, summary, market_overview,
             top_gainers, top_losers, sector_performance, ai_analysis)
            VALUES (:report_date, :report_type, :title, :content, :summary, :market_overview,
                    :top_gainers, :top_losers, :sector_performance, :ai_analysis)
            RETURNING id
        """

        report_id = await self._manager.fetch_value(
            query,
            {
                "report_date": report.report_date.isoformat(),
                "report_type": report.report_type,
                "title": report.title,
                "content": report.content,
                "summary": report.summary,
                "market_overview": json.dumps(report.market_overview) if report.market_overview else None,
                "top_gainers": json.dumps(report.top_gainers) if report.top_gainers else None,
                "top_losers": json.dumps(report.top_losers) if report.top_losers else None,
                "sector_performance": json.dumps(report.sector_performance) if report.sector_performance else None,
                "ai_analysis": report.ai_analysis,
            },
        )
        return report_id

    async def get_daily_report(self, report_date: date) -> Optional[DailyReport]:
        """Get daily report for a specific date."""
        query = "SELECT * FROM daily_reports WHERE report_date = :report_date"

        row = await self._manager.fetch_one(
            query,
            {"report_date": report_date.isoformat()},
        )

        if not row:
            return None

        import json
        return DailyReport(
            id=row["id"],
            report_date=row["report_date"],
            report_type=row["report_type"],
            title=row["title"],
            content=row["content"],
            summary=row["summary"],
            market_overview=json.loads(row["market_overview"]) if row["market_overview"] else None,
            top_gainers=json.loads(row["top_gainers"]) if row["top_gainers"] else None,
            top_losers=json.loads(row["top_losers"]) if row["top_losers"] else None,
            sector_performance=json.loads(row["sector_performance"]) if row["sector_performance"] else None,
            ai_analysis=row["ai_analysis"],
        )

    async def save_news(self, news: News) -> int:
        """Save news article."""
        query = """
            INSERT INTO news
            (symbol, title, content, source, url, publish_time, sentiment_score, sentiment_label)
            VALUES (:symbol, :title, :content, :source, :url, :publish_time, :sentiment_score, :sentiment_label)
            RETURNING id
        """

        news_id = await self._manager.fetch_value(
            query,
            {
                "symbol": news.symbol,
                "title": news.title,
                "content": news.content,
                "source": news.source,
                "url": news.url,
                "publish_time": news.publish_time.isoformat() if news.publish_time else None,
                "sentiment_score": news.sentiment_score,
                "sentiment_label": news.sentiment_label,
            },
        )
        return news_id

    async def get_recent_news(
        self,
        symbol: Optional[str] = None,
        days: int = 7,
    ) -> pd.DataFrame:
        """Get recent news articles."""
        start_date = datetime.now() - timedelta(days=days)

        if symbol:
            query = """
                SELECT * FROM news
                WHERE symbol = :symbol AND publish_time >= :start
                ORDER BY publish_time DESC
            """
            rows = await self._manager.fetch_all(
                query,
                {"symbol": symbol, "start": start_date.isoformat()},
            )
        else:
            query = """
                SELECT * FROM news
                WHERE publish_time >= :start
                ORDER BY publish_time DESC
            """
            rows = await self._manager.fetch_all(
                query,
                {"start": start_date.isoformat()},
            )

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows)

    async def log_task(
        self,
        task_name: str,
        status: str,
        error_message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> int:
        """Log task execution status."""
        import json
        query = """
            INSERT INTO task_logs
            (task_name, status, started_at, completed_at, error_message, details)
            VALUES (:task_name, :status, :started_at, :completed_at, :error_message, :details)
            RETURNING id
        """

        now = datetime.now().isoformat()
        task_id = await self._manager.fetch_value(
            query,
            {
                "task_name": task_name,
                "status": status,
                "started_at": now,
                "completed_at": now if status in ["success", "failed"] else None,
                "error_message": error_message,
                "details": json.dumps(details) if details else None,
            },
        )
        return task_id


async def get_repository():
    """
    Get the appropriate repository based on configuration.

    Returns:
        DataRepository (PostgreSQL) or SQLiteRepository based on settings
    """
    if settings.database_backend == "sqlite":
        repo = SQLiteRepository()
        await repo.initialize()
        return repo
    else:
        from src.data.repository import DataRepository
        repo = DataRepository()
        await repo.initialize()
        return repo