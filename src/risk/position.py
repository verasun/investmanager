"""Position management and sizing."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


class SizingMethod(Enum):
    """Position sizing methods."""

    FIXED = "fixed"
    PERCENTAGE = "percentage"
    VOLATILITY = "volatility"
    KELLY = "kelly"
    RISK_PARITY = "risk_parity"


@dataclass
class PositionConstraints:
    """Constraints for position sizing."""

    max_position_pct: float = 0.10  # Max 10% of portfolio in single position
    max_sector_pct: float = 0.30  # Max 30% in single sector
    max_positions: int = 20  # Maximum number of positions
    min_position_pct: float = 0.01  # Minimum position size
    max_leverage: float = 1.0  # Maximum leverage


class PositionSizer(ABC):
    """Abstract base class for position sizing."""

    @abstractmethod
    def calculate_size(
        self,
        portfolio_value: float,
        symbol: str,
        price: float,
        **kwargs,
    ) -> float:
        """
        Calculate position size.

        Args:
            portfolio_value: Total portfolio value
            symbol: Security symbol
            price: Current price

        Returns:
            Number of shares to trade
        """
        pass


class FixedSizer(PositionSizer):
    """Fixed position size."""

    def __init__(self, fixed_amount: float = 10000.0):
        self.fixed_amount = fixed_amount

    def calculate_size(
        self,
        portfolio_value: float,
        symbol: str,
        price: float,
        **kwargs,
    ) -> float:
        return self.fixed_amount / price


class PercentageSizer(PositionSizer):
    """Percentage of portfolio position size."""

    def __init__(self, percentage: float = 0.05):
        self.percentage = percentage

    def calculate_size(
        self,
        portfolio_value: float,
        symbol: str,
        price: float,
        **kwargs,
    ) -> float:
        return (portfolio_value * self.percentage) / price


class VolatilitySizer(PositionSizer):
    """Volatility-adjusted position size."""

    def __init__(
        self,
        target_volatility: float = 0.02,
        lookback: int = 20,
    ):
        self.target_volatility = target_volatility
        self.lookback = lookback

    def calculate_size(
        self,
        portfolio_value: float,
        symbol: str,
        price: float,
        volatility: Optional[float] = None,
        returns: Optional[pd.Series] = None,
        **kwargs,
    ) -> float:
        if volatility is None and returns is not None:
            volatility = returns.tail(self.lookback).std() * np.sqrt(252)

        if volatility is None or volatility == 0:
            return 0.0

        # Size inversely proportional to volatility
        position_value = portfolio_value * (self.target_volatility / volatility)
        return position_value / price


class KellySizer(PositionSizer):
    """Kelly criterion position sizing."""

    def __init__(self, fraction: float = 0.25):
        """
        Initialize Kelly sizer.

        Args:
            fraction: Fraction of Kelly to use (0.25 = quarter Kelly)
        """
        self.fraction = fraction

    def calculate_size(
        self,
        portfolio_value: float,
        symbol: str,
        price: float,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
        **kwargs,
    ) -> float:
        if win_rate is None or avg_win is None or avg_loss is None:
            return 0.0

        # Kelly fraction: f = p - (1-p)/(w/l)
        # where p = win rate, w = avg win, l = avg loss
        if avg_loss == 0:
            return 0.0

        win_loss_ratio = avg_win / avg_loss
        kelly = win_rate - (1 - win_rate) / win_loss_ratio

        # Apply fractional Kelly
        kelly *= self.fraction

        # Ensure positive
        kelly = max(0, kelly)

        return (portfolio_value * kelly) / price


class PositionManager:
    """
    Portfolio position manager.

    Tracks positions, calculates sizes, and enforces constraints.
    """

    def __init__(
        self,
        sizer: Optional[PositionSizer] = None,
        constraints: Optional[PositionConstraints] = None,
    ):
        """
        Initialize position manager.

        Args:
            sizer: Position sizer
            constraints: Position constraints
        """
        self.sizer = sizer or PercentageSizer()
        self.constraints = constraints or PositionConstraints()
        self.positions: dict[str, float] = {}  # symbol -> quantity
        self.position_values: dict[str, float] = {}  # symbol -> market value
        self.sector_map: dict[str, str] = {}  # symbol -> sector

    def set_sector(self, symbol: str, sector: str) -> None:
        """Map symbol to sector."""
        self.sector_map[symbol] = sector

    def update_position(
        self,
        symbol: str,
        quantity: float,
        price: float,
    ) -> None:
        """
        Update position after trade.

        Args:
            symbol: Security symbol
            quantity: New quantity
            price: Current price
        """
        if quantity == 0:
            if symbol in self.positions:
                del self.positions[symbol]
            if symbol in self.position_values:
                del self.position_values[symbol]
        else:
            self.positions[symbol] = quantity
            self.position_values[symbol] = quantity * price

    def get_portfolio_value(self) -> float:
        """Get total portfolio value."""
        return sum(self.position_values.values())

    def get_position_weight(self, symbol: str) -> float:
        """Get position weight in portfolio."""
        total = self.get_portfolio_value()
        if total == 0:
            return 0.0
        return self.position_values.get(symbol, 0) / total

    def get_sector_weights(self) -> dict[str, float]:
        """Get weights by sector."""
        total = self.get_portfolio_value()
        if total == 0:
            return {}

        sector_values: dict[str, float] = {}
        for symbol, value in self.position_values.items():
            sector = self.sector_map.get(symbol, "Unknown")
            sector_values[sector] = sector_values.get(sector, 0) + value

        return {s: v / total for s, v in sector_values.items()}

    def check_constraints(
        self,
        symbol: str,
        proposed_value: float,
        portfolio_value: float,
    ) -> tuple[bool, list[str]]:
        """
        Check if proposed position violates constraints.

        Args:
            symbol: Security symbol
            proposed_value: Proposed position value
            portfolio_value: Total portfolio value

        Returns:
            Tuple of (is_valid, list of violations)
        """
        violations = []

        # Check max position size
        position_weight = proposed_value / portfolio_value
        if position_weight > self.constraints.max_position_pct:
            violations.append(
                f"Position {symbol} would be {position_weight:.1%}, "
                f"exceeds max {self.constraints.max_position_pct:.1%}"
            )

        # Check max positions
        if symbol not in self.positions and len(self.positions) >= self.constraints.max_positions:
            violations.append(
                f"Already at max positions ({self.constraints.max_positions})"
            )

        # Check sector concentration
        sector = self.sector_map.get(symbol, "Unknown")
        sector_weights = self.get_sector_weights()
        current_sector_weight = sector_weights.get(sector, 0)
        new_sector_weight = current_sector_weight + position_weight

        if new_sector_weight > self.constraints.max_sector_pct:
            violations.append(
                f"Sector {sector} would be {new_sector_weight:.1%}, "
                f"exceeds max {self.constraints.max_sector_pct:.1%}"
            )

        return len(violations) == 0, violations

    def calculate_position_size(
        self,
        symbol: str,
        price: float,
        portfolio_value: float,
        **kwargs,
    ) -> float:
        """
        Calculate position size using sizer and constraints.

        Args:
            symbol: Security symbol
            price: Current price
            portfolio_value: Portfolio value

        Returns:
            Number of shares
        """
        # Get raw size from sizer
        size = self.sizer.calculate_size(
            portfolio_value=portfolio_value,
            symbol=symbol,
            price=price,
            **kwargs,
        )

        # Check constraints
        proposed_value = size * price
        is_valid, violations = self.check_constraints(
            symbol, proposed_value, portfolio_value
        )

        if not is_valid:
            # Reduce size to meet constraints
            max_value = portfolio_value * self.constraints.max_position_pct
            size = max_value / price

            for msg in violations:
                logger.warning(f"Position constraint: {msg}")

        # Round to whole shares
        return int(size)

    def get_position_report(self, prices: dict[str, float]) -> dict:
        """
        Generate position report.

        Args:
            prices: Current prices by symbol

        Returns:
            Position report dictionary
        """
        total_value = 0.0
        positions = []

        for symbol, quantity in self.positions.items():
            price = prices.get(symbol, 0)
            value = quantity * price
            total_value += value

            positions.append(
                {
                    "symbol": symbol,
                    "quantity": quantity,
                    "price": price,
                    "value": value,
                    "weight": 0.0,  # Will be calculated below
                    "sector": self.sector_map.get(symbol, "Unknown"),
                }
            )

        # Calculate weights
        for pos in positions:
            pos["weight"] = pos["value"] / total_value if total_value > 0 else 0

        # Sector summary
        sector_summary = {}
        for pos in positions:
            sector = pos["sector"]
            if sector not in sector_summary:
                sector_summary[sector] = {"value": 0, "weight": 0}
            sector_summary[sector]["value"] += pos["value"]
            sector_summary[sector]["weight"] += pos["weight"]

        return {
            "total_value": total_value,
            "num_positions": len(positions),
            "positions": positions,
            "sectors": sector_summary,
        }