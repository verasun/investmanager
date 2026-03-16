"""Task API routes."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from src.orchestrator import TaskOrchestrator, Task, TaskType, TaskPriority, TaskStatus


router = APIRouter()

# Global orchestrator instance
_orchestrator: Optional[TaskOrchestrator] = None


def get_orchestrator() -> TaskOrchestrator:
    """Get or create the orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        # Disable signal handlers for test environments (non-main threads)
        import threading
        is_main_thread = threading.current_thread() is threading.main_thread()
        _orchestrator = TaskOrchestrator(register_signals=is_main_thread)
    return _orchestrator


# Request/Response schemas
class TaskCreateRequest(BaseModel):
    """Request to create a new task."""

    type: str = Field(..., description="Task type: data_fetch, analysis, backtest, report, email")
    input: dict = Field(..., description="Task input parameters")
    name: Optional[str] = Field(None, description="Task name")
    description: Optional[str] = Field(None, description="Task description")
    dependencies: list[str] = Field(default_factory=list, description="Task IDs this task depends on")
    priority: int = Field(5, ge=1, le=20, description="Task priority (1-20)")
    max_retries: int = Field(3, ge=0, le=10, description="Maximum retry attempts")
    tags: list[str] = Field(default_factory=list, description="Task tags")


class TaskResponse(BaseModel):
    """Task response."""

    id: str
    name: str
    type: str
    status: str
    created_at: str
    input: dict
    output: Optional[dict] = None
    error: Optional[str] = None
    dependencies: list[str] = []
    priority: int
    retry_count: int
    max_retries: int
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskListResponse(BaseModel):
    """Task list response."""

    tasks: list[TaskResponse]
    total: int
    status_counts: dict[str, int]


class PipelineRequest(BaseModel):
    """Request to create a task pipeline."""

    symbols: list[str] = Field(..., description="Stock symbols to analyze")
    strategies: Optional[list[str]] = Field(None, description="Strategies to backtest")
    email_recipients: Optional[list[str]] = Field(None, description="Email recipients")
    priority: int = Field(5, description="Task priority")


class PipelineResponse(BaseModel):
    """Pipeline creation response."""

    task_ids: list[str]
    message: str


class OrchestratorStatus(BaseModel):
    """Orchestrator status response."""

    running: bool
    current_task: Optional[str] = None
    queue_size: dict[str, int]


# API Endpoints
@router.post("/tasks", response_model=TaskResponse)
async def create_task(request: TaskCreateRequest):
    """
    Create a new task.

    The task will be queued for execution by the orchestrator.
    """
    try:
        task_type = TaskType(request.type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task type: {request.type}. "
                  f"Valid types: {[t.value for t in TaskType]}"
        )

    task = Task(
        type=task_type,
        input=request.input,
        name=request.name,
        description=request.description,
        dependencies=request.dependencies,
        priority=TaskPriority(request.priority),
        max_retries=request.max_retries,
        tags=request.tags,
    )

    orchestrator = get_orchestrator()
    task_id = orchestrator.submit_task(task)

    return TaskResponse(
        id=task_id,
        name=task.name,
        type=task.type.value,
        status=task.status.value,
        created_at=task.created_at.isoformat(),
        input=task.input,
        dependencies=task.dependencies,
        priority=task.priority.value,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """
    Get task status by ID.

    Returns the current status and details of a task.
    """
    orchestrator = get_orchestrator()
    task_data = orchestrator.get_task_status(task_id)

    if not task_data:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    return TaskResponse(
        id=task_data["id"],
        name=task_data["name"],
        type=task_data["type"],
        status=task_data["status"],
        created_at=task_data["created_at"],
        input=task_data["input"],
        output=task_data.get("output"),
        error=task_data.get("error"),
        dependencies=task_data.get("dependencies", []),
        priority=task_data.get("priority", 5),
        retry_count=task_data.get("retry_count", 0),
        max_retries=task_data.get("max_retries", 3),
        started_at=task_data.get("started_at"),
        completed_at=task_data.get("completed_at"),
    )


@router.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    List tasks with optional filtering.

    Query parameters:
    - status: Filter by status (pending, running, completed, failed)
    - limit: Maximum number of tasks to return
    - offset: Pagination offset
    """
    orchestrator = get_orchestrator()
    queue = orchestrator.task_queue

    if status:
        try:
            task_status = TaskStatus(status)
            tasks = queue.get_by_status(task_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}"
            )
    else:
        tasks = queue.get_all(limit=limit, offset=offset)

    # Count by status
    status_counts = {
        "pending": queue.count(TaskStatus.PENDING),
        "queued": queue.count(TaskStatus.QUEUED),
        "running": queue.count(TaskStatus.RUNNING),
        "completed": queue.count(TaskStatus.COMPLETED),
        "failed": queue.count(TaskStatus.FAILED),
        "retrying": queue.count(TaskStatus.RETRYING),
    }

    return TaskListResponse(
        tasks=[
            TaskResponse(
                id=t.id,
                name=t.name,
                type=t.type.value,
                status=t.status.value,
                created_at=t.created_at.isoformat(),
                input=t.input,
                output=t.output,
                error=t.error,
                dependencies=t.dependencies,
                priority=t.priority.value,
                retry_count=t.retry_count,
                max_retries=t.max_retries,
                started_at=t.started_at.isoformat() if t.started_at else None,
                completed_at=t.completed_at.isoformat() if t.completed_at else None,
            )
            for t in tasks
        ],
        total=sum(status_counts.values()),
        status_counts=status_counts,
    )


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    Cancel a pending task.

    Only pending or queued tasks can be cancelled.
    """
    orchestrator = get_orchestrator()
    success = orchestrator.cancel_task(task_id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel task {task_id}. Task may already be running or completed."
        )

    return {"message": f"Task {task_id} cancelled", "task_id": task_id}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: str):
    """
    Retry a failed task.

    Only failed tasks can be retried.
    """
    orchestrator = get_orchestrator()
    success = orchestrator.retry_task(task_id)

    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry task {task_id}. Task must be in failed status."
        )

    return {"message": f"Task {task_id} scheduled for retry", "task_id": task_id}


@router.post("/tasks/pipeline", response_model=PipelineResponse)
async def create_pipeline(request: PipelineRequest):
    """
    Create a complete analysis pipeline.

    Creates a chain of tasks: data_fetch -> analysis -> backtest -> report -> email
    """
    orchestrator = get_orchestrator()

    task_ids = orchestrator.submit_pipeline(
        symbols=request.symbols,
        strategies=request.strategies,
        email_recipients=request.email_recipients,
        priority=TaskPriority(request.priority),
    )

    return PipelineResponse(
        task_ids=task_ids,
        message=f"Created pipeline with {len(task_ids)} tasks",
    )


@router.get("/status", response_model=OrchestratorStatus)
async def get_status():
    """
    Get orchestrator status.

    Returns current state and queue statistics.
    """
    orchestrator = get_orchestrator()
    stats = orchestrator.get_stats()

    return OrchestratorStatus(**stats)


@router.post("/cleanup")
async def cleanup_tasks(days: int = 7):
    """
    Clean up old completed tasks.

    Removes completed and cancelled tasks older than specified days.
    """
    orchestrator = get_orchestrator()
    deleted = orchestrator.task_queue.cleanup_completed(days=days)

    return {
        "message": f"Cleaned up {deleted} old tasks",
        "deleted_count": deleted,
    }