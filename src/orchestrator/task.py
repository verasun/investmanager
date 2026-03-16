"""Task and TaskResult data models."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class TaskType(Enum):
    """Task type enumeration."""

    DATA_FETCH = "data_fetch"
    ANALYSIS = "analysis"
    BACKTEST = "backtest"
    REPORT = "report"
    EMAIL = "email"
    PIPELINE = "pipeline"  # Composite task with multiple steps


class TaskStatus(Enum):
    """Task status enumeration."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 1
    NORMAL = 5
    HIGH = 10
    URGENT = 20


@dataclass
class Task:
    """
    Standard task definition.

    Tasks are the basic unit of work in the orchestrator.
    They can have dependencies on other tasks and support
    automatic retry on failure.
    """

    type: TaskType
    input: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    name: Optional[str] = None
    description: Optional[str] = None
    dependencies: list[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Set default name if not provided."""
        if self.name is None:
            self.name = f"{self.type.value}_{self.id}"

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "input": self.input,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "priority": self.priority.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "output": self.output,
            "error": self.error,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        """Create task from dictionary."""
        return cls(
            id=data["id"],
            name=data.get("name"),
            type=TaskType(data["type"]),
            description=data.get("description"),
            input=data["input"],
            dependencies=data.get("dependencies", []),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", 5)),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            output=data.get("output"),
            error=data.get("error"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )

    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.retry_count < self.max_retries

    def mark_running(self) -> None:
        """Mark task as running."""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, output: Optional[dict[str, Any]] = None) -> None:
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        self.output = output

    def mark_failed(self, error: str, retry: bool = True) -> None:
        """Mark task as failed."""
        if retry and self.can_retry():
            self.retry_count += 1
            self.status = TaskStatus.RETRYING
        else:
            self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()


@dataclass
class TaskResult:
    """
    Task execution result.

    Returned by task runners after executing a task.
    Contains success status, output data, and metrics.
    """

    task_id: str
    success: bool
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    memory_used_mb: Optional[float] = None
    artifacts: list[str] = field(default_factory=list)  # File paths produced

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time": self.execution_time,
            "memory_used_mb": self.memory_used_mb,
            "artifacts": self.artifacts,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskResult":
        """Create result from dictionary."""
        return cls(
            task_id=data["task_id"],
            success=data["success"],
            output=data.get("output"),
            error=data.get("error"),
            execution_time=data.get("execution_time", 0.0),
            memory_used_mb=data.get("memory_used_mb"),
            artifacts=data.get("artifacts", []),
        )


@dataclass
class PipelineTask(Task):
    """
    A pipeline task that contains multiple sub-tasks.

    Pipeline tasks execute their sub-tasks sequentially,
    passing output from one task to the next.
    """

    steps: list[Task] = field(default_factory=list)
    current_step: int = 0

    def __post_init__(self):
        """Set type to PIPELINE."""
        self.type = TaskType.PIPELINE
        if self.name is None:
            self.name = f"pipeline_{self.id}"

    def to_dict(self) -> dict[str, Any]:
        """Convert pipeline task to dictionary."""
        data = super().to_dict()
        data["steps"] = [step.to_dict() for step in self.steps]
        data["current_step"] = self.current_step
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineTask":
        """Create pipeline task from dictionary."""
        steps = [Task.from_dict(step) for step in data.get("steps", [])]
        return cls(
            id=data["id"],
            name=data.get("name"),
            description=data.get("description"),
            steps=steps,
            current_step=data.get("current_step", 0),
            input=data.get("input", {}),
            dependencies=data.get("dependencies", []),
            status=TaskStatus(data.get("status", "pending")),
            priority=TaskPriority(data.get("priority", 5)),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            output=data.get("output"),
            error=data.get("error"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )