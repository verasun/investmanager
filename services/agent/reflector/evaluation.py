"""Reflection Result - Data structures for evaluation."""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StepEvaluation:
    """Evaluation of a single step."""

    step_id: str
    success: bool
    score: float = 0.0  # 0.0 to 1.0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ReflectionResult:
    """Result of reflection on execution."""

    goal_achieved: bool = False
    partial_achievement: float = 0.0  # 0.0 to 1.0
    step_evaluations: list[StepEvaluation] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    failure_reasons: dict[str, str] = field(default_factory=dict)
    corrections: list[dict] = field(default_factory=list)
    should_retry: bool = False
    summary: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "goal_achieved": self.goal_achieved,
            "partial_achievement": self.partial_achievement,
            "failed_steps": self.failed_steps,
            "failure_reasons": self.failure_reasons,
            "corrections": self.corrections,
            "should_retry": self.should_retry,
            "summary": self.summary,
        }