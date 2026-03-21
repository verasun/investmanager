#!/usr/bin/env python
"""LLM Service - Main entry point.

This service provides a unified LLM API for InvestManager,
supporting multiple providers and web search integration.

Architecture:
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Gateway   │────▶│  LLM Service │────▶│  LLM Providers   │
│   :8000     │     │   :8001      │     │  (Alibaba/etc)   │
└─────────────┘     └──────────────┘     └──────────────────┘

Registration:
This service registers its capabilities with the Gateway on startup.
"""

import argparse
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel, Field

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings
from services.llm.providers import (
    LLMProviderFactory,
    ChatRequest,
    ChatResponse,
    IntentRequest,
    IntentResponse,
)


# ============================================
# Configuration
# ============================================

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))


# ============================================
# Web Search Tool Definition
# ============================================

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "搜索互联网获取最新信息。当用户询问时事新闻、最新数据、实时信息、当前事件或需要最新资料时使用此工具。",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词，应该是简洁、准确的搜索词"
                }
            },
            "required": ["query"]
        }
    }
}


# ============================================
# Request/Response Models
# ============================================

class ChatRequestBody(BaseModel):
    """Request body for chat endpoint."""
    messages: list[dict[str, Any]]  # Support tool_calls with content=None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 800
    user_id: Optional[str] = None
    enable_web_search: bool = False
    # Multi-model support
    task_type: str = "text"  # text, deep_thinking, visual, coding
    enable_consensus: bool = False  # Force consensus mode for complex tasks
    preferred_models: list[str] = []  # Override routing with specific models


class IntentRequestBody(BaseModel):
    """Request body for intent parsing."""
    message: str
    system_prompt: Optional[str] = None


class EmbedRequestBody(BaseModel):
    """Request body for embedding."""
    texts: list[str]


class EmbeddingResponse(BaseModel):
    """Response for embedding."""
    embeddings: list[list[float]]
    model: str
    dimensions: int


class HandleRequest(BaseModel):
    """Request for handling a message (for Gateway routing)."""
    user_id: str
    chat_id: str
    message_id: str
    raw_text: str
    work_mode: str = "llm"
    trace_id: Optional[str] = None
    source: str = "feishu"
    timestamp: Optional[float] = None


class HandleResponse(BaseModel):
    """Response from handling a message."""
    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    should_reply: bool = True


class WebSearchRequest(BaseModel):
    """Request for web search."""
    query: str
    max_results: int = 5


class WebSearchResult(BaseModel):
    """Single search result."""
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    """Response from web search."""
    query: str
    results: list[WebSearchResult]
    error: Optional[str] = None


class ServiceInfo(BaseModel):
    """Service information."""
    name: str
    version: str
    provider: str
    model: str
    web_search_enabled: bool
    multi_model_enabled: bool = False


class FeedbackRequest(BaseModel):
    """Request for submitting user feedback."""
    trace_id: str
    model_id: str
    user_id: str
    message_id: str
    rating: int  # 1-5


class ImplicitFeedbackRequest(BaseModel):
    """Request for recording implicit feedback."""
    trace_id: str
    model_id: str
    signal_type: str  # reask, followup, positive_ack, ignore
    signal_value: float = 1.0


class ModelStatsResponse(BaseModel):
    """Response for model statistics."""
    models: list[dict[str, Any]]
    total_models: int


class ConsensusRequest(BaseModel):
    """Request for consensus-based chat."""
    messages: list[dict[str, Any]]
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 800
    user_id: Optional[str] = None
    preferred_models: list[str] = []  # Optional: restrict models used
    min_models: int = 3
    max_rounds: int = 3


# ============================================
# LLM Service
# ============================================

class LLMService:
    """Core LLM service logic."""

    def __init__(self):
        self._provider: Optional[Any] = None
        self._web_searcher = None
        self._web_search_enabled = settings.web_search_enabled
        self._multi_model_provider: Optional[Any] = None

    @property
    def provider(self) -> Any:
        """Get or create the LLM provider."""
        if self._provider is None:
            self._provider = self._create_provider()
        return self._provider

    @property
    def multi_model_provider(self) -> Any:
        """Get or create the multi-model provider."""
        if self._multi_model_provider is None and settings.multi_model_enabled:
            from services.llm.providers import LLMProviderFactory
            self._multi_model_provider = LLMProviderFactory.create(
                provider_type="multi_model",
                api_key=settings.alibaba_bailian_api_key,
            )
        return self._multi_model_provider

    def _create_provider(self) -> Optional[Any]:
        """Create the configured LLM provider."""
        provider_type = settings.llm_provider

        # Get API key for the provider
        if provider_type == "alibaba_bailian":
            api_key = settings.alibaba_bailian_api_key
            model = settings.alibaba_bailian_model
        elif provider_type == "openai":
            api_key = settings.openai_api_key
            model = settings.llm_model or None
        elif provider_type == "anthropic":
            api_key = settings.anthropic_api_key
            model = settings.llm_model or None
        else:
            logger.warning(f"Unknown provider type: {provider_type}")
            return None

        if not api_key:
            logger.warning(f"No API key configured for provider: {provider_type}")
            return None

        return LLMProviderFactory.create(
            provider_type=provider_type,
            api_key=api_key,
            model=model,
        )

    def _get_web_searcher(self):
        """Get or create web searcher."""
        if self._web_searcher is None and self._web_search_enabled:
            from src.web import get_web_searcher
            self._web_searcher = get_web_searcher()
        return self._web_searcher

    async def chat(self, request: ChatRequestBody) -> ChatResponse:
        """Execute chat completion, optionally with web search or consensus."""
        # Check for consensus mode
        if request.enable_consensus and settings.multi_model_enabled:
            return await self._run_consensus(request)

        # Use multi-model provider if enabled
        if settings.multi_model_enabled and self.multi_model_provider:
            return await self._chat_multi_model(request)

        # Check if provider is available
        if not self.provider:
            raise HTTPException(status_code=503, detail="LLM provider not configured")

        # Standard chat without web search
        if not request.enable_web_search or not self._web_search_enabled:
            chat_request = ChatRequest(
                messages=request.messages,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                user_id=request.user_id,
                task_type=request.task_type,
            )
            return await self.provider.chat(chat_request)

        # Chat with web search tool calling
        return await self._chat_with_web_search(request)

    async def _chat_with_web_search(self, request: ChatRequestBody) -> ChatResponse:
        """Execute chat with web search tool calling."""
        web_searcher = self._get_web_searcher()
        if not web_searcher:
            # Fallback to regular chat
            chat_request = ChatRequest(
                messages=request.messages,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            return await self.provider.chat(chat_request)

        try:
            # Try tool calling first
            chat_request = ChatRequest(
                messages=request.messages,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                tools=[WEB_SEARCH_TOOL],
                tool_choice="auto",
            )

            response = await self.provider.chat_with_tools(
                chat_request,
                [WEB_SEARCH_TOOL],
            )

            # Handle tool call if present
            if response.tool_calls:
                for tool_call in response.tool_calls:
                    if tool_call.get("function", {}).get("name") == "web_search":
                        args = json.loads(tool_call["function"]["arguments"])
                        query = args.get("query", request.messages[-1].get("content", ""))

                        logger.info(f"Web search triggered: {query}")

                        # Execute search with error handling
                        from src.web import SearchEngine
                        engine = SearchEngine(settings.web_search_engine)
                        search_result = await web_searcher.search(query, engine)

                        # Check if search failed (error or empty results)
                        if search_result.error or search_result.is_empty():
                            logger.warning(f"Web search failed or returned no results: {search_result.error or 'No results'}, generating response without search")
                            # Search failed, generate response without search results
                            chat_request = ChatRequest(
                                messages=request.messages,
                                system_prompt=request.system_prompt,
                                temperature=request.temperature,
                                max_tokens=request.max_tokens,
                            )
                            return await self.provider.chat(chat_request)

                        search_context = web_searcher.format_results_for_llm(search_result)

                        # Continue conversation with search results
                        messages = list(request.messages)
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [tool_call],
                        })
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "content": search_context,
                        })

                        final_request = ChatRequest(
                            messages=messages,
                            system_prompt=request.system_prompt,
                            temperature=request.temperature,
                            max_tokens=request.max_tokens,
                        )
                        return await self.provider.chat(final_request)

            return response

        except Exception as e:
            logger.warning(f"Tool calling failed, using keyword-based search: {e}")
            # Fallback: keyword-based search detection
            return await self._chat_with_keyword_search(request)

    async def _chat_with_keyword_search(self, request: ChatRequestBody) -> ChatResponse:
        """Chat with keyword-based web search."""
        from src.web import get_intent_detector, SearchEngine

        intent_detector = get_intent_detector()
        web_searcher = self._get_web_searcher()

        # Get last user message
        last_message = request.messages[-1].get("content", "")

        # Prepare messages (with or without search results)
        messages = request.messages

        if intent_detector.needs_search(last_message):
            intent = intent_detector.detect(last_message)
            query = intent.query or last_message

            try:
                engine = SearchEngine(settings.web_search_engine)
                search_result = await web_searcher.search(query, engine)
                search_context = web_searcher.format_results_for_llm(search_result)

                # Enrich the message with search results
                enriched_messages = list(request.messages[:-1])
                enriched_messages.append({
                    "role": "user",
                    "content": f"{last_message}\n\n[搜索结果]\n{search_context}",
                })
                messages = enriched_messages
                logger.info(f"Web search succeeded for query: {query[:50]}")
            except Exception as e:
                logger.warning(f"Web search failed, continuing without search: {e}")
                # Continue without search results

        chat_request = ChatRequest(
            messages=messages,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return await self.provider.chat(chat_request)

    async def _chat_multi_model(self, request: ChatRequestBody) -> ChatResponse:
        """Execute chat using multi-model provider with intelligent routing."""
        if not self.multi_model_provider:
            raise HTTPException(status_code=503, detail="Multi-model provider not configured")

        chat_request = ChatRequest(
            messages=request.messages,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            user_id=request.user_id,
            task_type=request.task_type,
        )

        return await self.multi_model_provider.chat(chat_request)

    async def _run_consensus(self, request: ChatRequestBody) -> ChatResponse:
        """Run consensus-based multi-model discussion."""
        from services.llm.scoring import get_model_router, TaskType
        from services.llm.consensus import get_consensus_coordinator, ConsensusConfig

        # Get participating models
        router = get_model_router()
        task_type = TaskType(request.task_type) if request.task_type in ["text", "deep_thinking", "visual", "coding"] else TaskType.DEEP_THINKING

        models, arbitrator = await router.select_consensus_models(
            task_type=task_type,
            min_models=settings.consensus_min_models,
            preferred_models=request.preferred_models if request.preferred_models else None,
        )

        # Configure consensus
        config = ConsensusConfig(
            min_models=settings.consensus_min_models,
            max_rounds=settings.consensus_max_rounds,
            timeout_seconds=settings.consensus_timeout_seconds,
        )
        coordinator = get_consensus_coordinator(config)

        # Define model execution function
        async def execute_model(model_id: str, messages: list[dict], system_prompt: Optional[str] = None) -> str:
            """Execute a single model call."""
            chat_request = ChatRequest(
                messages=messages,
                system_prompt=system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            response = await self.multi_model_provider.chat_with_specific_model(chat_request, model_id)
            return response.content

        # Run consensus
        result = await coordinator.run_consensus(
            messages=request.messages,
            models=models,
            arbitrator_model=arbitrator,
            execute_model_func=execute_model,
            system_prompt=request.system_prompt,
        )

        logger.info(
            f"Consensus completed: {result.rounds} rounds, "
            f"agreement: {result.agreement_level:.2f}, "
            f"latency: {result.total_latency_ms}ms"
        )

        return ChatResponse(
            content=result.final_response,
            model=",".join(result.participating_models),
            provider="consensus",
            usage={
                "total_tokens": result.total_tokens_used,
                "prompt_tokens": 0,
                "completion_tokens": result.total_tokens_used,
            },
        )

    async def parse_intent(self, request: IntentRequestBody) -> IntentResponse:
        """Parse intent from message."""
        if not self.provider:
            raise HTTPException(status_code=503, detail="LLM provider not configured")

        intent_request = IntentRequest(
            message=request.message,
            system_prompt=request.system_prompt,
        )

        result = await self.provider.parse_intent(intent_request)

        if not result:
            return IntentResponse(intent="unknown", confidence=0.0)

        return result

    async def web_search(self, request: WebSearchRequest) -> WebSearchResponse:
        """Execute web search."""
        if not self._web_search_enabled:
            raise HTTPException(status_code=503, detail="Web search not enabled")

        web_searcher = self._get_web_searcher()
        if not web_searcher:
            raise HTTPException(status_code=503, detail="Web searcher not available")

        from src.web import SearchEngine
        engine = SearchEngine(settings.web_search_engine)
        result = await web_searcher.search(request.query, engine, request.max_results)

        results = [
            WebSearchResult(
                title=r.title,
                url=r.url,
                snippet=r.snippet,
            )
            for r in result.results
        ]

        return WebSearchResponse(
            query=result.query,
            results=results,
            error=result.error,
        )

    def get_info(self) -> ServiceInfo:
        """Get service information."""
        return ServiceInfo(
            name="InvestManager LLM Service",
            version="1.1.0",
            provider=settings.llm_provider,
            model=settings.alibaba_bailian_model if settings.llm_provider == "alibaba_bailian"
                   else settings.llm_model or "unknown",
            web_search_enabled=self._web_search_enabled,
            multi_model_enabled=settings.multi_model_enabled,
        )

    async def get_model_stats(self) -> ModelStatsResponse:
        """Get statistics for all models."""
        if not self.multi_model_provider:
            return ModelStatsResponse(models=[], total_models=0)

        stats = await self.multi_model_provider.get_model_stats()
        return ModelStatsResponse(models=stats, total_models=len(stats))

    async def record_feedback(self, request: FeedbackRequest) -> dict:
        """Record explicit user feedback."""
        if not self.multi_model_provider:
            raise HTTPException(status_code=503, detail="Multi-model not enabled")

        await self.multi_model_provider.record_feedback(
            trace_id=request.trace_id,
            model_id=request.model_id,
            user_id=request.user_id,
            message_id=request.message_id,
            rating=request.rating,
        )

        return {
            "status": "success",
            "message": f"Recorded rating {request.rating} for model {request.model_id}",
        }

    async def record_implicit_feedback(self, request: ImplicitFeedbackRequest) -> dict:
        """Record implicit feedback signal."""
        from services.llm.scoring import get_score_manager

        score_manager = get_score_manager()

        # Calculate signal value based on type
        signal_multipliers = {
            "reask": -0.2,  # Negative: user wasn't satisfied
            "followup": 0.1,  # Positive: engaged conversation
            "positive_ack": 0.15,  # Positive: acknowledged response
            "ignore": -0.1,  # Negative: ignored response
        }

        multiplier = signal_multipliers.get(request.signal_type, 0)
        final_value = request.signal_value * multiplier

        await score_manager.record_feedback(
            trace_id=request.trace_id,
            user_id="",  # May not have user_id for implicit
            message_id="",
            model_id=request.model_id,
            feedback_type="implicit",
            signal_type=request.signal_type,
            signal_value=final_value,
        )

        return {
            "status": "success",
            "signal_type": request.signal_type,
            "signal_value": final_value,
        }


# Global service instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create the LLM service."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


# ============================================
# FastAPI Application
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting LLM Service...")

    # Initialize provider
    service = get_llm_service()
    if service.provider:
        logger.info(f"LLM provider initialized: {settings.llm_provider}")
    else:
        logger.warning("LLM provider not configured - service will return errors")

    if settings.web_search_enabled:
        logger.info(f"Web search enabled: {settings.web_search_engine}")

    # Register with Gateway
    from services.registration import ServiceRegistrar
    from services.capability_protocol import get_llm_capability

    capability = get_llm_capability()
    capability.base_url = f"http://localhost:{SERVICE_PORT}"

    registrar = ServiceRegistrar(
        gateway_url=GATEWAY_URL,
        capability=capability,
        retry_count=5,
        retry_delay=2.0,
    )

    registered = await registrar.register()
    if registered:
        logger.info("Successfully registered with Gateway")
    else:
        logger.warning("Failed to register with Gateway, continuing anyway")

    yield

    # Cleanup
    logger.info("Shutting down LLM Service...")

    # Unregister from Gateway
    await registrar.unregister()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="InvestManager LLM Service",
        description="Unified LLM API with multi-model support, intelligent routing, and consensus",
        version="1.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_routes(app)

    return app


def register_routes(app: FastAPI):
    """Register all routes."""

    @app.get("/")
    async def root():
        """Root endpoint with service info."""
        service = get_llm_service()
        return service.get_info().model_dump()

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        service = get_llm_service()
        info = service.get_info()
        return {
            "status": "healthy",
            "service": "llm",
            "provider": info.provider,
            "model": info.model,
        }

    @app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequestBody):
        """Execute chat completion.

        This is the main endpoint for LLM chat completions.
        Optionally integrates web search if enabled.
        """
        service = get_llm_service()
        return await service.chat(request)

    @app.post("/intent", response_model=IntentResponse)
    async def parse_intent(request: IntentRequestBody):
        """Parse intent from a message.

        Uses LLM to extract structured intent and parameters.
        """
        service = get_llm_service()
        return await service.parse_intent(request)

    @app.post("/search", response_model=WebSearchResponse)
    async def web_search(request: WebSearchRequest):
        """Execute web search.

        Direct web search endpoint (used internally by chat).
        """
        service = get_llm_service()
        return await service.web_search(request)

    @app.post("/embed", response_model=EmbeddingResponse)
    async def embed(request: EmbedRequestBody):
        """Generate embeddings for texts.

        Note: Currently a placeholder - requires embedding model configuration.
        """
        raise HTTPException(
            status_code=501,
            detail="Embedding not yet implemented",
        )

    @app.post("/handle", response_model=HandleResponse)
    async def handle_message(request: HandleRequest):
        """Handle a message from Gateway routing.

        This endpoint allows the LLM service to be used as a capability
        for direct user message handling.
        """
        service = get_llm_service()
        trace_id = request.trace_id or f"llm_{int(time.time() * 1000)}"

        try:
            chat_request = ChatRequestBody(
                messages=[{"role": "user", "content": request.raw_text}],
                user_id=request.user_id,
                enable_web_search=True,  # Enable web search for LLM routing
                task_type="text",
            )

            response = await service.chat(chat_request)

            return HandleResponse(
                success=True,
                message=response.content,
                data={
                    "model": response.model,
                    "provider": response.provider,
                    "trace_id": trace_id,
                },
            )

        except Exception as e:
            logger.error(f"[{trace_id}] Handle message failed: {e}")
            return HandleResponse(
                success=False,
                message=f"处理消息时出错: {str(e)}",
            )

    # ========================================
    # Multi-Model Endpoints
    # ========================================

    @app.get("/models", response_model=ModelStatsResponse)
    async def list_models():
        """List all available models with their scores.

        Returns model statistics including quality scores per capability.
        """
        service = get_llm_service()
        return await service.get_model_stats()

    @app.get("/models/{model_id}/stats")
    async def get_model_stats(model_id: str):
        """Get detailed statistics for a specific model."""
        from services.llm.scoring import get_model_registry, get_score_manager

        registry = get_model_registry()
        model = registry.get(model_id)

        if not model:
            raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

        score_manager = get_score_manager()
        scores = {}

        for cap in model.capabilities:
            score = await score_manager.get_score(model_id, cap.value)
            scores[cap.value] = score.to_dict()

        return {
            "model_id": model_id,
            "display_name": model.display_name,
            "capabilities": [c.value for c in model.capabilities],
            "scores": scores,
        }

    @app.post("/feedback")
    async def submit_feedback(request: FeedbackRequest):
        """Submit explicit user feedback (1-5 rating).

        Used to update model quality scores based on user satisfaction.
        """
        service = get_llm_service()
        return await service.record_feedback(request)

    @app.post("/feedback/implicit")
    async def submit_implicit_feedback(request: ImplicitFeedbackRequest):
        """Record implicit feedback signal.

        Signal types: reask, followup, positive_ack, ignore
        """
        service = get_llm_service()
        return await service.record_implicit_feedback(request)

    @app.post("/consensus", response_model=ChatResponse)
    async def run_consensus(request: ConsensusRequest):
        """Run consensus-based multi-model discussion.

        Uses multiple models to analyze complex tasks with
        voting and arbitrator for final decision.
        """
        chat_request = ChatRequestBody(
            messages=request.messages,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            user_id=request.user_id,
            enable_consensus=True,
            preferred_models=request.preferred_models,
            task_type="deep_thinking",
        )
        service = get_llm_service()
        return await service.chat(chat_request)


# ============================================
# Entry Point
# ============================================

def run_llm_service():
    """Run the LLM service."""
    import uvicorn

    parser = argparse.ArgumentParser(description="InvestManager LLM Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8001, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "services.llm.main:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=args.reload,
    )


if __name__ == "__main__":
    run_llm_service()