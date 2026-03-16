"""Backtest engine for strategy testing."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import pandas as pd
from loguru import logger

from src.backtest.execution import OrderExecutor, OrderType
from src.backtest.metrics import MetricsCalculator, PerformanceMetrics
from src.backtest.portfolio import Portfolio
from src.backtest.strategy import Signal, Strategy


@dataclass
class BacktestConfig:
    """Configuration for backtest run."""

    initial_cash: float = 100000.0
    commission_rate: float = 0.001
    min_commission: float = 1.0
    slippage_rate: float = 0.0005
    position_size_pct: float = 0.95  # Percentage of available cash to use
    max_positions: int = 10
    allow_short: bool = False
    benchmark_symbol: Optional[str] = None


@dataclass
class BacktestResult:
    """Results from a backtest run."""

    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_value: float
    final_value: float
    portfolio_history: pd.DataFrame
    trade_history: pd.DataFrame
    metrics: PerformanceMetrics
    config: BacktestConfig


class BacktestEngine:
    """
    Main backtest engine for running strategy simulations.

    Supports multiple strategies, benchmarking, and comprehensive metrics.
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        """
        Initialize backtest engine.

        Args:
            config: Backtest configuration
        """
        self.config = config or BacktestConfig()
        self.portfolio = Portfolio(
            initial_cash=self.config.initial_cash,
            commission_rate=self.config.commission_rate,
            min_commission=self.config.min_commission,
            slippage_rate=self.config.slippage_rate,
        )
        self.executor = OrderExecutor(slippage_rate=self.config.slippage_rate)
        self.metrics_calculator = MetricsCalculator()

    def _validate_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Validate and prepare data for backtest.

        Args:
            data: Input DataFrame

        Returns:
            Validated DataFrame
        """
        required_columns = ["open", "high", "low", "close", "volume"]
        missing = [col for col in required_columns if col not in data.columns]

        if missing:
            raise ValueError(f"Missing required columns: {missing}")

        # Ensure datetime index
        if not isinstance(data.index, pd.DatetimeIndex):
            if "date" in data.columns:
                data = data.set_index("date")
            elif "timestamp" in data.columns:
                data = data.set_index("timestamp")
            else:
                raise ValueError("Data must have a datetime index or date/timestamp column")

        # Sort by date
        data = data.sort_index()

        return data

    def _calculate_position_size(
        self,
        symbol: str,
        price: float,
        signal: Signal,
    ) -> float:
        """
        Calculate position size based on signal and config.

        Args:
            symbol: Security symbol
            price: Current price
            signal: Trading signal

        Returns:
            Position size (number of shares)
        """
        if signal == Signal.HOLD:
            return 0.0

        available_cash = self.portfolio.cash * self.config.position_size_pct
        current_position = self.portfolio.get_position_size(symbol)

        if signal == Signal.BUY:
            # Calculate shares to buy
            shares = available_cash / price
            return int(shares)  # Round down to whole shares

        elif signal == Signal.SELL:
            # Sell all current position
            return current_position

        return 0.0

    def _process_signal(
        self,
        symbol: str,
        signal: Signal,
        price: float,
        timestamp: datetime,
    ) -> None:
        """
        Process a trading signal.

        Args:
            symbol: Security symbol
            signal: Trading signal
            price: Current price
            timestamp: Current timestamp
        """
        current_position = self.portfolio.get_position_size(symbol)

        if signal == Signal.BUY and current_position <= 0:
            # Buy signal and no existing position
            quantity = self._calculate_position_size(symbol, price, signal)
            if quantity > 0:
                self.portfolio.buy(symbol, quantity, price, timestamp)

        elif signal == Signal.SELL and current_position > 0:
            # Sell signal and have position
            self.portfolio.sell(symbol, current_position, price, timestamp)

    def run(
        self,
        strategy: Strategy,
        data: pd.DataFrame,
        symbol: str = "STOCK",
    ) -> BacktestResult:
        """
        Run backtest for a single strategy.

        Args:
            strategy: Strategy to test
            data: OHLCV DataFrame
            symbol: Symbol name for the data

        Returns:
            BacktestResult with performance metrics
        """
        logger.info(f"Running backtest for strategy: {strategy.name}")

        # Reset state
        self.portfolio.reset()
        self.executor.clear_pending_orders()

        # Validate data
        data = self._validate_data(data)

        # Generate signals
        signals = strategy.generate_signals(data)

        # Run through data
        portfolio_values = []

        for i, (timestamp, row) in enumerate(data.iterrows()):
            # Get current signal
            if timestamp in signals.index:
                signal = signals.loc[timestamp]
            else:
                signal = Signal.HOLD

            # Process signal
            close_price = row["close"]
            self._process_signal(symbol, signal, close_price, timestamp)

            # Record portfolio state
            total_value = self.portfolio.update_prices({symbol: close_price})
            portfolio_values.append(
                {
                    "timestamp": timestamp,
                    "value": total_value,
                    "cash": self.portfolio.cash,
                    "position": self.portfolio.get_position_size(symbol),
                }
            )

        # Create result
        portfolio_df = pd.DataFrame(portfolio_values).set_index("timestamp")
        trade_df = self.portfolio.get_trade_history()

        # Calculate metrics
        value_series = portfolio_df["value"]
        metrics = self.metrics_calculator.calculate_all_metrics(value_series, trade_df)

        result = BacktestResult(
            strategy_name=strategy.name,
            start_date=data.index[0],
            end_date=data.index[-1],
            initial_value=self.config.initial_cash,
            final_value=value_series.iloc[-1],
            portfolio_history=portfolio_df,
            trade_history=trade_df,
            metrics=metrics,
            config=self.config,
        )

        logger.info(
            f"Backtest complete: {metrics.total_return:.2%} return, "
            f"{metrics.sharpe_ratio:.2f} Sharpe ratio"
        )

        return result

    def run_multiple(
        self,
        strategies: dict[str, Strategy],
        data: pd.DataFrame,
        symbol: str = "STOCK",
    ) -> dict[str, BacktestResult]:
        """
        Run backtest for multiple strategies.

        Args:
            strategies: Dictionary of strategy name to strategy
            data: OHLCV DataFrame
            symbol: Symbol name

        Returns:
            Dictionary of results by strategy name
        """
        results = {}

        for name, strategy in strategies.items():
            strategy.name = name
            result = self.run(strategy, data, symbol)
            results[name] = result

        return results

    def compare_results(
        self,
        results: dict[str, BacktestResult],
    ) -> pd.DataFrame:
        """
        Compare results from multiple backtests.

        Args:
            results: Dictionary of backtest results

        Returns:
            DataFrame with comparison metrics
        """
        comparison_data = []

        for name, result in results.items():
            metrics = result.metrics
            comparison_data.append(
                {
                    "Strategy": name,
                    "Total Return": metrics.total_return,
                    "Ann. Return": metrics.annualized_return,
                    "Volatility": metrics.volatility,
                    "Sharpe": metrics.sharpe_ratio,
                    "Sortino": metrics.sortino_ratio,
                    "Max DD": metrics.max_drawdown,
                    "Win Rate": metrics.win_rate,
                    "Trades": metrics.total_trades,
                }
            )

        return pd.DataFrame(comparison_data)

    def generate_report(
        self,
        result: BacktestResult,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Generate a text report from backtest results.

        Args:
            result: Backtest result
            output_path: Optional path to save report

        Returns:
            Report string
        """
        lines = [
            "=" * 60,
            f"BACKTEST REPORT: {result.strategy_name}",
            "=" * 60,
            "",
            f"Period: {result.start_date.date()} to {result.end_date.date()}",
            f"Initial Value: ${result.initial_value:,.2f}",
            f"Final Value: ${result.final_value:,.2f}",
            "",
            "-" * 40,
            "PERFORMANCE METRICS",
            "-" * 40,
        ]

        metrics_dict = result.metrics.to_dict()
        for category, values in metrics_dict.items():
            lines.append(f"\n{category}:")
            for key, value in values.items():
                lines.append(f"  {key}: {value}")

        report = "\n".join(lines)

        if output_path:
            with open(output_path, "w") as f:
                f.write(report)
            logger.info(f"Report saved to {output_path}")

        return report