"""Trend following trading strategy."""

from typing import Optional

import pandas as pd
import numpy as np

from src.backtest.strategy import Signal
from src.strategies.base import BaseStrategy, StrategyConfig


class TrendFollowingConfig(StrategyConfig):
    """Configuration for trend following strategy."""

    name: str = "TrendFollowingStrategy"
    description: str = "Trend following strategy using moving averages"

    # Trend parameters
    fast_period: int = 20
    slow_period: int = 50
    trend_filter_period: int = 200
    atr_period: int = 14
    atr_multiplier: float = 2.0


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend following trading strategy.

    Follows established trends using moving averages.

    Generates buy signals when:
    - Fast MA crosses above slow MA
    - Price is above long-term trend filter
    - ADX shows trending market

    Generates sell signals when:
    - Fast MA crosses below slow MA
    - Trend weakens
    """

    def __init__(self, config: Optional[TrendFollowingConfig] = None):
        """
        Initialize trend following strategy.

        Args:
            config: Strategy configuration
        """
        config = config or TrendFollowingConfig()
        super().__init__(config)
        self.config: TrendFollowingConfig = config

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate trend following signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        if not self.validate_data(data):
            raise ValueError("Invalid data format")

        df = data.copy()

        # Moving averages
        df["fast_ma"] = self.indicators.sma(df["close"], self.config.fast_period)
        df["slow_ma"] = self.indicators.sma(df["close"], self.config.slow_period)
        df["trend_filter"] = self.indicators.sma(df["close"], self.config.trend_filter_period)

        # ADX for trend strength
        adx = self.indicators.adx(
            df["high"],
            df["low"],
            df["close"],
        )
        df["adx"] = adx["adx"]

        # ATR for trailing stops
        df["atr"] = self.indicators.atr(
            df["high"],
            df["low"],
            df["close"],
            self.config.atr_period,
        )

        # Trend direction
        df["trend_up"] = df["fast_ma"] > df["slow_ma"]
        df["trend_down"] = df["fast_ma"] < df["slow_ma"]

        # Generate signals
        signals = pd.Series(Signal.HOLD, index=df.index)

        # Buy: Golden cross with trend filter
        buy_condition = (
            (df["fast_ma"] > df["slow_ma"]) &
            (df["fast_ma"].shift(1) <= df["slow_ma"].shift(1)) &
            (df["close"] > df["trend_filter"]) &
            (df["adx"] > 25)  # Strong trend
        )

        # Sell: Death cross or trend weakness
        sell_condition = (
            (df["fast_ma"] < df["slow_ma"]) &
            (df["fast_ma"].shift(1) >= df["slow_ma"].shift(1))
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals

    def calculate_trailing_stop(
        self,
        data: pd.DataFrame,
        position_side: str,
    ) -> pd.Series:
        """
        Calculate ATR-based trailing stop levels.

        Args:
            data: OHLCV DataFrame
            position_side: 'long' or 'short'

        Returns:
            Series of stop prices
        """
        df = data.copy()

        atr = self.indicators.atr(
            df["high"],
            df["low"],
            df["close"],
            self.config.atr_period,
        )

        if position_side == "long":
            # Trailing stop below price
            return df["close"] - atr * self.config.atr_multiplier
        else:
            # Trailing stop above price
            return df["close"] + atr * self.config.atr_multiplier


class BreakoutStrategy(BaseStrategy):
    """
    Breakout trading strategy.

    Enters on breakouts from consolidation ranges.
    """

    def __init__(
        self,
        lookback: int = 20,
        atr_period: int = 14,
        volume_threshold: float = 1.5,
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize breakout strategy.

        Args:
            lookback: Lookback period for range calculation
            atr_period: ATR period for volatility
            volume_threshold: Volume must be X times average
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="BreakoutStrategy")
        super().__init__(config)
        self.lookback = lookback
        self.atr_period = atr_period
        self.volume_threshold = volume_threshold

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate breakout signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        df = data.copy()

        # Calculate range
        df["range_high"] = df["high"].rolling(window=self.lookback).max()
        df["range_low"] = df["low"].rolling(window=self.lookback).min()
        df["range"] = df["range_high"] - df["range_low"]

        # ATR for volatility filter
        df["atr"] = self.indicators.atr(
            df["high"],
            df["low"],
            df["close"],
            self.atr_period,
        )

        # Volume filter
        df["volume_ma"] = df["volume"].rolling(window=self.lookback).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ma"]

        # Breakout conditions
        signals = pd.Series(Signal.HOLD, index=df.index)

        # Upside breakout
        buy_condition = (
            (df["close"] > df["range_high"].shift(1)) &
            (df["volume_ratio"] > self.volume_threshold) &
            (df["range"] > df["atr"])  # Meaningful range
        )

        # Downside breakout (for shorts or exits)
        sell_condition = (
            df["close"] < df["range_low"].shift(1)
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals


class IchimokuStrategy(BaseStrategy):
    """
    Ichimoku Cloud based trend strategy.

    Uses Ichimoku components for trend identification and signals.
    """

    def __init__(
        self,
        tenkan: int = 9,
        kijun: int = 26,
        senkou: int = 52,
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize Ichimoku strategy.

        Args:
            tenkan: Tenkan-sen period
            kijun: Kijun-sen period
            senkou: Senkou Span B period
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="IchimokuStrategy")
        super().__init__(config)
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou = senkou

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate Ichimoku signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        df = data.copy()

        # Calculate Ichimoku components
        ichimoku = self.indicators.ichimoku(
            df["high"],
            df["low"],
            df["close"],
            self.tenkan,
            self.kijun,
            self.senkou,
        )

        df["tenkan"] = ichimoku["tenkan_sen"]
        df["kijun"] = ichimoku["kijun_sen"]
        df["senkou_a"] = ichimoku["senkou_span_a"]
        df["senkou_b"] = ichimoku["senkou_span_b"]

        # Cloud colors
        df["cloud_green"] = df["senkou_a"] > df["senkou_b"]
        df["cloud_red"] = df["senkou_a"] < df["senkou_b"]

        # Generate signals
        signals = pd.Series(Signal.HOLD, index=df.index)

        # Buy: TK cross above cloud
        buy_condition = (
            (df["tenkan"] > df["kijun"]) &
            (df["tenkan"].shift(1) <= df["kijun"].shift(1)) &
            (df["close"] > df["senkou_a"]) &
            (df["close"] > df["senkou_b"]) &
            df["cloud_green"]
        )

        # Sell: TK cross below cloud or cloud turns red
        sell_condition = (
            (df["tenkan"] < df["kijun"]) &
            (df["tenkan"].shift(1) >= df["kijun"].shift(1))
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals