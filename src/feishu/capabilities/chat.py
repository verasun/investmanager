"""Chat capability for general conversation."""

from typing import Optional

from loguru import logger

from src.feishu.capabilities.base import Capability, CapabilityResult
from src.feishu.gateway.message_router import MessageContext


class ChatCapability(Capability):
    """Capability for general conversation.

    Handles:
    - Casual chat
    - Questions about any topic
    - Personalized interactions
    """

    @property
    def name(self) -> str:
        return "chat"

    @property
    def description(self) -> str:
        return "通用对话模式 - 可以聊任何话题"

    async def handle(self, context: MessageContext) -> CapabilityResult:
        """Handle general chat message.

        This uses the LLM with personalization but without
        investment-focused system prompts.
        """
        from src.feishu.intent_parser import get_intent_parser

        user_id = context.user_id
        text = context.raw_text

        logger.info(f"ChatCapability handling message from {user_id}: {text[:50]}...")

        parser = get_intent_parser()

        # Check for learning response first
        learning_result = await parser.handle_learning_response(user_id, text)
        if learning_result:
            return CapabilityResult(
                success=True,
                message=learning_result.get("message", "好的"),
                data={"type": "learning_response", "result": learning_result},
            )

        # Get personalized chat response (unrestricted mode)
        try:
            reply = await parser.chat(text, unrestricted=True, user_id=user_id)
            return CapabilityResult(
                success=True,
                message=reply,
                data={"type": "chat_response"},
            )
        except Exception as e:
            logger.error(f"ChatCapability error: {e}")
            return CapabilityResult(
                success=False,
                message=f"处理消息时出错: {str(e)}",
            )


# Global instance
_chat_capability: Optional[ChatCapability] = None


def get_chat_capability() -> ChatCapability:
    """Get or create the global ChatCapability instance."""
    global _chat_capability
    if _chat_capability is None:
        _chat_capability = ChatCapability()
    return _chat_capability