"""Base strategy class for backtesting."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd


class Signal(Enum):
    """Trading signal types."""

    BUY = 1
    SELL = -1
    HOLD = 0


@dataclass
class Position:
    """Represents a position in a security."""

    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    entry_time: pd.Timestamp

    @property
    def market_value(self) -> float:
        """Current market value of position."""
        return self.quantity * self.current_price

    @property
    def cost_basis(self) -> float:
        """Total cost of position."""
        return self.quantity * self.entry_price

    @property
    def unrealized_pnl(self) -> float:
        """Unrealized profit/loss."""
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        """Unrealized profit/loss percentage."""
        if self.cost_basis == 0:
            return 0.0
        return (self.current_price - self.entry_price) / self.entry_price * 100


class Strategy(ABC):
    """
    Abstract base class for trading strategies.

    Subclasses must implement the generate_signals method.
    """

    def __init__(self, name: str = "BaseStrategy"):
        self.name = name
        self.positions: dict[str, Position] = {}
        self._data: Optional[pd.DataFrame] = None

    @property
    def data(self) -> Optional[pd.DataFrame]:
        """Get the data used by the strategy."""
        return self._data

    @data.setter
    def data(self, value: pd.DataFrame) -> None:
        """Set the data for the strategy."""
        self._data = value

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Generate trading signals based on the data.

        Args:
            data: DataFrame with OHLCV data

        Returns:
            Series of Signal values indexed by timestamp
        """
        pass

    def on_bar(self, bar: pd.Series) -> Signal:
        """
        Process a single bar and return signal.

        Override this for bar-by-bar processing.

        Args:
            bar: Single bar of OHLCV data

        Returns:
            Trading signal
        """
        return Signal.HOLD

    def on_tick(self, tick: dict) -> Signal:
        """
        Process a tick update.

        Override this for tick-based strategies.

        Args:
            tick: Tick data dictionary

        Returns:
            Trading signal
        """
        return Signal.HOLD

    def update_position(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: pd.Timestamp,
    ) -> None:
        """
        Update or create a position.

        Args:
            symbol: Security symbol
            quantity: Position quantity (positive for long, negative for short)
            price: Current price
            timestamp: Current timestamp
        """
        if quantity == 0:
            if symbol in self.positions:
                del self.positions[symbol]
            return

        if symbol in self.positions:
            pos = self.positions[symbol]
            total_quantity = pos.quantity + quantity
            if total_quantity == 0:
                del self.positions[symbol]
            else:
                # Update average entry price for adds
                if (pos.quantity > 0 and quantity > 0) or (pos.quantity < 0 and quantity < 0):
                    total_cost = pos.cost_basis + abs(quantity) * price
                    pos.entry_price = total_cost / abs(total_quantity)
                pos.quantity = total_quantity
                pos.current_price = price
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                entry_price=price,
                current_price=price,
                entry_time=timestamp,
            )

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get current position for a symbol.

        Args:
            symbol: Security symbol

        Returns:
            Position if exists, None otherwise
        """
        return self.positions.get(symbol)

    def get_total_value(self, prices: dict[str, float]) -> float:
        """
        Calculate total portfolio value.

        Args:
            prices: Dictionary of current prices by symbol

        Returns:
            Total portfolio value
        """
        total = 0.0
        for symbol, position in self.positions.items():
            position.current_price = prices.get(symbol, position.current_price)
            total += position.market_value
        return total

    def reset(self) -> None:
        """Reset strategy state."""
        self.positions.clear()
        self._data = None