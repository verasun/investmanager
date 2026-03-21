#!/usr/bin/env python
"""Chat Service - Main entry point.

This service handles general chat messages with personalization
support and learning user preferences.

Architecture:
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Gateway   │────▶│ Chat Service │────▶│   LLM Service    │
│   :8000     │     │   :8011       │     │   (via Gateway)  │
└─────────────┘     └──────────────┘     └──────────────────┘

Registration:
This service registers its capabilities with the Gateway on startup.
"""

import argparse
import json
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

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8011"))


# ============================================
# Models
# ============================================

class MessageContext(BaseModel):
    """Context for processing a message."""
    user_id: str
    chat_id: str
    message_id: str
    raw_text: str
    work_mode: str = "chat"
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


class LearningRequest(BaseModel):
    """Request for learning response handling."""
    user_id: str
    message: str


class LearningResponse(BaseModel):
    """Response from learning handling."""
    handled: bool
    task_type: Optional[str] = None
    preference_set: Optional[str] = None
    message: Optional[str] = None


# ============================================
# LLM Client (via Gateway)
# ============================================

class LLMClient:
    """Client for calling LLM through Gateway proxy."""

    def __init__(self, gateway_url: str, api_key: str = ""):
        self.gateway_url = gateway_url.rstrip("/")
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

    async def chat(
        self,
        messages: list[dict],
        system_prompt: Optional[str] = None,
        user_id: Optional[str] = None,
        enable_web_search: bool = True,
        trace_id: Optional[str] = None,
    ) -> str:
        """Call LLM chat through Gateway."""
        import time as time_module
        client = await self._get_client()
        tid = trace_id or "no-trace"

        payload = {
            "messages": messages,
            "system_prompt": system_prompt,
            "user_id": user_id,
            "enable_web_search": enable_web_search,
        }

        try:
            logger.info(f"[{tid}] -> gateway /llm/chat")
            start_time = time_module.time()
            response = await client.post(
                f"{self.gateway_url}/llm/chat",
                json=payload,
            )
            duration_ms = (time_module.time() - start_time) * 1000
            response.raise_for_status()
            data = response.json()
            content_len = len(data.get('content', ''))
            logger.info(f"[{tid}] <- gateway /llm/chat status={response.status_code} len={content_len} ({duration_ms:.0f}ms)")
            return data.get("content", "")
        except httpx.HTTPError as e:
            logger.error(f"[{tid}] LLM chat failed: {e}")
            raise


# ============================================
# Personalization Manager
# ============================================

class PersonalizationManager:
    """Manages user personalization for chat mode."""

    def __init__(self):
        self._modules_loaded = False
        self._profile_manager = None
        self._conversation_memory = None
        self._preference_extractor = None
        self._prompt_builder = None
        self._learning_manager = None

    def _load_modules(self):
        """Lazily load memory modules."""
        if self._modules_loaded:
            return

        try:
            from src.memory import (
                get_profile_manager,
                get_conversation_memory,
                get_preference_extractor,
                get_prompt_builder,
                get_learning_manager,
            )
            self._profile_manager = get_profile_manager()
            self._conversation_memory = get_conversation_memory()
            self._preference_extractor = get_preference_extractor()
            self._prompt_builder = get_prompt_builder()
            self._learning_manager = get_learning_manager()
            self._modules_loaded = True
        except Exception as e:
            logger.warning(f"Failed to load personalization modules: {e}")

    async def get_chat_prompt(self, user_id: str) -> Optional[str]:
        """Get personalized chat prompt for general conversation."""
        self._load_modules()
        if not self._modules_loaded:
            return None

        try:
            profile = await self._profile_manager.get(user_id)
            return self._prompt_builder.build_chat_prompt(
                profile,
                is_unrestricted=True,
            )
        except Exception as e:
            logger.warning(f"Failed to get chat prompt: {e}")
            return None

    async def get_pending_learning_task(self, user_id: str) -> Optional[dict]:
        """Get pending learning task for user."""
        self._load_modules()
        if not self._modules_loaded:
            return None

        try:
            return await self._learning_manager.get_pending_task_for_user(user_id)
        except Exception as e:
            logger.warning(f"Failed to get learning task: {e}")
            return None

    async def handle_learning_response(
        self,
        user_id: str,
        message: str,
    ) -> Optional[dict]:
        """Handle response to learning task."""
        self._load_modules()
        if not self._modules_loaded:
            return None

        try:
            import aiosqlite

            db_path = settings.sqlite_db_path or "./data/investmanager.db"

            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    """
                    SELECT * FROM learning_tasks
                    WHERE user_id = ? AND asked = 1 AND answered = 0
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id,),
                )
                row = await cursor.fetchone()

                if not row:
                    return None

                task_id = row["task_id"]
                options = json.loads(row["options"])

            option_idx = self._preference_extractor.detect_option_selection(
                message, options
            )

            if option_idx is not None:
                preference_value = await self._learning_manager.complete_task(
                    task_id, message, option_idx
                )
                return {
                    "type": "learning_response",
                    "task_id": task_id,
                    "preference_set": preference_value,
                    "message": "好的，已记录您的偏好！",
                }

            return None

        except Exception as e:
            logger.warning(f"Failed to handle learning response: {e}")
            return None

    async def record_interaction(
        self,
        user_id: str,
        user_message: str,
        assistant_message: str,
    ):
        """Record interaction for learning."""
        self._load_modules()
        if not self._modules_loaded:
            return

        try:
            await self._conversation_memory.add_message(
                user_id, "user", user_message
            )
            await self._conversation_memory.add_message(
                user_id, "assistant", assistant_message
            )
            await self._profile_manager.increment_interactions(user_id)

            # Extract preferences
            extracted = self._preference_extractor.extract(user_message)
            if extracted.has_preferences() or extracted.mentioned_stocks:
                await self._conversation_memory.add_message(
                    user_id, "user", user_message,
                    preferences_extracted=extracted.to_dict()
                )

                if extracted.mentioned_stocks:
                    for stock in extracted.mentioned_stocks:
                        await self._profile_manager.add_stock_mention(user_id, stock)

        except Exception as e:
            logger.warning(f"Failed to record interaction: {e}")


# ============================================
# Chat Service
# ============================================

class ChatService:
    """Core Chat service logic."""

    def __init__(self, gateway_url: str, api_key: str = ""):
        self.llm_client = LLMClient(gateway_url, api_key)
        self.personalization = PersonalizationManager()

    async def handle_message(self, context: MessageContext) -> HandleResponse:
        """Handle general chat message."""
        user_id = context.user_id
        text = context.raw_text
        trace_id = context.trace_id or "no-trace"

        logger.info(f"[{trace_id}] ChatService: {text[:50]}... from {user_id}")

        # Check for learning response first
        learning_result = await self.personalization.handle_learning_response(
            user_id, text
        )
        if learning_result:
            return HandleResponse(
                success=True,
                message=learning_result.get("message", "好的"),
                data={"type": "learning_response"},
            )

        # Get personalized chat prompt (unrestricted mode)
        system_prompt = await self.personalization.get_chat_prompt(user_id)

        # Get pending learning task
        learning_task = await self.personalization.get_pending_learning_task(user_id)

        # Build messages
        messages = [{"role": "user", "content": text}]

        try:
            # Call LLM through Gateway
            response = await self.llm_client.chat(
                messages=messages,
                system_prompt=system_prompt,
                user_id=user_id,
                enable_web_search=True,
                trace_id=trace_id,
            )

            # Append learning task if present
            if learning_task:
                options_text = "\n".join(
                    f"{i+1}. {opt}"
                    for i, opt in enumerate(learning_task["options"])
                )
                response = f"{response}\n\n{learning_task['question']}\n{options_text}"

            # Record interaction
            await self.personalization.record_interaction(user_id, text, response)

            return HandleResponse(
                success=True,
                message=response,
                data={"type": "chat_response"},
            )

        except Exception as e:
            logger.error(f"[{trace_id}] ChatService error: {e}")
            return HandleResponse(
                success=False,
                message=f"处理消息时出错: {str(e)}",
            )

    async def handle_learning(self, request: LearningRequest) -> LearningResponse:
        """Handle learning response directly."""
        result = await self.personalization.handle_learning_response(
            request.user_id,
            request.message,
        )

        if result:
            return LearningResponse(
                handled=True,
                task_type=result.get("type"),
                preference_set=result.get("preference_set"),
                message=result.get("message"),
            )

        return LearningResponse(handled=False)


# Global instances
_chat_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    """Get or create Chat service instance."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService(GATEWAY_URL, SERVICE_API_KEY)
    return _chat_service


# ============================================
# FastAPI Application
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Chat Service...")
    logger.info(f"Gateway URL: {GATEWAY_URL}")

    # Initialize profile manager
    try:
        from src.memory import get_profile_manager
        profile_manager = get_profile_manager()
        await profile_manager.get("init_check")
        logger.info("Profile manager initialized")
    except Exception as e:
        logger.warning(f"Failed to initialize profile manager: {e}")

    # Register with Gateway
    from services.registration import ServiceRegistrar
    from services.capability_protocol import get_chat_capability

    capability = get_chat_capability()
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
    logger.info("Shutting down Chat Service...")
    service = get_chat_service()
    await service.llm_client.close()

    # Unregister from Gateway
    await registrar.unregister()


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="InvestManager Chat Service",
        description="General conversation with personalization",
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
        """Root endpoint."""
        return {
            "name": "InvestManager Chat Service",
            "version": "1.0.0",
            "gateway_url": GATEWAY_URL,
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "chat",
        }

    @app.post("/handle", response_model=HandleResponse)
    async def handle_message(context: MessageContext):
        """Handle a message in chat mode.

        This is the main entry point for the gateway service.
        """
        service = get_chat_service()
        return await service.handle_message(context)

    @app.post("/learning", response_model=LearningResponse)
    async def handle_learning(request: LearningRequest):
        """Handle learning response directly.

        This can be used to process learning responses separately.
        """
        service = get_chat_service()
        return await service.handle_learning(request)


# ============================================
# Entry Point
# ============================================

def run_chat_service():
    """Run the Chat service."""
    import uvicorn

    parser = argparse.ArgumentParser(description="InvestManager Chat Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8011, help="Port to bind")
    parser.add_argument("--gateway-url", default=None, help="Gateway URL")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    if args.gateway_url:
        global GATEWAY_URL
        GATEWAY_URL = args.gateway_url

    uvicorn.run(
        "services.chat.main:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=args.reload,
    )


if __name__ == "__main__":
    run_chat_service()