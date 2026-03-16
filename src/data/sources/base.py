"""Abstract base class for data sources."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

import pandas as pd

from src.data.models import Market


class DataSource(ABC):
    """Abstract base class for all data sources."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Get the name of this data source."""
        pass

    @property
    @abstractmethod
    def supported_markets(self) -> list[Market]:
        """Get list of supported markets."""
        pass

    @abstractmethod
    async def fetch_ohlcv(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fetch OHLCV (Open-High-Low-Close-Volume) data.

        Args:
            symbol: Stock symbol
            start: Start datetime
            end: End datetime
            interval: Data interval ('1d', '1h', '1m', etc.)

        Returns:
            DataFrame with columns: time, open, high, low, close, volume
        """
        pass

    @abstractmethod
    async def fetch_latest(self, symbol: str) -> pd.Series:
        """
        Fetch the latest data for a symbol.

        Args:
            symbol: Stock symbol

        Returns:
            Series with latest OHLCV data
        """
        pass

    @abstractmethod
    async def get_stock_list(self, market: Market) -> pd.DataFrame:
        """
        Get list of stocks for a market.

        Args:
            market: Market to get stocks for

        Returns:
            DataFrame with stock metadata
        """
        pass

    @abstractmethod
    async def get_stock_info(self, symbol: str) -> dict:
        """
        Get detailed information for a stock.

        Args:
            symbol: Stock symbol

        Returns:
            Dictionary with stock information
        """
        pass

    async def health_check(self) -> bool:
        """
        Check if the data source is healthy and accessible.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Default implementation tries to get a single data point
            markets = self.supported_markets
            if markets:
                stocks = await self.get_stock_list(markets[0])
                return not stocks.empty
            return True
        except Exception:
            return False

    def normalize_symbol(self, symbol: str, market: Market) -> str:
        """
        Normalize symbol format for the data source.

        Args:
            symbol: Raw symbol
            market: Market type

        Returns:
            Normalized symbol
        """
        return symbol.upper()

    @staticmethod
    def validate_interval(interval: str) -> bool:
        """
        Validate if interval format is supported.

        Args:
            interval: Interval string (e.g., '1d', '1h', '5m')

        Returns:
            True if valid
        """
        valid_intervals = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]
        return interval in valid_intervals