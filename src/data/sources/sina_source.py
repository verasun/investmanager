"""A-share data source using Sina Finance API."""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
import pandas as pd
from loguru import logger

from config.settings import settings
from src.data.models import Market
from src.data.sources.base import DataSource


class SinaFinanceSource(DataSource):
    """Data source for A-share market using Sina Finance API."""

    BASE_URL = "https://hq.sinajs.cn"
    HISTORY_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"

    def __init__(self):
        """Initialize Sina Finance data source."""
        self._cache: dict[str, pd.DataFrame] = {}

    @property
    def name(self) -> str:
        """Get the name of this data source."""
        return "sina_finance"

    @property
    def supported_markets(self) -> list[Market]:
        """Get list of supported markets."""
        return [Market.A_SHARE]

    def _get_symbol_prefix(self, symbol: str) -> str:
        """Get Sina symbol prefix (sh/sz)."""
        code = symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
        # Shanghai stocks start with 6, Shenzhen stocks start with 0 or 3
        if code.startswith(("6", "5", "9")):
            return f"sh{code}"
        else:
            return f"sz{code}"

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
            interval: Data interval ('1d' for daily)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            code = symbol.replace("sh", "").replace("sz", "").replace("SH", "").replace("SZ", "")
            sina_symbol = self._get_symbol_prefix(symbol)

            logger.info(f"Fetching OHLCV for {code} from Sina Finance ({start} to {end})")

            # Calculate required data points (trading days ~ 252 per year)
            days_needed = (end - start).days
            trading_days = int(days_needed * 252 / 365) + 50  # Add buffer

            # Sina API allows up to ~1000 data points
            datalen = min(max(trading_days, 500), 1000)

            params = {
                "symbol": sina_symbol,
                "scale": "240" if interval == "1d" else "60",  # 240 = daily, 60 = hourly
                "ma": "no",
                "datalen": str(datalen),
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(self.HISTORY_URL, params=params)
                response.raise_for_status()

                # Parse JSON response
                data = response.json()

            if not data:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Parse the data
            records = []
            for item in data:
                try:
                    record = {
                        "time": pd.to_datetime(item.get("day", "")),
                        "open": float(item.get("open", 0)),
                        "high": float(item.get("high", 0)),
                        "low": float(item.get("low", 0)),
                        "close": float(item.get("close", 0)),
                        "volume": float(item.get("volume", 0)),
                    }
                    records.append(record)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse record: {item}, error: {e}")
                    continue

            if not records:
                return pd.DataFrame()

            df = pd.DataFrame(records)

            # Filter by date range
            df = df[(df["time"] >= start) & (df["time"] <= end)]
            df = df.sort_values("time").reset_index(drop=True)

            df["symbol"] = code
            df["amount"] = df["close"] * df["volume"]  # Estimate amount

            logger.info(f"Fetched {len(df)} records for {symbol}")
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
        start = end - timedelta(days=7)

        df = await self.fetch_ohlcv(symbol, start, end, "1d")

        if df.empty:
            raise ValueError(f"No data available for {symbol}")

        return df.iloc[-1]

    async def get_realtime_quote(self, symbol: str) -> dict:
        """
        Get realtime quote for a single symbol.

        Args:
            symbol: Stock code

        Returns:
            Dictionary with realtime quote data
        """
        try:
            sina_symbol = self._get_symbol_prefix(symbol)
            url = f"{self.BASE_URL}/list={sina_symbol}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                text = response.text

            # Parse Sina format: var hq_str_sh601688="name,open,prev_close,close,high,low,..."
            match = re.search(r'="([^"]+)"', text)
            if not match:
                logger.warning(f"No quote data found for {symbol}")
                return {}

            parts = match.group(1).split(",")
            if len(parts) < 32:
                logger.warning(f"Invalid quote data format for {symbol}")
                return {}

            return {
                "symbol": symbol,
                "name": parts[0],
                "open": float(parts[1]) if parts[1] else 0,
                "prev_close": float(parts[2]) if parts[2] else 0,
                "close": float(parts[3]) if parts[3] else 0,
                "high": float(parts[4]) if parts[4] else 0,
                "low": float(parts[5]) if parts[5] else 0,
                "volume": float(parts[8]) if parts[8] else 0,
                "amount": float(parts[9]) if parts[9] else 0,
                "date": parts[30],
                "time": parts[31],
            }

        except Exception as e:
            logger.error(f"Error fetching realtime quote for {symbol}: {e}")
            return {}

    async def get_realtime_quotes(self, symbols: list[str]) -> pd.DataFrame:
        """
        Get realtime quotes for multiple symbols.

        Args:
            symbols: List of stock codes

        Returns:
            DataFrame with realtime quotes
        """
        try:
            sina_symbols = [self._get_symbol_prefix(s) for s in symbols]
            url = f"{self.BASE_URL}/list={','.join(sina_symbols)}"

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                text = response.text

            records = []
            for line in text.strip().split("\n"):
                match = re.match(r'var hq_str_(\w+)="([^"]*)"', line)
                if not match:
                    continue

                symbol = match.group(1)
                data = match.group(2)

                if not data:
                    continue

                parts = data.split(",")
                if len(parts) >= 32:
                    records.append({
                        "symbol": symbol,
                        "name": parts[0],
                        "open": float(parts[1]) if parts[1] else 0,
                        "prev_close": float(parts[2]) if parts[2] else 0,
                        "close": float(parts[3]) if parts[3] else 0,
                        "high": float(parts[4]) if parts[4] else 0,
                        "low": float(parts[5]) if parts[5] else 0,
                        "volume": float(parts[8]) if parts[8] else 0,
                        "amount": float(parts[9]) if parts[9] else 0,
                        "date": parts[30],
                        "time": parts[31],
                    })

            return pd.DataFrame(records)

        except Exception as e:
            logger.error(f"Error fetching realtime quotes: {e}")
            return pd.DataFrame()

    async def get_stock_info(self, symbol: str) -> dict:
        """
        Get detailed information for a stock.

        Args:
            symbol: Stock code

        Returns:
            Dictionary with stock information
        """
        try:
            # Get realtime quote which includes basic info
            quote = await self.get_realtime_quote(symbol)

            if not quote:
                return {}

            return {
                "股票简称": quote.get("name", symbol),
                "最新价": quote.get("close", 0),
                "昨收": quote.get("prev_close", 0),
                "今开": quote.get("open", 0),
                "最高": quote.get("high", 0),
                "最低": quote.get("low", 0),
                "成交量": quote.get("volume", 0),
                "成交额": quote.get("amount", 0),
            }

        except Exception as e:
            logger.error(f"Error fetching stock info for {symbol}: {e}")
            return {}

    async def get_stock_list(self, market: Market = Market.A_SHARE) -> pd.DataFrame:
        """
        Get list of A-share stocks.

        Note: Sina doesn't provide a simple stock list API.
        This returns a limited set from a predefined list.

        Args:
            market: Market (only A_SHARE supported)

        Returns:
            DataFrame with stock list
        """
        if market != Market.A_SHARE:
            raise ValueError(f"Market {market} not supported by Sina Finance")

        # Use a sample of major stocks
        sample_symbols = [
            "600519", "600036", "601318", "600276", "600887",
            "000001", "000002", "000333", "000651", "000858",
            "601688", "601398", "601288", "600030", "600016",
        ]

        try:
            df = await self.get_realtime_quotes(sample_symbols)
            return df
        except Exception as e:
            logger.error(f"Error fetching stock list: {e}")
            return pd.DataFrame()

    async def get_index_data(
        self,
        index_code: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Get index data.

        Args:
            index_code: Index code (e.g., 'sh000001' for Shanghai Composite)
            start: Start datetime
            end: End datetime

        Returns:
            DataFrame with index OHLCV data
        """
        # Use the same OHLCV method for indices
        return await self.fetch_ohlcv(index_code, start, end, "1d")