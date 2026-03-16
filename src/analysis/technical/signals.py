"""Trading signal generation based on technical analysis."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from src.analysis.technical.indicators import TechnicalIndicators
from src.analysis.technical.patterns import PatternRecognition
from src.data.models import SignalType, TradingSignal


class SignalStrength(str, Enum):
    """Signal strength levels."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class SignalGenerator:
    """Generate trading signals based on technical analysis."""

    def __init__(self):
        """Initialize signal generator."""
        self.indicators = TechnicalIndicators()
        self.patterns = PatternRecognition()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals from OHLCV data.

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with signals added
        """
        if df.empty or len(df) < 50:
            logger.warning("Insufficient data for signal generation")
            return df

        df = df.copy()

        # Add indicators
        df = self.indicators.add_all_indicators(df)

        # Add patterns
        df = self.patterns.recognize_all(df)

        # Generate individual signals
        df["rsi_signal"] = self._rsi_signal(df)
        df["macd_signal"] = self._macd_signal(df)
        df["bb_signal"] = self._bollinger_signal(df)
        df["kdj_signal"] = self._kdj_signal(df)
        df["ma_signal"] = self._ma_crossover_signal(df)
        df["adx_signal"] = self._adx_signal(df)
        df["pattern_signal"] = self._pattern_signal(df)
        df["volume_signal"] = self._volume_signal(df)

        # Combine signals into composite signal
        df["composite_signal"] = self._composite_signal(df)

        # Calculate signal strength
        df["signal_strength"] = self._calculate_strength(df)

        return df

    def _rsi_signal(self, df: pd.DataFrame) -> pd.Series:
        """RSI-based signal."""
        signal = pd.Series(0, index=df.index)

        # Oversold - buy signal
        signal[df["rsi_14"] < 30] = 1
        # Overbought - sell signal
        signal[df["rsi_14"] > 70] = -1

        # Stronger signals at extremes
        signal[df["rsi_14"] < 20] = 2
        signal[df["rsi_14"] > 80] = -2

        return signal

    def _macd_signal(self, df: pd.DataFrame) -> pd.Series:
        """MACD-based signal."""
        signal = pd.Series(0, index=df.index)

        # MACD cross above signal line - buy
        macd_cross_up = (df["macd"] > df["macd_signal"]) & (
            df["macd"].shift(1) <= df["macd_signal"].shift(1)
        )
        signal[macd_cross_up] = 1

        # MACD cross below signal line - sell
        macd_cross_down = (df["macd"] < df["macd_signal"]) & (
            df["macd"].shift(1) >= df["macd_signal"].shift(1)
        )
        signal[macd_cross_down] = -1

        # Histogram direction
        hist_positive = df["macd_hist"] > 0
        hist_negative = df["macd_hist"] < 0

        signal[hist_positive & (signal == 0)] = 0.5
        signal[hist_negative & (signal == 0)] = -0.5

        return signal

    def _bollinger_signal(self, df: pd.DataFrame) -> pd.Series:
        """Bollinger Bands-based signal."""
        signal = pd.Series(0, index=df.index)

        # Price below lower band - buy
        signal[df["close"] < df["bb_lower"]] = 1

        # Price above upper band - sell
        signal[df["close"] > df["bb_upper"]] = -1

        # Price near bands
        df["bb_position"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
        signal[df["bb_position"] < 0.2] = 0.5
        signal[df["bb_position"] > 0.8] = -0.5

        return signal

    def _kdj_signal(self, df: pd.DataFrame) -> pd.Series:
        """KDJ-based signal."""
        signal = pd.Series(0, index=df.index)

        # K crosses above D - buy
        k_cross_up = (df["k"] > df["d"]) & (df["k"].shift(1) <= df["d"].shift(1))
        signal[k_cross_up] = 1

        # K crosses below D - sell
        k_cross_down = (df["k"] < df["d"]) & (df["k"].shift(1) >= df["d"].shift(1))
        signal[k_cross_down] = -1

        # Oversold/overbought
        signal[(df["k"] < 20) & (df["d"] < 20)] = 1
        signal[(df["k"] > 80) & (df["d"] > 80)] = -1

        return signal

    def _ma_crossover_signal(self, df: pd.DataFrame) -> pd.Series:
        """Moving average crossover signal."""
        signal = pd.Series(0, index=df.index)

        # SMA 5/20 crossover
        sma5_cross_up = (df["sma_5"] > df["sma_20"]) & (
            df["sma_5"].shift(1) <= df["sma_20"].shift(1)
        )
        sma5_cross_down = (df["sma_5"] < df["sma_20"]) & (
            df["sma_5"].shift(1) >= df["sma_20"].shift(1)
        )

        signal[sma5_cross_up] = 1
        signal[sma5_cross_down] = -1

        # Price above/below SMA 50
        signal[(df["close"] > df["sma_50"]) & (signal == 0)] = 0.3
        signal[(df["close"] < df["sma_50"]) & (signal == 0)] = -0.3

        # Golden cross (50/200)
        golden_cross = (df["sma_50"] > df["sma_200"]) & (
            df["sma_50"].shift(1) <= df["sma_200"].shift(1)
        )
        death_cross = (df["sma_50"] < df["sma_200"]) & (
            df["sma_50"].shift(1) >= df["sma_200"].shift(1)
        )

        signal[golden_cross] = 2
        signal[death_cross] = -2

        return signal

    def _adx_signal(self, df: pd.DataFrame) -> pd.Series:
        """ADX trend strength signal."""
        signal = pd.Series(0, index=df.index)

        # Strong trend conditions
        strong_trend = df["adx"] > 25

        # DI crossover with trend
        di_cross_up = (df["plus_di"] > df["minus_di"]) & (
            df["plus_di"].shift(1) <= df["minus_di"].shift(1)
        )
        di_cross_down = (df["plus_di"] < df["minus_di"]) & (
            df["plus_di"].shift(1) >= df["minus_di"].shift(1)
        )

        signal[di_cross_up & strong_trend] = 1
        signal[di_cross_down & strong_trend] = -1

        return signal

    def _pattern_signal(self, df: pd.DataFrame) -> pd.Series:
        """Candlestick pattern-based signal."""
        signal = pd.Series(0, index=df.index)

        # Bullish patterns
        bullish_patterns = [
            "hammer",
            "inverted_hammer",
            "bullish_engulfing",
            "piercing_line",
            "tweezer_bottom",
            "morning_star",
            "three_white_soldiers",
            "three_inside_up",
        ]

        # Bearish patterns
        bearish_patterns = [
            "hanging_man",
            "shooting_star",
            "bearish_engulfing",
            "dark_cloud_cover",
            "tweezer_top",
            "evening_star",
            "three_black_crows",
            "three_inside_down",
        ]

        for pattern in bullish_patterns:
            if pattern in df.columns:
                signal[df[pattern]] = 1

        for pattern in bearish_patterns:
            if pattern in df.columns:
                signal[df[pattern]] = -1

        return signal

    def _volume_signal(self, df: pd.DataFrame) -> pd.Series:
        """Volume-based signal."""
        signal = pd.Series(0, index=df.index)

        if "volume_ratio" not in df.columns:
            df["volume_ratio"] = df["volume"] / df["volume"].rolling(20).mean()

        # High volume with price increase
        high_vol_up = (df["volume_ratio"] > 1.5) & (df["close"] > df["open"])
        signal[high_vol_up] = 0.5

        # High volume with price decrease
        high_vol_down = (df["volume_ratio"] > 1.5) & (df["close"] < df["open"])
        signal[high_vol_down] = -0.5

        return signal

    def _composite_signal(self, df: pd.DataFrame) -> pd.Series:
        """Combine all signals into composite signal."""
        signal_columns = [
            "rsi_signal",
            "macd_signal",
            "bb_signal",
            "kdj_signal",
            "ma_signal",
            "adx_signal",
            "pattern_signal",
            "volume_signal",
        ]

        weights = {
            "rsi_signal": 1.0,
            "macd_signal": 1.5,
            "bb_signal": 1.0,
            "kdj_signal": 1.0,
            "ma_signal": 2.0,
            "adx_signal": 1.0,
            "pattern_signal": 1.5,
            "volume_signal": 0.5,
        }

        composite = pd.Series(0.0, index=df.index)
        total_weight = 0

        for col in signal_columns:
            if col in df.columns:
                composite += df[col] * weights[col]
                total_weight += weights[col]

        if total_weight > 0:
            composite = composite / total_weight

        return composite

    def _calculate_strength(self, df: pd.DataFrame) -> pd.Series:
        """Calculate signal strength from composite signal."""
        strength = pd.Series(SignalStrength.NEUTRAL, index=df.index)

        strength[df["composite_signal"] >= 1.5] = SignalStrength.STRONG_BUY
        strength[df["composite_signal"] >= 0.5] = SignalStrength.BUY
        strength[df["composite_signal"] <= -1.5] = SignalStrength.STRONG_SELL
        strength[df["composite_signal"] <= -0.5] = SignalStrength.SELL

        return strength

    def get_latest_signal(self, df: pd.DataFrame, symbol: str) -> Optional[TradingSignal]:
        """
        Get the latest trading signal for a symbol.

        Args:
            df: DataFrame with signals
            symbol: Stock symbol

        Returns:
            TradingSignal object or None
        """
        if df.empty:
            return None

        df = self.generate_signals(df)
        latest = df.iloc[-1]

        strength = latest.get("signal_strength", SignalStrength.NEUTRAL)
        composite = latest.get("composite_signal", 0)

        # Map to signal value
        if strength == SignalStrength.STRONG_BUY:
            signal_value = SignalType.BUY
            confidence = 0.9
        elif strength == SignalStrength.BUY:
            signal_value = SignalType.BUY
            confidence = 0.7
        elif strength == SignalStrength.STRONG_SELL:
            signal_value = SignalType.SELL
            confidence = 0.9
        elif strength == SignalStrength.SELL:
            signal_value = SignalType.SELL
            confidence = 0.7
        else:
            signal_value = SignalType.HOLD
            confidence = 0.5

        return TradingSignal(
            symbol=symbol,
            signal_type="composite",
            signal_value=signal_value,
            confidence=Decimal(str(abs(composite))),
            price_at_signal=Decimal(str(latest["close"])),
            generated_at=datetime.now(),
            strategy_name="technical_composite",
            parameters={
                "rsi": float(latest.get("rsi_14", 0)),
                "macd_hist": float(latest.get("macd_hist", 0)),
                "adx": float(latest.get("adx", 0)),
                "strength": strength.value if isinstance(strength, SignalStrength) else strength,
            },
        )