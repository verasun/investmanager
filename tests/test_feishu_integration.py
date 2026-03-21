#!/usr/bin/env python
"""Feishu Integration Tests for InvestManager.

This script tests Feishu webhook message handling:
1. Help commands (帮助, 帮助 xxx, 快速开始, 引导, 小技巧, 常见问题)
2. Mode switching commands (切换模式, 当前模式, 使用xxx模块)
3. Intent routing (股票分析, 日常聊天, 代码开发)
4. Message deduplication
5. Error handling

Usage:
    python tests/test_feishu_integration.py

Note: These tests use mock message_id, so Feishu API calls will fail.
      The tests verify that the Gateway handles messages correctly and
      returns proper responses, not that Feishu messages are actually sent.
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configuration
GATEWAY_URL = "http://localhost:8000"

# Test results
results = {"passed": 0, "failed": 0, "tests": []}


def log_test(name: str, passed: bool, message: str = ""):
    """Log test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status}: {name}")
    if message:
        print(f"         {message}")
    results["tests"].append({"name": name, "passed": passed, "message": message})
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1


def make_feishu_event(event_id: str, user_id: str, message_id: str, text: str) -> dict:
    """Create a Feishu webhook event payload."""
    return {
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1"
        },
        "event": {
            "sender": {
                "sender_id": {
                    "open_id": user_id
                }
            },
            "message": {
                "message_id": message_id,
                "chat_id": "oc_test_chat",
                "content": json.dumps({"text": text})
            }
        }
    }


async def test_help_commands(client: httpx.AsyncClient):
    """Test help command handling."""
    print("\n=== Testing Help Commands ===")

    help_commands = [
        ("帮助", "显示帮助菜单"),
        ("帮助 invest_guide", "显示投资指南"),
        ("帮助 stock_analysis", "显示股票分析帮助"),
        ("帮助 chat_guide", "显示对话指南"),
        ("帮助 dev_guide", "显示开发指南"),
        ("帮助 mode_switch", "显示模式切换说明"),
        ("帮助 不存在的主题", "搜索帮助"),
        ("快速开始", "快速开始教程"),
        ("引导", "功能引导"),
        ("小技巧", "快速提示"),
        ("常见问题", "FAQ"),
    ]

    for command, description in help_commands:
        try:
            event = make_feishu_event(
                event_id=f"help_{command}_{hash(command)}",
                user_id="ou_help_test",
                message_id=f"msg_help_{hash(command)}",
                text=command
            )
            response = await client.post(
                f"{GATEWAY_URL}/api/feishu/webhook",
                json=event,
            )
            data = response.json()
            is_ok = data.get("status") == "ok" and response.status_code == 200
            log_test(f"帮助命令: {command}", is_ok, description)

        except Exception as e:
            log_test(f"帮助命令: {command}", False, str(e))


async def test_mode_commands(client: httpx.AsyncClient):
    """Test mode switching commands."""
    print("\n=== Testing Mode Commands ===")

    mode_commands = [
        ("当前模式", "查询当前模式"),
        ("切换模式", "循环切换模式"),
        ("切换到投资模式", "切换到invest"),
        ("切换到对话模式", "切换到chat"),
        ("切换到开发模式", "切换到dev"),
        ("使用 invest 模块", "强制使用invest模块"),
        ("使用 chat 模块", "强制使用chat模块"),
    ]

    for command, description in mode_commands:
        try:
            event = make_feishu_event(
                event_id=f"mode_{hash(command)}",
                user_id="ou_mode_test",
                message_id=f"msg_mode_{hash(command)}",
                text=command
            )
            response = await client.post(
                f"{GATEWAY_URL}/api/feishu/webhook",
                json=event,
            )
            data = response.json()
            is_ok = data.get("status") == "ok" and response.status_code == 200
            log_test(f"模式命令: {command}", is_ok, description)

        except Exception as e:
            log_test(f"模式命令: {command}", False, str(e))


async def test_intent_routing(client: httpx.AsyncClient):
    """Test intent-based message routing."""
    print("\n=== Testing Intent Routing ===")

    messages = [
        ("分析茅台股票", "invest", "股票分析"),
        ("今天天气怎么样", "chat", "日常聊天"),
        ("帮我写一个函数", "dev", "代码开发"),
        ("600519股价如何", "invest", "股票查询"),
        ("你好", "chat", "简单问候"),
    ]

    for text, expected_service, description in messages:
        try:
            event = make_feishu_event(
                event_id=f"intent_{hash(text)}",
                user_id="ou_intent_test",
                message_id=f"msg_intent_{hash(text)}",
                text=text
            )
            response = await client.post(
                f"{GATEWAY_URL}/api/feishu/webhook",
                json=event,
            )
            data = response.json()
            is_ok = data.get("status") == "ok" and response.status_code == 200
            log_test(f"意图路由: {description}", is_ok, f"消息: {text[:20]}...")

        except Exception as e:
            log_test(f"意图路由: {description}", False, str(e))


async def test_message_deduplication(client: httpx.AsyncClient):
    """Test message deduplication."""
    print("\n=== Testing Message Deduplication ===")

    event = make_feishu_event(
        event_id="dedup_test_001",
        user_id="ou_dedup_test",
        message_id="msg_dedup_same",  # Same message ID
        text="测试消息去重"
    )

    try:
        # First request - should be processed
        response1 = await client.post(
            f"{GATEWAY_URL}/api/feishu/webhook",
            json=event,
        )
        data1 = response1.json()

        # Second request with same message_id - should be detected as duplicate
        response2 = await client.post(
            f"{GATEWAY_URL}/api/feishu/webhook",
            json=event,
        )
        data2 = response2.json()

        # First should be "ok", second should be "duplicate"
        first_ok = data1.get("status") == "ok"
        second_dup = data2.get("status") == "duplicate"

        log_test("首次消息处理", first_ok)
        log_test("重复消息检测", second_dup, "相同message_id应返回duplicate")

    except Exception as e:
        log_test("消息去重测试", False, str(e))


async def test_empty_and_invalid(client: httpx.AsyncClient):
    """Test empty and invalid messages."""
    print("\n=== Testing Empty and Invalid Messages ===")

    test_cases = [
        # Empty text
        ({
            "header": {"event_id": "empty_001", "event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_empty"}},
                "message": {
                    "message_id": "msg_empty_001",
                    "chat_id": "oc_test",
                    "content": json.dumps({"text": ""})
                }
            }
        }, "空消息", "ok"),

        # Missing content
        ({
            "header": {"event_id": "missing_001", "event_type": "im.message.receive_v1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou_missing"}},
                "message": {
                    "message_id": "msg_missing_001",
                    "chat_id": "oc_test",
                    "content": "{}"
                }
            }
        }, "缺少内容", "ok"),

        # Invalid event type
        ({
            "header": {"event_id": "invalid_001", "event_type": "unknown.event"},
            "event": {}
        }, "未知事件类型", "ignored"),
    ]

    for event, description, expected_status in test_cases:
        try:
            response = await client.post(
                f"{GATEWAY_URL}/api/feishu/webhook",
                json=event,
            )
            data = response.json()
            is_ok = data.get("status") == expected_status
            log_test(f"边缘情况: {description}", is_ok, f"期望: {expected_status}")

        except Exception as e:
            log_test(f"边缘情况: {description}", False, str(e))


async def test_forced_mode_integration(client: httpx.AsyncClient):
    """Test forced mode with Feishu messages."""
    print("\n=== Testing Forced Mode Integration ===")

    user_id = "ou_forced_test"

    try:
        # Set forced mode via API
        response = await client.post(
            f"{GATEWAY_URL}/forced-mode",
            json={"user_id": user_id, "service_id": "invest"},
        )
        data = response.json()
        log_test("设置强制模式", data.get("success"), data.get("message", ""))

        # Send message that would normally go to chat
        event = make_feishu_event(
            event_id="forced_test_001",
            user_id=user_id,
            message_id="msg_forced_001",
            text="今天天气怎么样"  # Normally goes to chat
        )
        response = await client.post(
            f"{GATEWAY_URL}/api/feishu/webhook",
            json=event,
        )
        data = response.json()
        log_test("强制模式下消息处理", data.get("status") == "ok")

        # Clear forced mode
        response = await client.delete(f"{GATEWAY_URL}/forced-mode/{user_id}")
        data = response.json()
        log_test("清除强制模式", data.get("cleared", False))

    except Exception as e:
        log_test("强制模式集成测试", False, str(e))


async def test_new_user_help_tip(client: httpx.AsyncClient):
    """Test that new users get help tips."""
    print("\n=== Testing New User Help Tip ===")

    # Use a unique user ID that hasn't been seen before
    import uuid
    new_user_id = f"ou_new_user_{uuid.uuid4().hex[:8]}"

    try:
        event = make_feishu_event(
            event_id=f"new_user_{uuid.uuid4().hex[:8]}",
            user_id=new_user_id,
            message_id=f"msg_new_{uuid.uuid4().hex[:8]}",
            text="你好"  # Simple greeting
        )
        response = await client.post(
            f"{GATEWAY_URL}/api/feishu/webhook",
            json=event,
        )
        data = response.json()
        log_test("新用户消息处理", data.get("status") == "ok", "新用户应收到帮助提示")

    except Exception as e:
        log_test("新用户帮助提示测试", False, str(e))


async def run_tests():
    """Run all tests."""
    print("=" * 60)
    print("  InvestManager Feishu Integration Tests")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # First check gateway health
        try:
            response = await client.get(f"{GATEWAY_URL}/health")
            if response.status_code != 200:
                print("Gateway is not healthy, aborting tests")
                return False
        except Exception as e:
            print(f"Cannot connect to gateway: {e}")
            return False

        await test_help_commands(client)
        await test_mode_commands(client)
        await test_intent_routing(client)
        await test_message_deduplication(client)
        await test_empty_and_invalid(client)
        await test_forced_mode_integration(client)
        await test_new_user_help_tip(client)

    # Summary
    print("\n" + "=" * 60)
    print(f"  Results: {results['passed']} passed, {results['failed']} failed")
    print("=" * 60)

    # List failed tests
    if results["failed"] > 0:
        print("\nFailed tests:")
        for test in results["tests"]:
            if not test["passed"]:
                print(f"  - {test['name']}: {test['message']}")

    return results["failed"] == 0


if __name__ == "__main__":
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)