"""Data normalization utilities."""

from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class DataNormalizer:
    """Normalizer for standardizing data across different sources and formats."""

    def __init__(
        self,
        price_precision: int = 4,
        volume_precision: int = 0,
        normalize_prices: bool = True,
        base_date: Optional[str] = None,
    ):
        """
        Initialize data normalizer.

        Args:
            price_precision: Decimal places for prices
            volume_precision: Decimal places for volume
            normalize_prices: Whether to normalize prices to start from 100
            base_date: Base date for price normalization (default: first date)
        """
        self.price_precision = price_precision
        self.volume_precision = volume_precision
        self.normalize_prices = normalize_prices
        self.base_date = base_date

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize the DataFrame.

        Args:
            df: Input DataFrame

        Returns:
            Normalized DataFrame
        """
        if df.empty:
            return df

        df = df.copy()

        # Standardize column names
        df = self._standardize_columns(df)

        # Standardize data types
        df = self._standardize_dtypes(df)

        # Normalize prices if requested
        if self.normalize_prices and "close" in df.columns:
            df = self._normalize_prices(df)

        # Round precision
        df = self._round_precision(df)

        return df

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize column names to snake_case."""
        # Common column name mappings
        column_mapping = {
            "Date": "time",
            "datetime": "time",
            "timestamp": "time",
            "Datetime": "time",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
            "Amount": "amount",
            "Turnover": "turnover",
            "Symbol": "symbol",
            "Code": "symbol",
            "代码": "symbol",
            "名称": "name",
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

        df = df.rename(columns=column_mapping)

        # Ensure symbol column exists
        if "symbol" not in df.columns and hasattr(df, "name"):
            df["symbol"] = df.name

        return df

    def _standardize_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize data types for each column."""
        # Time column
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])

        # Price columns
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # Volume column
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").astype("Int64")

        # Percentage columns
        pct_cols = ["pct_change", "turnover_rate"]
        for col in pct_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def _normalize_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize prices to start from 100 (for comparison across assets)."""
        if self.base_date:
            base_mask = df["time"] == pd.Timestamp(self.base_date)
            if base_mask.any():
                base_price = df.loc[base_mask, "close"].iloc[0]
            else:
                base_price = df["close"].iloc[0]
        else:
            base_price = df["close"].iloc[0]

        if pd.isna(base_price) or base_price == 0:
            return df

        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if col in df.columns:
                df[f"{col}_normalized"] = (df[col] / base_price) * 100

        return df

    def _round_precision(self, df: pd.DataFrame) -> pd.DataFrame:
        """Round numeric columns to specified precision."""
        price_cols = ["open", "high", "low", "close"]
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col].round(self.price_precision)

        if "volume" in df.columns:
            df["volume"] = df["volume"].round(self.volume_precision)

        return df

    def normalize_returns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add normalized return columns.

        Args:
            df: DataFrame with close prices

        Returns:
            DataFrame with return columns added
        """
        if "close" not in df.columns:
            return df

        df = df.copy()

        # Simple returns
        df["return"] = df["close"].pct_change()

        # Log returns
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))

        # Cumulative returns
        df["cumulative_return"] = (1 + df["return"]).cumprod() - 1

        return df

    def normalize_by_zscore(self, series: pd.Series, window: Optional[int] = None) -> pd.Series:
        """
        Normalize a series using z-score.

        Args:
            series: Input series
            window: Rolling window (None for expanding)

        Returns:
            Z-score normalized series
        """
        if window:
            mean = series.rolling(window=window).mean()
            std = series.rolling(window=window).std()
        else:
            mean = series.mean()
            std = series.std()

        return (series - mean) / std

    def normalize_by_minmax(
        self,
        series: pd.Series,
        min_val: float = 0,
        max_val: float = 1,
    ) -> pd.Series:
        """
        Normalize a series using min-max scaling.

        Args:
            series: Input series
            min_val: Minimum value after scaling
            max_val: Maximum value after scaling

        Returns:
            Min-max normalized series
        """
        series_min = series.min()
        series_max = series.max()

        return min_val + (series - series_min) * (max_val - min_val) / (series_max - series_min)


def calculate_adjusted_prices(
    df: pd.DataFrame,
    adjustment_factor: float = 1.0,
    dividend: float = 0.0,
) -> pd.DataFrame:
    """
    Calculate adjusted prices for splits and dividends.

    Args:
        df: DataFrame with OHLCV data
        adjustment_factor: Split ratio (e.g., 2 for 2:1 split)
        dividend: Dividend amount per share

    Returns:
        DataFrame with adjusted prices
    """
    df = df.copy()

    price_cols = ["open", "high", "low", "close"]

    if adjustment_factor != 1.0:
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col] / adjustment_factor

        if "volume" in df.columns:
            df["volume"] = df["volume"] * adjustment_factor

    if dividend > 0 and "close" in df.columns:
        # Adjust for dividend
        adj_factor = (df["close"] - dividend) / df["close"]
        for col in price_cols:
            if col in df.columns:
                df[col] = df[col] * adj_factor

    return df