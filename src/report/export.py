"""Report export functionality."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger


class ExportFormat(Enum):
    """Export format types."""

    HTML = "html"
    PDF = "pdf"
    MARKDOWN = "md"
    CSV = "csv"
    EXCEL = "xlsx"
    JSON = "json"


class ReportExporter:
    """
    Export reports in various formats.

    Supports HTML, PDF, Markdown, CSV, Excel, and JSON formats.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize report exporter.

        Args:
            output_dir: Directory for exported files
        """
        self.output_dir = output_dir or Path("reports")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        content: str,
        filename: str,
        format: ExportFormat,
        **kwargs,
    ) -> Path:
        """
        Export content to file.

        Args:
            content: Content to export
            filename: Base filename (without extension)
            format: Export format
            **kwargs: Additional format-specific options

        Returns:
            Path to exported file
        """
        output_path = self.output_dir / f"{filename}.{format.value}"

        if format == ExportFormat.HTML:
            output_path = self._export_html(content, output_path, **kwargs)
        elif format == ExportFormat.PDF:
            output_path = self._export_pdf(content, output_path, **kwargs)
        elif format == ExportFormat.MARKDOWN:
            output_path = self._export_markdown(content, output_path, **kwargs)
        elif format == ExportFormat.CSV:
            output_path = self._export_csv(content, output_path, **kwargs)
        elif format == ExportFormat.EXCEL:
            output_path = self._export_excel(content, output_path, **kwargs)
        elif format == ExportFormat.JSON:
            output_path = self._export_json(content, output_path, **kwargs)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Report exported to: {output_path}")
        return output_path

    def _export_html(
        self,
        content: str,
        output_path: Path,
        title: str = "Report",
        **kwargs,
    ) -> Path:
        """Export as HTML file."""
        if not content.startswith("<!DOCTYPE") and not content.startswith("<html"):
            # Wrap in HTML if not already
            content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
    </style>
</head>
<body>
{content}
</body>
</html>"""

        output_path.write_text(content, encoding="utf-8")
        return output_path

    def _export_pdf(
        self,
        content: str,
        output_path: Path,
        **kwargs,
    ) -> Path:
        """Export as PDF file."""
        try:
            # Try using weasyprint for PDF generation
            import weasyprint

            if content.startswith("<!DOCTYPE") or content.startswith("<html"):
                html = content
            else:
                html = f"<html><body>{content}</body></html>"

            weasyprint.HTML(string=html).write_pdf(output_path)
            return output_path

        except ImportError:
            logger.warning("weasyprint not installed, falling back to HTML")
            # Fall back to HTML
            html_path = output_path.with_suffix(".html")
            return self._export_html(content, html_path, **kwargs)

    def _export_markdown(
        self,
        content: str,
        output_path: Path,
        **kwargs,
    ) -> Path:
        """Export as Markdown file."""
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def _export_csv(
        self,
        content,
        output_path: Path,
        **kwargs,
    ) -> Path:
        """Export as CSV file."""
        if isinstance(content, pd.DataFrame):
            content.to_csv(output_path, index=True)
        elif isinstance(content, list):
            df = pd.DataFrame(content)
            df.to_csv(output_path, index=False)
        else:
            # Assume it's already CSV formatted
            output_path.write_text(str(content), encoding="utf-8")

        return output_path

    def _export_excel(
        self,
        content,
        output_path: Path,
        sheet_name: str = "Report",
        **kwargs,
    ) -> Path:
        """Export as Excel file."""
        if isinstance(content, pd.DataFrame):
            content.to_excel(output_path, sheet_name=sheet_name, index=True)
        elif isinstance(content, list):
            df = pd.DataFrame(content)
            df.to_excel(output_path, sheet_name=sheet_name, index=False)
        elif isinstance(content, dict):
            # Multiple sheets
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                for name, data in content.items():
                    if isinstance(data, pd.DataFrame):
                        data.to_excel(writer, sheet_name=name, index=True)
                    elif isinstance(data, list):
                        pd.DataFrame(data).to_excel(writer, sheet_name=name, index=False)
        else:
            raise ValueError("Excel export requires DataFrame, list, or dict")

        return output_path

    def _export_json(
        self,
        content,
        output_path: Path,
        **kwargs,
    ) -> Path:
        """Export as JSON file."""
        import json

        if isinstance(content, str):
            # Try to parse as JSON
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {"content": content}

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, default=str)

        return output_path

    def export_backtest_results(
        self,
        result,
        format: ExportFormat = ExportFormat.HTML,
    ) -> Path:
        """
        Export backtest results.

        Args:
            result: BacktestResult object
            format: Export format

        Returns:
            Path to exported file
        """
        from src.report.generator import ReportGenerator

        generator = ReportGenerator()
        report = generator.generate_backtest_report(result)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backtest_{result.strategy_name}_{timestamp}"

        return self.export(report, filename, format)

    def export_portfolio_data(
        self,
        portfolio_data: dict,
        format: ExportFormat = ExportFormat.EXCEL,
    ) -> Path:
        """
        Export portfolio data.

        Args:
            portfolio_data: Portfolio data dictionary
            format: Export format

        Returns:
            Path to exported file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"portfolio_{timestamp}"

        if format == ExportFormat.EXCEL:
            # Create multi-sheet export
            export_data = {}

            if "positions" in portfolio_data:
                export_data["Positions"] = portfolio_data["positions"]

            if "history" in portfolio_data:
                export_data["History"] = portfolio_data["history"]

            if "trades" in portfolio_data:
                export_data["Trades"] = portfolio_data["trades"]

            return self.export(export_data, filename, format)

        return self.export(portfolio_data, filename, format)

    def export_trade_history(
        self,
        trades: pd.DataFrame,
        format: ExportFormat = ExportFormat.CSV,
    ) -> Path:
        """
        Export trade history.

        Args:
            trades: Trade history DataFrame
            format: Export format

        Returns:
            Path to exported file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trades_{timestamp}"

        return self.export(trades, filename, format)

    def list_reports(self) -> list[dict]:
        """
        List all exported reports.

        Returns:
            List of report info dictionaries
        """
        reports = []

        for file in self.output_dir.iterdir():
            if file.is_file():
                stat = file.stat()
                reports.append(
                    {
                        "filename": file.name,
                        "path": str(file),
                        "size": stat.st_size,
                        "modified": datetime.fromtimestamp(stat.st_mtime),
                        "format": file.suffix.lstrip("."),
                    }
                )

        return sorted(reports, key=lambda x: x["modified"], reverse=True)

    def cleanup_old_reports(self, days: int = 30) -> int:
        """
        Remove reports older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of files deleted
        """
        cutoff = datetime.now().timestamp() - (days * 86400)
        deleted = 0

        for file in self.output_dir.iterdir():
            if file.is_file() and file.stat().st_mtime < cutoff:
                file.unlink()
                deleted += 1

        if deleted > 0:
            logger.info(f"Deleted {deleted} old report files")

        return deleted