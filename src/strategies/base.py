"""Base strategy implementation."""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.backtest.strategy import Signal, Strategy
from src.analysis.technical.indicators import TechnicalIndicators


@dataclass
class StrategyConfig:
    """Configuration for a strategy."""

    name: str = "BaseStrategy"
    description: str = ""
    symbols: list[str] = None
    timeframe: str = "1d"
    risk_per_trade: float = 0.02
    max_positions: int = 5
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10


class BaseStrategy(Strategy):
    """
    Enhanced base strategy with common functionality.

    Extends the basic Strategy class with additional features:
    - Configuration management
    - Risk management
    - Signal filtering
    - Performance tracking
    """

    def __init__(self, config: Optional[StrategyConfig] = None):
        """
        Initialize strategy with configuration.

        Args:
            config: Strategy configuration
        """
        config = config or StrategyConfig()
        super().__init__(name=config.name)
        self.config = config
        self.indicators = TechnicalIndicators()

        # Signal tracking
        self._signals_history: list[dict] = []
        self._trade_history: list[dict] = []

    @abstractmethod
    def calculate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Calculate raw signals from data.

        This method should be implemented by subclasses.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        pass

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate filtered signals.

        Applies risk management filters to raw signals.

        Args:
            data: OHLCV DataFrame

        Returns:
            Series of Signal values
        """
        # Get raw signals
        signals = self.calculate_signals(data)

        # Apply filters
        signals = self._apply_filters(signals, data)

        # Store signals
        for timestamp, signal in signals.items():
            if signal != Signal.HOLD:
                self._signals_history.append(
                    {
                        "timestamp": timestamp,
                        "signal": signal.name,
                        "price": data.loc[timestamp, "close"],
                    }
                )

        return signals

    def _apply_filters(self, signals: pd.Series, data: pd.DataFrame) -> pd.Series:
        """
        Apply filters to signals.

        Override this method to add custom filters.

        Args:
            signals: Raw signals
            data: OHLCV DataFrame

        Returns:
            Filtered signals
        """
        filtered = signals.copy()

        # Example: Don't generate new signals if we have max positions
        # This would need actual position tracking in a real implementation

        return filtered

    def calculate_stop_loss(
        self,
        entry_price: float,
        position_side: str,
    ) -> float:
        """
        Calculate stop loss price.

        Args:
            entry_price: Entry price
            position_side: 'long' or 'short'

        Returns:
            Stop loss price
        """
        if position_side == "long":
            return entry_price * (1 - self.config.stop_loss_pct)
        return entry_price * (1 + self.config.stop_loss_pct)

    def calculate_take_profit(
        self,
        entry_price: float,
        position_side: str,
    ) -> float:
        """
        Calculate take profit price.

        Args:
            entry_price: Entry price
            position_side: 'long' or 'short'

        Returns:
            Take profit price
        """
        if position_side == "long":
            return entry_price * (1 + self.config.take_profit_pct)
        return entry_price * (1 - self.config.take_profit_pct)

    def get_signals_history(self) -> pd.DataFrame:
        """
        Get history of generated signals.

        Returns:
            DataFrame with signal history
        """
        if not self._signals_history:
            return pd.DataFrame()
        return pd.DataFrame(self._signals_history)

    def add_technical_indicators(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Add common technical indicators to data.

        Args:
            data: OHLCV DataFrame

        Returns:
            DataFrame with indicators
        """
        return self.indicators.add_all_indicators(data)

    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        Validate that data has required columns.

        Args:
            data: DataFrame to validate

        Returns:
            True if valid
        """
        required = ["open", "high", "low", "close", "volume"]
        return all(col in data.columns for col in required)

    def reset(self) -> None:
        """Reset strategy state."""
        super().reset()
        self._signals_history.clear()
        self._trade_history.clear()