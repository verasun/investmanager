"""Base capability class for work mode handlers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from src.feishu.gateway.message_router import MessageContext


@dataclass
class CapabilityResult:
    """Result from a capability handler."""

    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    should_reply: bool = True


class Capability(ABC):
    """Abstract base class for capability handlers.

    Each capability represents a work mode and handles
    messages in its specific way.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the capability name (should match work mode)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a short description of this capability."""
        pass

    @abstractmethod
    async def handle(self, context: MessageContext) -> CapabilityResult:
        """Handle an incoming message.

        Args:
            context: Message context with all relevant info

        Returns:
            CapabilityResult with response info
        """
        pass

    async def initialize(self) -> None:
        """Initialize the capability (optional override)."""
        pass

    async def shutdown(self) -> None:
        """Cleanup when shutting down (optional override)."""
        pass