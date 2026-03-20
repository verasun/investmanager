#!/usr/bin/env python
"""LLM Service - Main entry point.

This service provides a unified LLM API for InvestManager,
supporting multiple providers and web search integration.

Architecture:
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Gateway   │────▶│  LLM Service │────▶│  LLM Providers   │
│   :8000     │     │   :8001      │     │  (Alibaba/etc)   │
└─────────────┘     └──────────────┘     └──────────────────┘
"""

import argparse
import json
import os
import sys
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
    messages: list[dict[str, str]]
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 800
    user_id: Optional[str] = None
    enable_web_search: bool = False


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


# ============================================
# LLM Service
# ============================================

class LLMService:
    """Core LLM service logic."""

    def __init__(self):
        self._provider: Optional[Any] = None
        self._web_searcher = None
        self._web_search_enabled = settings.web_search_enabled

    @property
    def provider(self) -> Any:
        """Get or create the LLM provider."""
        if self._provider is None:
            self._provider = self._create_provider()
        return self._provider

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
        """Execute chat completion, optionally with web search."""
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

                        # Execute search
                        from src.web import SearchEngine
                        engine = SearchEngine(settings.web_search_engine)
                        search_result = await web_searcher.search(query, engine)
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

        if intent_detector.needs_search(last_message):
            intent = intent_detector.detect(last_message)
            query = intent.query or last_message

            engine = SearchEngine(settings.web_search_engine)
            search_result = await web_searcher.search(query, engine)
            search_context = web_searcher.format_results_for_llm(search_result)

            # Enrich the message with search results
            enriched_messages = list(request.messages[:-1])
            enriched_messages.append({
                "role": "user",
                "content": f"{last_message}\n\n[搜索结果]\n{search_context}",
            })

            chat_request = ChatRequest(
                messages=enriched_messages,
                system_prompt=request.system_prompt,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            return await self.provider.chat(chat_request)

        # No search needed
        chat_request = ChatRequest(
            messages=request.messages,
            system_prompt=request.system_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return await self.provider.chat(chat_request)

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
            version="1.0.0",
            provider=settings.llm_provider,
            model=settings.alibaba_bailian_model if settings.llm_provider == "alibaba_bailian"
                   else settings.llm_model or "unknown",
            web_search_enabled=self._web_search_enabled,
        )


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

    yield

    logger.info("Shutting down LLM Service...")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="InvestManager LLM Service",
        description="Unified LLM API for InvestManager",
        version="1.0.0",
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