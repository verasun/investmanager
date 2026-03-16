"""A-share data source using akshare."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import akshare as ak
import pandas as pd
from loguru import logger

from config.settings import settings
from src.data.models import Market
from src.data.sources.base import DataSource


class AkshareSource(DataSource):
    """Data source for A-share market using akshare library."""

    def __init__(self):
        """Initialize akshare data source."""
        self._cache: dict[str, pd.DataFrame] = {}

    @property
    def name(self) -> str:
        """Get the name of this data source."""
        return "akshare"

    @property
    def supported_markets(self) -> list[Market]:
        """Get list of supported markets."""
        return [Market.A_SHARE]

    async def fetch_ohlcv(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for A-share stocks.

        Args:
            symbol: Stock code (e.g., '000001' or 'sh000001')
            start: Start datetime
            end: End datetime
            interval: Data interval ('1d' for daily, others may not be supported)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Normalize symbol - remove prefix
            code = symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")

            logger.info(f"Fetching OHLCV for {code} from {start} to {end}")

            # Run in thread pool since akshare is synchronous
            df = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=code,
                period="daily" if interval == "1d" else interval,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",  # Forward adjusted price
            )

            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Standardize column names
            df = df.rename(
                columns={
                    "日期": "time",
                    "开盘": "open",
                    "最高": "high",
                    "最低": "low",
                    "收盘": "close",
                    "成交量": "volume",
                    "成交额": "amount",
                    "换手率": "turnover_rate",
                    "涨跌幅": "pct_change",
                }
            )

            # Convert time to datetime
            df["time"] = pd.to_datetime(df["time"])
            df["symbol"] = code

            # Select and reorder columns
            columns = [
                "time",
                "symbol",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "turnover_rate",
                "pct_change",
            ]
            df = df[[col for col in columns if col in df.columns]]

            return df

        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            raise

    async def fetch_latest(self, symbol: str) -> pd.Series:
        """
        Fetch the latest data for a symbol.

        Args:
            symbol: Stock code

        Returns:
            Series with latest OHLCV data
        """
        end = datetime.now()
        start = end - timedelta(days=7)  # Get last week to ensure we have latest

        df = await self.fetch_ohlcv(symbol, start, end, "1d")

        if df.empty:
            raise ValueError(f"No data available for {symbol}")

        return df.iloc[-1]

    async def get_stock_list(self, market: Market = Market.A_SHARE) -> pd.DataFrame:
        """
        Get list of A-share stocks.

        Args:
            market: Market (only A_SHARE supported)

        Returns:
            DataFrame with stock list
        """
        if market != Market.A_SHARE:
            raise ValueError(f"Market {market} not supported by akshare")

        try:
            logger.info("Fetching A-share stock list")

            # Get stock list from akshare
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)

            if df.empty:
                logger.warning("No stock list returned")
                return pd.DataFrame()

            # Standardize column names
            df = df.rename(
                columns={
                    "代码": "symbol",
                    "名称": "name",
                    "最新价": "price",
                    "涨跌幅": "pct_change",
                    "涨跌额": "change",
                    "成交量": "volume",
                    "成交额": "amount",
                    "最高": "high",
                    "最低": "low",
                    "今开": "open",
                    "昨收": "prev_close",
                }
            )

            # Add market and exchange info
            df["market"] = "A股"
            df["exchange"] = df["symbol"].apply(
                lambda x: "SH" if x.startswith(("6", "5")) else "SZ"
            )

            return df

        except Exception as e:
            logger.error(f"Error fetching stock list: {e}")
            raise

    async def get_stock_info(self, symbol: str) -> dict:
        """
        Get detailed information for a stock.

        Args:
            symbol: Stock code

        Returns:
            Dictionary with stock information
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").upper()

            # Get individual stock info
            df = await asyncio.to_thread(
                ak.stock_individual_info_em,
                symbol=code,
            )

            info = {}
            if not df.empty:
                for _, row in df.iterrows():
                    info[row["item"]] = row["value"]

            return info

        except Exception as e:
            logger.error(f"Error fetching stock info for {symbol}: {e}")
            return {}

    async def get_index_data(
        self,
        index_code: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get index data (e.g., 上证指数 'sh000001', 深证成指 'sz399001').

        Args:
            index_code: Index code
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with index OHLCV data
        """
        try:
            code = index_code.replace("sh", "").replace("sz", "").upper()

            df = await asyncio.to_thread(
                ak.stock_zh_index_daily,
                symbol=f"sh{code}" if code.startswith("0") else f"sz{code}",
            )

            if df.empty:
                return pd.DataFrame()

            # Filter by date range
            df["date"] = pd.to_datetime(df["date"])
            df = df[(df["date"] >= start) & (df["date"] <= end)]

            df = df.rename(
                columns={
                    "date": "time",
                }
            )
            df["symbol"] = index_code

            return df

        except Exception as e:
            logger.error(f"Error fetching index data for {index_code}: {e}")
            raise

    async def get_sector_data(self) -> pd.DataFrame:
        """
        Get sector/industry data and performance.

        Returns:
            DataFrame with sector data
        """
        try:
            df = await asyncio.to_thread(ak.stock_board_industry_name_em)
            return df
        except Exception as e:
            logger.error(f"Error fetching sector data: {e}")
            return pd.DataFrame()

    async def get_realtime_quotes(self, symbols: list[str]) -> pd.DataFrame:
        """
        Get realtime quotes for multiple symbols.

        Args:
            symbols: List of stock codes

        Returns:
            DataFrame with realtime quotes
        """
        try:
            # Get all realtime data and filter
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)

            if df.empty:
                return pd.DataFrame()

            # Filter for requested symbols
            codes = [s.replace("sh", "").replace("sz", "").upper() for s in symbols]
            df = df[df["代码"].isin(codes)]

            return df

        except Exception as e:
            logger.error(f"Error fetching realtime quotes: {e}")
            raise