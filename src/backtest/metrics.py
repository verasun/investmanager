"""Performance metrics calculation for backtesting."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""

    # Return metrics
    total_return: float = 0.0
    annualized_return: float = 0.0
    benchmark_return: float = 0.0
    excess_return: float = 0.0

    # Risk metrics
    volatility: float = 0.0
    downside_volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    var_95: float = 0.0
    cvar_95: float = 0.0

    # Risk-adjusted metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0
    treynor_ratio: float = 0.0

    # Trade metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    avg_trade_return: float = 0.0

    # Other metrics
    alpha: float = 0.0
    beta: float = 0.0
    tracking_error: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "Return Metrics": {
                "Total Return": f"{self.total_return:.2%}",
                "Annualized Return": f"{self.annualized_return:.2%}",
                "Benchmark Return": f"{self.benchmark_return:.2%}",
                "Excess Return": f"{self.excess_return:.2%}",
            },
            "Risk Metrics": {
                "Volatility": f"{self.volatility:.2%}",
                "Downside Volatility": f"{self.downside_volatility:.2%}",
                "Max Drawdown": f"{self.max_drawdown:.2%}",
                "Max Drawdown Duration": f"{self.max_drawdown_duration} days",
                "VaR (95%)": f"{self.var_95:.2%}",
                "CVaR (95%)": f"{self.cvar_95:.2%}",
            },
            "Risk-Adjusted Metrics": {
                "Sharpe Ratio": f"{self.sharpe_ratio:.2f}",
                "Sortino Ratio": f"{self.sortino_ratio:.2f}",
                "Calmar Ratio": f"{self.calmar_ratio:.2f}",
                "Information Ratio": f"{self.information_ratio:.2f}",
            },
            "Trade Metrics": {
                "Total Trades": self.total_trades,
                "Winning Trades": self.winning_trades,
                "Losing Trades": self.losing_trades,
                "Win Rate": f"{self.win_rate:.2%}",
                "Avg Win": f"{self.avg_win:.2%}",
                "Avg Loss": f"{self.avg_loss:.2%}",
                "Profit Factor": f"{self.profit_factor:.2f}",
            },
        }


class MetricsCalculator:
    """Calculator for various performance metrics."""

    def __init__(
        self,
        risk_free_rate: float = 0.02,
        trading_days: int = 252,
    ):
        """
        Initialize metrics calculator.

        Args:
            risk_free_rate: Annual risk-free rate
            trading_days: Number of trading days per year
        """
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days
        self.daily_rf = risk_free_rate / trading_days

    def calculate_returns(self, prices: pd.Series) -> pd.Series:
        """
        Calculate daily returns from price series.

        Args:
            prices: Price series

        Returns:
            Daily returns series
        """
        return prices.pct_change().dropna()

    def total_return(self, prices: pd.Series) -> float:
        """Calculate total return."""
        if len(prices) < 2:
            return 0.0
        return (prices.iloc[-1] / prices.iloc[0]) - 1

    def annualized_return(self, total_ret: float, days: int) -> float:
        """Calculate annualized return."""
        if days <= 0:
            return 0.0
        years = days / self.trading_days
        return (1 + total_ret) ** (1 / years) - 1

    def volatility(self, returns: pd.Series) -> float:
        """Calculate annualized volatility."""
        return returns.std() * np.sqrt(self.trading_days)

    def downside_volatility(self, returns: pd.Series) -> float:
        """Calculate downside volatility."""
        negative_returns = returns[returns < 0]
        if len(negative_returns) == 0:
            return 0.0
        return negative_returns.std() * np.sqrt(self.trading_days)

    def max_drawdown(self, prices: pd.Series) -> tuple[float, int]:
        """
        Calculate maximum drawdown and duration.

        Args:
            prices: Price series

        Returns:
            Tuple of (max_drawdown, max_duration)
        """
        if len(prices) < 2:
            return 0.0, 0

        # Calculate running maximum
        running_max = prices.cummax()

        # Calculate drawdown
        drawdown = (prices - running_max) / running_max

        # Maximum drawdown
        max_dd = drawdown.min()

        # Maximum drawdown duration
        is_drawdown = drawdown < 0
        drawdown_periods = is_drawdown.astype(int)

        # Find longest drawdown period
        max_duration = 0
        current_duration = 0
        for val in drawdown_periods:
            if val == 1:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0

        return abs(max_dd), max_duration

    def var(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Calculate Value at Risk.

        Args:
            returns: Returns series
            confidence: Confidence level

        Returns:
            VaR value
        """
        return abs(returns.quantile(1 - confidence))

    def cvar(self, returns: pd.Series, confidence: float = 0.95) -> float:
        """
        Calculate Conditional VaR (Expected Shortfall).

        Args:
            returns: Returns series
            confidence: Confidence level

        Returns:
            CVaR value
        """
        var_threshold = returns.quantile(1 - confidence)
        return abs(returns[returns <= var_threshold].mean())

    def sharpe_ratio(self, returns: pd.Series) -> float:
        """Calculate Sharpe ratio."""
        excess_returns = returns - self.daily_rf
        if excess_returns.std() == 0:
            return 0.0
        return excess_returns.mean() / excess_returns.std() * np.sqrt(self.trading_days)

    def sortino_ratio(self, returns: pd.Series) -> float:
        """Calculate Sortino ratio."""
        excess_returns = returns - self.daily_rf
        downside_std = self.downside_volatility(returns) / np.sqrt(self.trading_days)
        if downside_std == 0:
            return 0.0
        return excess_returns.mean() / downside_std * np.sqrt(self.trading_days)

    def calmar_ratio(self, annualized_ret: float, max_dd: float) -> float:
        """Calculate Calmar ratio."""
        if max_dd == 0:
            return 0.0
        return annualized_ret / max_dd

    def information_ratio(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series,
    ) -> float:
        """Calculate information ratio."""
        excess = returns - benchmark_returns
        tracking_error = excess.std() * np.sqrt(self.trading_days)
        if tracking_error == 0:
            return 0.0
        return excess.mean() / excess.std() * np.sqrt(self.trading_days)

    def beta(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series,
    ) -> float:
        """Calculate beta."""
        covariance = returns.cov(benchmark_returns)
        variance = benchmark_returns.var()
        if variance == 0:
            return 0.0
        return covariance / variance

    def alpha(
        self,
        returns: pd.Series,
        benchmark_returns: pd.Series,
        beta: float,
    ) -> float:
        """Calculate alpha."""
        return (
            self.annualized_return(self.total_return(returns), len(returns))
            - beta * self.annualized_return(
                self.total_return(benchmark_returns), len(benchmark_returns)
            )
            - self.risk_free_rate
        )

    def trade_statistics(
        self,
        trades: pd.DataFrame,
    ) -> dict:
        """
        Calculate trade statistics.

        Args:
            trades: DataFrame with trade records

        Returns:
            Dictionary of trade statistics
        """
        if trades.empty:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "avg_trade_return": 0.0,
            }

        # Calculate PnL for each trade pair
        trade_returns = []
        position = {}

        for _, trade in trades.iterrows():
            symbol = trade["symbol"]
            side = trade["side"]
            quantity = trade["quantity"]
            price = trade["price"]

            if symbol not in position:
                position[symbol] = {"quantity": 0, "cost": 0.0}

            if side == "BUY":
                position[symbol]["cost"] += quantity * price
                position[symbol]["quantity"] += quantity
            else:
                if position[symbol]["quantity"] > 0:
                    avg_cost = position[symbol]["cost"] / position[symbol]["quantity"]
                    pnl = (price - avg_cost) * min(quantity, position[symbol]["quantity"])
                    trade_returns.append(pnl / (avg_cost * min(quantity, position[symbol]["quantity"])))
                position[symbol]["quantity"] -= quantity
                position[symbol]["cost"] -= avg_cost * min(quantity, position[symbol]["quantity"] + quantity)

        if not trade_returns:
            return {
                "total_trades": len(trades) // 2,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "avg_trade_return": 0.0,
            }

        trade_returns = pd.Series(trade_returns)
        wins = trade_returns[trade_returns > 0]
        losses = trade_returns[trade_returns < 0]

        total_trades = len(trade_returns)
        winning_trades = len(wins)
        losing_trades = len(losses)

        avg_win = wins.mean() if len(wins) > 0 else 0.0
        avg_loss = abs(losses.mean()) if len(losses) > 0 else 0.0

        total_wins = wins.sum() if len(wins) > 0 else 0.0
        total_losses = abs(losses.sum()) if len(losses) > 0 else 0.0

        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf") if total_wins > 0 else 0.0

        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": winning_trades / total_trades if total_trades > 0 else 0.0,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "avg_trade_return": trade_returns.mean(),
        }

    def calculate_all_metrics(
        self,
        portfolio_values: pd.Series,
        trades: Optional[pd.DataFrame] = None,
        benchmark_values: Optional[pd.Series] = None,
    ) -> PerformanceMetrics:
        """
        Calculate all performance metrics.

        Args:
            portfolio_values: Portfolio value series
            trades: Optional trade records DataFrame
            benchmark_values: Optional benchmark value series

        Returns:
            PerformanceMetrics object
        """
        returns = self.calculate_returns(portfolio_values)

        # Basic return metrics
        total_ret = self.total_return(portfolio_values)
        ann_ret = self.annualized_return(total_ret, len(portfolio_values))

        # Risk metrics
        vol = self.volatility(returns)
        down_vol = self.downside_volatility(returns)
        max_dd, max_dd_dur = self.max_drawdown(portfolio_values)
        var_95 = self.var(returns)
        cvar_95 = self.cvar(returns)

        # Risk-adjusted metrics
        sharpe = self.sharpe_ratio(returns)
        sortino = self.sortino_ratio(returns)
        calmar = self.calmar_ratio(ann_ret, max_dd)

        # Benchmark comparison
        benchmark_ret = 0.0
        excess_ret = 0.0
        info_ratio = 0.0
        beta_val = 0.0
        alpha_val = 0.0
        tracking_error = 0.0

        if benchmark_values is not None and len(benchmark_values) == len(portfolio_values):
            benchmark_returns = self.calculate_returns(benchmark_values)
            benchmark_ret = self.total_return(benchmark_values)
            excess_ret = total_ret - benchmark_ret
            info_ratio = self.information_ratio(returns, benchmark_returns)
            beta_val = self.beta(returns, benchmark_returns)
            alpha_val = self.alpha(returns, benchmark_returns, beta_val)
            tracking_error = (returns - benchmark_returns).std() * np.sqrt(self.trading_days)

        # Trade metrics
        trade_stats = self.trade_statistics(trades) if trades is not None else {}

        return PerformanceMetrics(
            total_return=total_ret,
            annualized_return=ann_ret,
            benchmark_return=benchmark_ret,
            excess_return=excess_ret,
            volatility=vol,
            downside_volatility=down_vol,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_dur,
            var_95=var_95,
            cvar_95=cvar_95,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            information_ratio=info_ratio,
            alpha=alpha_val,
            beta=beta_val,
            tracking_error=tracking_error,
            total_trades=trade_stats.get("total_trades", 0),
            winning_trades=trade_stats.get("winning_trades", 0),
            losing_trades=trade_stats.get("losing_trades", 0),
            win_rate=trade_stats.get("win_rate", 0.0),
            avg_win=trade_stats.get("avg_win", 0.0),
            avg_loss=trade_stats.get("avg_loss", 0.0),
            profit_factor=trade_stats.get("profit_factor", 0.0),
            avg_trade_return=trade_stats.get("avg_trade_return", 0.0),
        )