"""Backtest Tool - Strategy backtesting."""

import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .base import BaseTool, ToolResult


class BacktestTool(BaseTool):
    """Tool for backtesting trading strategies.

    Simulates trading strategies on historical data.
    """

    name = "backtest"
    description = "对股票策略进行回测。模拟交易策略在历史数据上的表现，计算收益率、夏普比率等指标。"
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {
                "type": "string",
                "description": "股票代码",
            },
            "strategy": {
                "type": "string",
                "enum": ["ma_cross", "rsi", "macd", "buy_hold"],
                "description": "策略类型: ma_cross(均线交叉), rsi(RSI策略), macd(MACD策略), buy_hold(买入持有)",
                "default": "buy_hold",
            },
            "days": {
                "type": "integer",
                "description": "回测天数",
                "default": 365,
            },
            "initial_capital": {
                "type": "number",
                "description": "初始资金",
                "default": 1000000,
            },
        },
        "required": ["symbol"],
    }
    timeout = 120

    async def execute(
        self,
        symbol: str,
        strategy: str = "buy_hold",
        days: int = 365,
        initial_capital: float = 1000000,
    ) -> ToolResult:
        """Execute backtest.

        Args:
            symbol: Stock symbol
            strategy: Strategy to test
            days: Number of days to backtest
            initial_capital: Initial capital

        Returns:
            ToolResult with backtest results
        """
        try:
            # First get the stock data
            from .stock_data import StockDataTool

            data_tool = StockDataTool()
            data_result = await data_tool.execute(symbol, days=days, data_type="kline")

            if not data_result.success:
                return ToolResult(
                    success=False,
                    error=f"无法获取股票数据: {data_result.error}",
                )

            records = data_result.data.get("records", [])
            if not records:
                return ToolResult(
                    success=False,
                    error="无足够数据进行回测",
                )

            # Run backtest based on strategy
            result = await self._run_backtest(
                records,
                strategy,
                initial_capital,
            )

            return ToolResult(
                success=True,
                data=result,
                metadata={
                    "symbol": symbol,
                    "strategy": strategy,
                    "days": days,
                    "initial_capital": initial_capital,
                },
            )

        except Exception as e:
            logger.error(f"Backtest failed: {e}")
            return ToolResult(
                success=False,
                error=f"回测失败: {str(e)}",
            )

    async def _run_backtest(
        self,
        records: list,
        strategy: str,
        initial_capital: float,
    ) -> dict:
        """Run backtest on historical data."""
        import pandas as pd
        import numpy as np

        df = pd.DataFrame(records)

        # Handle column names
        close_col = None
        for col in ["close", "收盘", "Close"]:
            if col in df.columns:
                close_col = col
                break

        if close_col is None:
            raise ValueError("No close price data")

        prices = df[close_col].astype(float).values

        # Generate signals based on strategy
        if strategy == "buy_hold":
            signals = self._buy_hold_signals(len(prices))
        elif strategy == "ma_cross":
            signals = self._ma_cross_signals(prices)
        elif strategy == "rsi":
            signals = self._rsi_signals(prices)
        elif strategy == "macd":
            signals = self._macd_signals(prices)
        else:
            signals = self._buy_hold_signals(len(prices))

        # Simulate trading
        cash = initial_capital
        shares = 0
        trades = []
        portfolio_values = []

        for i, (price, signal) in enumerate(zip(prices, signals)):
            # Buy signal
            if signal == 1 and shares == 0 and cash > 0:
                shares_to_buy = int(cash / price)
                if shares_to_buy > 0:
                    shares = shares_to_buy
                    cash -= shares * price
                    trades.append({
                        "day": i,
                        "type": "buy",
                        "price": price,
                        "shares": shares,
                    })

            # Sell signal
            elif signal == -1 and shares > 0:
                cash += shares * price
                trades.append({
                    "day": i,
                    "type": "sell",
                    "price": price,
                    "shares": shares,
                })
                shares = 0

            # Track portfolio value
            portfolio_values.append(cash + shares * price)

        # Final value
        final_value = cash + shares * prices[-1]
        total_return = (final_value - initial_capital) / initial_capital

        # Calculate metrics
        returns = pd.Series(portfolio_values).pct_change().dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

        # Max drawdown
        peak = np.maximum.accumulate(portfolio_values)
        drawdown = (np.array(portfolio_values) - peak) / peak
        max_drawdown = np.min(drawdown)

        return {
            "initial_capital": initial_capital,
            "final_value": round(final_value, 2),
            "total_return": round(total_return * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown": round(max_drawdown * 100, 2),
            "total_trades": len(trades),
            "trades": trades[:20],  # Limit to 20 trades
            "win_rate": self._calculate_win_rate(trades),
        }

    def _buy_hold_signals(self, length: int) -> list:
        """Buy and hold strategy - buy at start, never sell."""
        signals = [0] * length
        if length > 0:
            signals[0] = 1  # Buy on first day
        return signals

    def _ma_cross_signals(self, prices: list) -> list:
        """Moving average crossover strategy."""
        import numpy as np

        prices = np.array(prices)
        signals = [0] * len(prices)

        if len(prices) < 20:
            return signals

        # Calculate MAs
        ma5 = np.convolve(prices, np.ones(5) / 5, mode="valid")
        ma20 = np.convolve(prices, np.ones(20) / 20, mode="valid")

        # Align lengths
        offset = 19  # len(prices) - len(ma20)

        for i in range(1, len(ma20)):
            actual_i = i + offset
            # Golden cross - buy
            if ma5[i] > ma20[i] and ma5[i - 1] <= ma20[i - 1]:
                signals[actual_i] = 1
            # Death cross - sell
            elif ma5[i] < ma20[i] and ma5[i - 1] >= ma20[i - 1]:
                signals[actual_i] = -1

        return signals

    def _rsi_signals(self, prices: list) -> list:
        """RSI strategy - buy when oversold, sell when overbought."""
        import numpy as np

        signals = [0] * len(prices)

        if len(prices) < 15:
            return signals

        # Calculate RSI
        prices = np.array(prices)
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        avg_gain = np.convolve(gains, np.ones(14) / 14, mode="valid")
        avg_loss = np.convolve(losses, np.ones(14) / 14, mode="valid")

        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 0)
        rsi = 100 - (100 / (1 + rs))

        # Generate signals
        offset = 14
        for i, r in enumerate(rsi):
            actual_i = i + offset
            if r < 30:  # Oversold - buy
                signals[actual_i] = 1
            elif r > 70:  # Overbought - sell
                signals[actual_i] = -1

        return signals

    def _macd_signals(self, prices: list) -> list:
        """MACD strategy."""
        import pandas as pd

        signals = [0] * len(prices)

        if len(prices) < 26:
            return signals

        prices_series = pd.Series(prices)

        # Calculate MACD
        ema12 = prices_series.ewm(span=12).mean()
        ema26 = prices_series.ewm(span=26).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9).mean()

        # Generate signals
        for i in range(1, len(prices)):
            # Bullish crossover - buy
            if macd.iloc[i] > signal_line.iloc[i] and macd.iloc[i - 1] <= signal_line.iloc[i - 1]:
                signals[i] = 1
            # Bearish crossover - sell
            elif macd.iloc[i] < signal_line.iloc[i] and macd.iloc[i - 1] >= signal_line.iloc[i - 1]:
                signals[i] = -1

        return signals

    def _calculate_win_rate(self, trades: list) -> float:
        """Calculate win rate from trades."""
        if len(trades) < 2:
            return 0.0

        wins = 0
        total_pairs = 0

        for i in range(0, len(trades) - 1, 2):
            if i + 1 < len(trades):
                buy = trades[i]
                sell = trades[i + 1]
                if buy["type"] == "buy" and sell["type"] == "sell":
                    if sell["price"] > buy["price"]:
                        wins += 1
                    total_pairs += 1

        return round(wins / total_pairs * 100, 2) if total_pairs > 0 else 0.0