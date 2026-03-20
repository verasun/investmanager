"""LLM Provider abstraction layer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class ProviderType(str, Enum):
    """Supported LLM providers."""
    ALIBABA_BAILIAN = "alibaba_bailian"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ChatRequest(BaseModel):
    """Request for LLM chat completion."""
    messages: list[dict[str, str]]
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 800
    user_id: Optional[str] = None
    tools: Optional[list[dict]] = None
    tool_choice: str = "auto"


class ChatResponse(BaseModel):
    """Response from LLM chat completion."""
    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    tool_calls: Optional[list[dict]] = None


class IntentRequest(BaseModel):
    """Request for intent parsing."""
    message: str
    system_prompt: Optional[str] = None


class IntentResponse(BaseModel):
    """Response from intent parsing."""
    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    explanation: Optional[str] = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key
        self.model = model or self.default_model
        self.base_url = base_url

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider."""
        pass

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion."""
        pass

    @abstractmethod
    async def chat_with_tools(
        self,
        request: ChatRequest,
        tools: list[dict],
    ) -> ChatResponse:
        """Execute chat completion with tool calling support."""
        pass

    async def parse_intent(
        self,
        request: IntentRequest,
    ) -> Optional[IntentResponse]:
        """Parse intent from message.

        Default implementation uses chat completion.
        Override for provider-specific implementations.
        """
        import json
        from loguru import logger

        system_prompt = request.system_prompt or self._default_intent_prompt()

        chat_request = ChatRequest(
            messages=[{"role": "user", "content": request.message}],
            system_prompt=system_prompt,
            temperature=0.0,
            max_tokens=500,
        )

        response = await self.chat(chat_request)

        # Parse JSON from response
        try:
            content = response.content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            data = json.loads(content)
            return IntentResponse(
                intent=data.get("intent", "unknown"),
                params=data.get("params", {}),
                confidence=data.get("confidence", 0.0),
                explanation=data.get("explanation"),
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse intent JSON: {e}")
            return None

    def _default_intent_prompt(self) -> str:
        """Default system prompt for intent parsing."""
        return """你是一个股票分析机器人的指令解析器。分析用户消息，提取用户意图和参数。

支持的意图类型：
- collect_data: 收集股票数据
- analyze: 单独分析股票（仅技术分析）
- backtest: 单独策略回测
- comprehensive: 组合指令，串行执行完整分析流程
- mode_switch: 切换工作模式
- mode_status: 查询当前模式
- report: 生成报告
- status: 查询任务状态
- help: 获取帮助
- unknown: 无法识别

请以JSON格式返回：
{
  "intent": "意图类型",
  "params": {
    "symbols": ["股票代码列表"],
    "strategy": "策略名",
    "days": 天数数字
  },
  "confidence": 0.0-1.0的置信度,
  "explanation": "简短解释"
}

注意：
1. 股票代码通常是6位数字，如600519、000001
2. 策略名可能是：ma、均线、momentum、macd等
3. 只返回JSON，不要其他内容"""


class LLMProviderFactory:
    """Factory for creating LLM providers."""

    _providers: dict[str, type[LLMProvider]] = {}

    @classmethod
    def register(cls, name: str, provider_class: type[LLMProvider]):
        """Register a provider class."""
        cls._providers[name] = provider_class

    @classmethod
    def create(
        cls,
        provider_type: str,
        api_key: str,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Optional[LLMProvider]:
        """Create a provider instance."""
        provider_class = cls._providers.get(provider_type)
        if not provider_class:
            return None
        return provider_class(api_key=api_key, model=model, base_url=base_url)

    @classmethod
    def available_providers(cls) -> list[str]:
        """List available provider types."""
        return list(cls._providers.keys())