"""Mean reversion trading strategy."""

from typing import Optional

import pandas as pd
import numpy as np

from src.backtest.strategy import Signal
from src.strategies.base import BaseStrategy, StrategyConfig


class MeanReversionConfig(StrategyConfig):
    """Configuration for mean reversion strategy."""

    name: str = "MeanReversionStrategy"
    description: str = "Mean reversion strategy using Bollinger Bands"

    # Mean reversion parameters
    lookback_period: int = 20
    std_dev: float = 2.0
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    zscore_threshold: float = 2.0


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion trading strategy.

    Assumes prices will revert to the mean.

    Generates buy signals when:
    - Price is below lower Bollinger Band
    - RSI is oversold
    - Z-score is below negative threshold

    Generates sell signals when:
    - Price is above upper Bollinger Band
    - RSI is overbought
    - Z-score is above positive threshold
    """

    def __init__(self, config: Optional[MeanReversionConfig] = None):
        """
        Initialize mean reversion strategy.

        Args:
            config: Strategy configuration
        """
        config = config or MeanReversionConfig()
        super().__init__(config)
        self.config: MeanReversionConfig = config

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate mean reversion signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        if not self.validate_data(data):
            raise ValueError("Invalid data format")

        df = data.copy()

        # Bollinger Bands
        bb = self.indicators.bollinger_bands(
            df["close"],
            self.config.lookback_period,
            self.config.std_dev,
        )
        df["bb_upper"] = bb["upper"]
        df["bb_lower"] = bb["lower"]
        df["bb_middle"] = bb["middle"]
        df["bb_width"] = bb["width"]

        # Z-score
        df["zscore"] = self._calculate_zscore(df["close"], self.config.lookback_period)

        # RSI
        df["rsi"] = self.indicators.rsi(df["close"], 14)

        # %B indicator (position within Bollinger Bands)
        df["percent_b"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # Generate signals
        signals = pd.Series(Signal.HOLD, index=df.index)

        # Buy conditions: Price at lower extreme
        buy_condition = (
            (df["close"] < df["bb_lower"]) &
            (df["zscore"] < -self.config.zscore_threshold) &
            (df["rsi"] < self.config.rsi_oversold)
        )

        # Sell conditions: Price at upper extreme
        sell_condition = (
            (df["close"] > df["bb_upper"]) &
            (df["zscore"] > self.config.zscore_threshold) &
            (df["rsi"] > self.config.rsi_overbought)
        )

        # Exit conditions for long positions
        exit_long = (
            (df["close"] > df["bb_middle"]) |
            (df["percent_b"] > 0.8)
        )

        # Exit conditions for short positions
        exit_short = (
            (df["close"] < df["bb_middle"]) |
            (df["percent_b"] < 0.2)
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals

    def _calculate_zscore(self, series: pd.Series, window: int) -> pd.Series:
        """
        Calculate rolling z-score.

        Args:
            series: Price series
            window: Rolling window

        Returns:
            Z-score series
        """
        mean = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        return (series - mean) / (std + 1e-10)


class PairsTradingStrategy(BaseStrategy):
    """
    Pairs trading strategy.

    Trades the spread between two correlated instruments.
    """

    def __init__(
        self,
        lookback: int = 30,
        entry_zscore: float = 2.0,
        exit_zscore: float = 0.5,
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize pairs trading strategy.

        Args:
            lookback: Lookback period for spread calculation
            entry_zscore: Z-score threshold for entry
            exit_zscore: Z-score threshold for exit
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="PairsTradingStrategy")
        super().__init__(config)
        self.lookback = lookback
        self.entry_zscore = entry_zscore
        self.exit_zscore = exit_zscore

    def calculate_signals(
        self,
        data: pd.DataFrame,
        pair_data: Optional[pd.DataFrame] = None,
    ) -> pd.Series:
        """
        Calculate pairs trading signals.

        Args:
            data: Primary OHLCV DataFrame
            pair_data: Secondary OHLCV DataFrame for the pair

        Returns:
            Series of Signal values
        """
        if pair_data is None:
            # Use synthetic pair (e.g., sector ETF)
            return pd.Series(Signal.HOLD, index=data.index)

        # Calculate spread
        spread = self._calculate_spread(data["close"], pair_data["close"])

        # Calculate z-score of spread
        zscore = self._calculate_zscore(spread, self.lookback)

        signals = pd.Series(Signal.HOLD, index=data.index)

        # Buy when spread is too wide (expect convergence)
        buy_condition = zscore < -self.entry_zscore

        # Sell when spread is too narrow or reversed
        sell_condition = zscore > self.entry_zscore

        # Exit positions when spread normalizes
        # This would be handled by position management

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals

    def _calculate_spread(
        self,
        series1: pd.Series,
        series2: pd.Series,
    ) -> pd.Series:
        """
        Calculate spread between two series using hedge ratio.

        Args:
            series1: First price series
            series2: Second price series

        Returns:
            Spread series
        """
        # Calculate hedge ratio using rolling regression
        window = self.lookback

        hedge_ratios = []
        for i in range(window, len(series1)):
            y = series1.iloc[i - window : i]
            x = series2.iloc[i - window : i]

            # Simple OLS: y = beta * x
            beta = (y * x).sum() / (x * x).sum()
            hedge_ratios.append(beta)

        hedge_ratios = pd.Series([np.nan] * window + hedge_ratios, index=series1.index)

        # Calculate spread
        spread = series1 - hedge_ratios * series2

        return spread


class RSIMeanReversionStrategy(BaseStrategy):
    """
    RSI-based mean reversion strategy.

    Uses RSI extremes for mean reversion entries.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 25.0,
        overbought: float = 75.0,
        exit_middle: float = 50.0,
        config: Optional[StrategyConfig] = None,
    ):
        """
        Initialize RSI mean reversion strategy.

        Args:
            rsi_period: RSI calculation period
            oversold: Oversold threshold for buying
            overbought: Overbought threshold for selling
            exit_middle: RSI level to exit positions
            config: Strategy configuration
        """
        config = config or StrategyConfig(name="RSIMeanReversionStrategy")
        super().__init__(config)
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
        self.exit_middle = exit_middle

    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate RSI mean reversion signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        df = data.copy()

        # Calculate RSI
        df["rsi"] = self.indicators.rsi(df["close"], self.rsi_period)

        signals = pd.Series(Signal.HOLD, index=df.index)

        # Buy: RSI deeply oversold and turning up
        buy_condition = (
            (df["rsi"] < self.oversold) &
            (df["rsi"] > df["rsi"].shift(1))
        )

        # Sell: RSI deeply overbought and turning down
        sell_condition = (
            (df["rsi"] > self.overbought) &
            (df["rsi"] < df["rsi"].shift(1))
        )

        signals[buy_condition] = Signal.BUY
        signals[sell_condition] = Signal.SELL

        return signals