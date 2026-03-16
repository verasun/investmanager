"""Feishu bot for event handling and command processing."""

import asyncio
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from loguru import logger

from config.settings import settings
from src.feishu.client import FeishuClient, get_feishu_client


class CommandType(str, Enum):
    """Supported command types."""

    COLLECT_DATA = "collect_data"
    ANALYZE = "analyze"
    BACKTEST = "backtest"
    GENERATE_REPORT = "generate_report"
    SEND_REPORT = "send_report"
    TASK_STATUS = "task_status"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class ParsedCommand:
    """Parsed command result."""

    command_type: CommandType
    params: dict[str, Any]
    raw_text: str
    user_id: str
    chat_id: str
    message_id: str


class CommandParser:
    """Parser for Feishu bot commands."""

    COMMAND_PATTERNS = {
        CommandType.COLLECT_DATA: [
            r"收集数据\s+(.+)",
            r"collect\s+(.+)",
            r"获取数据\s+(.+)",
        ],
        CommandType.ANALYZE: [
            r"分析\s+(.+)",
            r"analyze\s+(.+)",
        ],
        CommandType.BACKTEST: [
            r"回测\s+(\S+)\s+(.+)",
            r"backtest\s+(\S+)\s+(.+)",
        ],
        CommandType.GENERATE_REPORT: [
            r"生成报告\s*(\S*)",
            r"report\s*(\S*)",
        ],
        CommandType.SEND_REPORT: [
            r"发送报告\s+(.+)",
            r"send\s+(.+)",
        ],
        CommandType.TASK_STATUS: [
            r"任务状态\s+(.+)",
            r"status\s+(.+)",
        ],
        CommandType.HELP: [
            r"帮助",
            r"help",
            r"\?",
        ],
    }

    HELP_TEXT = """
📈 InvestManager 机器人使用指南

可用命令:

📊 数据收集:
  收集数据 <股票代码>  - 收集指定股票数据
  例: 收集数据 600519

📈 数据分析:
  分析 <股票代码>  - 分析指定股票
  例: 分析 600519

🔄 策略回测:
  回测 <策略名> <股票代码>  - 运行回测
  例: 回测 momentum 600519

📋 报告生成:
  生成报告 [类型]  - 生成分析报告
  类型: daily, weekly, monthly
  例: 生成报告 daily

📧 发送报告:
  发送报告 <邮箱/飞书>  - 发送最新报告

📝 任务状态:
  任务状态 <任务ID>  - 查询任务执行状态

❓ 帮助:
  帮助  - 显示此帮助信息
""".strip()

    def __init__(self):
        """Initialize command parser."""
        self._handlers: dict[CommandType, Callable] = {}

    def register_handler(
        self,
        command_type: CommandType,
        handler: Callable,
    ) -> None:
        """
        Register a command handler.

        Args:
            command_type: Command type to handle
            handler: Async function to handle command
        """
        self._handlers[command_type] = handler

    def parse(self, text: str, context: dict) -> ParsedCommand:
        """
        Parse command text.

        Args:
            text: Message text
            context: Message context (user_id, chat_id, etc.)

        Returns:
            ParsedCommand with type and params
        """
        import re

        text = text.strip()
        command_type = CommandType.UNKNOWN
        params: dict[str, Any] = {}

        # Check each command pattern
        for cmd_type, patterns in self.COMMAND_PATTERNS.items():
            for pattern in patterns:
                match = re.match(pattern, text, re.IGNORECASE)
                if match:
                    command_type = cmd_type
                    params = self._extract_params(cmd_type, match)
                    break
            if command_type != CommandType.UNKNOWN:
                break

        return ParsedCommand(
            command_type=command_type,
            params=params,
            raw_text=text,
            user_id=context.get("user_id", ""),
            chat_id=context.get("chat_id", ""),
            message_id=context.get("message_id", ""),
        )

    def _extract_params(
        self,
        command_type: CommandType,
        match: Any,
    ) -> dict[str, Any]:
        """Extract parameters from regex match."""
        if command_type == CommandType.COLLECT_DATA:
            return {"symbols": match.group(1).split()}
        elif command_type == CommandType.ANALYZE:
            return {"symbol": match.group(1).strip()}
        elif command_type == CommandType.BACKTEST:
            return {
                "strategy": match.group(1).strip(),
                "symbol": match.group(2).strip(),
            }
        elif command_type == CommandType.GENERATE_REPORT:
            report_type = match.group(1).strip() if match.group(1) else "daily"
            return {"report_type": report_type}
        elif command_type == CommandType.SEND_REPORT:
            return {"destination": match.group(1).strip()}
        elif command_type == CommandType.TASK_STATUS:
            return {"task_id": match.group(1).strip()}
        else:
            return {}


class FeishuBot:
    """Feishu bot for handling events and commands."""

    def __init__(self, client: Optional[FeishuClient] = None):
        """
        Initialize Feishu bot.

        Args:
            client: FeishuClient instance
        """
        self._client = client or get_feishu_client()
        self._parser = CommandParser()
        self._running = False

    def register_command_handler(
        self,
        command_type: CommandType,
        handler: Callable,
    ) -> None:
        """Register a handler for a command type."""
        self._parser.register_handler(command_type, handler)

    async def handle_event(self, event: dict) -> Optional[dict]:
        """
        Handle Feishu event.

        Args:
            event: Event data from Feishu webhook

        Returns:
            Response dict or None
        """
        event_type = event.get("type") or event.get("header", {}).get("event_type")

        if event_type == "url_verification":
            # Handle URL verification challenge
            return {"challenge": event.get("challenge")}

        if event_type == "im.message.receive_v1":
            return await self._handle_message_event(event)

        logger.warning(f"Unhandled event type: {event_type}")
        return None

    async def _handle_message_event(self, event: dict) -> Optional[dict]:
        """Handle incoming message event."""
        event_data = event.get("event", {})
        message = event_data.get("message", {})

        # Extract message info
        message_id = message.get("message_id")
        chat_id = message.get("chat_id")
        user_id = message.get("sender", {}).get("sender_id", {}).get("user_id", "")

        # Parse message content
        content = message.get("content", "{}")
        if isinstance(content, str):
            content = json.loads(content)

        text = content.get("text", "")
        if not text:
            return None

        # Parse command
        context = {
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
        }

        command = self._parser.parse(text, context)
        logger.info(f"Parsed command: {command.command_type} from {user_id}")

        # Handle help command directly
        if command.command_type == CommandType.HELP:
            await self._client.reply_message(message_id, self._parser.HELP_TEXT)
            return {"status": "ok"}

        # Execute handler if registered
        handler = self._parser._handlers.get(command.command_type)
        if handler:
            try:
                result = await handler(command)
                if result:
                    await self._client.reply_message(
                        message_id,
                        json.dumps(result) if isinstance(result, dict) else str(result),
                    )
            except Exception as e:
                logger.error(f"Command handler error: {e}")
                await self._client.reply_message(
                    message_id,
                    f"命令执行失败: {str(e)}",
                )
        else:
            await self._client.reply_message(
                message_id,
                "未识别的命令。发送 '帮助' 查看可用命令。",
            )

        return {"status": "ok"}

    async def send_notification(
        self,
        chat_id: str,
        title: str,
        content: str,
    ) -> dict:
        """
        Send notification to a chat.

        Args:
            chat_id: Target chat ID
            title: Message title
            content: Message content

        Returns:
            API response
        """
        return await self._client.send_markdown_message(
            chat_id,
            "chat_id",
            title,
            content,
        )

    async def send_report_card(
        self,
        chat_id: str,
        report_title: str,
        summary: str,
        details: Optional[dict] = None,
    ) -> dict:
        """
        Send report as interactive card.

        Args:
            chat_id: Target chat ID
            report_title: Report title
            summary: Report summary
            details: Additional details

        Returns:
            API response
        """
        elements = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": summary,
                },
            }
        ]

        if details:
            for key, value in details.items():
                elements.append({
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**{key}**\n{value}",
                            },
                        }
                    ],
                })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": report_title,
                },
                "template": "blue",
            },
            "elements": elements,
        }

        return await self._client.send_card_message(chat_id, "chat_id", card)


# Global bot instance
_feishu_bot: Optional[FeishuBot] = None


def get_feishu_bot() -> Optional[FeishuBot]:
    """Get or create the global Feishu bot instance."""
    global _feishu_bot
    if _feishu_bot is None and settings.feishu_enabled:
        _feishu_bot = FeishuBot()
        logger.info("Feishu bot initialized")
    return _feishu_bot