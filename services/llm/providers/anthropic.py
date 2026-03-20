"""Anthropic LLM Provider."""

from typing import Optional

from .base import LLMProvider, ChatRequest, ChatResponse


class AnthropicProvider(LLMProvider):
    """Anthropic provider for Claude models."""

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return "claude-3-haiku-20240307"

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat completion."""
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        # Anthropic uses separate system parameter
        response = await client.messages.create(
            model=self.model,
            max_tokens=request.max_tokens,
            system=request.system_prompt,
            messages=request.messages,
        )

        # Extract text content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return ChatResponse(
            content=content,
            model=response.model,
            provider=self.name,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
        )

    async def chat_with_tools(
        self,
        request: ChatRequest,
        tools: list[dict],
    ) -> ChatResponse:
        """Execute chat completion with tool calling support.

        Anthropic supports tool use through the tools parameter.
        """
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self.api_key)

        # Convert tools to Anthropic format
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object"}),
                })

        response = await client.messages.create(
            model=self.model,
            max_tokens=request.max_tokens,
            system=request.system_prompt,
            messages=request.messages,
            tools=anthropic_tools if anthropic_tools else None,
        )

        # Extract content and tool use blocks
        content = ""
        tool_calls = []

        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
            elif hasattr(block, "type") and block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "tool_use",
                    "function": {
                        "name": block.name,
                        "arguments": block.input,
                    },
                })

        return ChatResponse(
            content=content,
            model=response.model,
            provider=self.name,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            tool_calls=tool_calls if tool_calls else None,
        )