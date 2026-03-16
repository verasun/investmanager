"""Data cleaning utilities."""

from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class DataCleaner:
    """Data cleaner for handling missing values, outliers, and data quality issues."""

    def __init__(
        self,
        fill_method: str = "ffill",
        drop_duplicates: bool = True,
        handle_outliers: bool = False,
        outlier_method: str = "iqr",
        outlier_threshold: float = 3.0,
    ):
        """
        Initialize data cleaner.

        Args:
            fill_method: Method to fill missing values ('ffill', 'bfill', 'interpolate', 'drop')
            drop_duplicates: Whether to drop duplicate rows
            handle_outliers: Whether to handle outliers
            outlier_method: Method for outlier detection ('iqr', 'zscore')
            outlier_threshold: Threshold for outlier detection
        """
        self.fill_method = fill_method
        self.drop_duplicates = drop_duplicates
        self.handle_outliers = handle_outliers
        self.outlier_method = outlier_method
        self.outlier_threshold = outlier_threshold

    def clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean the data by handling missing values, duplicates, and optionally outliers.

        Args:
            df: Input DataFrame

        Returns:
            Cleaned DataFrame
        """
        if df.empty:
            return df

        original_len = len(df)
        df = df.copy()

        # Drop duplicates
        if self.drop_duplicates:
            df = self._drop_duplicates(df)

        # Handle missing values
        df = self._handle_missing_values(df)

        # Handle outliers
        if self.handle_outliers:
            df = self._handle_outliers(df)

        # Validate OHLCV data
        df = self._validate_ohlcv(df)

        logger.info(
            f"Data cleaning complete: {original_len} -> {len(df)} rows "
            f"({len(df) / original_len * 100:.1f}% retained)"
        )

        return df

    def _drop_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate rows."""
        if "time" in df.columns and "symbol" in df.columns:
            df = df.drop_duplicates(subset=["time", "symbol"], keep="last")
        else:
            df = df.drop_duplicates(keep="last")
        return df

    def _handle_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handle missing values based on configured method."""
        numeric_cols = df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            if df[col].isna().any():
                if self.fill_method == "ffill":
                    df[col] = df[col].ffill()
                elif self.fill_method == "bfill":
                    df[col] = df[col].bfill()
                elif self.fill_method == "interpolate":
                    df[col] = df[col].interpolate(method="linear")
                elif self.fill_method == "drop":
                    df = df.dropna(subset=[col])

        return df

    def _handle_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect and handle outliers in price/volume data."""
        price_cols = ["open", "high", "low", "close"]

        for col in price_cols:
            if col not in df.columns:
                continue

            if self.outlier_method == "iqr":
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower = Q1 - self.outlier_threshold * IQR
                upper = Q3 + self.outlier_threshold * IQR

                # Cap outliers instead of removing
                df[col] = df[col].clip(lower, upper)

            elif self.outlier_method == "zscore":
                mean = df[col].mean()
                std = df[col].std()
                z_scores = np.abs((df[col] - mean) / std)

                # Cap extreme values
                df.loc[z_scores > self.outlier_threshold, col] = mean + self.outlier_threshold * std

        return df

    def _validate_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate OHLCV data consistency."""
        price_cols = ["open", "high", "low", "close"]

        # Check if all price columns exist
        if not all(col in df.columns for col in price_cols):
            return df

        # High should be >= all other prices
        df.loc[df["high"] < df[["open", "close", "low"]].max(axis=1), "high"] = df[
            ["open", "close", "low"]
        ].max(axis=1)

        # Low should be <= all other prices
        df.loc[df["low"] > df[["open", "close", "high"]].min(axis=1), "low"] = df[
            ["open", "close", "high"]
        ].min(axis=1)

        # Volume should be non-negative
        if "volume" in df.columns:
            df["volume"] = df["volume"].clip(lower=0)

        return df

    def clean_batch(self, dfs: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """
        Clean multiple DataFrames.

        Args:
            dfs: Dictionary of symbol -> DataFrame

        Returns:
            Dictionary of cleaned DataFrames
        """
        return {symbol: self.clean(df) for symbol, df in dfs.items()}


def detect_gaps(df: pd.DataFrame, freq: str = "D") -> pd.DatetimeIndex:
    """
    Detect gaps in time series data.

    Args:
        df: DataFrame with 'time' column
        freq: Expected frequency ('D' for daily, 'H' for hourly, etc.)

    Returns:
        DatetimeIndex of missing timestamps
    """
    if "time" not in df.columns:
        raise ValueError("DataFrame must have 'time' column")

    df = df.sort_values("time")
    full_range = pd.date_range(start=df["time"].min(), end=df["time"].max(), freq=freq)
    existing = pd.DatetimeIndex(df["time"])

    missing = full_range.difference(existing)
    return missing


def fill_gaps(
    df: pd.DataFrame,
    freq: str = "D",
    method: str = "ffill",
) -> pd.DataFrame:
    """
    Fill gaps in time series data.

    Args:
        df: DataFrame with 'time' column
        freq: Expected frequency
        method: Fill method

    Returns:
        DataFrame with gaps filled
    """
    if "time" not in df.columns:
        raise ValueError("DataFrame must have 'time' column")

    df = df.set_index("time")
    df = df.asfreq(freq)

    if method == "ffill":
        df = df.ffill()
    elif method == "bfill":
        df = df.bfill()
    elif method == "interpolate":
        df = df.interpolate()

    return df.reset_index()