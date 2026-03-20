"""Capability layer for handling different work modes."""

from src.feishu.capabilities.base import (
    Capability,
    CapabilityResult,
)
from src.feishu.capabilities.invest import InvestCapability
from src.feishu.capabilities.chat import ChatCapability
from src.feishu.capabilities.dev import DevCapability

__all__ = [
    "Capability",
    "CapabilityResult",
    "InvestCapability",
    "ChatCapability",
    "DevCapability",
]