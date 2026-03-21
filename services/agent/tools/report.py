"""Report Tool - Generate analysis reports."""

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from loguru import logger

from .base import BaseTool, ToolResult


class ReportTool(BaseTool):
    """Tool for generating analysis reports.

    Creates formatted reports from stock analysis, backtest results, etc.
    """

    name = "report"
    description = "生成分析报告。根据股票分析和回测结果，生成格式化的投资报告。"
    parameters = {
        "type": "object",
        "properties": {
            "report_type": {
                "type": "string",
                "enum": ["analysis", "backtest", "comprehensive"],
                "description": "报告类型: analysis(分析报告), backtest(回测报告), comprehensive(综合报告)",
                "default": "analysis",
            },
            "symbol": {
                "type": "string",
                "description": "股票代码",
            },
            "data": {
                "type": "object",
                "description": "报告数据(可选，如不提供则自动获取)",
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "text", "json"],
                "description": "输出格式",
                "default": "markdown",
            },
        },
        "required": ["symbol"],
    }
    timeout = 60

    async def execute(
        self,
        symbol: str,
        report_type: str = "analysis",
        data: Optional[dict] = None,
        format: str = "markdown",
    ) -> ToolResult:
        """Generate a report.

        Args:
            symbol: Stock symbol
            report_type: Type of report
            data: Optional pre-fetched data
            format: Output format

        Returns:
            ToolResult with formatted report
        """
        try:
            # Fetch data if not provided
            if data is None:
                data = await self._fetch_data(symbol, report_type)

            # Generate report based on type
            if report_type == "analysis":
                report = self._generate_analysis_report(symbol, data, format)
            elif report_type == "backtest":
                report = self._generate_backtest_report(symbol, data, format)
            elif report_type == "comprehensive":
                report = await self._generate_comprehensive_report(symbol, data, format)
            else:
                return ToolResult(
                    success=False,
                    error=f"Unknown report type: {report_type}",
                )

            return ToolResult(
                success=True,
                data={
                    "report": report,
                    "format": format,
                    "report_type": report_type,
                    "symbol": symbol,
                    "generated_at": datetime.now().isoformat(),
                },
                metadata={
                    "symbol": symbol,
                    "report_type": report_type,
                },
            )

        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return ToolResult(
                success=False,
                error=f"生成报告失败: {str(e)}",
            )

    async def _fetch_data(self, symbol: str, report_type: str) -> dict:
        """Fetch data for the report."""
        from .stock_data import StockDataTool
        from .analysis import StockAnalysisTool

        data = {}

        # Always get basic stock data
        stock_tool = StockDataTool()
        stock_result = await stock_tool.execute(symbol, data_type="realtime")
        if stock_result.success:
            data["stock"] = stock_result.data

        # Get analysis data for analysis and comprehensive reports
        if report_type in ["analysis", "comprehensive"]:
            analysis_tool = StockAnalysisTool()
            analysis_result = await analysis_tool.execute(symbol)
            if analysis_result.success:
                data["analysis"] = analysis_result.data

        return data

    def _generate_analysis_report(
        self,
        symbol: str,
        data: dict,
        format: str,
    ) -> str:
        """Generate analysis report."""
        stock = data.get("stock", {})
        analysis = data.get("analysis", {})
        technical = analysis.get("technical", {})
        fundamental = analysis.get("fundamental", {})

        if format == "markdown":
            lines = [
                f"# {stock.get('name', symbol)} ({symbol}) 分析报告",
                "",
                f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "",
                "## 技术分析",
                "",
                f"- **趋势**: {technical.get('trend', '未知')}",
                f"- **当前价格**: {technical.get('current_price', 'N/A')}",
                "",
                "### 技术指标",
                "",
            ]

            indicators = technical.get("indicators", {})
            for name, value in indicators.items():
                if value is not None:
                    lines.append(f"- **{name}**: {value}")

            signals = technical.get("signals", [])
            if signals:
                lines.extend([
                    "",
                    "### 技术信号",
                    "",
                ])
                for s in signals:
                    lines.append(f"- {s.get('indicator', '')}: {s.get('type', '')}")

            # Fundamental section
            lines.extend([
                "",
                "## 基本面分析",
                "",
            ])

            info = fundamental.get("info", fundamental)
            if isinstance(info, dict):
                for key, value in info.items():
                    if value is not None and value != 0:
                        lines.append(f"- **{key}**: {value}")

            summary = analysis.get("summary", "")
            if summary:
                lines.extend([
                    "",
                    "## 综合评价",
                    "",
                    summary,
                ])

            return "\n".join(lines)

        elif format == "text":
            lines = [
                f"{stock.get('name', symbol)} ({symbol}) 分析报告",
                f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "",
                "技术分析:",
                f"  趋势: {technical.get('trend', '未知')}",
                f"  当前价格: {technical.get('current_price', 'N/A')}",
                "",
                "技术指标:",
            ]

            indicators = technical.get("indicators", {})
            for name, value in indicators.items():
                if value is not None:
                    lines.append(f"  {name}: {value}")

            return "\n".join(lines)

        else:  # json
            import json

            return json.dumps(
                {
                    "symbol": symbol,
                    "stock": stock,
                    "analysis": analysis,
                    "generated_at": datetime.now().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )

    def _generate_backtest_report(
        self,
        symbol: str,
        data: dict,
        format: str,
    ) -> str:
        """Generate backtest report."""
        backtest = data.get("backtest", {})

        if format == "markdown":
            lines = [
                f"# {symbol} 回测报告",
                "",
                f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "",
                "## 回测结果",
                "",
                f"- **初始资金**: {backtest.get('initial_capital', 0):,.2f}",
                f"- **最终价值**: {backtest.get('final_value', 0):,.2f}",
                f"- **总收益率**: {backtest.get('total_return', 0):.2f}%",
                f"- **夏普比率**: {backtest.get('sharpe_ratio', 0):.3f}",
                f"- **最大回撤**: {backtest.get('max_drawdown', 0):.2f}%",
                f"- **交易次数**: {backtest.get('total_trades', 0)}",
                f"- **胜率**: {backtest.get('win_rate', 0):.2f}%",
            ]

            return "\n".join(lines)

        elif format == "text":
            return "\n".join([
                f"{symbol} 回测报告",
                f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                "",
                "回测结果:",
                f"  初始资金: {backtest.get('initial_capital', 0):,.2f}",
                f"  最终价值: {backtest.get('final_value', 0):,.2f}",
                f"  总收益率: {backtest.get('total_return', 0):.2f}%",
                f"  夏普比率: {backtest.get('sharpe_ratio', 0):.3f}",
                f"  最大回撤: {backtest.get('max_drawdown', 0):.2f}%",
                f"  交易次数: {backtest.get('total_trades', 0)}",
                f"  胜率: {backtest.get('win_rate', 0):.2f}%",
            ])

        else:  # json
            import json

            return json.dumps(
                {
                    "symbol": symbol,
                    "backtest": backtest,
                    "generated_at": datetime.now().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            )

    async def _generate_comprehensive_report(
        self,
        symbol: str,
        data: dict,
        format: str,
    ) -> str:
        """Generate comprehensive report with analysis and backtest."""
        from .backtest import BacktestTool

        # Run a quick backtest
        backtest_tool = BacktestTool()
        backtest_result = await backtest_tool.execute(symbol, strategy="buy_hold", days=365)

        if backtest_result.success:
            data["backtest"] = backtest_result.data

        # Combine reports
        analysis_report = self._generate_analysis_report(symbol, data, "markdown")

        if "backtest" in data:
            backtest_section = [
                "",
                "---",
                "",
                "## 一年收益回测",
                "",
                f"- **总收益率**: {data['backtest'].get('total_return', 0):.2f}%",
                f"- **最大回撤**: {data['backtest'].get('max_drawdown', 0):.2f}%",
            ]
            return analysis_report + "\n".join(backtest_section)

        return analysis_report