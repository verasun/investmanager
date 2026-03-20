"""LLM Service - Unified LLM API for InvestManager.

This service provides a unified interface for multiple LLM providers,
handling chat completions, intent parsing, and web search integration.

Architecture:
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Gateway   │────▶│  LLM Service │────▶│  LLM Providers   │
│   :8000     │     │   :8001      │     │  (Alibaba/etc)   │
└─────────────┘     └──────────────┘     └──────────────────┘
"""

from .main import create_app, run_llm_service
from .providers import (
    LLMProvider,
    LLMProviderFactory,
    ChatRequest,
    ChatResponse,
    IntentRequest,
    IntentResponse,
)

__all__ = [
    "create_app",
    "run_llm_service",
    "LLMProvider",
    "LLMProviderFactory",
    "ChatRequest",
    "ChatResponse",
    "IntentRequest",
    "IntentResponse",
]