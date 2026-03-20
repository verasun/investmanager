"""Message router for dispatching messages to appropriate capabilities."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional

from loguru import logger


class WorkMode(str, Enum):
    """Work modes for the bot."""

    INVEST = "invest"  # 投资助手模式
    CHAT = "chat"  # 通用对话模式
    DEV = "dev"  # 开发模式 (替代原有的 STRICT)


# Mode names for display
MODE_NAMES = {
    WorkMode.INVEST: "投资助手",
    WorkMode.CHAT: "通用对话",
    WorkMode.DEV: "开发模式",
}


@dataclass
class MessageContext:
    """Context for processing a message."""

    user_id: str
    chat_id: str
    message_id: str
    raw_text: str
    work_mode: str = "invest"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_invest_mode(self) -> bool:
        """Check if in invest mode."""
        return self.work_mode == WorkMode.INVEST

    @property
    def is_chat_mode(self) -> bool:
        """Check if in chat mode."""
        return self.work_mode == WorkMode.CHAT

    @property
    def is_dev_mode(self) -> bool:
        """Check if in dev mode."""
        return self.work_mode == WorkMode.DEV


@dataclass
class CapabilityResult:
    """Result from a capability handler."""

    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    should_reply: bool = True


class MessageRouter:
    """Router for dispatching messages to appropriate capabilities."""

    def __init__(self):
        """Initialize message router."""
        self._capabilities: dict[str, Callable] = {}
        self._initialized = False

    def register_capability(self, mode: str, handler: Callable) -> None:
        """Register a capability handler for a mode.

        Args:
            mode: Work mode name
            handler: Async function that handles MessageContext -> CapabilityResult
        """
        self._capabilities[mode] = handler
        logger.info(f"Registered capability for mode: {mode}")

    async def get_user_mode(self, user_id: str) -> str:
        """Get user's current work mode from persistent storage.

        Args:
            user_id: User's unique identifier

        Returns:
            Current work mode string
        """
        try:
            from src.memory import get_profile_manager

            profile_manager = get_profile_manager()
            return await profile_manager.get_work_mode(user_id)
        except Exception as e:
            logger.warning(f"Failed to get user mode: {e}, defaulting to invest")
            return WorkMode.INVEST

    async def set_user_mode(self, user_id: str, mode: str) -> None:
        """Set user's work mode in persistent storage.

        Args:
            user_id: User's unique identifier
            mode: Target work mode
        """
        try:
            from src.memory import get_profile_manager

            profile_manager = get_profile_manager()
            await profile_manager.set_work_mode(user_id, mode)
            logger.info(f"Set user {user_id} mode to: {mode}")
        except Exception as e:
            logger.error(f"Failed to set user mode: {e}")
            raise

    async def cycle_user_mode(self, user_id: str) -> str:
        """Cycle to next work mode for user.

        Args:
            user_id: User's unique identifier

        Returns:
            New work mode string
        """
        try:
            from src.memory import get_profile_manager

            profile_manager = get_profile_manager()
            new_mode, _ = await profile_manager.cycle_work_mode(user_id)
            logger.info(f"Cycled user {user_id} mode to: {new_mode}")
            return new_mode
        except Exception as e:
            logger.error(f"Failed to cycle user mode: {e}")
            raise

    async def route(self, context: MessageContext) -> CapabilityResult:
        """Route message to appropriate capability.

        Args:
            context: Message context with all relevant info

        Returns:
            CapabilityResult from the handler
        """
        mode = context.work_mode
        handler = self._capabilities.get(mode)

        if not handler:
            logger.warning(f"No handler registered for mode: {mode}")
            return CapabilityResult(
                success=False,
                message=f"未找到模式 {mode} 的处理器",
            )

        try:
            result = await handler(context)
            return result
        except Exception as e:
            logger.error(f"Capability handler error: {e}")
            return CapabilityResult(
                success=False,
                message=f"处理失败: {str(e)}",
            )

    def get_mode_name(self, mode: str) -> str:
        """Get display name for a mode."""
        try:
            return MODE_NAMES.get(WorkMode(mode), mode)
        except ValueError:
            return mode


# Global instance
_message_router: Optional[MessageRouter] = None


def get_message_router() -> MessageRouter:
    """Get or create the global message router instance."""
    global _message_router
    if _message_router is None:
        _message_router = MessageRouter()
    return _message_router