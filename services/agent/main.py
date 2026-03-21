#!/usr/bin/env python
"""Agent Service - FastAPI entry point.

This service provides a full agentic capabilities for InvestManager,
including task planning, tool execution, and autonomous scheduling.

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                         AGENT SERVICE (:8002)                       │
├─────────────────────────────────────────────────────────────────────┤
│  Endpoints:                                                         │
│  - POST /run          Run agent on user request                     │
│  - POST /schedule     Create scheduled task                         │
│  - GET  /tasks        List scheduled tasks                          │
│  - DELETE /tasks/:id  Cancel scheduled task                         │
│  - GET  /history      Get task history                              │
│  - GET  /tools        List available tools                          │
│  - GET  /health       Health check                                  │
└─────────────────────────────────────────────────────────────────────┘
"""

import argparse
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
# Request/Response Models
# ============================================

class RunRequest(BaseModel):
    """Request to run the agent."""
    prompt: str
    user_id: Optional[str] = None
    context: dict = {}


class RunResponse(BaseModel):
    """Response from agent execution."""
    trace_id: str
    success: bool
    output: str
    steps: list = []
    duration_ms: int = 0


class ScheduleRequest(BaseModel):
    """Request to create a scheduled task."""
    user_id: str
    name: str
    prompt: str
    trigger_type: str  # cron, interval, price, news
    trigger_config: dict
    notify_on_complete: bool = True


class ScheduleResponse(BaseModel):
    """Response from scheduling."""
    task_id: str
    name: str
    trigger_type: str
    next_run: Optional[str] = None


class TaskInfo(BaseModel):
    """Information about a task."""
    id: str
    user_id: str
    name: str
    prompt: str
    trigger_type: str
    enabled: bool
    last_run: Optional[str] = None
    next_run: Optional[str] = None
    run_count: int = 0


class ToolInfo(BaseModel):
    """Information about a tool."""
    name: str
    description: str
    parameters: dict


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    tools_count: int
    scheduler_running: bool


# ============================================
# Lifespan
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan."""
    from services.agent.service import get_agent_service

    # Startup
    logger.info("Starting Agent Service...")
    agent = get_agent_service()

    # Initialize LLM provider if available
    if settings.alibaba_bailian_api_key:
        from services.llm.providers import LLMProviderFactory
        provider = LLMProviderFactory.create(
            provider_type="multi_model",
            api_key=settings.alibaba_bailian_api_key,
        )
        agent.set_llm_provider(provider)
        logger.info("LLM provider initialized")

    # Start scheduler if enabled
    if settings.scheduler_enabled:
        await agent.start_scheduler()
        logger.info("Scheduler started")

    yield

    # Shutdown
    logger.info("Stopping Agent Service...")
    await agent.stop_scheduler()


# ============================================
# FastAPI App
# ============================================

app = FastAPI(
    title="InvestManager Agent Service",
    description="Full agentic capabilities for InvestManager",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# Endpoints
# ============================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    from services.agent.service import get_agent_service
    from services.agent.scheduler import get_scheduler

    agent = get_agent_service()
    scheduler = get_scheduler()

    return HealthResponse(
        status="healthy",
        tools_count=len(agent.tools),
        scheduler_running=scheduler._running if hasattr(scheduler, "_running") else False,
    )


@app.post("/run", response_model=RunResponse)
async def run_agent(request: RunRequest):
    """Run the agent on a user request."""
    from services.agent.service import get_agent_service

    agent = get_agent_service()

    try:
        result = await agent.run(
            user_request=request.prompt,
            user_id=request.user_id,
            context=request.context,
        )

        return RunResponse(
            trace_id=result.trace_id,
            success=result.success,
            output=result.output,
            steps=[s.to_dict() if hasattr(s, "to_dict") else str(s) for s in result.steps],
            duration_ms=result.duration_ms,
        )

    except Exception as e:
        logger.error(f"Agent execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/schedule", response_model=ScheduleResponse)
async def create_schedule(request: ScheduleRequest):
    """Create a scheduled task."""
    from services.agent.service import get_agent_service
    from services.agent.scheduler import (
        CronTrigger,
        IntervalTrigger,
        PriceTrigger,
        NewsTrigger,
    )

    agent = get_agent_service()

    # Create trigger based on type
    if request.trigger_type == "cron":
        trigger = CronTrigger(
            hour=request.trigger_config.get("hour", 9),
            minute=request.trigger_config.get("minute", 0),
        )
    elif request.trigger_type == "interval":
        trigger = IntervalTrigger(
            seconds=request.trigger_config.get("seconds", 3600),
        )
    elif request.trigger_type == "price":
        trigger = PriceTrigger(
            symbol=request.trigger_config.get("symbol", ""),
            target_price=request.trigger_config.get("target_price", 0),
            condition=request.trigger_config.get("condition", "above"),
        )
    elif request.trigger_type == "news":
        trigger = NewsTrigger(
            keywords=request.trigger_config.get("keywords", []),
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown trigger type: {request.trigger_type}")

    try:
        task = await agent.schedule_task(
            user_id=request.user_id,
            name=request.name,
            prompt=request.prompt,
            trigger=trigger,
            notify_on_complete=request.notify_on_complete,
        )

        return ScheduleResponse(
            task_id=task.id,
            name=task.name,
            trigger_type=request.trigger_type,
            next_run=task.next_run.isoformat() if task.next_run else None,
        )

    except Exception as e:
        logger.error(f"Schedule creation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tasks", response_model=list[TaskInfo])
async def list_tasks(user_id: Optional[str] = None):
    """List scheduled tasks."""
    from services.agent.service import get_agent_service

    agent = get_agent_service()
    tasks = await agent.list_scheduled_tasks(user_id)

    return [
        TaskInfo(
            id=t.id,
            user_id=t.user_id,
            name=t.name,
            prompt=t.prompt,
            trigger_type=t.trigger.trigger_type.value,
            enabled=t.enabled,
            last_run=t.last_run.isoformat() if t.last_run else None,
            next_run=t.next_run.isoformat() if t.next_run else None,
            run_count=t.run_count,
        )
        for t in tasks
    ]


@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    """Cancel a scheduled task."""
    from services.agent.service import get_agent_service

    agent = get_agent_service()
    success = await agent.cancel_scheduled_task(task_id)

    if not success:
        raise HTTPException(status_code=404, detail="Task not found")

    return {"status": "cancelled", "task_id": task_id}


@app.get("/history/{user_id}")
async def get_history(user_id: str, limit: int = 10):
    """Get task history for a user."""
    from services.agent.service import get_agent_service

    agent = get_agent_service()
    history = await agent.get_task_history(user_id, limit)

    return {"user_id": user_id, "tasks": history}


@app.get("/tools", response_model=list[ToolInfo])
async def list_tools():
    """List available tools."""
    from services.agent.service import get_agent_service

    agent = get_agent_service()
    tools = agent.tools.list_tools()

    return [
        ToolInfo(
            name=t.name,
            description=t.description,
            parameters=t.parameters,
        )
        for t in tools
    ]


# ============================================
# Entry Point
# ============================================

def run_agent_service():
    """Run the agent service."""
    import uvicorn

    parser = argparse.ArgumentParser(description="InvestManager Agent Service")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8002, help="Port to bind")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    uvicorn.run(
        "services.agent.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    run_agent_service()