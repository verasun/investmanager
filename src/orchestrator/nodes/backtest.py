"""Backtest task node."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from loguru import logger

from src.orchestrator.nodes.base import TaskNode, run_node
from src.backtest.engine import BacktestEngine, BacktestConfig
from src.strategies.momentum import MomentumStrategy
from src.strategies.mean_reversion import MeanReversionStrategy
from src.strategies.trend_following import TrendFollowingStrategy


class BacktestNode(TaskNode):
    """
    Task node for running strategy backtests.

    Input:
        data_path: Path to OHLCV data with analysis
        strategy: Strategy name or configuration
        config: Backtest configuration (initial_cash, commission, etc.)
        symbol: Symbol name for the backtest

    Output:
        backtest_path: Path to backtest results
        metrics: Performance metrics summary
        trades: Number of trades executed
    """

    # Available strategies
    STRATEGIES = {
        "momentum": MomentumStrategy,
        "mean_reversion": MeanReversionStrategy,
        "trend_following": TrendFollowingStrategy,
    }

    # Default backtest configuration
    DEFAULT_CONFIG = {
        "initial_cash": 100000.0,
        "commission_rate": 0.001,
        "min_commission": 1.0,
        "slippage_rate": 0.0005,
        "position_size_pct": 0.95,
        "max_positions": 10,
        "allow_short": False,
    }

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """Validate input data."""
        if "data_path" not in input_data:
            logger.error("Missing required field: data_path")
            return False

        strategy = input_data.get("strategy")
        if strategy and strategy not in self.STRATEGIES:
            logger.warning(f"Unknown strategy: {strategy}, using default")
        return True

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute backtest."""
        task_id = input_data.get("task_id", "unknown")
        data_path = input_data["data_path"]
        strategy_name = input_data.get("strategy", "momentum")
        config = input_data.get("config", {})
        symbol = input_data.get("symbol", "STOCK")

        logger.info(f"Loading data from {data_path}")

        # Load data
        df = self._load_data(data_path)
        logger.info(f"Loaded {len(df)} rows for backtest")

        # Prepare backtest config
        bt_config = BacktestConfig(
            **{**self.DEFAULT_CONFIG, **config}
        )

        # Create backtest engine
        engine = BacktestEngine(config=bt_config)

        # Get strategy
        strategy = self._get_strategy(strategy_name)
        if strategy is None:
            raise ValueError(f"Unknown strategy: {strategy_name}")

        logger.info(f"Running backtest with strategy: {strategy_name}")

        # Run backtest
        result = engine.run(strategy, df, symbol)

        logger.info(
            f"Backtest complete: {result.metrics.total_return:.2%} return, "
            f"{result.metrics.sharpe_ratio:.2f} Sharpe"
        )

        # Save results
        output_dir = self._ensure_output_dir(task_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save portfolio history
        portfolio_file = output_dir / f"portfolio_{timestamp}.parquet"
        result.portfolio_history.to_parquet(portfolio_file)

        # Save trade history
        trade_file = output_dir / f"trades_{timestamp}.parquet"
        result.trade_history.to_parquet(trade_file)

        # Save metrics summary
        metrics_summary = {
            "strategy_name": result.strategy_name,
            "start_date": str(result.start_date.date()),
            "end_date": str(result.end_date.date()),
            "initial_value": result.initial_value,
            "final_value": result.final_value,
            "total_return": result.metrics.total_return,
            "annualized_return": result.metrics.annualized_return,
            "sharpe_ratio": result.metrics.sharpe_ratio,
            "sortino_ratio": result.metrics.sortino_ratio,
            "max_drawdown": result.metrics.max_drawdown,
            "volatility": result.metrics.volatility,
            "win_rate": result.metrics.win_rate,
            "total_trades": result.metrics.total_trades,
            "profit_factor": result.metrics.profit_factor,
        }

        metrics_file = output_dir / f"metrics_{timestamp}.json"
        with open(metrics_file, "w") as f:
            json.dump(metrics_summary, f, indent=2)

        logger.info(f"Saved backtest results to {output_dir}")

        return {
            "backtest_path": str(output_dir),
            "portfolio_path": str(portfolio_file),
            "trades_path": str(trade_file),
            "metrics_path": str(metrics_file),
            "metrics": metrics_summary,
            "trades": result.metrics.total_trades,
            "artifacts": [
                str(portfolio_file),
                str(trade_file),
                str(metrics_file),
            ],
        }

    def _load_data(self, data_path: str) -> pd.DataFrame:
        """Load data from file."""
        path = self._resolve_path(data_path)

        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        elif path.suffix == ".json":
            df = pd.read_json(path)
        elif path.suffix == ".csv":
            df = pd.read_csv(path)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}")

        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if "time" in df.columns:
                df = df.set_index("time")
            elif "date" in df.columns:
                df = df.set_index("date")
            elif "timestamp" in df.columns:
                df = df.set_index("timestamp")

        df.index = pd.to_datetime(df.index)
        df = df.sort_index()

        # Ensure lowercase column names
        df.columns = [col.lower() for col in df.columns]

        return df

    def _get_strategy(self, strategy_name: str):
        """Get strategy instance by name."""
        strategy_class = self.STRATEGIES.get(strategy_name)
        if strategy_class:
            return strategy_class()
        return None

    def run_multiple_strategies(
        self,
        df: pd.DataFrame,
        strategies: list[str],
        symbol: str,
        config: BacktestConfig,
    ) -> dict:
        """Run backtest for multiple strategies."""
        engine = BacktestEngine(config=config)
        results = {}

        for strategy_name in strategies:
            strategy = self._get_strategy(strategy_name)
            if strategy:
                try:
                    result = engine.run(strategy, df, symbol)
                    results[strategy_name] = {
                        "total_return": result.metrics.total_return,
                        "sharpe_ratio": result.metrics.sharpe_ratio,
                        "max_drawdown": result.metrics.max_drawdown,
                        "win_rate": result.metrics.win_rate,
                        "total_trades": result.metrics.total_trades,
                    }
                except Exception as e:
                    logger.error(f"Backtest failed for {strategy_name}: {e}")
                    results[strategy_name] = {"error": str(e)}

        return results


if __name__ == "__main__":
    run_node(BacktestNode)