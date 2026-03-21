"""Execution Context - State management during execution."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ExecutionContext:
    """Context for execution of a plan.

    Holds state and data shared across steps during execution.
    """

    task_id: str
    user_id: Optional[str] = None
    trace_id: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    variables: dict = field(default_factory=dict)  # Shared variables between steps
    step_results: dict = field(default_factory=dict)  # Results by step_id
    metadata: dict = field(default_factory=dict)

    def set_variable(self, key: str, value: Any) -> None:
        """Set a shared variable."""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a shared variable."""
        return self.variables.get(key, default)

    def set_step_result(self, step_id: str, result: Any) -> None:
        """Store result for a step."""
        self.step_results[step_id] = {
            "result": result,
            "timestamp": datetime.now().isoformat(),
        }

    def get_step_result(self, step_id: str) -> Optional[Any]:
        """Get result for a step."""
        data = self.step_results.get(step_id)
        if data:
            return data.get("result")
        return None

    def get_all_results(self) -> dict:
        """Get all step results."""
        return {k: v.get("result") for k, v in self.step_results.items()}

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "user_id": self.user_id,
            "trace_id": self.trace_id,
            "started_at": self.started_at.isoformat(),
            "variables": self.variables,
            "step_results": self.step_results,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionResult:
    """Result of executing a plan."""

    success: bool
    task_id: str
    steps: list = field(default_factory=list)
    final_output: str = ""
    error: Optional[str] = None
    duration_ms: int = 0
    context: Optional[ExecutionContext] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "task_id": self.task_id,
            "steps": [s.to_dict() if hasattr(s, "to_dict") else str(s) for s in self.steps],
            "final_output": self.final_output,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }