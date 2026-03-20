"""Alibaba Bailian (DashScope) LLM Provider.

Supports Qwen models through OpenAI-compatible API.
API Base: https://dashscope.aliyuncs.com/compatible-mode/v1
"""

import json
from typing import Optional

from loguru import logger

from .base import LLMProvider, ChatRequest, ChatResponse


class AlibabaBailianProvider(LLMProvider):
    """Alibaba Bailian (DashScope) provider for Qwen models."""

    BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @property
    def name(self) -> str:
        return "alibaba_bailian"

    @property
    def default_model(self) -> str:
        return "qwen-turbo"

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion using OpenAI-compatible API."""
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url or self.BASE_URL,
        )

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)

        response = await client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        choice = response.choices[0]

        return ChatResponse(
            content=choice.message.content or "",
            model=response.model,
            provider=self.name,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        )

    async def chat_with_tools(
        self,
        request: ChatRequest,
        tools: list[dict],
    ) -> ChatResponse:
        """Execute chat completion with tool calling support.

        Qwen models support OpenAI-compatible function calling.
        """
        import openai

        client = openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url or self.BASE_URL,
        )

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice=request.tool_choice,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except Exception as e:
            # Some Qwen models may not support tools
            logger.warning(f"Alibaba Bailian tool calling failed: {e}, falling back to regular chat")
            return await self.chat(request)

        choice = response.choices[0]
        message = choice.message

        # Extract tool calls if present
        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        return ChatResponse(
            content=message.content or "",
            model=response.model,
            provider=self.name,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            tool_calls=tool_calls,
        )