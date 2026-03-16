"""Report generator with templates."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger


class ReportGenerator:
    """
    Report generator using Jinja2 templates.

    Supports multiple report types:
    - Daily market summary
    - Backtest results
    - Portfolio analysis
    - Risk reports
    """

    def __init__(self, template_dir: Optional[Path] = None):
        """
        Initialize report generator.

        Args:
            template_dir: Directory containing templates
        """
        if template_dir is None:
            template_dir = Path(__file__).parent / "templates"

        self.template_dir = template_dir
        self.template_dir.mkdir(parents=True, exist_ok=True)

        self.env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

        # Create default templates if they don't exist
        self._ensure_templates()

    def _ensure_templates(self) -> None:
        """Create default templates if they don't exist."""
        templates = {
            "daily_report.html": self._get_daily_report_template(),
            "backtest_report.html": self._get_backtest_report_template(),
            "risk_report.html": self._get_risk_report_template(),
        }

        for name, content in templates.items():
            template_path = self.template_dir / name
            if not template_path.exists():
                template_path.write_text(content)
                logger.info(f"Created template: {name}")

    def generate_daily_report(
        self,
        data: dict,
        output_format: str = "html",
    ) -> str:
        """
        Generate daily market summary report.

        Args:
            data: Dictionary containing:
                - date: Report date
                - market_summary: Market overview data
                - top_gainers: List of top gaining stocks
                - top_losers: List of top losing stocks
                - portfolio_summary: Portfolio performance
                - news: Market news headlines
            output_format: 'html' or 'markdown'

        Returns:
            Generated report string
        """
        template = self.env.get_template("daily_report.html")

        # Add computed values
        data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = template.render(**data)

        if output_format == "markdown":
            report = self._html_to_markdown(report)

        return report

    def generate_backtest_report(
        self,
        backtest_result,
        output_format: str = "html",
    ) -> str:
        """
        Generate backtest performance report.

        Args:
            backtest_result: BacktestResult object
            output_format: 'html' or 'markdown'

        Returns:
            Generated report string
        """
        template = self.env.get_template("backtest_report.html")

        metrics = backtest_result.metrics

        data = {
            "strategy_name": backtest_result.strategy_name,
            "start_date": backtest_result.start_date.strftime("%Y-%m-%d"),
            "end_date": backtest_result.end_date.strftime("%Y-%m-%d"),
            "initial_value": f"${backtest_result.initial_value:,.2f}",
            "final_value": f"${backtest_result.final_value:,.2f}",
            "total_return": f"{metrics.total_return:.2%}",
            "annualized_return": f"{metrics.annualized_return:.2%}",
            "sharpe_ratio": f"{metrics.sharpe_ratio:.2f}",
            "sortino_ratio": f"{metrics.sortino_ratio:.2f}",
            "max_drawdown": f"{metrics.max_drawdown:.2%}",
            "volatility": f"{metrics.volatility:.2%}",
            "win_rate": f"{metrics.win_rate:.2%}",
            "total_trades": metrics.total_trades,
            "profit_factor": f"{metrics.profit_factor:.2f}",
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        report = template.render(**data)

        if output_format == "markdown":
            report = self._html_to_markdown(report)

        return report

    def generate_risk_report(
        self,
        risk_data: dict,
        output_format: str = "html",
    ) -> str:
        """
        Generate risk analysis report.

        Args:
            risk_data: Dictionary containing:
                - exposure: Exposure metrics
                - var: VaR/CVaR data
                - stress_test: Stress test results
                - alerts: Risk alerts
            output_format: 'html' or 'markdown'

        Returns:
            Generated report string
        """
        template = self.env.get_template("risk_report.html")

        risk_data["generated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = template.render(**risk_data)

        if output_format == "markdown":
            report = self._html_to_markdown(report)

        return report

    def generate_portfolio_report(
        self,
        portfolio_data: dict,
        performance_data: Optional[dict] = None,
        output_format: str = "html",
    ) -> str:
        """
        Generate portfolio analysis report.

        Args:
            portfolio_data: Portfolio holdings and metrics
            performance_data: Historical performance data
            output_format: 'html' or 'markdown'

        Returns:
            Generated report string
        """
        data = {
            "portfolio": portfolio_data,
            "performance": performance_data or {},
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # Calculate summary stats
        if "positions" in portfolio_data:
            total_value = sum(p.get("value", 0) for p in portfolio_data["positions"])
            data["total_value"] = total_value
            data["num_positions"] = len(portfolio_data["positions"])

        template = self.env.get_template("daily_report.html")
        return template.render(**data)

    def _html_to_markdown(self, html: str) -> str:
        """
        Convert HTML to Markdown.

        Args:
            html: HTML string

        Returns:
            Markdown string
        """
        import re

        # Simple HTML to Markdown conversion
        text = html

        # Headers
        text = re.sub(r"<h1>(.*?)</h1>", r"# \1\n", text)
        text = re.sub(r"<h2>(.*?)</h2>", r"## \1\n", text)
        text = re.sub(r"<h3>(.*?)</h3>", r"### \1\n", text)

        # Bold and italic
        text = re.sub(r"<strong>(.*?)</strong>", r"**\1**", text)
        text = re.sub(r"<em>(.*?)</em>", r"*\1*", text)

        # Tables
        text = re.sub(r"<table.*?>", "", text)
        text = re.sub(r"</table>", "\n", text)
        text = re.sub(r"<tr.*?>", "", text)
        text = re.sub(r"</tr>", "\n", text)
        text = re.sub(r"<th.*?>(.*?)</th>", r"| \1 ", text)
        text = re.sub(r"<td.*?>(.*?)</td>", r"| \1 ", text)

        # Lists
        text = re.sub(r"<li>(.*?)</li>", r"- \1\n", text)

        # Paragraphs
        text = re.sub(r"<p>(.*?)</p>", r"\1\n\n", text)

        # Remove remaining tags
        text = re.sub(r"<[^>]+>", "", text)

        # Clean up whitespace
        text = re.sub(r"\n\s*\n\s*\n", "\n\n", text)

        return text.strip()

    def _get_daily_report_template(self) -> str:
        """Get default daily report template."""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Daily Market Report - {{ date }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #2c3e50; }
        h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #3498db; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .positive { color: #27ae60; }
        .negative { color: #e74c3c; }
        .summary-box { background: #ecf0f1; padding: 20px; border-radius: 5px; margin: 20px 0; }
    </style>
</head>
<body>
    <h1>Daily Market Report</h1>
    <p><strong>Date:</strong> {{ date }}</p>
    <p><em>Generated at: {{ generated_at }}</em></p>

    <div class="summary-box">
        <h2>Market Summary</h2>
        {% if market_summary %}
        <table>
            <tr>
                <th>Index</th>
                <th>Close</th>
                <th>Change</th>
                <th>Change %</th>
            </tr>
            {% for item in market_summary %}
            <tr>
                <td>{{ item.name }}</td>
                <td>{{ "%.2f"|format(item.close) }}</td>
                <td class="{{ 'positive' if item.change >= 0 else 'negative' }}">
                    {{ "%.2f"|format(item.change) }}
                </td>
                <td class="{{ 'positive' if item.change_pct >= 0 else 'negative' }}">
                    {{ "%.2f%%"|format(item.change_pct) }}
                </td>
            </tr>
            {% endfor %}
        </table>
        {% else %}
        <p>No market summary data available.</p>
        {% endif %}
    </div>

    {% if top_gainers %}
    <h2>Top Gainers</h2>
    <table>
        <tr>
            <th>Symbol</th>
            <th>Close</th>
            <th>Change %</th>
        </tr>
        {% for stock in top_gainers %}
        <tr>
            <td>{{ stock.symbol }}</td>
            <td>{{ "%.2f"|format(stock.close) }}</td>
            <td class="positive">{{ "%.2f%%"|format(stock.change_pct) }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% if top_losers %}
    <h2>Top Losers</h2>
    <table>
        <tr>
            <th>Symbol</th>
            <th>Close</th>
            <th>Change %</th>
        </tr>
        {% for stock in top_losers %}
        <tr>
            <td>{{ stock.symbol }}</td>
            <td>{{ "%.2f"|format(stock.close) }}</td>
            <td class="negative">{{ "%.2f%%"|format(stock.change_pct) }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% if portfolio_summary %}
    <h2>Portfolio Summary</h2>
    <div class="summary-box">
        <p><strong>Total Value:</strong> ${{ "%.2f"|format(portfolio_summary.total_value) }}</p>
        <p><strong>Daily P&L:</strong>
            <span class="{{ 'positive' if portfolio_summary.daily_pnl >= 0 else 'negative' }}">
                ${{ "%.2f"|format(portfolio_summary.daily_pnl) }}
                ({{ "%.2f%%"|format(portfolio_summary.daily_pnl_pct) }})
            </span>
        </p>
    </div>
    {% endif %}

    {% if news %}
    <h2>Market News</h2>
    <ul>
        {% for item in news %}
        <li>{{ item.title }} - <em>{{ item.source }}</em></li>
        {% endfor %}
    </ul>
    {% endif %}

    <hr>
    <p><em>This report was automatically generated by InvestManager.</em></p>
</body>
</html>'''

    def _get_backtest_report_template(self) -> str:
        """Get default backtest report template."""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Backtest Report - {{ strategy_name }}</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #2c3e50; }
        h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }
        .metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }
        .metric-box { background: #ecf0f1; padding: 15px; border-radius: 5px; text-align: center; }
        .metric-value { font-size: 24px; font-weight: bold; color: #2c3e50; }
        .metric-label { color: #7f8c8d; font-size: 12px; }
        .positive { color: #27ae60; }
        .negative { color: #e74c3c; }
    </style>
</head>
<body>
    <h1>Backtest Performance Report</h1>
    <h2>{{ strategy_name }}</h2>
    <p><strong>Period:</strong> {{ start_date }} to {{ end_date }}</p>
    <p><em>Generated at: {{ generated_at }}</em></p>

    <h2>Return Metrics</h2>
    <div class="metrics-grid">
        <div class="metric-box">
            <div class="metric-value">{{ total_return }}</div>
            <div class="metric-label">Total Return</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{{ annualized_return }}</div>
            <div class="metric-label">Annualized Return</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{{ sharpe_ratio }}</div>
            <div class="metric-label">Sharpe Ratio</div>
        </div>
    </div>

    <h2>Risk Metrics</h2>
    <div class="metrics-grid">
        <div class="metric-box">
            <div class="metric-value">{{ volatility }}</div>
            <div class="metric-label">Volatility</div>
        </div>
        <div class="metric-box">
            <div class="metric-value {{ 'negative' if max_drawdown|replace('%','')|float > 0.1 else '' }}">{{ max_drawdown }}</div>
            <div class="metric-label">Max Drawdown</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{{ sortino_ratio }}</div>
            <div class="metric-label">Sortino Ratio</div>
        </div>
    </div>

    <h2>Trade Statistics</h2>
    <div class="metrics-grid">
        <div class="metric-box">
            <div class="metric-value">{{ total_trades }}</div>
            <div class="metric-label">Total Trades</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{{ win_rate }}</div>
            <div class="metric-label">Win Rate</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{{ profit_factor }}</div>
            <div class="metric-label">Profit Factor</div>
        </div>
    </div>

    <h2>Summary</h2>
    <table>
        <tr>
            <th>Metric</th>
            <th>Value</th>
        </tr>
        <tr>
            <td>Initial Capital</td>
            <td>{{ initial_value }}</td>
        </tr>
        <tr>
            <td>Final Capital</td>
            <td>{{ final_value }}</td>
        </tr>
    </table>

    <hr>
    <p><em>This report was automatically generated by InvestManager.</em></p>
</body>
</html>'''

    def _get_risk_report_template(self) -> str:
        """Get default risk report template."""
        return '''<!DOCTYPE html>
<html>
<head>
    <title>Risk Analysis Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        h1 { color: #2c3e50; }
        h2 { color: #34495e; border-bottom: 2px solid #e74c3c; padding-bottom: 5px; }
        .warning { background: #f39c12; color: white; padding: 10px; border-radius: 5px; }
        .danger { background: #e74c3c; color: white; padding: 10px; border-radius: 5px; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #e74c3c; color: white; }
        .metric-box { background: #ecf0f1; padding: 15px; border-radius: 5px; margin: 10px 0; }
    </style>
</head>
<body>
    <h1>Risk Analysis Report</h1>
    <p><em>Generated at: {{ generated_at }}</em></p>

    {% if alerts %}
    <h2>Active Alerts</h2>
    {% for alert in alerts %}
    <div class="{{ 'danger' if alert.severity == 'critical' else 'warning' }}">
        <strong>{{ alert.severity|upper }}:</strong> {{ alert.message }}
    </div>
    {% endfor %}
    {% endif %}

    {% if exposure %}
    <h2>Exposure Summary</h2>
    <div class="metric-box">
        <p><strong>Gross Exposure:</strong> {{ "%.1f%%"|format(exposure.gross_exposure_pct * 100) }}</p>
        <p><strong>Net Exposure:</strong> {{ "%.1f%%"|format(exposure.net_exposure_pct * 100) }}</p>
        <p><strong>Leverage:</strong> {{ "%.2f"|format(exposure.leverage) }}x</p>
    </div>
    {% endif %}

    {% if var %}
    <h2>Value at Risk</h2>
    <table>
        <tr>
            <th>Confidence</th>
            <th>VaR</th>
            <th>CVaR</th>
        </tr>
        <tr>
            <td>95%</td>
            <td>{{ "%.2f%%"|format(var.var_95 * 100) }}</td>
            <td>{{ "%.2f%%"|format(var.cvar_95 * 100) }}</td>
        </tr>
        <tr>
            <td>99%</td>
            <td>{{ "%.2f%%"|format(var.var_99 * 100) }}</td>
            <td>{{ "%.2f%%"|format(var.cvar_99 * 100) }}</td>
        </tr>
    </table>
    {% endif %}

    {% if stress_test %}
    <h2>Stress Test Results</h2>
    <table>
        <tr>
            <th>Scenario</th>
            <th>Impact</th>
            <th>Impact %</th>
        </tr>
        {% for scenario, result in stress_test.items() %}
        <tr>
            <td>{{ scenario }}</td>
            <td>{{ "%.2f"|format(result.total_impact) }}</td>
            <td>{{ "%.2f%%"|format(result.impact_pct * 100) }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    <hr>
    <p><em>This report was automatically generated by InvestManager.</em></p>
</body>
</html>'''