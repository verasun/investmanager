#!/usr/bin/env python
"""Capability Router Service - Main entry point.

This service routes messages to the appropriate capability service
based on user's work mode and handles mode management.

Architecture:
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Gateway   │────▶│  Capability  │────▶│  Invest Service  │
│   :8000     │     │   :8002       │     │   :8002          │
└─────────────┘     │  (Router)     │────▶│  Chat Service    │
                    └──────────────┘     │  Dev Service     │
                                         └──────────────────┘
"""

import argparse
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings


# ============================================
# Configuration
# ============================================

# Service URLs
INVEST_SERVICE_URL = os.getenv("INVEST_SERVICE_URL", "http://localhost:8002")
CHAT_SERVICE_URL = os.getenv("CHAT_SERVICE_URL", "http://localhost:8003")
DEV_SERVICE_URL = os.getenv("DEV_SERVICE_URL", "http://localhost:8004")

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
    trace_id: Optional[str] = None
    source: str = "feishu"
    timestamp: Optional[float] = None


class HandleResponse(BaseModel):
    """Response from handling a message."""
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


# ============================================
# Service Client
# ============================================

class CapabilityServiceClient:
    """Client for calling capability services."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        self._service_urls = {
            "invest": INVEST_SERVICE_URL,
            "chat": CHAT_SERVICE_URL,
            "dev": DEV_SERVICE_URL,
        }

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["X-Service-Key"] = self.api_key
            self._client = httpx.AsyncClient(timeout=120.0, headers=headers)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def get_service_url(self, mode: str) -> str:
        """Get service URL for a mode."""
        return self._service_urls.get(mode, INVEST_SERVICE_URL)

    async def handle_message(self, context: MessageContext) -> HandleResponse:
        """Route message to appropriate service."""
        mode = context.work_mode
        url = self.get_service_url(mode)

        client = await self._get_client()
        try:
            response = await client.post(
                f"{url}/handle",
                json=context.model_dump(),
            )
            response.raise_for_status()
            return HandleResponse(**response.json())
        except httpx.HTTPError as e:
            logger.error(f"Failed to call {mode} service: {e}")
            return HandleResponse(
                success=False,
                message=f"服务调用失败: {str(e)}",
            )


# ============================================
# Mode Management
# ============================================

MODE_NAMES = {
    "invest": "投资助手",
    "chat": "通用对话",
    "dev": "开发模式",
}


async def get_user_mode(user_id: str) -> str:
    """Get user's current work mode from persistent storage."""
    try:
        from src.memory import get_profile_manager

        profile_manager = get_profile_manager()
        return await profile_manager.get_work_mode(user_id)
    except Exception as e:
        logger.warning(f"Failed to get user mode: {e}, defaulting to invest")
        return "invest"


async def set_user_mode(user_id: str, mode: str) -> ModeResponse:
    """Set user's work mode in persistent storage."""
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


async def cycle_user_mode(user_id: str) -> ModeResponse:
    """Cycle to next work mode for user."""
    try:
        from src.memory import get_profile_manager

        profile_manager = get_profile_manager()
        new_mode, _ = await profile_manager.cycle_work_mode(user_id)

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


# ============================================
# Global Instances
# ============================================

_capability_client: Optional[CapabilityServiceClient] = None


def get_capability_client() -> CapabilityServiceClient:
    """Get or create capability client."""
    global _capability_client
    if _capability_client is None:
        _capability_client = CapabilityServiceClient(SERVICE_API_KEY)
    return _capability_client


# ============================================
# FastAPI Application
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Capability Router Service...")
    logger.info(f"Invest Service: {INVEST_SERVICE_URL}")
    logger.info(f"Chat Service: {CHAT_SERVICE_URL}")
    logger.info(f"Dev Service: {DEV_SERVICE_URL}")

    # Initialize profile manager
    try:
        from src.memory import get_profile_manager
        profile_manager = get_profile_manager()
        await profile_manager.get("init_check")
        logger.info("Profile manager initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize profile manager: {e}")

    yield

    logger.info("Shutting down Capability Router Service...")
    client = get_capability_client()
    await client.close()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="InvestManager Capability Router",
        description="Routes messages to appropriate capability services",
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

    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "name": "InvestManager Capability Router",
            "version": "2.0.0",
            "services": {
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
            "service": "capability_router",
        }

    @app.post("/handle", response_model=HandleResponse)
    async def handle_message(context: MessageContext):
        """Handle a message based on user's work mode.

        Routes to the appropriate capability service.
        """
        client = get_capability_client()
        return await client.handle_message(context)

    @app.get("/mode/{user_id}")
    async def get_mode(user_id: str):
        """Get user's current work mode."""
        mode = await get_user_mode(user_id)
        mode_name = MODE_NAMES.get(mode, mode)
        return {
            "user_id": user_id,
            "mode": mode,
            "mode_name": mode_name,
        }

    @app.put("/mode/{user_id}", response_model=ModeResponse)
    async def set_mode(user_id: str, mode: str):
        """Set user's work mode."""
        valid_modes = {"invest", "chat", "dev"}
        if mode not in valid_modes:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode: {mode}. Valid modes: {valid_modes}",
            )
        return await set_user_mode(user_id, mode)

    @app.post("/mode/{user_id}/cycle", response_model=ModeResponse)
    async def cycle_mode(user_id: str):
        """Cycle to next work mode for user."""
        return await cycle_user_mode(user_id)

    # Direct mode endpoints (for health checks, etc.)

    @app.post("/handle/invest", response_model=HandleResponse)
    async def handle_invest(context: MessageContext):
        """Handle message in INVEST mode directly."""
        context.work_mode = "invest"
        client = get_capability_client()
        return await client.handle_message(context)

    @app.post("/handle/chat", response_model=HandleResponse)
    async def handle_chat(context: MessageContext):
        """Handle message in CHAT mode directly."""
        context.work_mode = "chat"
        client = get_capability_client()
        return await client.handle_message(context)

    @app.post("/handle/dev", response_model=HandleResponse)
    async def handle_dev(context: MessageContext):
        """Handle message in DEV mode directly."""
        context.work_mode = "dev"
        client = get_capability_client()
        return await client.handle_message(context)


# ============================================
# Entry Point
# ============================================

def run_capability_service():
    """Run the capability router service."""
    import uvicorn

    parser = argparse.ArgumentParser(description="InvestManager Capability Router Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8002, help="Port to bind")
    parser.add_argument("--invest-url", default=None, help="Invest service URL")
    parser.add_argument("--chat-url", default=None, help="Chat service URL")
    parser.add_argument("--dev-url", default=None, help="Dev service URL")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    if args.invest_url:
        global INVEST_SERVICE_URL
        INVEST_SERVICE_URL = args.invest_url

    if args.chat_url:
        global CHAT_SERVICE_URL
        CHAT_SERVICE_URL = args.chat_url

    if args.dev_url:
        global DEV_SERVICE_URL
        DEV_SERVICE_URL = args.dev_url

    uvicorn.run(
        "services.capabilities.main:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=args.reload,
    )


if __name__ == "__main__":
    run_capability_service()