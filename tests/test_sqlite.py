"""Tests for SQLite manager and repository."""

import asyncio
import tempfile
from datetime import datetime, date
from pathlib import Path
from decimal import Decimal

import pytest
import pandas as pd

from src.data.sqlite_manager import SQLiteManager
from src.data.sqlite_repository import SQLiteRepository
from src.data.models import Stock, OHLCV, TradingSignal, BacktestResult, DailyReport, News


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test.db"


@pytest.fixture
async def sqlite_manager(temp_db_path):
    """Create and initialize SQLite manager."""
    manager = SQLiteManager(str(temp_db_path))
    await manager.initialize()
    yield manager
    await manager.close()


@pytest.fixture
async def sqlite_repo(temp_db_path):
    """Create and initialize SQLite repository."""
    repo = SQLiteRepository(str(temp_db_path))
    await repo.initialize()
    yield repo
    await repo.close()


class TestSQLiteManager:
    """Test cases for SQLiteManager."""

    @pytest.mark.asyncio
    async def test_initialize_creates_tables(self, temp_db_path):
        """Test that initialization creates all required tables."""
        manager = SQLiteManager(str(temp_db_path))
        await manager.initialize()

        # Check that tables exist
        tables = await manager.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        table_names = [t["name"] for t in tables]

        assert "stocks" in table_names
        assert "market_data" in table_names
        assert "trading_signals" in table_names
        assert "backtest_runs" in table_names
        assert "daily_reports" in table_names
        assert "news" in table_names
        assert "task_logs" in table_names

        await manager.close()

    @pytest.mark.asyncio
    async def test_insert_and_fetch(self, sqlite_manager):
        """Test basic insert and fetch operations."""
        # Insert a record
        await sqlite_manager.execute(
            "INSERT INTO stocks (symbol, name, exchange, market) VALUES (:symbol, :name, :exchange, :market)",
            {"symbol": "AAPL", "name": "Apple Inc", "exchange": "NASDAQ", "market": "US"},
        )

        # Fetch the record
        result = await sqlite_manager.fetch_one(
            "SELECT * FROM stocks WHERE symbol = :symbol",
            {"symbol": "AAPL"},
        )

        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["name"] == "Apple Inc"

    @pytest.mark.asyncio
    async def test_execute_many(self, sqlite_manager):
        """Test batch insert operations."""
        records = [
            {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ", "market": "US"},
            {"symbol": "MSFT", "name": "Microsoft", "exchange": "NASDAQ", "market": "US"},
            {"symbol": "GOOGL", "name": "Google", "exchange": "NASDAQ", "market": "US"},
        ]

        await sqlite_manager.execute_many(
            "INSERT INTO stocks (symbol, name, exchange, market) VALUES (:symbol, :name, :exchange, :market)",
            records,
        )

        results = await sqlite_manager.fetch_all("SELECT * FROM stocks ORDER BY symbol")
        assert len(results) == 3


class TestSQLiteRepository:
    """Test cases for SQLiteRepository."""

    @pytest.mark.asyncio
    async def test_save_and_get_market_data(self, sqlite_repo):
        """Test saving and retrieving market data."""
        # Create test data
        df = pd.DataFrame({
            "time": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "symbol": ["AAPL", "AAPL"],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [98.0, 99.0],
            "close": [103.0, 104.0],
            "volume": [1000000, 1100000],
            "amount": [103000000.0, 114400000.0],
            "turnover_rate": [0.5, 0.55],
            "pct_change": [1.0, 0.97],
        })

        count = await sqlite_repo.save_market_data(df)
        assert count == 2

        # Retrieve data
        result = await sqlite_repo.get_market_data(
            "AAPL",
            datetime(2024, 1, 1),
            datetime(2024, 1, 3),
        )

        assert len(result) == 2
        assert result["symbol"].tolist() == ["AAPL", "AAPL"]

    @pytest.mark.asyncio
    async def test_save_and_get_stock(self, sqlite_repo):
        """Test saving and retrieving stock metadata."""
        stock = Stock(
            symbol="AAPL",
            name="Apple Inc",
            exchange="NASDAQ",
            market="US",
            sector="Technology",
            industry="Consumer Electronics",
        )

        await sqlite_repo.save_stock(stock)

        # Retrieve stocks
        df = await sqlite_repo.get_stocks(market="US")
        assert len(df) == 1
        assert df.iloc[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_latest_price(self, sqlite_repo):
        """Test getting latest price."""
        # Save market data
        df = pd.DataFrame({
            "time": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "symbol": ["AAPL", "AAPL"],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [98.0, 99.0],
            "close": [103.0, 104.0],
            "volume": [1000000, 1100000],
        })

        await sqlite_repo.save_market_data(df)

        # Get latest price
        price = await sqlite_repo.get_latest_price("AAPL")
        assert price == 104.0

    @pytest.mark.asyncio
    async def test_save_trading_signal(self, sqlite_repo):
        """Test saving trading signal."""
        signal = TradingSignal(
            symbol="AAPL",
            signal_type="technical",
            signal_value="buy",
            confidence=Decimal("0.85"),
            price_at_signal=Decimal("150.0"),
            strategy_name="momentum",
        )

        signal_id = await sqlite_repo.save_trading_signal(signal)
        assert signal_id > 0

        # Retrieve signals
        signals = await sqlite_repo.get_recent_signals(symbol="AAPL", days=7)
        assert len(signals) == 1

    @pytest.mark.asyncio
    async def test_save_backtest_result(self, sqlite_repo):
        """Test saving backtest result."""
        result = BacktestResult(
            strategy_name="momentum",
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("120000"),
            total_return=Decimal("0.20"),
            annual_return=Decimal("0.20"),
            sharpe_ratio=Decimal("1.5"),
            max_drawdown=Decimal("0.10"),
            win_rate=Decimal("0.60"),
            profit_factor=Decimal("1.8"),
            total_trades=100,
        )

        run_id = await sqlite_repo.save_backtest_result(result)
        assert run_id > 0

    @pytest.mark.asyncio
    async def test_save_and_get_daily_report(self, sqlite_repo):
        """Test saving and retrieving daily report."""
        report = DailyReport(
            report_date=date(2024, 1, 15),
            report_type="daily",
            title="Daily Market Report",
            summary="Market summary for today",
            market_overview={"index": "SP500", "change": 0.5},
        )

        report_id = await sqlite_repo.save_daily_report(report)
        assert report_id > 0

        # Retrieve report
        retrieved = await sqlite_repo.get_daily_report(date(2024, 1, 15))
        assert retrieved is not None
        assert retrieved.title == "Daily Market Report"

    @pytest.mark.asyncio
    async def test_save_news(self, sqlite_repo):
        """Test saving news article."""
        news = News(
            symbol="AAPL",
            title="Apple announces new product",
            content="Apple announced a new product today...",
            source="Reuters",
            sentiment_score=Decimal("0.75"),
            sentiment_label="positive",
        )

        news_id = await sqlite_repo.save_news(news)
        assert news_id > 0

    @pytest.mark.asyncio
    async def test_log_task(self, sqlite_repo):
        """Test logging task execution."""
        task_id = await sqlite_repo.log_task(
            task_name="data_fetch",
            status="success",
            details={"symbols": ["AAPL", "MSFT"]},
        )
        assert task_id > 0