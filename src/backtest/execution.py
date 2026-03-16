"""Order execution for backtesting."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pandas as pd
from loguru import logger


class OrderType(Enum):
    """Order type enumeration."""

    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status enumeration."""

    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    """Represents an order."""

    symbol: str
    side: str  # 'BUY' or 'SELL'
    quantity: float
    order_type: OrderType
    timestamp: datetime
    order_id: Optional[str] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    fill_timestamp: Optional[datetime] = None

    @property
    def remaining_quantity(self) -> float:
        """Remaining unfilled quantity."""
        return self.quantity - self.filled_quantity

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.status in (OrderStatus.PENDING, OrderStatus.PARTIALLY_FILLED)


class OrderExecutor:
    """
    Order execution engine for backtesting.

    Handles order matching, fill simulation, and execution logic.
    """

    def __init__(
        self,
        slippage_rate: float = 0.0005,
        partial_fills: bool = False,
    ):
        """
        Initialize order executor.

        Args:
            slippage_rate: Slippage rate for execution
            partial_fills: Allow partial order fills
        """
        self.slippage_rate = slippage_rate
        self.partial_fills = partial_fills

        self.pending_orders: dict[str, Order] = {}
        self.order_counter = 0

    def generate_order_id(self) -> str:
        """Generate a unique order ID."""
        self.order_counter += 1
        return f"ORD-{self.order_counter:06d}"

    def submit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        timestamp: Optional[datetime] = None,
    ) -> Order:
        """
        Submit a new order.

        Args:
            symbol: Security symbol
            side: 'BUY' or 'SELL'
            quantity: Order quantity
            order_type: Type of order
            limit_price: Limit price for limit orders
            stop_price: Stop price for stop orders
            timestamp: Order submission time

        Returns:
            Order object
        """
        order = Order(
            symbol=symbol,
            side=side.upper(),
            quantity=quantity,
            order_type=order_type,
            timestamp=timestamp or datetime.now(),
            order_id=self.generate_order_id(),
            limit_price=limit_price,
            stop_price=stop_price,
        )

        self.pending_orders[order.order_id] = order
        logger.debug(f"Order submitted: {order.order_id} {side} {quantity} {symbol}")
        return order

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a pending order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        if order_id in self.pending_orders:
            order = self.pending_orders[order_id]
            if order.is_active:
                order.status = OrderStatus.CANCELLED
                del self.pending_orders[order_id]
                logger.debug(f"Order cancelled: {order_id}")
                return True
        return False

    def process_market_order(
        self,
        order: Order,
        bar: pd.Series,
    ) -> tuple[float, float]:
        """
        Process a market order against current bar.

        Args:
            order: Order to process
            bar: Current price bar

        Returns:
            Tuple of (fill_price, fill_quantity)
        """
        # Use open price for market orders (simulates immediate execution)
        base_price = bar.get("open", bar.get("close", 0))

        # Apply slippage
        if order.side == "BUY":
            fill_price = base_price * (1 + self.slippage_rate)
        else:
            fill_price = base_price * (1 - self.slippage_rate)

        fill_quantity = order.remaining_quantity

        return fill_price, fill_quantity

    def process_limit_order(
        self,
        order: Order,
        bar: pd.Series,
    ) -> Optional[tuple[float, float]]:
        """
        Process a limit order against current bar.

        Args:
            order: Order to process
            bar: Current price bar

        Returns:
            Tuple of (fill_price, fill_quantity) if filled, None otherwise
        """
        if not order.limit_price:
            return None

        high = bar.get("high", bar.get("close", 0))
        low = bar.get("low", bar.get("close", 0))

        # Check if limit order can be filled
        if order.side == "BUY":
            # Buy limit: fill if price drops to or below limit
            if low <= order.limit_price:
                fill_price = min(order.limit_price, bar.get("open", order.limit_price))
                return fill_price, order.remaining_quantity
        else:
            # Sell limit: fill if price rises to or above limit
            if high >= order.limit_price:
                fill_price = max(order.limit_price, bar.get("open", order.limit_price))
                return fill_price, order.remaining_quantity

        return None

    def process_stop_order(
        self,
        order: Order,
        bar: pd.Series,
    ) -> Optional[tuple[float, float]]:
        """
        Process a stop order against current bar.

        Args:
            order: Order to process
            bar: Current price bar

        Returns:
            Tuple of (fill_price, fill_quantity) if triggered, None otherwise
        """
        if not order.stop_price:
            return None

        high = bar.get("high", bar.get("close", 0))
        low = bar.get("low", bar.get("close", 0))

        # Check if stop is triggered
        if order.side == "BUY":
            # Buy stop: trigger if price rises to or above stop
            if high >= order.stop_price:
                fill_price = max(order.stop_price, bar.get("open", order.stop_price))
                fill_price *= 1 + self.slippage_rate
                return fill_price, order.remaining_quantity
        else:
            # Sell stop: trigger if price drops to or below stop
            if low <= order.stop_price:
                fill_price = min(order.stop_price, bar.get("open", order.stop_price))
                fill_price *= 1 - self.slippage_rate
                return fill_price, order.remaining_quantity

        return None

    def process_stop_limit_order(
        self,
        order: Order,
        bar: pd.Series,
    ) -> Optional[tuple[float, float]]:
        """
        Process a stop-limit order.

        Args:
            order: Order to process
            bar: Current price bar

        Returns:
            Tuple of (fill_price, fill_quantity) if filled, None otherwise
        """
        # First check if stop is triggered
        result = self.process_stop_order(order, bar)
        if result:
            # If stop triggered, convert to limit order logic
            order.limit_price = order.limit_price or order.stop_price
            return self.process_limit_order(order, bar)
        return None

    def execute_pending_orders(
        self,
        bar: pd.Series,
        symbol: str,
    ) -> list[Order]:
        """
        Execute all pending orders for a symbol.

        Args:
            bar: Current price bar
            symbol: Symbol to process orders for

        Returns:
            List of filled orders
        """
        filled_orders = []

        for order_id, order in list(self.pending_orders.items()):
            if order.symbol != symbol or not order.is_active:
                continue

            fill_result = None

            if order.order_type == OrderType.MARKET:
                fill_result = self.process_market_order(order, bar)
            elif order.order_type == OrderType.LIMIT:
                fill_result = self.process_limit_order(order, bar)
            elif order.order_type == OrderType.STOP:
                fill_result = self.process_stop_order(order, bar)
            elif order.order_type == OrderType.STOP_LIMIT:
                fill_result = self.process_stop_limit_order(order, bar)

            if fill_result:
                fill_price, fill_quantity = fill_result

                order.filled_price = fill_price
                order.filled_quantity = fill_quantity
                order.fill_timestamp = bar.name if hasattr(bar, "name") else datetime.now()
                order.status = OrderStatus.FILLED

                filled_orders.append(order)
                del self.pending_orders[order_id]

                logger.debug(
                    f"Order filled: {order.order_id} {order.side} "
                    f"{fill_quantity} @ {fill_price:.2f}"
                )

        return filled_orders

    def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        """
        Get all open orders, optionally filtered by symbol.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of open orders
        """
        orders = [o for o in self.pending_orders.values() if o.is_active]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders

    def clear_pending_orders(self) -> None:
        """Clear all pending orders."""
        self.pending_orders.clear()