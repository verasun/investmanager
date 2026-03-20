"""InvestManager Services Package.

This package contains the multi-process services:
- gateway: Webhook handler and message router
- llm: Unified LLM API with web search
- invest: Investment analysis capability
- chat: General conversation with personalization
- dev: Development mode with Claude Code
"""

__all__ = [
    "gateway",
    "llm",
    "invest",
    "chat",
    "dev",
]