#!/usr/bin/env python
"""Gateway Service - Main entry point.

This service acts as the entry point for Feishu messages,
routing them to the appropriate capability service based on
the user's work mode, and proxying LLM requests.

Architecture:
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Feishu    │────▶│   Gateway    │────▶│   LLM Service    │
│   Webhook   │     │   :8000      │     │   :8001          │
└─────────────┘     └──────────────┘     └──────────────────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │ Capability Svc   │
                    │   :8002          │
                    └──────────────────┘
"""

import argparse
import asyncio
import json
import os
import sys
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
    """Client for communicating with capability services using resilient requests."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    async def handle_message(self, context: MessageContext) -> RouteResponse:
        """Route message to appropriate capability service based on mode."""
        from services.service_registry import get_resilient_client

        mode = context.work_mode
        try:
            client = get_resilient_client(mode)
            response = await client.post(
                "/handle",
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

    async def chat(self, request: LLMChatRequest) -> dict:
        """Proxy chat request to LLM service."""
        from services.service_registry import get_resilient_client

        client = get_resilient_client("llm")
        try:
            response = await client.post(
                "/chat",
                json=request.model_dump(),
            )
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
        from services.service_registry import get_resilient_client

        client = get_resilient_client("llm")
        try:
            response = await client.post(
                "/intent",
                json=request.model_dump(),
            )
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
        from services.service_registry import get_resilient_client

        client = get_resilient_client("llm")
        try:
            response = await client.post(
                "/search",
                json=request.model_dump(),
            )
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


def parse_command(text: str) -> tuple[str, dict[str, Any]]:
    """Parse command from text.

    Returns:
        Tuple of (command_type, params)
    """
    import re
    text = text.strip().lower()

    # Mode switch patterns
    if re.match(r"切换模式", text):
        return CommandType.MODE_SWITCH, {}
    if re.match(r"切换到投资模式", text) or re.match(r"切换到invest", text):
        return CommandType.MODE_SWITCH, {"target_mode": "invest"}
    if re.match(r"切换到对话模式", text) or re.match(r"切换到chat", text):
        return CommandType.MODE_SWITCH, {"target_mode": "chat"}
    if re.match(r"切换到开发模式", text) or re.match(r"切换到dev", text):
        return CommandType.MODE_SWITCH, {"target_mode": "dev"}

    # Mode status
    if re.match(r"当前模式", text) or re.match(r"什么模式", text):
        return CommandType.MODE_STATUS, {}

    # Help
    if re.match(r"帮助|help|\?", text):
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

    # Register services with the service registry
    from services.service_registry import (
        get_service_registry,
        register_service,
    )

    # Register all services - they don't need to be up at startup
    register_service("llm", LLM_SERVICE_URL)
    register_service("invest", INVEST_SERVICE_URL)
    register_service("chat", CHAT_SERVICE_URL)
    register_service("dev", DEV_SERVICE_URL)

    logger.info(f"LLM Service URL: {LLM_SERVICE_URL}")
    logger.info(f"Invest Service URL: {INVEST_SERVICE_URL}")
    logger.info(f"Chat Service URL: {CHAT_SERVICE_URL}")
    logger.info(f"Dev Service URL: {DEV_SERVICE_URL}")

    # Start health monitor (runs in background)
    registry = get_service_registry()
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

    yield

    # Cleanup
    logger.info("Shutting down Gateway Service...")
    await registry.close()


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
        from services.service_registry import get_service_registry, ServiceStatus

        registry = get_service_registry()
        results = {}

        for name, endpoint in registry._services.items():
            status = endpoint._status.value
            results[name] = {
                "url": endpoint.url,
                "status": status,
                "circuit_open": endpoint._circuit_open,
                "failure_count": endpoint._failure_count,
            }

        return {"services": results}

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
        from src.feishu.client import get_feishu_client

        event_data = event.get("event", {})
        message = event_data.get("message", {})

        # Extract message info
        message_id = message.get("message_id")
        chat_id = message.get("chat_id")

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

        logger.info(f"Message from {user_id}: {text[:50]}...")

        # Get capability client
        capability_client = get_capability_client()

        # Parse command
        command_type, params = parse_command(text)

        # Handle help command directly
        if command_type == CommandType.HELP:
            feishu_client = get_feishu_client()
            if feishu_client:
                await feishu_client.reply_message(message_id, HELP_TEXT)
            return {"status": "ok"}

        # Handle mode commands
        if command_type == CommandType.MODE_STATUS:
            result = await capability_client.get_mode(user_id)
            mode_name = {"invest": "投资助手", "chat": "通用对话", "dev": "开发模式"}.get(result, result)
            reply = f"当前模式：「{mode_name}」"
            feishu_client = get_feishu_client()
            if feishu_client:
                await feishu_client.reply_message(message_id, reply)
            return {"status": "ok"}

        if command_type == CommandType.MODE_SWITCH:
            target_mode = params.get("target_mode")
            if target_mode:
                result = await capability_client.set_mode(user_id, target_mode)
            else:
                # Cycle mode using the new cycle_mode method
                result = await capability_client.cycle_mode(user_id)

            feishu_client = get_feishu_client()
            if feishu_client and result.mode:
                await feishu_client.reply_message(message_id, result.message)
            return {"status": "ok"}

        # Get user's current mode
        work_mode = await capability_client.get_mode(user_id)
        logger.info(f"User {user_id} mode: {work_mode}")

        # Create message context
        context = MessageContext(
            user_id=user_id,
            chat_id=chat_id,
            message_id=message_id,
            raw_text=text,
            work_mode=work_mode,
        )

        # Route to capability service
        result = await capability_client.handle_message(context)

        # Send reply
        if result.should_reply and result.message:
            feishu_client = get_feishu_client()
            if feishu_client:
                await feishu_client.reply_message(message_id, result.message)

        return {"status": "ok"}

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