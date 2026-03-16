"""Momentum trading strategy."""

from typing import Optional

import pandas as pd
import numpy as np

from src.backtest.strategy import Signal
from src.strategies.base import BaseStrategy, StrategyConfig


class MomentumConfig(StrategyConfig):
    """Configuration for momentum strategy."""

    name: str = "MomentumStrategy"
    description: str = "Momentum strategy based on price momentum indicators"

    # Momentum parameters
    lookback_period: int = 20
    momentum_threshold: float = 0.02  # 2% momentum threshold
    volume_factor: float = 1.5  # Volume should be X times average
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0


class MomentumStrategy(BaseStrategy):
    """
    Momentum trading strategy.

    Generates buy signals when:
    - Price momentum is positive and above threshold
    - Volume is above average
    - RSI is not overbought

    Generates sell signals when:
    - Price momentum is negative
    - RSI is overbought
    """

    def __init__(self, config: Optional[MomentumConfig] = None):
        """
        Initialize momentum strategy.

        Args:
            config: Strategy configuration
        """
        config = config or MomentumConfig()
        super().__init__(config)
        self.config: MomentumConfig = config

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate momentum signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        if not self.validate_data(data):
            raise ValueError("Invalid data format")

        # Calculate indicators
        df = self.add_technical_indicators(data.copy())

        # Price momentum
        df["momentum"] = df["close"].pct_change(self.config.lookback_period)
        df["momentum_ma"] = df["momentum"].rolling(window=self.config.lookback_period).mean()

        # Volume analysis
        df["volume_ma"] = df["volume"].rolling(window=self.config.lookback_period).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ma"]

        # Generate signals
        signals = pd.Series(Signal.HOLD, index=df.index)

        # Buy conditions
        buy_condition = (
            (df["momentum"] > self.config.momentum_threshold) &
            (df["momentum"] > df["momentum_ma"]) &
            (df["volume_ratio"] > self.config.volume_factor) &
            (df["rsi_14"] < self.config.rsi_overbought) &
            (df["rsi_14"] > self.config.rsi_oversold)
        )

        # Sell conditions
        sell_condition = (
            (df["momentum"] < -self.config.momentum_threshold) |
            (df["rsi_14"] > self.config.rsi_overbought)
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        # Avoid consecutive signals
        signals = self._filter_consecutive_signals(signals)

        return signals

    def _filter_consecutive_signals(self, signals: pd.Series) -> pd.Series:
        """
        Filter out consecutive signals of the same type.

        Args:
            signals: Raw signals

        Returns:
            Filtered signals
        """
        filtered = signals.copy()
        last_signal = Signal.HOLD

        for idx in filtered.index:
            current = filtered[idx]
            if current == last_signal:
                filtered[idx] = Signal.HOLD
            else:
                last_signal = current

        return filtered


class RSIMomentumStrategy(BaseStrategy):
    """
    RSI-based momentum strategy.

    Uses RSI crossovers for signal generation.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize RSI momentum strategy.

        Args:
            rsi_period: RSI calculation period
            oversold: Oversold threshold
            overbought: Overbought threshold
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="RSIMomentumStrategy")
        super().__init__(config)
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate RSI momentum signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        df = data.copy()

        # Calculate RSI
        df["rsi"] = self.indicators.rsi(df["close"], self.rsi_period)
        df["rsi_ma"] = df["rsi"].rolling(window=5).mean()

        signals = pd.Series(Signal.HOLD, index=df.index)

        # Buy: RSI crosses above oversold from below
        buy_condition = (
            (df["rsi"] > self.oversold) &
            (df["rsi"].shift(1) <= self.oversold) &
            (df["rsi"] > df["rsi_ma"])
        )

        # Sell: RSI crosses below overbought from above
        sell_condition = (
            (df["rsi"] < self.overbought) &
            (df["rsi"].shift(1) >= self.overbought)
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals


class MACDMomentumStrategy(BaseStrategy):
    """
    MACD-based momentum strategy.

    Uses MACD crossovers and histogram for signals.
    """

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize MACD momentum strategy.

        Args:
            fast_period: Fast EMA period
            slow_period: Slow EMA period
            signal_period: Signal line period
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="MACDMomentumStrategy")
        super().__init__(config)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate MACD momentum signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        df = data.copy()

        # Calculate MACD
        macd = self.indicators.macd(
            df["close"],
            self.fast_period,
            self.slow_period,
            self.signal_period,
        )
        df["macd"] = macd["macd"]
        df["signal"] = macd["signal"]
        df["histogram"] = macd["histogram"]

        signals = pd.Series(Signal.HOLD, index=df.index)

        # Buy: MACD crosses above signal line
        buy_condition = (
            (df["macd"] > df["signal"]) &
            (df["macd"].shift(1) <= df["signal"].shift(1)) &
            (df["histogram"] > 0)
        )

        # Sell: MACD crosses below signal line
        sell_condition = (
            (df["macd"] < df["signal"]) &
            (df["macd"].shift(1) >= df["signal"].shift(1))
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals