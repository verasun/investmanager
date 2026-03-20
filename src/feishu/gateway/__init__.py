"""Gateway layer for message routing and mode dispatch."""

from src.feishu.gateway.message_router import (
    MessageRouter,
    MessageContext,
    WorkMode,
    MODE_NAMES,
    get_message_router,
)

__all__ = [
    "MessageRouter",
    "MessageContext",
    "WorkMode",
    "MODE_NAMES",
    "get_message_router",
]