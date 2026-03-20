#!/usr/bin/env python
"""Dev Service - Main entry point.

This service handles development mode messages through
Claude Code CLI integration.

Architecture:
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Gateway   │────▶│  Dev Service │────▶│   Claude Code    │
│   :8000     │     │   :8012       │     │   CLI            │
└─────────────┘     └──────────────┘     └──────────────────┘
"""

import argparse
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config.settings import settings


# ============================================
# Models
# ============================================

class MessageContext(BaseModel):
    """Context for processing a message."""
    user_id: str
    chat_id: str
    message_id: str
    raw_text: str
    work_mode: str = "dev"


class HandleResponse(BaseModel):
    """Response from handling a message."""
    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    should_reply: bool = True


class ExecuteRequest(BaseModel):
    """Request for Claude Code execution."""
    prompt: str
    working_dir: Optional[str] = None
    timeout: int = 120  # seconds


class ExecuteResponse(BaseModel):
    """Response from Claude Code execution."""
    success: bool
    output: str
    error: Optional[str] = None
    exit_code: int = 0


# ============================================
# Claude Code Executor
# ============================================

class ClaudeCodeExecutor:
    """Executes Claude Code CLI commands."""

    def __init__(self, working_dir: Optional[str] = None):
        self.working_dir = working_dir or os.getcwd()

    async def execute(
        self,
        prompt: str,
        timeout: int = 120,
    ) -> ExecuteResponse:
        """Execute Claude Code with the given prompt.

        Args:
            prompt: The prompt to send to Claude Code
            timeout: Maximum execution time in seconds

        Returns:
            ExecuteResponse with the result
        """
        if not settings.claude_code_enabled:
            return ExecuteResponse(
                success=False,
                output="",
                error="Claude Code integration is not enabled. Set CLAUDE_CODE_ENABLED=true",
            )

        work_dir = settings.claude_code_working_dir or self.working_dir

        logger.info(f"Executing Claude Code in {work_dir}")
        logger.debug(f"Prompt: {prompt[:100]}...")

        try:
            proc = await asyncio.create_subprocess_exec(
                "claude",
                "--print",
                prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

            output = stdout.decode() if stdout else ""
            error = stderr.decode() if stderr else ""

            if proc.returncode != 0:
                logger.error(f"Claude Code error: {error}")
                return ExecuteResponse(
                    success=False,
                    output=output,
                    error=error or "Unknown error",
                    exit_code=proc.returncode,
                )

            logger.info(f"Claude Code output: {output[:200]}...")

            return ExecuteResponse(
                success=True,
                output=output,
                error=error if error else None,
                exit_code=0,
            )

        except asyncio.TimeoutError:
            logger.error("Claude Code execution timed out")
            return ExecuteResponse(
                success=False,
                output="",
                error=f"Execution timed out after {timeout} seconds",
                exit_code=-1,
            )

        except FileNotFoundError:
            logger.error("Claude Code CLI not found")
            return ExecuteResponse(
                success=False,
                output="",
                error="Claude Code CLI not found. Please install it first.",
                exit_code=-1,
            )

        except Exception as e:
            logger.error(f"Claude Code execution failed: {e}")
            return ExecuteResponse(
                success=False,
                output="",
                error=str(e),
                exit_code=-1,
            )


# ============================================
# Dev Service
# ============================================

class DevService:
    """Core Dev service logic."""

    def __init__(self):
        self.executor = ClaudeCodeExecutor()

    async def handle_message(self, context: MessageContext) -> HandleResponse:
        """Handle development mode message."""
        user_id = context.user_id
        text = context.raw_text

        logger.info(f"DevService: {text[:50]}... from {user_id}")

        if not settings.claude_code_enabled:
            return HandleResponse(
                success=False,
                message="开发模式未启用。请在配置中设置 CLAUDE_CODE_ENABLED=true",
            )

        # Execute via Claude Code
        result = await self.executor.execute(text)

        if result.success:
            # Truncate very long outputs
            output = result.output
            if len(output) > 4000:
                output = output[:4000] + "\n... (输出已截断)"

            return HandleResponse(
                success=True,
                message=output,
                data={
                    "type": "claude_code_response",
                    "exit_code": result.exit_code,
                },
            )
        else:
            return HandleResponse(
                success=False,
                message=f"Claude Code 执行失败: {result.error}",
                data={
                    "type": "claude_code_error",
                    "error": result.error,
                    "exit_code": result.exit_code,
                },
            )


# Global instance
_dev_service: Optional[DevService] = None


def get_dev_service() -> DevService:
    """Get or create Dev service instance."""
    global _dev_service
    if _dev_service is None:
        _dev_service = DevService()
    return _dev_service


# ============================================
# FastAPI Application
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    logger.info("Starting Dev Service...")

    if settings.claude_code_enabled:
        logger.info(f"Claude Code enabled, working dir: {settings.claude_code_working_dir or 'default'}")
    else:
        logger.warning("Claude Code is not enabled")

    yield

    logger.info("Shutting down Dev Service...")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="InvestManager Dev Service",
        description="Development mode with Claude Code integration",
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
            "name": "InvestManager Dev Service",
            "version": "1.0.0",
            "claude_code_enabled": settings.claude_code_enabled,
            "working_dir": settings.claude_code_working_dir or os.getcwd(),
        }

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "dev",
            "claude_code_enabled": settings.claude_code_enabled,
        }

    @app.post("/handle", response_model=HandleResponse)
    async def handle_message(context: MessageContext):
        """Handle a message in development mode.

        This is the main entry point for the gateway service.
        """
        service = get_dev_service()
        return await service.handle_message(context)

    @app.post("/execute", response_model=ExecuteResponse)
    async def execute_claude_code(request: ExecuteRequest):
        """Execute Claude Code directly.

        This endpoint can be used for direct Claude Code execution.
        """
        service = get_dev_service()

        # Override working directory if provided
        if request.working_dir:
            service.executor.working_dir = request.working_dir

        return await service.executor.execute(
            prompt=request.prompt,
            timeout=request.timeout,
        )


# ============================================
# Entry Point
# ============================================

def run_dev_service():
    """Run the Dev service."""
    import uvicorn

    parser = argparse.ArgumentParser(description="InvestManager Dev Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8012, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "services.dev.main:create_app",
        host=args.host,
        port=args.port,
        factory=True,
        reload=args.reload,
    )


if __name__ == "__main__":
    run_dev_service()