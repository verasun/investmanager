"""Feature engineering for financial data."""

from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class FeatureEngineer:
    """Feature engineering for technical and fundamental analysis."""

    def __init__(self):
        """Initialize feature engineer."""
        pass

    def generate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all standard features.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with additional features
        """
        if df.empty:
            return df

        df = df.copy()

        # Price-based features
        df = self._add_price_features(df)

        # Volume features
        df = self._add_volume_features(df)

        # Volatility features
        df = self._add_volatility_features(df)

        # Momentum features
        df = self._add_momentum_features(df)

        # Trend features
        df = self._add_trend_features(df)

        return df

    def _add_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add price-based features."""
        if "close" not in df.columns:
            return df

        # Price position in daily range
        if all(col in df.columns for col in ["high", "low", "close"]):
            df["price_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"] + 1e-10)

        # Gap features
        if all(col in df.columns for col in ["open", "close"]):
            df["gap"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1)
            df["gap_up"] = (df["gap"] > 0).astype(int)
            df["gap_down"] = (df["gap"] < 0).astype(int)

        # Body and shadow (for candlestick analysis)
        if all(col in df.columns for col in ["open", "high", "low", "close"]):
            df["body"] = abs(df["close"] - df["open"])
            df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
            df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]
            df["body_ratio"] = df["body"] / (df["high"] - df["low"] + 1e-10)

        return df

    def _add_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volume-based features."""
        if "volume" not in df.columns:
            return df

        # Volume moving averages
        df["volume_ma_5"] = df["volume"].rolling(window=5).mean()
        df["volume_ma_10"] = df["volume"].rolling(window=10).mean()
        df["volume_ma_20"] = df["volume"].rolling(window=20).mean()

        # Volume ratio
        df["volume_ratio"] = df["volume"] / (df["volume_ma_5"] + 1e-10)

        # Volume trend
        df["volume_trend"] = df["volume"] > df["volume_ma_5"]

        # On-Balance Volume (OBV)
        if "close" in df.columns:
            obv = np.where(
                df["close"] > df["close"].shift(1),
                df["volume"],
                np.where(df["close"] < df["close"].shift(1), -df["volume"], 0),
            )
            df["obv"] = pd.Series(obv, index=df.index).cumsum()

        # Volume Rate of Change
        df["volume_roc"] = df["volume"].pct_change()

        return df

    def _add_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility-based features."""
        if "close" not in df.columns:
            return df

        # Returns
        df["returns"] = df["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df["close"].shift(1))

        # Rolling volatility (standard deviation of returns)
        df["volatility_5"] = df["returns"].rolling(window=5).std() * np.sqrt(252)
        df["volatility_10"] = df["returns"].rolling(window=10).std() * np.sqrt(252)
        df["volatility_20"] = df["returns"].rolling(window=20).std() * np.sqrt(252)

        # Parkinson volatility (using high-low)
        if all(col in df.columns for col in ["high", "low"]):
            df["parkinson_vol"] = np.sqrt(
                1 / (4 * np.log(2)) * (np.log(df["high"] / df["low"]) ** 2).rolling(window=20).mean()
            ) * np.sqrt(252)

        # Average True Range (ATR)
        if all(col in df.columns for col in ["high", "low", "close"]):
            tr1 = df["high"] - df["low"]
            tr2 = abs(df["high"] - df["close"].shift(1))
            tr3 = abs(df["low"] - df["close"].shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df["atr_14"] = tr.rolling(window=14).mean()

            # Normalized ATR
            df["atr_pct"] = df["atr_14"] / df["close"]

        # Bollinger Band Width
        df["bb_ma"] = df["close"].rolling(window=20).mean()
        df["bb_std"] = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_ma"] + 2 * df["bb_std"]
        df["bb_lower"] = df["bb_ma"] - 2 * df["bb_std"]
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_ma"]
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"] + 1e-10)

        return df

    def _add_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum-based features."""
        if "close" not in df.columns:
            return df

        # Rate of Change (ROC)
        for period in [5, 10, 20]:
            df[f"roc_{period}"] = (df["close"] - df["close"].shift(period)) / df["close"].shift(period) * 100

        # Momentum
        for period in [5, 10, 20]:
            df[f"momentum_{period}"] = df["close"] - df["close"].shift(period)

        # RSI
        for period in [6, 14, 24]:
            df = self._add_rsi(df, period)

        # MACD
        df = self._add_macd(df)

        return df

    def _add_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
        """Add Relative Strength Index."""
        if "close" not in df.columns:
            return df

        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / (avg_loss + 1e-10)
        df[f"rsi_{period}"] = 100 - (100 / (1 + rs))

        return df

    def _add_macd(
        self,
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> pd.DataFrame:
        """Add MACD indicator."""
        if "close" not in df.columns:
            return df

        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()

        df["macd"] = ema_fast - ema_slow
        df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        return df

    def _add_trend_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add trend-based features."""
        if "close" not in df.columns:
            return df

        # Moving averages
        for period in [5, 10, 20, 50, 100, 200]:
            df[f"ma_{period}"] = df["close"].rolling(window=period).mean()

        # Exponential moving averages
        for period in [12, 20, 50]:
            df[f"ema_{period}"] = df["close"].ewm(span=period, adjust=False).mean()

        # Price relative to MAs
        for period in [20, 50, 200]:
            if f"ma_{period}" in df.columns:
                df[f"price_to_ma_{period}"] = df["close"] / df[f"ma_{period}"] - 1

        # MA crossovers
        if "ma_5" in df.columns and "ma_20" in df.columns:
            df["ma_cross_5_20"] = (df["ma_5"] > df["ma_20"]).astype(int)

        if "ma_20" in df.columns and "ma_50" in df.columns:
            df["ma_cross_20_50"] = (df["ma_20"] > df["ma_50"]).astype(int)

        # Trend strength (ADX-like)
        if all(col in df.columns for col in ["high", "low", "close"]):
            plus_dm = df["high"].diff()
            minus_dm = df["low"].diff()
            plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm.abs()), 0)
            minus_dm = minus_dm.where((minus_dm < 0) & (minus_dm.abs() > plus_dm.abs()), 0)

            tr = pd.concat(
                [
                    df["high"] - df["low"],
                    abs(df["high"] - df["close"].shift(1)),
                    abs(df["low"] - df["close"].shift(1)),
                ],
                axis=1,
            ).max(axis=1)

            atr = tr.rolling(window=14).mean()
            plus_di = 100 * (plus_dm.rolling(window=14).mean() / atr)
            minus_di = 100 * (minus_dm.abs().rolling(window=14).mean() / atr)

            df["plus_di"] = plus_di
            df["minus_di"] = minus_di
            df["adx"] = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100).rolling(
                window=14
            ).mean()

        return df

    def generate_lagged_features(
        self,
        df: pd.DataFrame,
        columns: list[str],
        lags: list[int],
    ) -> pd.DataFrame:
        """
        Generate lagged features for specified columns.

        Args:
            df: Input DataFrame
            columns: Columns to create lags for
            lags: List of lag periods

        Returns:
            DataFrame with lagged features
        """
        df = df.copy()

        for col in columns:
            if col not in df.columns:
                continue
            for lag in lags:
                df[f"{col}_lag_{lag}"] = df[col].shift(lag)

        return df

    def generate_rolling_features(
        self,
        df: pd.DataFrame,
        columns: list[str],
        windows: list[int],
        aggregations: list[str] = ["mean", "std", "min", "max"],
    ) -> pd.DataFrame:
        """
        Generate rolling window features.

        Args:
            df: Input DataFrame
            columns: Columns to create rolling features for
            windows: List of window sizes
            aggregations: Aggregation functions to apply

        Returns:
            DataFrame with rolling features
        """
        df = df.copy()

        for col in columns:
            if col not in df.columns:
                continue
            for window in windows:
                for agg in aggregations:
                    df[f"{col}_rolling_{agg}_{window}"] = df[col].rolling(window=window).agg(agg)

        return df