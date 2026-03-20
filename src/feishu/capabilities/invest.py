"""Investment capability for stock analysis and investment advice."""

from typing import Any, Optional

from loguru import logger

from src.feishu.capabilities.base import Capability, CapabilityResult
from src.feishu.gateway.message_router import MessageContext


class InvestCapability(Capability):
    """Capability for investment-focused interactions.

    Handles:
    - Stock analysis commands
    - Portfolio discussions
    - Market insights
    - Investment advice
    """

    @property
    def name(self) -> str:
        return "invest"

    @property
    def description(self) -> str:
        return "投资助手模式 - 专注股票分析和投资建议"

    async def handle(self, context: MessageContext) -> CapabilityResult:
        """Handle investment-focused message.

        This delegates to:
        1. Command handlers for structured commands
        2. LLM chat for natural language queries about stocks/investments
        """
        from src.feishu.intent_parser import get_intent_parser

        user_id = context.user_id
        text = context.raw_text

        logger.info(f"InvestCapability handling message from {user_id}: {text[:50]}...")

        # Try to parse intent using LLM
        parser = get_intent_parser()

        # Check for learning response first
        learning_result = await parser.handle_learning_response(user_id, text)
        if learning_result:
            return CapabilityResult(
                success=True,
                message=learning_result.get("message", "好的"),
                data={"type": "learning_response", "result": learning_result},
            )

        # Get personalized chat response (investment-focused)
        try:
            reply = await parser.chat(text, unrestricted=False, user_id=user_id)
            return CapabilityResult(
                success=True,
                message=reply,
                data={"type": "chat_response"},
            )
        except Exception as e:
            logger.error(f"InvestCapability error: {e}")
            return CapabilityResult(
                success=False,
                message=f"处理消息时出错: {str(e)}",
            )

    async def handle_command(
        self,
        command_type: str,
        params: dict[str, Any],
        context: MessageContext,
    ) -> CapabilityResult:
        """Handle a structured command.

        Args:
            command_type: Type of command (e.g., 'analyze', 'backtest')
            params: Command parameters
            context: Message context

        Returns:
            CapabilityResult
        """
        # Command handling is done by handlers.py, this is just for
        # future extensibility if we want capability-specific command handling
        return CapabilityResult(
            success=True,
            message="Command received",
            data={"command_type": command_type, "params": params},
        )


# Global instance
_invest_capability: Optional[InvestCapability] = None


def get_invest_capability() -> InvestCapability:
    """Get or create the global InvestCapability instance."""
    global _invest_capability
    if _invest_capability is None:
        _invest_capability = InvestCapability()
    return _invest_capability