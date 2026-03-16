"""Report generation task node."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.orchestrator.nodes.base import TaskNode, run_node
from src.report.generator import ReportGenerator


class ReportNode(TaskNode):
    """
    Task node for generating reports.

    Supports multiple report types:
    - daily: Daily market summary report
    - backtest: Strategy backtest report
    - risk: Risk analysis report
    - portfolio: Portfolio analysis report

    Input:
        report_type: Type of report to generate
        data_path: Path to input data
        output_format: Output format ('html' or 'markdown')
        title: Report title (optional)

    Output:
        report_path: Path to generated report
        format: Report format
    """

    def setup(self) -> None:
        """Initialize report generator."""
        self.generator = ReportGenerator()

    def validate_input(self, input_data: dict[str, Any]) -> bool:
        """Validate input data."""
        if "data_path" not in input_data:
            logger.error("Missing required field: data_path")
            return False

        report_type = input_data.get("report_type", "daily")
        valid_types = ["daily", "backtest", "risk", "portfolio"]
        if report_type not in valid_types:
            logger.error(f"Invalid report type: {report_type}")
            return False

        return True

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Generate report."""
        task_id = input_data.get("task_id", "unknown")
        report_type = input_data.get("report_type", "daily")
        data_path = input_data["data_path"]
        output_format = input_data.get("output_format", "html")
        title = input_data.get("title")

        logger.info(f"Generating {report_type} report from {data_path}")

        # Load input data
        input_data_content = self._load_input_data(data_path)

        # Generate report based on type
        if report_type == "daily":
            report_content = self._generate_daily_report(input_data_content, title)
        elif report_type == "backtest":
            report_content = self._generate_backtest_report(input_data_content, title)
        elif report_type == "risk":
            report_content = self._generate_risk_report(input_data_content, title)
        elif report_type == "portfolio":
            report_content = self._generate_portfolio_report(input_data_content, title)
        else:
            raise ValueError(f"Unknown report type: {report_type}")

        # Save report
        output_dir = self._ensure_output_dir(task_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = "html" if output_format == "html" else "md"
        report_file = output_dir / f"report_{report_type}_{timestamp}.{extension}"

        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"Saved report to {report_file}")

        return {
            "report_path": str(report_file),
            "report_type": report_type,
            "format": output_format,
            "size_bytes": report_file.stat().st_size,
            "artifacts": [str(report_file)],
        }

    def _load_input_data(self, data_path: str) -> dict:
        """Load input data from file or task output."""
        path = self._resolve_path(data_path)

        if path.is_dir():
            # Look for JSON or parquet files in the directory
            json_files = list(path.glob("*.json"))
            parquet_files = list(path.glob("*.parquet"))

            if json_files:
                with open(json_files[0], "r") as f:
                    return json.load(f)
            elif parquet_files:
                import pandas as pd
                df = pd.read_parquet(parquet_files[0])
                return df.to_dict()
        else:
            if path.suffix == ".json":
                with open(path, "r") as f:
                    return json.load(f)
            elif path.suffix == ".parquet":
                import pandas as pd
                df = pd.read_parquet(path)
                return df.to_dict()

        return {}

    def _generate_daily_report(self, data: dict, title: Optional[str] = None) -> str:
        """Generate daily market report."""
        report_title = title or f"Daily Market Report - {datetime.now().strftime('%Y-%m-%d')}"

        # Prepare report data
        report_data = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "title": report_title,
            "market_summary": data.get("market_summary", []),
            "top_gainers": data.get("top_gainers", []),
            "top_losers": data.get("top_losers", []),
            "portfolio_summary": data.get("portfolio_summary"),
            "news": data.get("news", []),
        }

        # Use data from analysis if available
        if "indicators" in data:
            report_data["indicators_summary"] = self._summarize_indicators(data)

        return self.generator.generate_daily_report(report_data)

    def _generate_backtest_report(self, data: dict, title: Optional[str] = None) -> str:
        """Generate backtest performance report."""
        # Create a simple object with metrics for the generator
        class BacktestResult:
            def __init__(self, data: dict):
                self.strategy_name = data.get("strategy_name", "Unknown")
                self.start_date = datetime.strptime(
                    data.get("start_date", "2020-01-01"), "%Y-%m-%d"
                )
                self.end_date = datetime.strptime(
                    data.get("end_date", datetime.now().strftime("%Y-%m-%d")), "%Y-%m-%d"
                )
                self.initial_value = data.get("initial_value", 100000)
                self.final_value = data.get("final_value", 100000)
                self.metrics = self._create_metrics(data)

            def _create_metrics(self, data):
                class Metrics:
                    pass
                m = Metrics()
                m.total_return = data.get("total_return", 0)
                m.annualized_return = data.get("annualized_return", 0)
                m.sharpe_ratio = data.get("sharpe_ratio", 0)
                m.sortino_ratio = data.get("sortino_ratio", 0)
                m.max_drawdown = data.get("max_drawdown", 0)
                m.volatility = data.get("volatility", 0)
                m.win_rate = data.get("win_rate", 0)
                m.total_trades = data.get("total_trades", 0)
                m.profit_factor = data.get("profit_factor", 0)
                return m

        result = BacktestResult(data)
        return self.generator.generate_backtest_report(result)

    def _generate_risk_report(self, data: dict, title: Optional[str] = None) -> str:
        """Generate risk analysis report."""
        report_data = {
            "alerts": data.get("alerts", []),
            "exposure": data.get("exposure"),
            "var": data.get("var"),
            "stress_test": data.get("stress_test"),
        }
        return self.generator.generate_risk_report(report_data)

    def _generate_portfolio_report(self, data: dict, title: Optional[str] = None) -> str:
        """Generate portfolio analysis report."""
        return self.generator.generate_portfolio_report(data)

    def _summarize_indicators(self, data: dict) -> dict:
        """Summarize technical indicators for report."""
        summary = {}

        indicators = data.get("indicators", [])
        if isinstance(indicators, list):
            summary["indicators_calculated"] = indicators

        # Add key indicator values if available
        if "metrics" in data:
            metrics = data["metrics"]
            summary["key_metrics"] = {
                "total_return": metrics.get("total_return"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "max_drawdown": metrics.get("max_drawdown"),
            }

        return summary


if __name__ == "__main__":
    run_node(ReportNode)