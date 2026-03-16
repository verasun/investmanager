"""Candlestick pattern recognition."""

from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class PatternRecognition:
    """Recognize candlestick patterns in OHLCV data."""

    def __init__(self, min_body_ratio: float = 0.3):
        """
        Initialize pattern recognition.

        Args:
            min_body_ratio: Minimum body/candle ratio for pattern detection
        """
        self.min_body_ratio = min_body_ratio

    def recognize_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Recognize all patterns and return DataFrame with pattern flags.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with pattern columns added
        """
        df = df.copy()

        # Calculate basic candle properties
        df["body"] = df["close"] - df["open"]
        df["body_abs"] = df["body"].abs()
        df["upper_shadow"] = df["high"] - df[["open", "close"]].max(axis=1)
        df["lower_shadow"] = df[["open", "close"]].min(axis=1) - df["low"]
        df["candle_range"] = df["high"] - df["low"]
        df["is_bullish"] = df["close"] > df["open"]

        # Single candle patterns
        df["doji"] = self._detect_doji(df)
        df["hammer"] = self._detect_hammer(df)
        df["hanging_man"] = self._detect_hanging_man(df)
        df["inverted_hammer"] = self._detect_inverted_hammer(df)
        df["shooting_star"] = self._detect_shooting_star(df)
        df["marubozu"] = self._detect_marubozu(df)
        df["spinning_top"] = self._detect_spinning_top(df)

        # Double candle patterns
        df["bullish_engulfing"] = self._detect_bullish_engulfing(df)
        df["bearish_engulfing"] = self._detect_bearish_engulfing(df)
        df["piercing_line"] = self._detect_piercing_line(df)
        df["dark_cloud_cover"] = self._detect_dark_cloud_cover(df)
        df["tweezer_top"] = self._detect_tweezer_top(df)
        df["tweezer_bottom"] = self._detect_tweezer_bottom(df)

        # Triple candle patterns
        df["morning_star"] = self._detect_morning_star(df)
        df["evening_star"] = self._detect_evening_star(df)
        df["three_white_soldiers"] = self._detect_three_white_soldiers(df)
        df["three_black_crows"] = self._detect_three_black_crows(df)
        df["three_inside_up"] = self._detect_three_inside_up(df)
        df["three_inside_down"] = self._detect_three_inside_down(df)

        return df

    def _detect_doji(self, df: pd.DataFrame) -> pd.Series:
        """Detect Doji pattern (open ≈ close)."""
        body_threshold = df["candle_range"] * 0.1
        return (df["body_abs"] <= body_threshold) & (df["candle_range"] > 0)

    def _detect_hammer(self, df: pd.DataFrame) -> pd.Series:
        """Detect Hammer pattern (bullish reversal)."""
        return (
            (df["lower_shadow"] >= df["body_abs"] * 2)
            & (df["upper_shadow"] <= df["body_abs"] * 0.3)
            & (df["lower_shadow"] >= df["candle_range"] * 0.6)
        )

    def _detect_hanging_man(self, df: pd.DataFrame) -> pd.Series:
        """Detect Hanging Man pattern (bearish reversal)."""
        # Same as hammer but in uptrend
        hammer = (
            (df["lower_shadow"] >= df["body_abs"] * 2)
            & (df["upper_shadow"] <= df["body_abs"] * 0.3)
            & (df["lower_shadow"] >= df["candle_range"] * 0.6)
        )
        # Check if in uptrend (close > close 3 days ago)
        uptrend = df["close"] > df["close"].shift(3)
        return hammer & uptrend

    def _detect_inverted_hammer(self, df: pd.DataFrame) -> pd.Series:
        """Detect Inverted Hammer pattern (bullish reversal)."""
        return (
            (df["upper_shadow"] >= df["body_abs"] * 2)
            & (df["lower_shadow"] <= df["body_abs"] * 0.3)
            & (df["upper_shadow"] >= df["candle_range"] * 0.6)
        )

    def _detect_shooting_star(self, df: pd.DataFrame) -> pd.Series:
        """Detect Shooting Star pattern (bearish reversal)."""
        inverted_hammer = (
            (df["upper_shadow"] >= df["body_abs"] * 2)
            & (df["lower_shadow"] <= df["body_abs"] * 0.3)
            & (df["upper_shadow"] >= df["candle_range"] * 0.6)
        )
        uptrend = df["close"] > df["close"].shift(3)
        return inverted_hammer & uptrend

    def _detect_marubozu(self, df: pd.DataFrame) -> pd.Series:
        """Detect Marubozu pattern (strong directional candle)."""
        no_shadows = (df["upper_shadow"] <= df["candle_range"] * 0.05) & (
            df["lower_shadow"] <= df["candle_range"] * 0.05
        )
        has_body = df["body_abs"] >= df["candle_range"] * 0.9
        return no_shadows & has_body

    def _detect_spinning_top(self, df: pd.DataFrame) -> pd.Series:
        """Detect Spinning Top pattern (indecision)."""
        small_body = df["body_abs"] <= df["candle_range"] * 0.3
        equal_shadows = (df["upper_shadow"] >= df["body_abs"] * 0.5) & (
            df["lower_shadow"] >= df["body_abs"] * 0.5
        )
        return small_body & equal_shadows

    def _detect_bullish_engulfing(self, df: pd.DataFrame) -> pd.Series:
        """Detect Bullish Engulfing pattern."""
        prev_bearish = df["close"].shift(1) < df["open"].shift(1)
        curr_bullish = df["close"] > df["open"]
        engulf = (df["open"] < df["close"].shift(1)) & (df["close"] > df["open"].shift(1))
        return prev_bearish & curr_bullish & engulf

    def _detect_bearish_engulfing(self, df: pd.DataFrame) -> pd.Series:
        """Detect Bearish Engulfing pattern."""
        prev_bullish = df["close"].shift(1) > df["open"].shift(1)
        curr_bearish = df["close"] < df["open"]
        engulf = (df["open"] > df["close"].shift(1)) & (df["close"] < df["open"].shift(1))
        return prev_bullish & curr_bearish & engulf

    def _detect_piercing_line(self, df: pd.DataFrame) -> pd.Series:
        """Detect Piercing Line pattern (bullish reversal)."""
        prev_bearish = df["close"].shift(1) < df["open"].shift(1)
        curr_bullish = df["close"] > df["open"]
        opens_below = df["open"] < df["low"].shift(1)
        closes_mid = (df["close"] > (df["open"].shift(1) + df["close"].shift(1)) / 2) & (
            df["close"] < df["open"].shift(1)
        )
        return prev_bearish & curr_bullish & opens_below & closes_mid

    def _detect_dark_cloud_cover(self, df: pd.DataFrame) -> pd.Series:
        """Detect Dark Cloud Cover pattern (bearish reversal)."""
        prev_bullish = df["close"].shift(1) > df["open"].shift(1)
        curr_bearish = df["close"] < df["open"]
        opens_above = df["open"] > df["high"].shift(1)
        closes_mid = (df["close"] < (df["open"].shift(1) + df["close"].shift(1)) / 2) & (
            df["close"] > df["open"].shift(1)
        )
        return prev_bullish & curr_bearish & opens_above & closes_mid

    def _detect_tweezer_top(self, df: pd.DataFrame) -> pd.Series:
        """Detect Tweezer Top pattern (bearish reversal)."""
        same_high = abs(df["high"] - df["high"].shift(1)) <= df["high"] * 0.002
        first_bullish = df["close"].shift(1) > df["open"].shift(1)
        second_bearish = df["close"] < df["open"]
        return same_high & first_bullish & second_bearish

    def _detect_tweezer_bottom(self, df: pd.DataFrame) -> pd.Series:
        """Detect Tweezer Bottom pattern (bullish reversal)."""
        same_low = abs(df["low"] - df["low"].shift(1)) <= df["low"] * 0.002
        first_bearish = df["close"].shift(1) < df["open"].shift(1)
        second_bullish = df["close"] > df["open"]
        return same_low & first_bearish & second_bullish

    def _detect_morning_star(self, df: pd.DataFrame) -> pd.Series:
        """Detect Morning Star pattern (bullish reversal)."""
        # First candle: large bearish
        first_bearish = (df["close"].shift(2) < df["open"].shift(2)) & (
            df["body_abs"].shift(2) >= df["candle_range"].shift(2) * 0.6
        )
        # Second candle: small body (doji-like)
        second_small = df["body_abs"].shift(1) <= df["candle_range"].shift(1) * 0.3
        # Third candle: large bullish
        third_bullish = (df["close"] > df["open"]) & (
            df["body_abs"] >= df["candle_range"] * 0.6
        )
        # Third closes above first midpoint
        closes_above = df["close"] > (df["open"].shift(2) + df["close"].shift(2)) / 2

        return first_bearish & second_small & third_bullish & closes_above

    def _detect_evening_star(self, df: pd.DataFrame) -> pd.Series:
        """Detect Evening Star pattern (bearish reversal)."""
        # First candle: large bullish
        first_bullish = (df["close"].shift(2) > df["open"].shift(2)) & (
            df["body_abs"].shift(2) >= df["candle_range"].shift(2) * 0.6
        )
        # Second candle: small body (doji-like)
        second_small = df["body_abs"].shift(1) <= df["candle_range"].shift(1) * 0.3
        # Third candle: large bearish
        third_bearish = (df["close"] < df["open"]) & (
            df["body_abs"] >= df["candle_range"] * 0.6
        )
        # Third closes below first midpoint
        closes_below = df["close"] < (df["open"].shift(2) + df["close"].shift(2)) / 2

        return first_bullish & second_small & third_bearish & closes_below

    def _detect_three_white_soldiers(self, df: pd.DataFrame) -> pd.Series:
        """Detect Three White Soldiers pattern (strong bullish)."""
        three_bullish = (
            (df["close"].shift(2) > df["open"].shift(2))
            & (df["close"].shift(1) > df["open"].shift(1))
            & (df["close"] > df["open"])
        )
        each_closes_higher = (
            (df["close"].shift(1) > df["close"].shift(2))
            & (df["close"] > df["close"].shift(1))
        )
        small_shadows = (
            (df["upper_shadow"].shift(2) < df["body_abs"].shift(2))
            & (df["upper_shadow"].shift(1) < df["body_abs"].shift(1))
            & (df["upper_shadow"] < df["body_abs"])
        )

        return three_bullish & each_closes_higher & small_shadows

    def _detect_three_black_crows(self, df: pd.DataFrame) -> pd.Series:
        """Detect Three Black Crows pattern (strong bearish)."""
        three_bearish = (
            (df["close"].shift(2) < df["open"].shift(2))
            & (df["close"].shift(1) < df["open"].shift(1))
            & (df["close"] < df["open"])
        )
        each_closes_lower = (
            (df["close"].shift(1) < df["close"].shift(2))
            & (df["close"] < df["close"].shift(1))
        )
        small_shadows = (
            (df["lower_shadow"].shift(2) < df["body_abs"].shift(2))
            & (df["lower_shadow"].shift(1) < df["body_abs"].shift(1))
            & (df["lower_shadow"] < df["body_abs"])
        )

        return three_bearish & each_closes_lower & small_shadows

    def _detect_three_inside_up(self, df: pd.DataFrame) -> pd.Series:
        """Detect Three Inside Up pattern (bullish reversal)."""
        first_bearish = df["close"].shift(2) < df["open"].shift(2)
        first_large = df["body_abs"].shift(2) >= df["candle_range"].shift(2) * 0.6
        second_bullish = df["close"].shift(1) > df["open"].shift(1)
        second_inside = (df["open"].shift(1) > df["close"].shift(2)) & (
            df["close"].shift(1) < df["open"].shift(2)
        )
        third_bullish = df["close"] > df["open"]
        third_closes_higher = df["close"] > df["close"].shift(1)

        return first_bearish & first_large & second_bullish & second_inside & third_bullish & third_closes_higher

    def _detect_three_inside_down(self, df: pd.DataFrame) -> pd.Series:
        """Detect Three Inside Down pattern (bearish reversal)."""
        first_bullish = df["close"].shift(2) > df["open"].shift(2)
        first_large = df["body_abs"].shift(2) >= df["candle_range"].shift(2) * 0.6
        second_bearish = df["close"].shift(1) < df["open"].shift(1)
        second_inside = (df["open"].shift(1) < df["close"].shift(2)) & (
            df["close"].shift(1) > df["open"].shift(2)
        )
        third_bearish = df["close"] < df["open"]
        third_closes_lower = df["close"] < df["close"].shift(1)

        return first_bullish & first_large & second_bearish & second_inside & third_bearish & third_closes_lower

    def get_pattern_summary(self, df: pd.DataFrame) -> dict:
        """
        Get summary of detected patterns.

        Args:
            df: DataFrame with pattern flags

        Returns:
            Dictionary with pattern counts
        """
        pattern_cols = [
            "doji",
            "hammer",
            "hanging_man",
            "inverted_hammer",
            "shooting_star",
            "marubozu",
            "spinning_top",
            "bullish_engulfing",
            "bearish_engulfing",
            "piercing_line",
            "dark_cloud_cover",
            "tweezer_top",
            "tweezer_bottom",
            "morning_star",
            "evening_star",
            "three_white_soldiers",
            "three_black_crows",
            "three_inside_up",
            "three_inside_down",
        ]

        summary = {}
        for col in pattern_cols:
            if col in df.columns:
                count = df[col].sum()
                if count > 0:
                    summary[col] = int(count)

        return summary

    def get_latest_patterns(self, df: pd.DataFrame, n: int = 5) -> list[str]:
        """
        Get patterns detected in the latest candle.

        Args:
            df: DataFrame with pattern flags
            n: Number of recent candles to check

        Returns:
            List of detected pattern names
        """
        if df.empty:
            return []

        pattern_cols = [
            "doji",
            "hammer",
            "hanging_man",
            "inverted_hammer",
            "shooting_star",
            "marubozu",
            "spinning_top",
            "bullish_engulfing",
            "bearish_engulfing",
            "piercing_line",
            "dark_cloud_cover",
            "tweezer_top",
            "tweezer_bottom",
            "morning_star",
            "evening_star",
            "three_white_soldiers",
            "three_black_crows",
            "three_inside_up",
            "three_inside_down",
        ]

        detected = []
        latest = df.iloc[-1]

        for col in pattern_cols:
            if col in df.columns and latest[col]:
                detected.append(col)

        return detected

    def detect_all(self, df: pd.DataFrame) -> dict:
        """
        Detect all patterns and return a dictionary of pattern counts.
        Alias for get_pattern_summary after recognize_all.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            Dictionary with pattern names and their occurrence counts
        """
        result = self.recognize_all(df)
        return self.get_pattern_summary(result)


# Alias for backward compatibility
PatternDetector = PatternRecognition