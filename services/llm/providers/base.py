"""Base module for LLM providers."""

from .base import (
    LLMProvider,
    LLMProviderFactory,
    ChatRequest,
    ChatResponse,
    IntentRequest,
    IntentResponse,
    ProviderType,
)
from .alibaba import AlibabaBailianProvider
from .openai import OpenAIProvider
from .anthropic import AnthropicProvider

__all__ = [
    "LLMProvider",
    "LLMProviderFactory",
    "ChatRequest",
    "ChatResponse",
    "IntentRequest",
    "IntentResponse",
    "ProviderType",
    "AlibabaBailianProvider",
    "OpenAIProvider",
    "AnthropicProvider",
]

# Register providers
LLMProviderFactory.register("alibaba_bailian", AlibabaBailianProvider)
LLMProviderFactory.register("openai", OpenAIProvider)
LLMProviderFactory.register("anthropic", AnthropicProvider)