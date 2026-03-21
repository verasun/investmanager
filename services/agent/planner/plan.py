"""Execution Plan - Data structures for task planning."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class StepStatus(str, Enum):
    """Status of an execution step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Step:
    """A single step in the execution plan."""

    id: str
    description: str
    tool_name: Optional[str] = None
    parameters: dict = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def is_ready(self, completed_step_ids: set[str]) -> bool:
        """Check if this step is ready to execute.

        Args:
            completed_step_ids: Set of completed step IDs

        Returns:
            True if all dependencies are satisfied
        """
        return all(dep in completed_step_ids for dep in self.dependencies)

    def mark_running(self) -> None:
        """Mark step as running."""
        self.status = StepStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, result: Any = None) -> None:
        """Mark step as completed."""
        self.status = StepStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """Mark step as failed."""
        self.status = StepStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "description": self.description,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "error": self.error,
        }


@dataclass
class ExecutionPlan:
    """A complete execution plan for a task."""

    task_id: str
    goal: str
    steps: list[Step] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    context: dict = field(default_factory=dict)

    def get_step(self, step_id: str) -> Optional[Step]:
        """Get a step by ID.

        Args:
            step_id: Step ID

        Returns:
            Step or None if not found
        """
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_ready_steps(self) -> list[Step]:
        """Get steps that are ready to execute.

        Returns:
            List of steps with satisfied dependencies
        """
        completed_ids = {
            s.id for s in self.steps if s.status == StepStatus.COMPLETED
        }

        return [
            s for s in self.steps
            if s.status == StepStatus.PENDING and s.is_ready(completed_ids)
        ]

    def get_running_steps(self) -> list[Step]:
        """Get currently running steps."""
        return [s for s in self.steps if s.status == StepStatus.RUNNING]

    def get_failed_steps(self) -> list[Step]:
        """Get failed steps."""
        return [s for s in self.steps if s.status == StepStatus.FAILED]

    def is_complete(self) -> bool:
        """Check if all steps are complete (completed or skipped)."""
        return all(
            s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
            for s in self.steps
        )

    def has_failures(self) -> bool:
        """Check if any steps have failed."""
        return any(s.status == StepStatus.FAILED for s in self.steps)

    def progress(self) -> tuple[int, int]:
        """Get progress as (completed, total).

        Returns:
            Tuple of completed steps and total steps
        """
        completed = sum(
            1 for s in self.steps
            if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
        )
        return completed, len(self.steps)

    def get_execution_order(self) -> list[list[str]]:
        """Get steps grouped by execution order (parallel groups).

        Returns:
            List of lists, where each inner list contains step IDs
            that can be executed in parallel
        """
        result = []
        remaining = {s.id: s for s in self.steps}
        completed = set()

        while remaining:
            # Find steps with all dependencies met
            ready = [
                s_id for s_id, s in remaining.items()
                if all(d in completed for d in s.dependencies)
            ]

            if not ready:
                # Circular dependency or error
                break

            result.append(ready)
            for s_id in ready:
                completed.add(s_id)
                del remaining[s_id]

        return result

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        completed, total = self.progress()
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at.isoformat(),
            "progress": {
                "completed": completed,
                "total": total,
                "percentage": round(completed / total * 100, 1) if total > 0 else 0,
            },
        }

    def __repr__(self) -> str:
        completed, total = self.progress()
        return f"<ExecutionPlan {self.task_id}: {completed}/{total} steps>"


class PlanRequest(BaseModel):
    """Request for plan generation."""

    goal: str
    context: dict = {}
    available_tools: list[str] = []
    constraints: dict = {}


class PlanResponse(BaseModel):
    """Response from plan generation."""

    success: bool
    plan: Optional[ExecutionPlan] = None
    error: Optional[str] = None
    reasoning: Optional[str] = None