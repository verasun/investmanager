"""US stock data source using yfinance."""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger

from src.data.models import Market
from src.data.sources.base import DataSource


class YFinanceSource(DataSource):
    """Data source for US stock market using yfinance library."""

    def __init__(self):
        """Initialize yfinance data source."""
        self._cache: dict[str, pd.DataFrame] = {}

    @property
    def name(self) -> str:
        """Get the name of this data source."""
        return "yfinance"

    @property
    def supported_markets(self) -> list[Market]:
        """Get list of supported markets."""
        return [Market.US]

    async def fetch_ohlcv(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data for US stocks.

        Args:
            symbol: Stock ticker (e.g., 'AAPL', 'MSFT')
            start: Start datetime
            end: End datetime
            interval: Data interval ('1d', '1h', '5m', etc.)

        Returns:
            DataFrame with OHLCV data
        """
        try:
            symbol = symbol.upper()
            logger.info(f"Fetching OHLCV for {symbol} from {start} to {end}")

            # Map interval format
            yf_interval = self._map_interval(interval)

            # Fetch data using yfinance
            ticker = yf.Ticker(symbol)
            df = await asyncio.to_thread(
                ticker.history,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                interval=yf_interval,
                auto_adjust=True,
            )

            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Reset index to get date as column
            df = df.reset_index()
            df = df.rename(
                columns={
                    "Date": "time",
                    "Datetime": "time",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume",
                }
            )

            # Ensure time is datetime
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])

            df["symbol"] = symbol

            # Calculate additional metrics
            df["pct_change"] = df["close"].pct_change() * 100

            # Select columns
            columns = ["time", "symbol", "open", "high", "low", "close", "volume", "pct_change"]
            df = df[[col for col in columns if col in df.columns]]

            return df

        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            raise

    async def fetch_latest(self, symbol: str) -> pd.Series:
        """
        Fetch the latest data for a symbol.

        Args:
            symbol: Stock ticker

        Returns:
            Series with latest OHLCV data
        """
        try:
            symbol = symbol.upper()
            ticker = yf.Ticker(symbol)

            # Get fast info for current price
            info = await asyncio.to_thread(lambda: ticker.fast_info)

            return pd.Series(
                {
                    "symbol": symbol,
                    "close": info.get("last_price"),
                    "high": info.get("day_high"),
                    "low": info.get("day_low"),
                    "open": info.get("open"),
                    "volume": info.get("last_volume"),
                    "time": datetime.now(),
                }
            )

        except Exception as e:
            logger.error(f"Error fetching latest data for {symbol}: {e}")
            # Fallback to historical data
            end = datetime.now()
            start = end - timedelta(days=7)
            df = await self.fetch_ohlcv(symbol, start, end, "1d")
            if df.empty:
                raise ValueError(f"No data available for {symbol}")
            return df.iloc[-1]

    async def get_stock_list(self, market: Market = Market.US) -> pd.DataFrame:
        """
        Get list of US stocks.

        Note: yfinance doesn't provide a direct stock list API,
        so we use a predefined list of popular stocks.

        Args:
            market: Market (only US supported)

        Returns:
            DataFrame with stock list
        """
        if market != Market.US:
            raise ValueError(f"Market {market} not supported by yfinance")

        try:
            # Popular US stock tickers for demonstration
            # In production, this could be fetched from a data provider
            popular_stocks = [
                # Tech Giants
                "AAPL",
                "MSFT",
                "GOOGL",
                "AMZN",
                "META",
                "NVDA",
                "TSLA",
                "AMD",
                "INTC",
                "IBM",
                # Finance
                "JPM",
                "BAC",
                "WFC",
                "GS",
                "MS",
                # Healthcare
                "JNJ",
                "PFE",
                "UNH",
                "ABT",
                "MRK",
                # Consumer
                "WMT",
                "PG",
                "KO",
                "PEP",
                "MCD",
                # Industrial
                "BA",
                "CAT",
                "HON",
                "UPS",
                "GE",
                # Energy
                "XOM",
                "CVX",
                "COP",
                "SLB",
                # ETFs
                "SPY",
                "QQQ",
                "IWM",
                "VTI",
                "DIA",
            ]

            logger.info("Building US stock list")

            # Fetch basic info for each stock
            stocks_data = []
            for ticker in popular_stocks:
                try:
                    info = await asyncio.to_thread(lambda t=ticker: yf.Ticker(t).info)
                    stocks_data.append(
                        {
                            "symbol": ticker,
                            "name": info.get("longName", info.get("shortName", ticker)),
                            "sector": info.get("sector"),
                            "industry": info.get("industry"),
                            "market": "US",
                            "exchange": info.get("exchange", "NASDAQ"),
                        }
                    )
                except Exception as e:
                    logger.warning(f"Could not fetch info for {ticker}: {e}")
                    stocks_data.append(
                        {
                            "symbol": ticker,
                            "name": ticker,
                            "sector": None,
                            "industry": None,
                            "market": "US",
                            "exchange": "NASDAQ",
                        }
                    )

            return pd.DataFrame(stocks_data)

        except Exception as e:
            logger.error(f"Error building stock list: {e}")
            raise

    async def get_stock_info(self, symbol: str) -> dict:
        """
        Get detailed information for a stock.

        Args:
            symbol: Stock ticker

        Returns:
            Dictionary with stock information
        """
        try:
            symbol = symbol.upper()
            ticker = yf.Ticker(symbol)
            info = await asyncio.to_thread(lambda: ticker.info)

            # Extract relevant fields
            return {
                "symbol": symbol,
                "name": info.get("longName", info.get("shortName")),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
                "52week_high": info.get("fiftyTwoWeekHigh"),
                "52week_low": info.get("fiftyTwoWeekLow"),
                "avg_volume": info.get("averageVolume"),
                "description": info.get("longBusinessSummary"),
                "website": info.get("website"),
                "employees": info.get("fullTimeEmployees"),
            }

        except Exception as e:
            logger.error(f"Error fetching stock info for {symbol}: {e}")
            return {}

    async def get_dividends(self, symbol: str) -> pd.DataFrame:
        """
        Get dividend history for a stock.

        Args:
            symbol: Stock ticker

        Returns:
            DataFrame with dividend data
        """
        try:
            symbol = symbol.upper()
            ticker = yf.Ticker(symbol)
            dividends = await asyncio.to_thread(lambda: ticker.dividends)

            if dividends.empty:
                return pd.DataFrame()

            df = dividends.reset_index()
            df = df.rename(columns={"Date": "time", "Dividends": "dividend"})
            df["symbol"] = symbol

            return df

        except Exception as e:
            logger.error(f"Error fetching dividends for {symbol}: {e}")
            return pd.DataFrame()

    async def get_splits(self, symbol: str) -> pd.DataFrame:
        """
        Get stock split history.

        Args:
            symbol: Stock ticker

        Returns:
            DataFrame with split data
        """
        try:
            symbol = symbol.upper()
            ticker = yf.Ticker(symbol)
            splits = await asyncio.to_thread(lambda: ticker.splits)

            if splits.empty:
                return pd.DataFrame()

            df = splits.reset_index()
            df = df.rename(columns={"Date": "time", "Stock Splits": "split_ratio"})
            df["symbol"] = symbol

            return df

        except Exception as e:
            logger.error(f"Error fetching splits for {symbol}: {e}")
            return pd.DataFrame()

    async def get_recommendations(self, symbol: str) -> pd.DataFrame:
        """
        Get analyst recommendations.

        Args:
            symbol: Stock ticker

        Returns:
            DataFrame with recommendations
        """
        try:
            symbol = symbol.upper()
            ticker = yf.Ticker(symbol)
            recs = await asyncio.to_thread(lambda: ticker.recommendations)

            if recs is None or recs.empty:
                return pd.DataFrame()

            return recs

        except Exception as e:
            logger.error(f"Error fetching recommendations for {symbol}: {e}")
            return pd.DataFrame()

    def _map_interval(self, interval: str) -> str:
        """Map standard interval to yfinance format."""
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "15m": "15m",
            "30m": "30m",
            "1h": "1h",
            "1d": "1d",
            "1w": "1wk",
            "1M": "1mo",
        }
        return mapping.get(interval, "1d")