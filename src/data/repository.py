"""Data repository layer for database operations."""

from datetime import date, datetime, timedelta
from typing import Any, Optional

import asyncpg
import pandas as pd
from loguru import logger
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

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


class DataRepository:
    """Repository for database operations."""

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize data repository.

        Args:
            database_url: Database connection URL (defaults to settings)
        """
        self.database_url = database_url or settings.async_database_url
        self.engine = None
        self.async_session = None

    async def initialize(self) -> None:
        """Initialize database connection."""
        self.engine = create_async_engine(
            self.database_url,
            pool_size=settings.database_pool_size,
            echo=settings.is_development,
        )
        self.async_session = sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("Database connection initialized")

    async def close(self) -> None:
        """Close database connection."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection closed")

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

        # Prepare data for insertion
        records = []
        for _, row in df.iterrows():
            records.append(
                {
                    "time": row["time"],
                    "symbol": row["symbol"],
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume"),
                    "amount": row.get("amount"),
                    "turnover_rate": row.get("turnover_rate"),
                    "pct_change": row.get("pct_change"),
                }
            )

        async with self.async_session() as session:
            # Use upsert to handle duplicates
            stmt = insert(OHLCV.__table__).values(records)
            stmt = stmt.on_conflict_do_update(
                index_elements=["time", "symbol"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            await session.execute(stmt)
            await session.commit()

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
        query = text(
            """
            SELECT time, symbol, open, high, low, close, volume, amount,
                   turnover_rate, pct_change
            FROM market_data
            WHERE symbol = :symbol
            AND time >= :start
            AND time <= :end
            ORDER BY time ASC
        """
        )

        async with self.async_session() as session:
            result = await session.execute(
                query,
                {"symbol": symbol, "start": start, "end": end},
            )
            rows = result.fetchall()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=result.keys())
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
        query = text(
            """
            SELECT close
            FROM market_data
            WHERE symbol = :symbol
            ORDER BY time DESC
            LIMIT 1
        """
        )

        async with self.async_session() as session:
            result = await session.execute(query, {"symbol": symbol})
            row = result.fetchone()

        return row[0] if row else None

    async def save_stock(self, stock: Stock) -> None:
        """Save stock metadata to database."""
        query = text(
            """
            INSERT INTO stocks (symbol, name, exchange, market, sector, industry,
                              listing_date, is_active)
            VALUES (:symbol, :name, :exchange, :market, :sector, :industry,
                   :listing_date, :is_active)
            ON CONFLICT (symbol) DO UPDATE SET
                name = EXCLUDED.name,
                exchange = EXCLUDED.exchange,
                sector = EXCLUDED.sector,
                industry = EXCLUDED.industry,
                is_active = EXCLUDED.is_active,
                updated_at = CURRENT_TIMESTAMP
        """
        )

        async with self.async_session() as session:
            await session.execute(
                query,
                {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "market": stock.market,
                    "sector": stock.sector,
                    "industry": stock.industry,
                    "listing_date": stock.listing_date,
                    "is_active": stock.is_active,
                },
            )
            await session.commit()

    async def get_stocks(self, market: Optional[str] = None) -> pd.DataFrame:
        """
        Get list of stocks from database.

        Args:
            market: Filter by market (optional)

        Returns:
            DataFrame with stock list
        """
        if market:
            query = text(
                """
                SELECT * FROM stocks
                WHERE market = :market AND is_active = TRUE
                ORDER BY symbol
            """
            )
            params = {"market": market}
        else:
            query = text("SELECT * FROM stocks WHERE is_active = TRUE ORDER BY symbol")
            params = {}

        async with self.async_session() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows, columns=result.keys())

    async def save_trading_signal(self, signal: TradingSignal) -> int:
        """
        Save a trading signal to database.

        Args:
            signal: TradingSignal model

        Returns:
            Signal ID
        """
        query = text(
            """
            INSERT INTO trading_signals (symbol, signal_type, signal_value,
                                        confidence, price_at_signal, generated_at,
                                        strategy_name, parameters, notes)
            VALUES (:symbol, :signal_type, :signal_value, :confidence,
                   :price_at_signal, :generated_at, :strategy_name, :parameters, :notes)
            RETURNING id
        """
        )

        async with self.async_session() as session:
            result = await session.execute(
                query,
                {
                    "symbol": signal.symbol,
                    "signal_type": signal.signal_type,
                    "signal_value": signal.signal_value,
                    "confidence": signal.confidence,
                    "price_at_signal": signal.price_at_signal,
                    "generated_at": signal.generated_at,
                    "strategy_name": signal.strategy_name,
                    "parameters": signal.parameters,
                    "notes": signal.notes,
                },
            )
            signal_id = result.fetchone()[0]
            await session.commit()

        return signal_id

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
        if symbol:
            query = text(
                """
                SELECT * FROM trading_signals
                WHERE symbol = :symbol
                AND generated_at >= NOW() - INTERVAL ':days days'
                ORDER BY generated_at DESC
            """
            )
            params = {"symbol": symbol, "days": days}
        else:
            query = text(
                """
                SELECT * FROM trading_signals
                WHERE generated_at >= NOW() - INTERVAL ':days days'
                ORDER BY generated_at DESC
            """
            )
            params = {"days": days}

        async with self.async_session() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows, columns=result.keys())

    async def save_backtest_result(self, result: BacktestResult) -> int:
        """
        Save backtest result to database.

        Args:
            result: BacktestResult model

        Returns:
            Backtest run ID
        """
        query = text(
            """
            INSERT INTO backtest_runs (strategy_name, symbol, start_date, end_date,
                                       initial_capital, final_capital, total_return,
                                       annual_return, sharpe_ratio, max_drawdown,
                                       win_rate, profit_factor, total_trades, parameters)
            VALUES (:strategy_name, :symbol, :start_date, :end_date, :initial_capital,
                   :final_capital, :total_return, :annual_return, :sharpe_ratio,
                   :max_drawdown, :win_rate, :profit_factor, :total_trades, :parameters)
            RETURNING id
        """
        )

        async with self.async_session() as session:
            db_result = await session.execute(
                query,
                {
                    "strategy_name": result.strategy_name,
                    "symbol": result.symbol,
                    "start_date": result.start_date,
                    "end_date": result.end_date,
                    "initial_capital": result.initial_capital,
                    "final_capital": result.final_capital,
                    "total_return": result.total_return,
                    "annual_return": result.annual_return,
                    "sharpe_ratio": result.sharpe_ratio,
                    "max_drawdown": result.max_drawdown,
                    "win_rate": result.win_rate,
                    "profit_factor": result.profit_factor,
                    "total_trades": result.total_trades,
                    "parameters": result.parameters,
                },
            )
            run_id = db_result.fetchone()[0]
            await session.commit()

        return run_id

    async def save_trade(self, trade: Trade) -> int:
        """Save a trade record."""
        query = text(
            """
            INSERT INTO trades (backtest_run_id, symbol, side, quantity, price,
                               commission, executed_at, notes)
            VALUES (:backtest_run_id, :symbol, :side, :quantity, :price,
                   :commission, :executed_at, :notes)
            RETURNING id
        """
        )

        async with self.async_session() as session:
            result = await session.execute(
                query,
                {
                    "backtest_run_id": trade.backtest_run_id,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "commission": trade.commission,
                    "executed_at": trade.executed_at,
                    "notes": trade.notes,
                },
            )
            trade_id = result.fetchone()[0]
            await session.commit()

        return trade_id

    async def save_daily_report(self, report: DailyReport) -> int:
        """Save a daily report."""
        query = text(
            """
            INSERT INTO daily_reports (report_date, report_type, title, content,
                                       summary, market_overview, top_gainers,
                                       top_losers, sector_performance, ai_analysis)
            VALUES (:report_date, :report_type, :title, :content, :summary,
                   :market_overview, :top_gainers, :top_losers,
                   :sector_performance, :ai_analysis)
            ON CONFLICT (report_date) DO UPDATE SET
                report_type = EXCLUDED.report_type,
                title = EXCLUDED.title,
                content = EXCLUDED.content,
                summary = EXCLUDED.summary,
                market_overview = EXCLUDED.market_overview,
                top_gainers = EXCLUDED.top_gainers,
                top_losers = EXCLUDED.top_losers,
                sector_performance = EXCLUDED.sector_performance,
                ai_analysis = EXCLUDED.ai_analysis
            RETURNING id
        """
        )

        async with self.async_session() as session:
            result = await session.execute(
                query,
                {
                    "report_date": report.report_date,
                    "report_type": report.report_type,
                    "title": report.title,
                    "content": report.content,
                    "summary": report.summary,
                    "market_overview": report.market_overview,
                    "top_gainers": report.top_gainers,
                    "top_losers": report.top_losers,
                    "sector_performance": report.sector_performance,
                    "ai_analysis": report.ai_analysis,
                },
            )
            report_id = result.fetchone()[0]
            await session.commit()

        return report_id

    async def get_daily_report(self, report_date: date) -> Optional[DailyReport]:
        """Get daily report for a specific date."""
        query = text("SELECT * FROM daily_reports WHERE report_date = :report_date")

        async with self.async_session() as session:
            result = await session.execute(query, {"report_date": report_date})
            row = result.fetchone()

        if not row:
            return None

        return DailyReport(**dict(row._mapping))

    async def save_news(self, news: News) -> int:
        """Save news article."""
        query = text(
            """
            INSERT INTO news (symbol, title, content, source, url, publish_time,
                             sentiment_score, sentiment_label)
            VALUES (:symbol, :title, :content, :source, :url, :publish_time,
                   :sentiment_score, :sentiment_label)
            RETURNING id
        """
        )

        async with self.async_session() as session:
            result = await session.execute(
                query,
                {
                    "symbol": news.symbol,
                    "title": news.title,
                    "content": news.content,
                    "source": news.source,
                    "url": news.url,
                    "publish_time": news.publish_time,
                    "sentiment_score": news.sentiment_score,
                    "sentiment_label": news.sentiment_label,
                },
            )
            news_id = result.fetchone()[0]
            await session.commit()

        return news_id

    async def get_recent_news(
        self,
        symbol: Optional[str] = None,
        days: int = 7,
    ) -> pd.DataFrame:
        """Get recent news articles."""
        if symbol:
            query = text(
                """
                SELECT * FROM news
                WHERE symbol = :symbol
                AND publish_time >= NOW() - INTERVAL ':days days'
                ORDER BY publish_time DESC
            """
            )
            params = {"symbol": symbol, "days": days}
        else:
            query = text(
                """
                SELECT * FROM news
                WHERE publish_time >= NOW() - INTERVAL ':days days'
                ORDER BY publish_time DESC
            """
            )
            params = {"days": days}

        async with self.async_session() as session:
            result = await session.execute(query, params)
            rows = result.fetchall()

        if not rows:
            return pd.DataFrame()

        return pd.DataFrame(rows, columns=result.keys())

    async def log_task(
        self,
        task_name: str,
        status: str,
        error_message: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> int:
        """Log task execution status."""
        query = text(
            """
            INSERT INTO task_logs (task_name, status, started_at, completed_at,
                                  error_message, details)
            VALUES (:task_name, :status, :started_at, :completed_at,
                   :error_message, :details)
            RETURNING id
        """
        )

        now = datetime.now()
        async with self.async_session() as session:
            result = await session.execute(
                query,
                {
                    "task_name": task_name,
                    "status": status,
                    "started_at": now,
                    "completed_at": now if status in ["success", "failed"] else None,
                    "error_message": error_message,
                    "details": details,
                },
            )
            task_id = result.fetchone()[0]
            await session.commit()

        return task_id