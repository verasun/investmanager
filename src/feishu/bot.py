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
    COMPREHENSIVE = "comprehensive"  # 组合指令：串行执行完整分析流程
    MODE_SWITCH = "mode_switch"  # 切换工作模式
    MODE_STATUS = "mode_status"  # 查询当前模式
    PROFILE_VIEW = "profile_view"  # 查看用户画像
    PROFILE_CLEAR = "profile_clear"  # 清除用户记忆
    HELP = "help"
    UNKNOWN = "unknown"


# 工作模式
class WorkMode(str, Enum):
    """Work modes for the bot."""

    INVEST = "invest"  # 投资助手模式
    CHAT = "chat"  # 通用对话模式
    STRICT = "strict"  # 严格模式


# 用户模式存储
_user_modes: dict[str, str] = {}  # {user_id: mode}

# 模式名称映射
MODE_NAMES = {
    WorkMode.INVEST: "投资助手",
    WorkMode.CHAT: "通用对话",
    WorkMode.STRICT: "严格模式",
}


def get_user_mode(user_id: str) -> str:
    """Get user's current work mode."""
    return _user_modes.get(user_id, WorkMode.INVEST)


def set_user_mode(user_id: str, mode: str) -> None:
    """Set user's work mode."""
    _user_modes[user_id] = mode


def cycle_user_mode(user_id: str) -> str:
    """Cycle to next mode for user."""
    current = _user_modes.get(user_id, WorkMode.INVEST)
    modes = [WorkMode.INVEST, WorkMode.CHAT, WorkMode.STRICT]
    current_idx = modes.index(current)
    next_mode = modes[(current_idx + 1) % len(modes)]
    _user_modes[user_id] = next_mode
    return next_mode


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
            r"回测\s+(\S+)\s+(\S+)(?:\s+(\d+))?(?:\s+(\d{4}-\d{2}-\d{2})\s+(\d{4}-\d{2}-\d{2}))?",
            r"backtest\s+(\S+)\s+(.+?)(?:\s+(\d+d))?$",
        ],
        CommandType.COMPREHENSIVE: [
            r"综合分析\s+(.+)",
            r"完整分析\s+(.+)",
            r"深度评估\s+(.+)",
            r"全部分析\s+(.+)",
        ],
        CommandType.MODE_SWITCH: [
            r"切换模式",
            r"切换到投资模式",
            r"切换到对话模式",
            r"切换到严格模式",
            r"切换到chat模式",
            r"切换到invest模式",
            r"切换到strict模式",
        ],
        CommandType.MODE_STATUS: [
            r"当前模式",
            r"什么模式",
            r"查看模式",
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
        CommandType.PROFILE_VIEW: [
            r"我的画像",
            r"查看画像",
            r"个人资料",
            r"我的偏好",
        ],
        CommandType.PROFILE_CLEAR: [
            r"清除记忆",
            r"清空记忆",
            r"重置画像",
            r"忘记我",
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
  回测 <策略名> <股票代码> [天数]  - 运行回测
  策略: ma, momentum, 均线 (买入持有)
  天数: 默认365天，可指定如730(2年)、1095(3年)
  例: 回测 ma 600519
  例: 回测 ma 600519 730

📋 报告生成:
  生成报告 [类型]  - 生成分析报告
  类型: daily, weekly, monthly
  例: 生成报告 daily

📧 发送报告:
  发送报告 <邮箱/飞书>  - 发送最新报告

📝 任务状态:
  任务状态 <任务ID>  - 查询任务执行状态

🔄 工作模式:
  切换模式  - 切换工作模式
  当前模式  - 查看当前模式

👤 个人设置:
  我的画像  - 查看您的偏好设置
  清除记忆  - 清除您的个人信息

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
            params = {
                "strategy": match.group(1).strip(),
                "symbol": match.group(2).strip(),
            }
            # Check for days parameter
            if match.group(3):
                params["days"] = int(match.group(3))
            # Check for date range parameters
            if match.group(4) and match.group(5):
                params["start_date"] = match.group(4)
                params["end_date"] = match.group(5)
            return params
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

        # Extract sender ID - prefer open_id (most reliable), fallback to user_id/union_id
        sender = message.get("sender", {})
        sender_id = sender.get("sender_id", {})
        user_id = (
            sender_id.get("open_id") or
            sender_id.get("user_id") or
            sender_id.get("union_id") or
            ""
        )
        sender_type = sender.get("sender_type", "unknown")

        # Debug log the actual message structure
        logger.debug(f"Message sender info: sender_id={sender_id}, sender_type={sender_type}")

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

        # Get user's current mode
        user_mode = _user_modes.get(user_id, WorkMode.INVEST)
        logger.info(f"User {user_id} mode: {user_mode}")

        command = self._parser.parse(text, context)
        logger.info(f"Parsed command: {command.command_type} from {user_id}")

        # Handle help command directly
        if command.command_type == CommandType.HELP:
            await self._client.reply_message(message_id, self._parser.HELP_TEXT)
            return {"status": "ok"}

        # CHAT mode: Direct LLM conversation with personalization
        if user_mode == WorkMode.CHAT and command.command_type == CommandType.UNKNOWN:
            from src.feishu.intent_parser import get_intent_parser
            parser = get_intent_parser()

            # Check for learning response first
            learning_result = await parser.handle_learning_response(user_id, text)
            if learning_result:
                await self._client.reply_message(message_id, learning_result.get("message", "好的"))
                return {"status": "ok"}

            # Personalized chat with user_id
            reply = await parser.chat(text, unrestricted=True, user_id=user_id)
            await self._client.reply_message(message_id, reply)
            return {"status": "ok"}

        # STRICT mode: Only respond to commands, show help for unknown
        if user_mode == WorkMode.STRICT and command.command_type == CommandType.UNKNOWN:
            command = await self._try_intent_parsing(text, context, message_id, strict=True)
            if command is None:
                return {"status": "ok"}
        elif command.command_type == CommandType.UNKNOWN:
            # INVEST mode: Try intent parsing, then LLM chat
            command = await self._try_intent_parsing(text, context, message_id, strict=False)
            if command is None:
                return {"status": "ok"}

        # Execute handler if registered
        handler = self._parser._handlers.get(command.command_type)
        if handler:
            try:
                result = await handler(command)
                logger.info(f"Command handler result: {result}")
                if result:
                    reply_content = json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result)
                    logger.info(f"Sending reply: {reply_content}")
                    await self._client.reply_message(
                        message_id,
                        reply_content,
                    )
                    logger.info("Reply sent successfully")
            except Exception as e:
                logger.error(f"Command handler error: {e}")
                await self._client.reply_message(
                    message_id,
                    f"命令执行失败: {str(e)}",
                )
        else:
            await self._send_help_card(message_id)

        return {"status": "ok"}

    async def _try_intent_parsing(
        self,
        text: str,
        context: dict,
        message_id: str,
        strict: bool = False,
    ) -> Optional[ParsedCommand]:
        """Try to parse intent using LLM when regex fails.

        Args:
            text: User message text
            context: Context dict with user_id, chat_id, message_id
            message_id: Message ID for reply
            strict: If True, show help card for unknown instead of LLM chat

        Returns:
            ParsedCommand or None
        """
        from src.feishu.intent_parser import get_intent_parser

        parser = get_intent_parser()
        intent, params, confidence = await parser.parse(text)

        # Map intent to command type
        intent_map = {
            "collect_data": CommandType.COLLECT_DATA,
            "analyze": CommandType.ANALYZE,
            "backtest": CommandType.BACKTEST,
            "comprehensive": CommandType.COMPREHENSIVE,
            "mode_switch": CommandType.MODE_SWITCH,
            "mode_status": CommandType.MODE_STATUS,
            "profile_view": CommandType.PROFILE_VIEW,
            "profile_clear": CommandType.PROFILE_CLEAR,
            "report": CommandType.GENERATE_REPORT,
            "status": CommandType.TASK_STATUS,
            "help": CommandType.HELP,
        }

        command_type = intent_map.get(intent, CommandType.UNKNOWN)

        # Handle mode commands
        if command_type in (CommandType.MODE_SWITCH, CommandType.MODE_STATUS):
            logger.info(f"LLM parsed mode command: {command_type}")
            return ParsedCommand(
                command_type=command_type,
                params=params,
                raw_text=text,
                user_id=context.get("user_id", ""),
                chat_id=context.get("chat_id", ""),
                message_id=context.get("message_id", ""),
            )

        # If not a valid command
        if confidence < 0.5 or command_type == CommandType.UNKNOWN:
            if strict:
                # STRICT mode: Show help card
                logger.info(f"Strict mode: showing help card for unknown intent")
                await self._send_help_card(message_id)
            else:
                # INVEST mode: LLM chat response with personalization
                logger.info(f"Unknown intent or low confidence, using LLM chat")
                user_id = context.get("user_id", "")

                # Check for learning response first
                learning_result = await parser.handle_learning_response(user_id, text)
                if learning_result:
                    await self._client.reply_message(message_id, learning_result.get("message", "好的"))
                    return None

                reply = await parser.chat(text, user_id=user_id)
                await self._client.reply_message(message_id, reply)
            return None

        logger.info(f"LLM parsed command: {command_type} with params: {params}")

        return ParsedCommand(
            command_type=command_type,
            params=params,
            raw_text=text,
            user_id=context.get("user_id", ""),
            chat_id=context.get("chat_id", ""),
            message_id=context.get("message_id", ""),
        )

    async def _send_help_card(self, message_id: str) -> None:
        """Send interactive help card."""
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🤖 InvestManager 助手"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "抱歉，我没有理解您的意思。请选择您想要执行的操作：",
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📊 收集数据"},
                            "type": "primary",
                            "value": {"action": "collect"},
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📈 分析股票"},
                            "type": "default",
                            "value": {"action": "analyze"},
                        },
                    ],
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🔄 策略回测"},
                            "type": "default",
                            "value": {"action": "backtest"},
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "❓ 帮助"},
                            "type": "default",
                            "value": {"action": "help"},
                        },
                    ],
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**💡 示例命令：**\n"
                        "• 收集600519的数据\n"
                        "• 帮我分析一下平安银行\n"
                        "• 用均线策略回测茅台，2年\n"
                        "• 今天行情怎么样",
                    },
                },
            ],
        }

        await self._client.reply_message(
            message_id,
            json.dumps(card),
            msg_type="interactive",
        )

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