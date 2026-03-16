"""Portfolio management for backtesting."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger


@dataclass
class Trade:
    """Represents a completed trade."""

    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: float
    price: float
    timestamp: datetime
    commission: float = 0.0

    @property
    def value(self) -> float:
        """Total trade value."""
        return self.quantity * self.price

    @property
    def net_value(self) -> float:
        """Net trade value after commission."""
        if self.side == "BUY":
            return -self.value - self.commission
        return self.value - self.commission


@dataclass
class Holding:
    """Represents a holding in the portfolio."""

    symbol: str
    quantity: float
    avg_cost: float

    @property
    def cost_basis(self) -> float:
        """Total cost of holding."""
        return self.quantity * self.avg_cost

    def market_value(self, current_price: float) -> float:
        """Current market value."""
        return self.quantity * current_price

    def unrealized_pnl(self, current_price: float) -> float:
        """Unrealized profit/loss."""
        return self.quantity * (current_price - self.avg_cost)

    def unrealized_pnl_pct(self, current_price: float) -> float:
        """Unrealized profit/loss percentage."""
        if self.avg_cost == 0:
            return 0.0
        return (current_price - self.avg_cost) / self.avg_cost * 100


@dataclass
class PortfolioState:
    """Snapshot of portfolio state at a point in time."""

    timestamp: datetime
    cash: float
    holdings: dict[str, Holding]
    total_value: float
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0


class Portfolio:
    """
    Portfolio management class for backtesting.

    Handles cash, positions, trades, and portfolio state tracking.
    """

    def __init__(
        self,
        initial_cash: float = 100000.0,
        commission_rate: float = 0.001,
        min_commission: float = 1.0,
        slippage_rate: float = 0.0005,
    ):
        """
        Initialize portfolio.

        Args:
            initial_cash: Starting cash amount
            commission_rate: Commission rate per trade
            min_commission: Minimum commission per trade
            slippage_rate: Slippage rate for execution
        """
        self.initial_cash = initial_cash
        self.cash = initial_cash
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.slippage_rate = slippage_rate

        self.holdings: dict[str, Holding] = {}
        self.trades: list[Trade] = []
        self.states: list[PortfolioState] = []

        self._last_total_value = initial_cash

    @property
    def total_value(self) -> float:
        """Calculate total portfolio value using last known prices."""
        return self.cash + sum(h.cost_basis for h in self.holdings.values())

    def get_holding(self, symbol: str) -> Optional[Holding]:
        """Get holding for a symbol."""
        return self.holdings.get(symbol)

    def get_position_size(self, symbol: str) -> float:
        """Get position size for a symbol."""
        holding = self.holdings.get(symbol)
        return holding.quantity if holding else 0.0

    def calculate_commission(self, trade_value: float) -> float:
        """
        Calculate commission for a trade.

        Args:
            trade_value: Total trade value

        Returns:
            Commission amount
        """
        commission = trade_value * self.commission_rate
        return max(commission, self.min_commission)

    def apply_slippage(self, price: float, side: str) -> float:
        """
        Apply slippage to execution price.

        Args:
            price: Original price
            side: 'BUY' or 'SELL'

        Returns:
            Adjusted price with slippage
        """
        slippage = price * self.slippage_rate
        if side == "BUY":
            return price + slippage
        return price - slippage

    def can_buy(self, symbol: str, quantity: float, price: float) -> bool:
        """
        Check if we have enough cash to buy.

        Args:
            symbol: Security symbol
            quantity: Quantity to buy
            price: Price per share

        Returns:
            True if purchase is possible
        """
        adjusted_price = self.apply_slippage(price, "BUY")
        trade_value = quantity * adjusted_price
        commission = self.calculate_commission(trade_value)
        required_cash = trade_value + commission
        return self.cash >= required_cash

    def buy(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: datetime,
    ) -> Optional[Trade]:
        """
        Execute a buy order.

        Args:
            symbol: Security symbol
            quantity: Quantity to buy
            price: Price per share
            timestamp: Trade timestamp

        Returns:
            Trade record if successful, None otherwise
        """
        adjusted_price = self.apply_slippage(price, "BUY")
        trade_value = quantity * adjusted_price
        commission = self.calculate_commission(trade_value)
        total_cost = trade_value + commission

        if self.cash < total_cost:
            logger.warning(
                f"Insufficient cash for buy: need {total_cost:.2f}, have {self.cash:.2f}"
            )
            return None

        # Update cash
        self.cash -= total_cost

        # Update holdings
        if symbol in self.holdings:
            holding = self.holdings[symbol]
            new_quantity = holding.quantity + quantity
            new_cost = holding.cost_basis + trade_value
            holding.quantity = new_quantity
            holding.avg_cost = new_cost / new_quantity
        else:
            self.holdings[symbol] = Holding(
                symbol=symbol,
                quantity=quantity,
                avg_cost=adjusted_price,
            )

        # Record trade
        trade = Trade(
            symbol=symbol,
            side="BUY",
            quantity=quantity,
            price=adjusted_price,
            timestamp=timestamp,
            commission=commission,
        )
        self.trades.append(trade)

        logger.debug(f"BUY {symbol}: {quantity} @ {adjusted_price:.2f}")
        return trade

    def sell(
        self,
        symbol: str,
        quantity: float,
        price: float,
        timestamp: datetime,
    ) -> Optional[Trade]:
        """
        Execute a sell order.

        Args:
            symbol: Security symbol
            quantity: Quantity to sell
            price: Price per share
            timestamp: Trade timestamp

        Returns:
            Trade record if successful, None otherwise
        """
        holding = self.holdings.get(symbol)
        if not holding or holding.quantity < quantity:
            logger.warning(
                f"Insufficient position for sell: need {quantity}, have {holding.quantity if holding else 0}"
            )
            return None

        adjusted_price = self.apply_slippage(price, "SELL")
        trade_value = quantity * adjusted_price
        commission = self.calculate_commission(trade_value)
        net_proceeds = trade_value - commission

        # Update cash
        self.cash += net_proceeds

        # Update holdings
        holding.quantity -= quantity
        if holding.quantity <= 0:
            del self.holdings[symbol]

        # Record trade
        trade = Trade(
            symbol=symbol,
            side="SELL",
            quantity=quantity,
            price=adjusted_price,
            timestamp=timestamp,
            commission=commission,
        )
        self.trades.append(trade)

        logger.debug(f"SELL {symbol}: {quantity} @ {adjusted_price:.2f}")
        return trade

    def update_prices(self, prices: dict[str, float]) -> float:
        """
        Update holdings with current prices and return total value.

        Args:
            prices: Dictionary of current prices by symbol

        Returns:
            Total portfolio value
        """
        holdings_value = 0.0
        for symbol, holding in self.holdings.items():
            if symbol in prices:
                holdings_value += holding.quantity * prices[symbol]
            else:
                holdings_value += holding.cost_basis

        return self.cash + holdings_value

    def record_state(
        self,
        timestamp: datetime,
        prices: Optional[dict[str, float]] = None,
    ) -> PortfolioState:
        """
        Record current portfolio state.

        Args:
            timestamp: Current timestamp
            prices: Current prices by symbol

        Returns:
            Portfolio state snapshot
        """
        prices = prices or {}
        total_value = self.update_prices(prices)

        daily_pnl = total_value - self._last_total_value
        daily_pnl_pct = (
            (daily_pnl / self._last_total_value * 100)
            if self._last_total_value > 0
            else 0.0
        )

        state = PortfolioState(
            timestamp=timestamp,
            cash=self.cash,
            holdings=dict(self.holdings),
            total_value=total_value,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
        )
        self.states.append(state)

        self._last_total_value = total_value
        return state

    def get_trade_history(self) -> pd.DataFrame:
        """
        Get trade history as DataFrame.

        Returns:
            DataFrame with all trades
        """
        if not self.trades:
            return pd.DataFrame()

        records = [
            {
                "timestamp": t.timestamp,
                "symbol": t.symbol,
                "side": t.side,
                "quantity": t.quantity,
                "price": t.price,
                "value": t.value,
                "commission": t.commission,
                "net_value": t.net_value,
            }
            for t in self.trades
        ]
        return pd.DataFrame(records)

    def get_portfolio_history(self) -> pd.DataFrame:
        """
        Get portfolio value history as DataFrame.

        Returns:
            DataFrame with portfolio states over time
        """
        if not self.states:
            return pd.DataFrame()

        records = [
            {
                "timestamp": s.timestamp,
                "cash": s.cash,
                "total_value": s.total_value,
                "daily_pnl": s.daily_pnl,
                "daily_pnl_pct": s.daily_pnl_pct,
                "num_positions": len(s.holdings),
            }
            for s in self.states
        ]
        return pd.DataFrame(records)

    def reset(self) -> None:
        """Reset portfolio to initial state."""
        self.cash = self.initial_cash
        self.holdings.clear()
        self.trades.clear()
        self.states.clear()
        self._last_total_value = self.initial_cash