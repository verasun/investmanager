"""Multi-model provider with intelligent routing.

Supports dynamic model selection based on task type and performance scores.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional
from loguru import logger
import openai

from . import LLMProvider, ChatRequest, ChatResponse
from ..scoring import (
    ModelRouter,
    TaskType,
    get_model_router,
    get_score_manager,
    get_model_registry,
)
from ..scoring.score_manager import ExecutionRecord


@dataclass
class MultiModelConfig:
    """Configuration for multi-model provider."""
    api_key: str
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    default_task_type: TaskType = TaskType.TEXT
    enable_scoring: bool = True
    fallback_enabled: bool = True


class MultiModelProvider(LLMProvider):
    """Provider that supports multiple models with intelligent routing."""

    def __init__(
        self,
        api_key: str,
        model: Optional[str] = None,  # Ignored - we use dynamic model selection
        base_url: Optional[str] = None,
        config: Optional[MultiModelConfig] = None,
        router: Optional[ModelRouter] = None,
    ):
        self.config = config or MultiModelConfig(
            api_key=api_key,
            base_url=base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.router = router or get_model_router()
        self.score_manager = get_score_manager()
        self.registry = get_model_registry()
        self._clients: dict[str, openai.AsyncOpenAI] = {}
        self._lock = asyncio.Lock()
        # Store api_key and base_url for parent class compatibility
        self.api_key = api_key
        self.base_url = base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @property
    def name(self) -> str:
        return "multi_model"

    @property
    def default_model(self) -> str:
        return "qwen3.5-plus"  # Default fallback

    def _get_client(self, model_id: str) -> openai.AsyncOpenAI:
        """Get or create client for a model."""
        if model_id not in self._clients:
            self._clients[model_id] = openai.AsyncOpenAI(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
        return self._clients[model_id]

    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Execute chat with intelligent model selection."""
        # Determine task type from request metadata
        task_type_str = getattr(request, "task_type", "text")
        task_type = TaskType(task_type_str) if task_type_str in [t.value for t in TaskType] else TaskType.TEXT

        # Select best model
        decision = await self.router.select_model(task_type)
        model_id = decision.selected_model

        logger.info(f"Selected model {model_id} for {task_type.value} task (score: {decision.score:.3f})")

        # Execute with fallback support
        if self.config.fallback_enabled and decision.alternatives:
            return await self._chat_with_fallback(request, model_id, decision.alternatives, task_type)
        else:
            return await self._execute_chat(request, model_id, task_type)

    async def _chat_with_fallback(
        self,
        request: ChatRequest,
        primary_model: str,
        fallback_models: list[str],
        task_type: TaskType,
    ) -> ChatResponse:
        """Execute chat with fallback to alternative models."""
        try:
            return await self._execute_chat(request, primary_model, task_type)
        except Exception as e:
            logger.warning(f"Primary model {primary_model} failed: {e}")

            # Try fallback models
            for fallback in fallback_models:
                try:
                    logger.info(f"Trying fallback model: {fallback}")
                    return await self._execute_chat(request, fallback, task_type)
                except Exception as fe:
                    logger.warning(f"Fallback model {fallback} also failed: {fe}")

            # All models failed
            raise RuntimeError(f"All models failed for {task_type.value} task")

    async def _execute_chat(
        self,
        request: ChatRequest,
        model_id: str,
        task_type: TaskType,
    ) -> ChatResponse:
        """Execute a chat request and record metrics."""
        trace_id = getattr(request, "trace_id", f"chat_{int(time.time() * 1000)}")
        start_time = time.time()

        client = self._get_client(model_id)

        # Build messages
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)

        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            choice = response.choices[0]

            # Record execution for scoring
            if self.config.enable_scoring:
                await self._record_execution(
                    trace_id=trace_id,
                    model_id=model_id,
                    task_type=task_type,
                    latency_ms=latency_ms,
                    tokens_used=response.usage.total_tokens if response.usage else 0,
                    success=True,
                )

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

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)

            # Record failure
            if self.config.enable_scoring:
                await self._record_execution(
                    trace_id=trace_id,
                    model_id=model_id,
                    task_type=task_type,
                    latency_ms=latency_ms,
                    tokens_used=0,
                    success=False,
                )

            raise

    async def _record_execution(
        self,
        trace_id: str,
        model_id: str,
        task_type: TaskType,
        latency_ms: int,
        tokens_used: int,
        success: bool,
    ):
        """Record execution for scoring."""
        try:
            record = ExecutionRecord(
                trace_id=trace_id,
                model_id=model_id,
                scenario=task_type.value,
                task_type=task_type.value,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                success=success,
            )
            await self.score_manager.record_execution(record)
        except Exception as e:
            logger.warning(f"Failed to record execution: {e}")

    async def chat_with_tools(
        self,
        request: ChatRequest,
        tools: list[dict],
    ) -> ChatResponse:
        """Execute chat with tool calling support."""
        # Determine task type
        task_type_str = getattr(request, "task_type", "text")
        task_type = TaskType(task_type_str) if task_type_str in [t.value for t in TaskType] else TaskType.TEXT

        # Select model
        decision = await self.router.select_model(task_type)
        model_id = decision.selected_model

        client = self._get_client(model_id)

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.extend(request.messages)

        try:
            response = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                tools=tools,
                tool_choice=request.tool_choice,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
        except Exception as e:
            logger.warning(f"Tool calling failed with {model_id}: {e}, falling back to regular chat")
            return await self._execute_chat(request, model_id, task_type)

        choice = response.choices[0]
        message = choice.message

        # Extract tool calls
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

    async def chat_with_specific_model(
        self,
        request: ChatRequest,
        model_id: str,
    ) -> ChatResponse:
        """Execute chat with a specific model (bypasses routing)."""
        task_type_str = getattr(request, "task_type", "text")
        task_type = TaskType(task_type_str) if task_type_str in [t.value for t in TaskType] else TaskType.TEXT
        return await self._execute_chat(request, model_id, task_type)

    async def record_feedback(
        self,
        trace_id: str,
        model_id: str,
        user_id: str,
        message_id: str,
        rating: int,  # 1-5
    ):
        """Record explicit user feedback."""
        await self.score_manager.record_feedback(
            trace_id=trace_id,
            user_id=user_id,
            message_id=message_id,
            model_id=model_id,
            feedback_type="explicit",
            rating=rating,
        )

        # Update model score
        current = await self.score_manager.get_score(model_id, "text")
        # Recalculate with new feedback
        # This will be incorporated on next execution record

    async def get_model_stats(self) -> list[dict]:
        """Get statistics for all models."""
        models = self.registry.get_all()
        stats = []

        for model in models:
            model_stats = {
                "model_id": model.model_id,
                "display_name": model.display_name,
                "capabilities": [c.value for c in model.capabilities],
                "scores": {},
            }

            # Get scores for each capability
            for cap in model.capabilities:
                score = await self.score_manager.get_score(model.model_id, cap.value)
                model_stats["scores"][cap.value] = score.to_dict()

            stats.append(model_stats)

        return stats