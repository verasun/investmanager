"""Tests for Feishu client and bot."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.feishu.client import FeishuClient, FeishuConfig
from src.feishu.bot import CommandParser, CommandType, FeishuBot, ParsedCommand


class TestCommandParser:
    """Test cases for CommandParser."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = CommandParser()

    def test_parse_collect_data_command(self):
        """Test parsing collect data command."""
        command = self.parser.parse("收集数据 600519", {"user_id": "user1"})
        assert command.command_type == CommandType.COLLECT_DATA
        assert command.params["symbols"] == ["600519"]

    def test_parse_collect_data_multiple_symbols(self):
        """Test parsing collect data with multiple symbols."""
        command = self.parser.parse("收集数据 600519 000001", {"user_id": "user1"})
        assert command.command_type == CommandType.COLLECT_DATA
        assert command.params["symbols"] == ["600519", "000001"]

    def test_parse_analyze_command(self):
        """Test parsing analyze command."""
        command = self.parser.parse("分析 600519", {"user_id": "user1"})
        assert command.command_type == CommandType.ANALYZE
        assert command.params["symbol"] == "600519"

    def test_parse_backtest_command(self):
        """Test parsing backtest command."""
        command = self.parser.parse("回测 momentum 600519", {"user_id": "user1"})
        assert command.command_type == CommandType.BACKTEST
        assert command.params["strategy"] == "momentum"
        assert command.params["symbol"] == "600519"

    def test_parse_generate_report_command(self):
        """Test parsing generate report command."""
        command = self.parser.parse("生成报告 daily", {"user_id": "user1"})
        assert command.command_type == CommandType.GENERATE_REPORT
        assert command.params["report_type"] == "daily"

    def test_parse_generate_report_default(self):
        """Test parsing generate report with default type."""
        command = self.parser.parse("生成报告", {"user_id": "user1"})
        assert command.command_type == CommandType.GENERATE_REPORT
        assert command.params["report_type"] == "daily"

    def test_parse_send_report_command(self):
        """Test parsing send report command."""
        command = self.parser.parse("发送报告 test@example.com", {"user_id": "user1"})
        assert command.command_type == CommandType.SEND_REPORT
        assert command.params["destination"] == "test@example.com"

    def test_parse_task_status_command(self):
        """Test parsing task status command."""
        command = self.parser.parse("任务状态 task123", {"user_id": "user1"})
        assert command.command_type == CommandType.TASK_STATUS
        assert command.params["task_id"] == "task123"

    def test_parse_help_command(self):
        """Test parsing help command."""
        for text in ["帮助", "help", "?"]:
            command = self.parser.parse(text, {"user_id": "user1"})
            assert command.command_type == CommandType.HELP

    def test_parse_unknown_command(self):
        """Test parsing unknown command."""
        command = self.parser.parse("random text", {"user_id": "user1"})
        assert command.command_type == CommandType.UNKNOWN

    def test_parse_english_commands(self):
        """Test parsing English commands."""
        # Collect data
        command = self.parser.parse("collect 600519", {"user_id": "user1"})
        assert command.command_type == CommandType.COLLECT_DATA

        # Analyze
        command = self.parser.parse("analyze 600519", {"user_id": "user1"})
        assert command.command_type == CommandType.ANALYZE

        # Backtest
        command = self.parser.parse("backtest momentum 600519", {"user_id": "user1"})
        assert command.command_type == CommandType.BACKTEST


class TestFeishuBot:
    """Test cases for FeishuBot."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Feishu client."""
        client = MagicMock(spec=FeishuClient)
        client.send_text_message = AsyncMock(return_value={"code": 0})
        client.send_card_message = AsyncMock(return_value={"code": 0})
        client.reply_message = AsyncMock(return_value={"code": 0})
        client.get_access_token = AsyncMock(return_value="test_token")
        return client

    @pytest.fixture
    def bot(self, mock_client):
        """Create a FeishuBot with mock client."""
        return FeishuBot(client=mock_client)

    @pytest.mark.asyncio
    async def test_handle_url_verification(self, bot):
        """Test handling URL verification event."""
        event = {
            "type": "url_verification",
            "challenge": "test_challenge",
        }

        result = await bot.handle_event(event)
        assert result == {"challenge": "test_challenge"}

    @pytest.mark.asyncio
    async def test_handle_help_command(self, bot, mock_client):
        """Test handling help command."""
        event = {
            "type": "im.message.receive_v1",
            "event": {
                "message": {
                    "message_id": "msg123",
                    "chat_id": "chat123",
                    "sender": {"sender_id": {"user_id": "user123"}},
                    "content": json.dumps({"text": "帮助"}),
                }
            },
        }

        result = await bot.handle_event(event)
        assert result == {"status": "ok"}
        mock_client.reply_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_message_with_handler(self, bot, mock_client):
        """Test handling message with registered handler."""
        handler_called = False

        async def mock_handler(command):
            nonlocal handler_called
            handler_called = True
            return "Handler result"

        bot.register_command_handler(CommandType.COLLECT_DATA, mock_handler)

        event = {
            "type": "im.message.receive_v1",
            "event": {
                "message": {
                    "message_id": "msg123",
                    "chat_id": "chat123",
                    "sender": {"sender_id": {"user_id": "user123"}},
                    "content": json.dumps({"text": "收集数据 600519"}),
                }
            },
        }

        result = await bot.handle_event(event)
        assert result == {"status": "ok"}
        assert handler_called


class TestFeishuClient:
    """Test cases for FeishuClient."""

    @pytest.fixture
    def client(self):
        """Create a FeishuClient with test credentials."""
        return FeishuClient(
            app_id="test_app_id",
            app_secret="test_app_secret",
        )

    def test_config(self, client):
        """Test client configuration."""
        assert client._config.app_id == "test_app_id"
        assert client._config.app_secret == "test_app_secret"

    def test_verify_event_signature_no_key(self, client):
        """Test signature verification with no key."""
        # Should return True when no key is configured
        result = client.verify_event_signature("timestamp", "nonce", "body", "sig")
        assert result is True