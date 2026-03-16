"""Feishu report sender for sending reports via messages and documents."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from config.settings import settings
from src.feishu.client import FeishuClient, get_feishu_client


class FeishuReportSender:
    """Send reports to Feishu via messages and documents."""

    def __init__(self, client: Optional[FeishuClient] = None):
        """
        Initialize report sender.

        Args:
            client: FeishuClient instance
        """
        self._client = client or get_feishu_client()

    async def send_report_message(
        self,
        chat_id: str,
        report_type: str,
        title: str,
        summary: str,
        details: Optional[dict] = None,
    ) -> dict:
        """
        Send report as a message card.

        Args:
            chat_id: Target chat ID
            report_type: Type of report (daily, weekly, etc.)
            title: Report title
            summary: Report summary
            details: Additional details

        Returns:
            API response
        """
        # Build card content
        elements = [
            {
                "tag": "markdown",
                "content": summary,
            }
        ]

        if details:
            # Add key metrics
            if "metrics" in details:
                metric_fields = []
                for key, value in details["metrics"].items():
                    metric_fields.append({
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**{key}**\n{value}",
                        },
                    })
                elements.insert(0, {
                    "tag": "div",
                    "fields": metric_fields,
                })

            # Add top stocks
            if "top_stocks" in details:
                stock_content = "### 📈 关注股票\n\n"
                for stock in details["top_stocks"][:5]:
                    symbol = stock.get("symbol", "")
                    name = stock.get("name", "")
                    change = stock.get("change", 0)
                    emoji = "🔴" if change < 0 else "🟢"
                    stock_content += f"{emoji} {symbol} {name}: {change:+.2f}%\n"
                elements.append({
                    "tag": "markdown",
                    "content": stock_content,
                })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 {title}",
                },
                "template": "blue" if report_type == "daily" else "purple",
            },
            "elements": elements,
        }

        return await self._client.send_card_message(chat_id, "chat_id", card)

    async def send_report_document(
        self,
        chat_id: str,
        report_title: str,
        report_content: str,
        folder_token: Optional[str] = None,
    ) -> dict:
        """
        Create and send a Feishu document with report content.

        Args:
            chat_id: Target chat ID
            report_title: Document title
            report_content: Markdown content
            folder_token: Target folder token

        Returns:
            API response
        """
        folder_token = folder_token or settings.feishu_folder_token

        # Create document
        doc_response = await self._client.create_document(
            title=report_title,
            folder_token=folder_token,
        )

        if doc_response.get("code") != 0:
            logger.error(f"Failed to create document: {doc_response}")
            return doc_response

        document = doc_response.get("data", {}).get("document", {})
        document_id = document.get("document_id")

        if not document_id:
            logger.error("No document ID in response")
            return doc_response

        # Add content to document
        # Split content into paragraphs
        paragraphs = report_content.split("\n\n")

        for i, para in enumerate(paragraphs):
            if not para.strip():
                continue

            # Determine block type based on content
            if para.startswith("# "):
                # Heading 1
                text = para[2:]
                block = {
                    "block_type": 4,  # Heading1
                    "heading1": {
                        "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
                    },
                }
            elif para.startswith("## "):
                # Heading 2
                text = para[3:]
                block = {
                    "block_type": 5,  # Heading2
                    "heading2": {
                        "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
                    },
                }
            elif para.startswith("### "):
                # Heading 3
                text = para[4:]
                block = {
                    "block_type": 6,  # Heading3
                    "heading3": {
                        "elements": [{"text_run": {"content": text, "text_element_style": {}}}]
                    },
                }
            else:
                # Regular paragraph
                block = {
                    "block_type": 2,  # Text
                    "text": {
                        "elements": [{"text_run": {"content": para, "text_element_style": {}}}]
                    },
                    "style": {},
                }

            await self._client.create_document_block(document_id, document_id, block)

        # Send document link to chat
        doc_url = f"https://feishu.cn/docx/{document_id}"
        message = f"📄 报告已生成: [{report_title}]({doc_url})"
        await self._client.send_text_message(chat_id, "chat_id", message)

        logger.info(f"Report document created: {document_id}")
        return doc_response

    async def upload_report_file(
        self,
        chat_id: str,
        file_path: str,
        file_name: Optional[str] = None,
    ) -> dict:
        """
        Upload a report file and send to chat.

        Args:
            chat_id: Target chat ID
            file_path: Local file path
            file_name: Display file name

        Returns:
            API response
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Report file not found: {file_path}")

        file_name = file_name or file_path.name

        # Upload file
        upload_response = await self._client.upload_file(
            file_path=str(file_path),
            file_name=file_name,
            parent_type="ccm_import_open",
        )

        if upload_response.get("code") != 0:
            logger.error(f"Failed to upload file: {upload_response}")
            return upload_response

        file_token = upload_response.get("data", {}).get("file_token")

        # Send file to chat
        message = f"📎 报告附件: {file_name}"
        await self._client.send_text_message(chat_id, "chat_id", message)

        logger.info(f"Report file uploaded: {file_name}")
        return upload_response

    async def send_daily_report(
        self,
        chat_id: str,
        report_data: dict,
    ) -> dict:
        """
        Send a formatted daily report.

        Args:
            chat_id: Target chat ID
            report_data: Report data dict with:
                - report_date: str
                - market_overview: dict
                - top_gainers: list
                - top_losers: list
                - sector_performance: list
                - summary: str

        Returns:
            API response
        """
        report_date = report_data.get("report_date", datetime.now().strftime("%Y-%m-%d"))
        title = f"每日市场报告 - {report_date}"

        # Build summary content
        summary_parts = []

        if "market_overview" in report_data:
            overview = report_data["market_overview"]
            summary_parts.append(f"**市场概览**\n")
            for key, value in overview.items():
                summary_parts.append(f"- {key}: {value}")

        if report_data.get("summary"):
            summary_parts.append(f"\n**AI 分析摘要**\n{report_data['summary']}")

        summary = "\n".join(summary_parts)

        # Build details
        details = {}

        if report_data.get("top_gainers"):
            details["top_stocks"] = report_data["top_gainers"][:5]

        return await self.send_report_message(
            chat_id=chat_id,
            report_type="daily",
            title=title,
            summary=summary,
            details=details,
        )

    async def send_backtest_result(
        self,
        chat_id: str,
        result_data: dict,
    ) -> dict:
        """
        Send backtest result report.

        Args:
            chat_id: Target chat ID
            result_data: Backtest result dict

        Returns:
            API response
        """
        strategy = result_data.get("strategy_name", "Unknown")
        symbol = result_data.get("symbol", "Unknown")
        title = f"回测结果: {strategy} - {symbol}"

        summary = f"""
**策略**: {strategy}
**股票**: {symbol}
**回测周期**: {result_data.get('start_date')} 至 {result_data.get('end_date')}

**收益表现**
- 总收益率: {result_data.get('total_return', 0):.2%}
- 年化收益: {result_data.get('annual_return', 0):.2%}
- 夏普比率: {result_data.get('sharpe_ratio', 0):.2f}
- 最大回撤: {result_data.get('max_drawdown', 0):.2%}

**交易统计**
- 总交易次数: {result_data.get('total_trades', 0)}
- 胜率: {result_data.get('win_rate', 0):.2%}
- 盈亏比: {result_data.get('profit_factor', 0):.2f}
"""

        metrics = {
            "总收益": f"{result_data.get('total_return', 0):.2%}",
            "夏普比率": f"{result_data.get('sharpe_ratio', 0):.2f}",
            "最大回撤": f"{result_data.get('max_drawdown', 0):.2%}",
            "胜率": f"{result_data.get('win_rate', 0):.2%}",
        }

        return await self.send_report_message(
            chat_id=chat_id,
            report_type="backtest",
            title=title,
            summary=summary,
            details={"metrics": metrics},
        )


# Global instance
_feishu_report_sender: Optional[FeishuReportSender] = None


def get_feishu_report_sender() -> Optional[FeishuReportSender]:
    """Get or create the global Feishu report sender instance."""
    global _feishu_report_sender
    if _feishu_report_sender is None and settings.feishu_enabled:
        _feishu_report_sender = FeishuReportSender()
    return _feishu_report_sender