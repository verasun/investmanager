#!/usr/bin/env python
"""Gateway Service - Main entry point.

This service acts as the entry point for Feishu messages,
routing them to the appropriate capability service based on
intent parsing, and proxying LLM requests.

Architecture:
┌─────────────────────────────────────────────────────────────────────────┐
│                              GATEWAY (:8000)                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────────┐ │
│  │  Registry   │  │ Intent      │  │  LLM        │  │  Capability   │ │
│  │  Manager    │  │ Router      │  │  Proxy      │  │  Router       │ │
│  └─────────────┘  └─────────────┘  └─────────────┘  └───────────────┘ │
│         ▲                │                                 │           │
│         │                ▼                                 ▼           │
│  ┌──────┴──────┐  ┌─────────────┐                  ┌───────────────┐  │
│  │  Service    │  │ LLM Service │                  │ Capability    │  │
│  │  Registry   │  │   :8001     │                  │ Services      │  │
│  └─────────────┘  └─────────────┘                  └───────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
         ▲                                                       ▲
         │ REGISTER                                               │ HANDLE
         │                                                        │
┌────────┴────────┐  ┌────────────────┐  ┌────────────────┐  ┌────┴───────┐
│ Invest Service  │  │  Chat Service  │  │  Dev Service   │  │  Future    │
│    :8010        │  │    :8011       │  │    :8012       │  │  Services  │
└─────────────────┘  └────────────────┘  └────────────────┘  └────────────┘
"""

import argparse
import asyncio
import json
import os
import sys
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings
from services.capability_protocol import (
    CapabilityInfo,
    RegisterRequest,
    RegisterResponse,
    UnregisterRequest,
    UnregisterResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    ForcedModeRequest,
    ForcedModeResponse,
    ServiceListResponse,
    CapabilityListResponse,
    IntentParseRequest,
    IntentParseResponse,
)
from services.gateway.help_system import get_help_manager, HelpCategory


# ============================================
# Message Deduplication
# ============================================

class MessageDeduplicator:
    """LRU cache for message deduplication to prevent duplicate processing."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def is_duplicate(self, message_id: str) -> bool:
        """Check if message was already processed."""
        # Clean up expired entries
        self._cleanup()

        if message_id in self._cache:
            # Move to end (most recently accessed)
            self._cache.move_to_end(message_id)
            return True
        return False

    def mark_processed(self, message_id: str):
        """Mark message as processed."""
        if message_id in self._cache:
            self._cache.move_to_end(message_id)
        else:
            self._cache[message_id] = asyncio.get_event_loop().time()
            # Evict oldest if over capacity
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def _cleanup(self):
        """Remove expired entries."""
        current_time = asyncio.get_event_loop().time()
        expired = [
            msg_id for msg_id, timestamp in self._cache.items()
            if current_time - timestamp > self._ttl_seconds
        ]
        for msg_id in expired:
            del self._cache[msg_id]


# Global deduplicator instance
_message_deduplicator = MessageDeduplicator()


# ============================================
# Configuration
# ============================================

# Capability Service URLs (direct routing)
INVEST_SERVICE_URL = os.getenv(
    "INVEST_SERVICE_URL",
    "http://localhost:8010"
)

CHAT_SERVICE_URL = os.getenv(
    "CHAT_SERVICE_URL",
    "http://localhost:8011"
)

DEV_SERVICE_URL = os.getenv(
    "DEV_SERVICE_URL",
    "http://localhost:8012"
)

# Map of mode to service URL
CAPABILITY_URLS = {
    "invest": INVEST_SERVICE_URL,
    "chat": CHAT_SERVICE_URL,
    "dev": DEV_SERVICE_URL,
}

# Legacy capability service URL (for backwards compatibility)
CAPABILITY_SERVICE_URL = os.getenv(
    "CAPABILITY_SERVICE_URL",
    INVEST_SERVICE_URL  # Default to Invest service
)

LLM_SERVICE_URL = os.getenv(
    "LLM_SERVICE_URL",
    "http://localhost:8001"
)

# Service API key for internal service authentication
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")


# ============================================
# Models
# ============================================

class MessageContext(BaseModel):
    """Context for processing a message."""
    user_id: str
    chat_id: str
    message_id: str
    raw_text: str
    work_mode: str = "invest"
    # 链路追踪字段
    trace_id: Optional[str] = None  # 链路追踪ID
    source: str = "feishu"          # 请求来源
    timestamp: Optional[float] = None  # 请求时间戳(unix ms)


class RouteRequest(BaseModel):
    """Request to route a message."""
    context: MessageContext


class RouteResponse(BaseModel):
    """Response from routing a message."""
    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    should_reply: bool = True


class ModeResponse(BaseModel):
    """Response for mode operations."""
    status: str
    message: str
    mode: Optional[str] = None
    mode_name: Optional[str] = None


# LLM Proxy Models

class LLMChatRequest(BaseModel):
    """Request for LLM chat via proxy."""
    messages: list[dict[str, str]]
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 800
    user_id: Optional[str] = None
    enable_web_search: bool = False


class LLMIntentRequest(BaseModel):
    """Request for LLM intent parsing via proxy."""
    message: str
    system_prompt: Optional[str] = None


class LLMSearchRequest(BaseModel):
    """Request for web search via proxy."""
    query: str
    max_results: int = 5


# ============================================
# HTTP Clients
# ============================================

class ServiceClient:
    """Base client for internal service communication."""

    def __init__(self, base_url: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["X-Service-Key"] = self.api_key
            self._client = httpx.AsyncClient(timeout=60.0, headers=headers)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


class CapabilityClient:
    """Client for communicating with capability services using registry."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["X-Service-Key"] = self.api_key
            self._client = httpx.AsyncClient(timeout=60.0, headers=headers)
        return self._client

    async def _get_service_url(self, service_id: str) -> str:
        """Get service URL from registry."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        service = registry.get_service(service_id)
        if service:
            return service.base_url
        raise RuntimeError(f"Service '{service_id}' not registered")

    async def handle_message(self, context: MessageContext) -> RouteResponse:
        """Route message to appropriate capability service based on mode."""
        from services.gateway.registry import get_registry_manager

        mode = context.work_mode
        try:
            base_url = await self._get_service_url(mode)
            client = await self._get_client()
            response = await client.post(
                f"{base_url}/handle",
                json=context.model_dump(),
            )
            data = response.json()
            return RouteResponse(**data)
        except RuntimeError as e:
            logger.error(f"Service {mode} unavailable: {e}")
            return RouteResponse(
                success=False,
                message=f"服务暂时不可用，请稍后重试",
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to call {mode} capability service: {e}")
            return RouteResponse(
                success=False,
                message=f"能力服务调用失败: {str(e)}",
            )

    async def get_mode(self, user_id: str) -> str:
        """Get user's work mode from persistent storage."""
        try:
            from src.memory import get_profile_manager
            profile_manager = get_profile_manager()
            return await profile_manager.get_work_mode(user_id)
        except Exception as e:
            logger.warning(f"Failed to get user mode: {e}, defaulting to invest")
            return "invest"

    async def set_mode(self, user_id: str, mode: str) -> ModeResponse:
        """Set user's work mode in persistent storage."""
        MODE_NAMES = {
            "invest": "投资助手",
            "chat": "通用对话",
            "dev": "开发模式",
        }

        valid_modes = {"invest", "chat", "dev"}
        if mode not in valid_modes:
            return ModeResponse(
                status="error",
                message=f"无效模式: {mode}",
            )

        try:
            from src.memory import get_profile_manager
            profile_manager = get_profile_manager()
            await profile_manager.set_work_mode(user_id, mode)

            mode_name = MODE_NAMES.get(mode, mode)
            logger.info(f"Set user {user_id} mode to: {mode}")

            return ModeResponse(
                status="success",
                message=f"已切换到「{mode_name}」模式",
                mode=mode,
                mode_name=mode_name,
            )
        except Exception as e:
            logger.error(f"Failed to set user mode: {e}")
            return ModeResponse(
                status="error",
                message=f"设置模式失败: {str(e)}",
            )

    async def cycle_mode(self, user_id: str) -> ModeResponse:
        """Cycle to next work mode for user."""
        try:
            from src.memory import get_profile_manager
            profile_manager = get_profile_manager()
            new_mode, _ = await profile_manager.cycle_work_mode(user_id)

            MODE_NAMES = {
                "invest": "投资助手",
                "chat": "通用对话",
                "dev": "开发模式",
            }
            mode_name = MODE_NAMES.get(new_mode, new_mode)
            logger.info(f"Cycled user {user_id} mode to: {new_mode}")

            return ModeResponse(
                status="success",
                message=f"已切换到「{mode_name}」模式",
                mode=new_mode,
                mode_name=mode_name,
            )
        except Exception as e:
            logger.error(f"Failed to cycle user mode: {e}")
            return ModeResponse(
                status="error",
                message=f"切换模式失败: {str(e)}",
            )


class LLMProxyClient:
    """Client for proxying requests to LLM service with retry support."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def _get_service_url(self) -> str:
        """Get LLM service URL from registry."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        service = registry.get_service("llm")
        if service:
            return service.base_url
        raise RuntimeError("Service 'llm' not registered")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def chat(self, request: LLMChatRequest) -> dict:
        """Proxy chat request to LLM service."""
        try:
            base_url = await self._get_service_url()
            client = await self._get_client()
            response = await client.post(
                f"{base_url}/chat",
                json=request.model_dump(),
            )
            response.raise_for_status()
            return response.json()
        except RuntimeError as e:
            logger.error(f"LLM proxy chat failed: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"LLM service unavailable: {str(e)}",
            )
        except httpx.HTTPError as e:
            logger.error(f"LLM proxy chat failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"LLM service error: {str(e)}",
            )

    async def parse_intent(self, request: LLMIntentRequest) -> dict:
        """Proxy intent parsing request to LLM service."""
        try:
            base_url = await self._get_service_url()
            client = await self._get_client()
            response = await client.post(
                f"{base_url}/intent",
                json=request.model_dump(),
            )
            response.raise_for_status()
            return response.json()
        except RuntimeError as e:
            logger.error(f"LLM proxy intent failed: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"LLM service unavailable: {str(e)}",
            )
        except httpx.HTTPError as e:
            logger.error(f"LLM proxy intent failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"LLM service error: {str(e)}",
            )

    async def search(self, request: LLMSearchRequest) -> dict:
        """Proxy search request to LLM service."""
        try:
            base_url = await self._get_service_url()
            client = await self._get_client()
            response = await client.post(
                f"{base_url}/search",
                json=request.model_dump(),
            )
            response.raise_for_status()
            return response.json()
        except RuntimeError as e:
            logger.error(f"LLM proxy search failed: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"LLM service unavailable: {str(e)}",
            )
        except httpx.HTTPError as e:
            logger.error(f"LLM proxy search failed: {e}")
            raise HTTPException(
                status_code=502,
                detail=f"LLM service error: {str(e)}",
            )


# Global clients (lazy initialization)
_capability_client: Optional[CapabilityClient] = None
_llm_proxy_client: Optional[LLMProxyClient] = None


def get_capability_client() -> CapabilityClient:
    """Get or create the capability client."""
    global _capability_client
    if _capability_client is None:
        _capability_client = CapabilityClient(SERVICE_API_KEY)
    return _capability_client


def get_llm_proxy_client() -> LLMProxyClient:
    """Get or create the LLM proxy client."""
    global _llm_proxy_client
    if _llm_proxy_client is None:
        _llm_proxy_client = LLMProxyClient()
    return _llm_proxy_client


# ============================================
# Service Authentication
# ============================================

def verify_service_key(x_service_key: Optional[str] = None) -> bool:
    """Verify service API key for internal requests.

    Returns True if authentication passes or is not required.
    """
    if not SERVICE_API_KEY:
        # No API key configured, allow all internal requests
        return True

    if not x_service_key:
        return False

    return x_service_key == SERVICE_API_KEY


# ============================================
# Feishu Bot Integration
# ============================================

class CommandType:
    """Supported command types."""
    MODE_SWITCH = "mode_switch"
    MODE_STATUS = "mode_status"
    HELP = "help"
    HELP_TOPIC = "help_topic"
    GUIDE = "guide"
    QUICK_START = "quick_start"
    TIPS = "tips"
    FAQ = "faq"


def parse_command(text: str) -> tuple[str, dict[str, Any]]:
    """Parse command from text.

    Returns:
        Tuple of (command_type, params)
    """
    import re
    text_lower = text.strip().lower()
    text_original = text.strip()

    # Mode switch patterns
    if re.match(r"切换模式", text_lower):
        return CommandType.MODE_SWITCH, {}
    if re.match(r"切换到投资模式", text_lower) or re.match(r"切换到invest", text_lower):
        return CommandType.MODE_SWITCH, {"target_mode": "invest"}
    if re.match(r"切换到对话模式", text_lower) or re.match(r"切换到chat", text_lower):
        return CommandType.MODE_SWITCH, {"target_mode": "chat"}
    if re.match(r"切换到开发模式", text_lower) or re.match(r"切换到dev", text_lower):
        return CommandType.MODE_SWITCH, {"target_mode": "dev"}

    # Mode status
    if re.match(r"当前模式", text_lower) or re.match(r"什么模式", text_lower):
        return CommandType.MODE_STATUS, {}

    # Help with topic: 帮助 xxx
    help_match = re.match(r"帮助\s+(.+)", text_lower)
    if help_match:
        return CommandType.HELP_TOPIC, {"topic": help_match.group(1).strip()}

    # Quick start guide
    if re.match(r"快速开始|新手引导|入门", text_lower):
        return CommandType.QUICK_START, {}

    # Interactive guide
    if re.match(r"引导|功能引导|功能介绍", text_lower):
        return CommandType.GUIDE, {}

    # Tips
    if re.match(r"小技巧|提示|技巧", text_lower):
        return CommandType.TIPS, {}

    # FAQ
    if re.match(r"常见问题|faq|问题列表", text_lower):
        return CommandType.FAQ, {}

    # Help
    if re.match(r"帮助|help|\?", text_lower):
        return CommandType.HELP, {}

    return "unknown", {}


HELP_TEXT = """
📈 InvestManager 机器人使用指南

🔄 工作模式:
  切换模式  - 切换工作模式
  当前模式  - 查看当前模式

📊 投资分析 (INVEST模式):
  综合分析 <股票代码>  - 完整分析流程

💬 通用对话 (CHAT模式):
  可以和我聊任何话题

💻 开发模式 (DEV模式):
  通过 Claude Code 协助开发

❓ 帮助:
  帮助  - 显示此帮助信息
""".strip()


# ============================================
# FastAPI Application
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Gateway Service...")

    # Initialize the new registry manager
    from services.gateway.registry import get_registry_manager

    registry = get_registry_manager()

    # Start health monitor (runs in background)
    await registry.start_health_monitor()
    logger.info("Service health monitor started")

    # Initialize profile manager for mode persistence
    try:
        from src.memory import get_profile_manager
        profile_manager = get_profile_manager()
        await profile_manager.get("init_check")
        logger.info("Profile manager initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize profile manager: {e}")

    # Initialize Feishu client if enabled
    if settings.feishu_enabled:
        from src.feishu.client import get_feishu_client
        client = get_feishu_client()
        if client:
            logger.info("Feishu client initialized")

    # Initialize intent router
    from services.gateway.intent_router import get_intent_router
    get_intent_router()
    logger.info("Intent router initialized")

    yield

    # Cleanup
    logger.info("Shutting down Gateway Service...")
    await registry.close()

    # Close intent router
    from services.gateway.intent_router import get_intent_router
    router = get_intent_router()
    await router.close()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="InvestManager Gateway",
        description="Gateway service for message routing, mode dispatch, and LLM proxy",
        version="2.0.0",
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

    # ========================================
    # Basic Endpoints
    # ========================================

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "InvestManager Gateway",
            "version": "2.0.0",
            "services": {
                "llm": LLM_SERVICE_URL,
                "invest": INVEST_SERVICE_URL,
                "chat": CHAT_SERVICE_URL,
                "dev": DEV_SERVICE_URL,
            },
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "gateway",
        }

    @app.get("/services")
    async def list_services():
        """List connected services and their status."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        response = registry.list_services()

        results = {}
        for service in response.services:
            results[service.service_id] = {
                "name": service.service_name,
                "url": service.base_url,
                "status": service.status.value,
                "version": service.version,
                "registered_at": service.registered_at.isoformat() if service.registered_at else None,
            }

        return {"services": results, "total": response.total}

    # ========================================
    # Registry API Endpoints
    # ========================================

    @app.post("/registry/register", response_model=RegisterResponse)
    async def register_service(request: RegisterRequest):
        """Register a service capability.

        Services call this endpoint to register their capabilities.
        """
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        return await registry.register(request)

    @app.post("/registry/unregister", response_model=UnregisterResponse)
    async def unregister_service(request: UnregisterRequest):
        """Unregister a service capability."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        return await registry.unregister(request)

    @app.post("/registry/heartbeat", response_model=HeartbeatResponse)
    async def service_heartbeat(request: HeartbeatRequest):
        """Process heartbeat from a registered service."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        return await registry.heartbeat(request)

    @app.get("/registry/capabilities")
    async def list_capabilities():
        """List all available capabilities across services."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        return registry.list_capabilities()

    @app.get("/registry/description")
    async def get_capability_description():
        """Get capability description for LLM prompt."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        return {"description": registry.get_capability_description()}

    # ========================================
    # Intent Parsing Endpoints
    # ========================================

    @app.post("/intent/parse", response_model=IntentParseResponse)
    async def parse_intent(request: IntentParseRequest):
        """Parse user intent and determine routing.

        Uses LLM to determine which service should handle the message.
        """
        from services.gateway.registry import get_registry_manager
        from services.gateway.intent_router import get_intent_router

        registry = get_registry_manager()
        router = get_intent_router()

        # Check for forced mode
        if request.user_id:
            forced_service = registry.get_forced_mode(request.user_id)
            if forced_service:
                request.force_service = forced_service

        # Get available capabilities
        capabilities = {
            service_id: service
            for service_id, service in registry._capabilities.items()
        }

        return await router.parse_intent(request, capabilities)

    # ========================================
    # Forced Mode Endpoints
    # ========================================

    @app.post("/forced-mode", response_model=ForcedModeResponse)
    async def set_forced_mode(request: ForcedModeRequest):
        """Set or clear forced mode for a user.

        When forced mode is set, all messages from that user will be
        routed to the specified service, bypassing intent parsing.
        """
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        return registry.set_forced_mode(request)

    @app.get("/forced-mode/{user_id}")
    async def get_forced_mode(user_id: str):
        """Get forced mode for a user."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        service_id = registry.get_forced_mode(user_id)

        return {
            "user_id": user_id,
            "forced_mode": service_id,
            "is_forced": service_id is not None,
        }

    @app.delete("/forced-mode/{user_id}")
    async def clear_forced_mode(user_id: str):
        """Clear forced mode for a user."""
        from services.gateway.registry import get_registry_manager

        registry = get_registry_manager()
        cleared = registry.clear_forced_mode(user_id)

        return {
            "user_id": user_id,
            "cleared": cleared,
        }

    # ========================================
    # Help System Endpoints
    # ========================================

    @app.get("/help")
    async def get_help_menu():
        """Get help menu."""
        from services.gateway.help_system import get_help_manager

        help_manager = get_help_manager()
        return {
            "menu": help_manager.format_help_menu(),
            "categories": [
                {"id": "general", "name": "通用"},
                {"id": "invest", "name": "投资分析"},
                {"id": "chat", "name": "对话聊天"},
                {"id": "dev", "name": "开发模式"},
                {"id": "system", "name": "系统功能"},
            ],
        }

    @app.get("/help/{help_id}")
    async def get_help_content(help_id: str):
        """Get specific help content."""
        from services.gateway.help_system import get_help_manager

        help_manager = get_help_manager()
        content = help_manager.get_store().get(help_id)

        if not content:
            raise HTTPException(status_code=404, detail="Help content not found")

        return {
            "id": content.id,
            "title": content.title,
            "description": content.description,
            "type": content.help_type.value,
            "category": content.category.value,
            "formatted": help_manager.format_help(content),
        }

    @app.get("/help/search/{query}")
    async def search_help(query: str):
        """Search help content."""
        from services.gateway.help_system import get_help_manager

        help_manager = get_help_manager()
        results = help_manager.get_store().search(query)

        return {
            "query": query,
            "results": [
                {
                    "id": r.content.id,
                    "title": r.content.title,
                    "relevance": r.relevance,
                }
                for r in results
            ],
        }

    @app.get("/help/category/{category}")
    async def get_help_by_category(category: str):
        """Get help content by category."""
        from services.gateway.help_system import get_help_manager, HelpCategory

        help_manager = get_help_manager()

        try:
            cat = HelpCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")

        contents = help_manager.get_store().get_by_category(cat)

        return {
            "category": category,
            "contents": [
                {
                    "id": c.id,
                    "title": c.title,
                    "description": c.description,
                }
                for c in contents
            ],
        }

    @app.get("/quick-start")
    async def get_quick_start():
        """Get quick start guide."""
        from services.gateway.help_system import get_help_manager

        help_manager = get_help_manager()
        content = help_manager.get_store().get("quick_start")

        if not content:
            raise HTTPException(status_code=404, detail="Quick start guide not found")

        return {
            "formatted": help_manager.format_help(content),
            "steps": [
                {
                    "step": s.step_number,
                    "title": s.title,
                    "description": s.description,
                    "example": s.example,
                }
                for s in content.steps
            ],
        }

    @app.get("/tips")
    async def get_tips():
        """Get quick tips."""
        from services.gateway.help_system import get_help_manager

        help_manager = get_help_manager()
        return {
            "tips": help_manager.format_quick_tips(),
        }

    # ========================================
    # LLM Proxy Routes
    # ========================================

    # ========================================
    # LLM Proxy Endpoints (Internal Services)
    # ========================================

    @app.post("/llm/chat")
    async def llm_chat(
        request: LLMChatRequest,
        x_service_key: Optional[str] = Header(None),
    ):
        """Proxy LLM chat request to LLM service.

        This endpoint is for internal service use only.
        Requires X-Service-Key header if SERVICE_API_KEY is configured.
        """
        if not verify_service_key(x_service_key):
            raise HTTPException(status_code=403, detail="Invalid service key")

        llm_client = get_llm_proxy_client()
        return await llm_client.chat(request)

    @app.post("/llm/intent")
    async def llm_intent(
        request: LLMIntentRequest,
        x_service_key: Optional[str] = Header(None),
    ):
        """Proxy intent parsing request to LLM service.

        This endpoint is for internal service use only.
        """
        if not verify_service_key(x_service_key):
            raise HTTPException(status_code=403, detail="Invalid service key")

        llm_client = get_llm_proxy_client()
        return await llm_client.parse_intent(request)

    @app.post("/llm/search")
    async def llm_search(
        request: LLMSearchRequest,
        x_service_key: Optional[str] = Header(None),
    ):
        """Proxy search request to LLM service.

        This endpoint is for internal service use only.
        """
        if not verify_service_key(x_service_key):
            raise HTTPException(status_code=403, detail="Invalid service key")

        llm_client = get_llm_proxy_client()
        return await llm_client.search(request)

    # ========================================
    # Feishu Webhook
    # ========================================

    @app.post("/feishu/webhook")
    @app.post("/api/feishu/webhook")
    async def feishu_webhook(request: Request):
        """Handle Feishu webhook events.

        This is the main entry point for all Feishu messages.
        """
        event = await request.json()
        logger.info(f"Received webhook event: {json.dumps(event, ensure_ascii=False)[:500]}")

        # Handle encrypted event
        if "encrypt" in event:
            from src.feishu.client import get_feishu_client
            feishu_client = get_feishu_client()
            if feishu_client:
                try:
                    decrypted = feishu_client.decrypt_event_data(event["encrypt"])
                    event = json.loads(decrypted)
                    logger.info(f"Decrypted event: {json.dumps(event, ensure_ascii=False)[:500]}")
                except Exception as e:
                    logger.error(f"Failed to decrypt event: {e}")
                    return {"status": "decrypt_failed"}

        event_type = event.get("type") or event.get("header", {}).get("event_type")

        # URL verification
        if event_type == "url_verification":
            return {"challenge": event.get("challenge")}

        # Message event
        if event_type == "im.message.receive_v1":
            return await handle_message_event(event)

        logger.warning(f"Unhandled event type: {event_type}")
        return {"status": "ignored"}

    async def handle_message_event(event: dict) -> dict:
        """Handle incoming message event."""
        import uuid
        import time as time_module
        from src.feishu.client import get_feishu_client
        from services.gateway.registry import get_registry_manager
        from services.gateway.intent_router import get_intent_router

        # Generate trace_id for this request
        trace_id = f"req_{uuid.uuid4().hex[:16]}_{int(time_module.time()*1000)}"

        event_data = event.get("event", {})
        message = event_data.get("message", {})

        # Extract message info
        message_id = message.get("message_id")
        chat_id = message.get("chat_id")

        # Check for duplicate message (Feishu may retry)
        if _message_deduplicator.is_duplicate(message_id):
            logger.debug(f"Duplicate message ignored: {message_id}")
            return {"status": "duplicate"}

        # Mark message as being processed
        _message_deduplicator.mark_processed(message_id)

        # Extract sender ID
        sender = event_data.get("sender", {})
        sender_id = sender.get("sender_id", {})
        user_id = (
            sender_id.get("open_id") or
            sender_id.get("user_id") or
            sender_id.get("union_id") or
            ""
        )

        # Parse message content
        content = message.get("content", "{}")
        if isinstance(content, str):
            content = json.loads(content)

        text = content.get("text", "")
        if not text:
            return {"status": "ok"}

        logger.info(f"[{trace_id}] Message from {user_id}: {text[:50]}...")

        # Parse command
        command_type, params = parse_command(text)

        # Handle help command directly
        if command_type == CommandType.HELP:
            try:
                feishu_client = get_feishu_client()
                if feishu_client:
                    help_manager = get_help_manager()
                    help_text = help_manager.format_help_menu()
                    await feishu_client.reply_message(message_id, help_text)
            except Exception as e:
                logger.error(f"Failed to handle help command: {e}")
            return {"status": "ok"}

        # Handle help topic: 帮助 xxx
        if command_type == CommandType.HELP_TOPIC:
            try:
                feishu_client = get_feishu_client()
                if feishu_client:
                    help_manager = get_help_manager()
                    topic = params.get("topic", "")

                    # First try to get by ID
                    content = help_manager.get_store().get(topic)
                    if content:
                        help_text = help_manager.format_help(content)
                    else:
                        # Search by keyword
                        results = help_manager.get_store().search(topic, limit=1)
                        if results:
                            help_text = help_manager.format_help(results[0].content)
                        else:
                            help_text = f"未找到关于「{topic}」的帮助内容。\n\n发送「帮助」查看所有帮助主题。"

                    await feishu_client.reply_message(message_id, help_text)
            except Exception as e:
                logger.error(f"Failed to handle help topic command: {e}")
            return {"status": "ok"}

        # Handle quick start
        if command_type == CommandType.QUICK_START:
            try:
                feishu_client = get_feishu_client()
                if feishu_client:
                    help_manager = get_help_manager()
                    content = help_manager.get_store().get("quick_start")
                    if content:
                        help_text = help_manager.format_help(content)
                        help_manager.mark_help_viewed(user_id, "quick_start")
                        await feishu_client.reply_message(message_id, help_text)
            except Exception as e:
                logger.error(f"Failed to handle quick start command: {e}")
            return {"status": "ok"}

        # Handle interactive guide
        if command_type == CommandType.GUIDE:
            try:
                feishu_client = get_feishu_client()
                if feishu_client:
                    help_text = """🎯 **功能引导**

选择您想了解的功能：

**投资分析**
• 发送「帮助 invest_guide」了解股票分析功能
• 发送「帮助 stock_analysis」学习股票分析步骤

**对话模式**
• 发送「帮助 chat_guide」了解对话功能

**开发模式**
• 发送「帮助 dev_guide」了解代码助手功能

**系统功能**
• 发送「帮助 mode_switch」了解模式切换
• 发送「帮助 profile_guide」了解个性化功能

💡 或者发送「快速开始」开始新手教程"""
                    await feishu_client.reply_message(message_id, help_text)
            except Exception as e:
                logger.error(f"Failed to handle guide command: {e}")
            return {"status": "ok"}

        # Handle tips
        if command_type == CommandType.TIPS:
            try:
                feishu_client = get_feishu_client()
                if feishu_client:
                    help_manager = get_help_manager()
                    tips_text = help_manager.format_quick_tips()
                    await feishu_client.reply_message(message_id, tips_text)
            except Exception as e:
                logger.error(f"Failed to handle tips command: {e}")
            return {"status": "ok"}

        # Handle FAQ
        if command_type == CommandType.FAQ:
            try:
                feishu_client = get_feishu_client()
                if feishu_client:
                    help_manager = get_help_manager()
                    content = help_manager.get_store().get("faq_general")
                    if content:
                        help_text = help_manager.format_help(content)
                        await feishu_client.reply_message(message_id, help_text)
            except Exception as e:
                logger.error(f"Failed to handle FAQ command: {e}")
            return {"status": "ok"}

        # Handle mode/status commands (legacy compatibility)
        if command_type == CommandType.MODE_STATUS:
            try:
                # Check forced mode first
                registry = get_registry_manager()
                forced_service = registry.get_forced_mode(user_id)
                if forced_service:
                    service = registry.get_service(forced_service)
                    mode_name = service.service_name if service else forced_service
                    reply = f"当前强制模式：「{mode_name}」"
                else:
                    # Fall back to work mode
                    capability_client = get_capability_client()
                    result = await capability_client.get_mode(user_id)
                    mode_name = {"invest": "投资助手", "chat": "通用对话", "dev": "开发模式"}.get(result, result)
                    reply = f"当前模式：「{mode_name}」(智能路由)"

                feishu_client = get_feishu_client()
                if feishu_client:
                    await feishu_client.reply_message(message_id, reply)
            except Exception as e:
                logger.error(f"Failed to handle mode status command: {e}")
            return {"status": "ok"}

        if command_type == CommandType.MODE_SWITCH:
            try:
                registry = get_registry_manager()
                target_mode = params.get("target_mode")

                if target_mode:
                    # Set forced mode for specific service
                    result = registry.set_forced_mode(ForcedModeRequest(
                        user_id=user_id,
                        service_id=target_mode,
                    ))
                else:
                    # Clear forced mode to enable smart routing
                    result = registry.set_forced_mode(ForcedModeRequest(
                        user_id=user_id,
                        service_id=None,
                    ))

                feishu_client = get_feishu_client()
                if feishu_client:
                    await feishu_client.reply_message(message_id, result.message)
            except Exception as e:
                logger.error(f"Failed to handle mode switch command: {e}")
            return {"status": "ok"}

        # Check for "使用xxx模块" command for forced mode
        import re
        force_match = re.match(r"使用\s*(\w+)\s*模块?", text.lower())
        if force_match:
            try:
                target_service = force_match.group(1)
                registry = get_registry_manager()
                result = registry.set_forced_mode(ForcedModeRequest(
                    user_id=user_id,
                    service_id=target_service,
                ))
                feishu_client = get_feishu_client()
                if feishu_client:
                    await feishu_client.reply_message(message_id, result.message)
            except Exception as e:
                logger.error(f"Failed to handle force module command: {e}")
            return {"status": "ok"}

        # Route message using intent router
        try:
            registry = get_registry_manager()
            router = get_intent_router()

            # Check forced mode first
            forced_service = registry.get_forced_mode(user_id)

            # Build intent parse request
            intent_request = IntentParseRequest(
                user_message=text,
                user_id=user_id,
                force_service=forced_service,
            )

            # Get available capabilities
            capabilities = dict(registry._capabilities)

            # Parse intent
            intent_response = await router.parse_intent(intent_request, capabilities)

            if not intent_response.service_id:
                # No service available
                feishu_client = get_feishu_client()
                if feishu_client:
                    await feishu_client.reply_message(
                        message_id,
                        "抱歉，当前没有可用的服务来处理您的请求。"
                    )
                return {"status": "ok"}

            logger.info(
                f"Routing message to {intent_response.service_id} "
                f"(confidence: {intent_response.confidence:.2f})"
            )

            # Check if user is new and should see proactive help
            help_manager = get_help_manager()
            is_new_user = help_manager.is_new_user(user_id)

            # Get the target service
            target_service = registry.get_service(intent_response.service_id)
            if not target_service:
                feishu_client = get_feishu_client()
                if feishu_client:
                    await feishu_client.reply_message(
                        message_id,
                        f"服务 '{intent_response.service_id}' 暂时不可用。"
                    )
                return {"status": "ok"}

            # Create message context for the service
            context = MessageContext(
                user_id=user_id,
                chat_id=chat_id,
                message_id=message_id,
                raw_text=text,
                work_mode=intent_response.service_id,  # Use service_id as work_mode
                trace_id=trace_id,
                source="feishu",
                timestamp=time_module.time() * 1000,
            )

            # Call the target service
            capability_client = get_capability_client()
            logger.info(f"[{trace_id}] -> {intent_response.service_id} /handle")
            result = await capability_client.handle_message(context)
            logger.info(f"[{trace_id}] <- {intent_response.service_id} success={result.success}, len={len(result.message) if result.message else 0}")

            # Send reply with optional proactive help for new users
            if result.should_reply and result.message:
                feishu_client = get_feishu_client()
                if feishu_client:
                    reply_text = result.message

                    # Append help tip for new users
                    if is_new_user:
                        help_tip = "\n\n---\n💡 **新手提示：** 发送「帮助」或「快速开始」了解更多功能！"
                        reply_text += help_tip
                        help_manager.mark_help_viewed(user_id, "quick_start")

                    await feishu_client.reply_message(message_id, reply_text)
                    logger.info(f"[{trace_id}] -> feishu reply sent")

        except Exception as e:
            logger.error(f"[{trace_id}] Failed to route message: {e}")

        return {"status": "ok"}

    def _build_help_text(registry) -> str:
        """Build dynamic help text based on registered services."""
        services_desc = registry.get_capability_description()

        return f"""📈 InvestManager 机器人使用指南

🔄 工作模式:
  切换模式  - 切换到智能路由模式
  切换到投资模式 / 切换到invest - 强制使用投资服务
  切换到对话模式 / 切换到chat - 强制使用对话服务
  切换到开发模式 / 切换到dev - 强制使用开发服务
  使用 <模块名> 模块 - 强制指定模块
  当前模式  - 查看当前模式

{services_desc}

❓ 帮助:
  帮助  - 显示此帮助信息
""".strip()

    # ========================================
    # Mode Management
    # ========================================

    @app.get("/mode/{user_id}")
    async def get_user_mode(user_id: str):
        """Get user's current work mode."""
        capability_client = get_capability_client()
        mode = await capability_client.get_mode(user_id)
        return {"user_id": user_id, "mode": mode}

    @app.put("/mode/{user_id}")
    async def set_user_mode(user_id: str, mode: str):
        """Set user's work mode."""
        capability_client = get_capability_client()
        result = await capability_client.set_mode(user_id, mode)
        return result.model_dump()


# ============================================
# Entry Point
# ============================================

def run_gateway():
    """Run the gateway service."""
    import uvicorn

    parser = argparse.ArgumentParser(description="InvestManager Gateway Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind")
    parser.add_argument("--llm-url", default=None, help="LLM service URL")
    parser.add_argument("--invest-url", default=None, help="Invest service URL")
    parser.add_argument("--chat-url", default=None, help="Chat service URL")
    parser.add_argument("--dev-url", default=None, help="Dev service URL")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    global LLM_SERVICE_URL, INVEST_SERVICE_URL, CHAT_SERVICE_URL, DEV_SERVICE_URL

    if args.llm_url:
        LLM_SERVICE_URL = args.llm_url

    if args.invest_url:
        INVEST_SERVICE_URL = args.invest_url
        CAPABILITY_URLS["invest"] = INVEST_SERVICE_URL

    if args.chat_url:
        CHAT_SERVICE_URL = args.chat_url
        CAPABILITY_URLS["chat"] = CHAT_SERVICE_URL

    if args.dev_url:
        DEV_SERVICE_URL = args.dev_url
        CAPABILITY_URLS["dev"] = DEV_SERVICE_URL

    uvicorn.run(
        "services.gateway:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=args.reload,
    )


if __name__ == "__main__":
    run_gateway()