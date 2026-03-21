"""Intelligent model router.

Routes requests to the best model based on task type, capabilities, and scores.
"""

import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from loguru import logger

from .model_registry import ModelRegistry, ModelCapability, Capability, get_model_registry
from .score_manager import ScoreManager, get_score_manager
from .score_calculator import ScoreCalculator, ScoreWeights


class TaskType(str, Enum):
    """Task types for model routing."""
    TEXT = "text"
    DEEP_THINKING = "deep_thinking"
    VISUAL = "visual"
    CODING = "coding"
    CONSENSUS = "consensus"  # Special: requires multiple models


@dataclass
class RoutingDecision:
    """Result of a routing decision."""
    selected_model: str
    task_type: TaskType
    capability: Capability
    score: float
    is_exploration: bool  # True if using lower-ranked model for exploration
    alternatives: list[str]  # Fallback models


class ModelRouter:
    """Routes requests to the best model based on task type and scores."""

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        score_manager: Optional[ScoreManager] = None,
        exploration_rate: float = 0.1,  # 10% of requests explore lower-ranked models
        quality_weight: float = 0.5,
        latency_weight: float = 0.3,
        cost_weight: float = 0.2,
    ):
        self.registry = registry or get_model_registry()
        self.score_manager = score_manager or get_score_manager()
        self.exploration_rate = exploration_rate
        self.calculator = ScoreCalculator(
            quality_weight=quality_weight,
            latency_weight=latency_weight,
            cost_weight=cost_weight,
        )
        self.weights = ScoreWeights(
            quality=quality_weight,
            latency=latency_weight,
            cost=cost_weight,
        )

    def _task_to_capability(self, task_type: TaskType) -> Capability:
        """Map task type to capability."""
        mapping = {
            TaskType.TEXT: Capability.TEXT,
            TaskType.DEEP_THINKING: Capability.DEEP_THINKING,
            TaskType.VISUAL: Capability.VISUAL,
            TaskType.CODING: Capability.CODING,
            TaskType.CONSENSUS: Capability.DEEP_THINKING,  # Consensus uses deep thinking
        }
        return mapping.get(task_type, Capability.TEXT)

    async def _get_model_scores(
        self,
        models: list[ModelCapability],
        capability: Capability,
    ) -> list[tuple[ModelCapability, float]]:
        """Get scored models for a capability.

        Returns:
            List of (model, weighted_score) tuples, sorted by score descending
        """
        scored = []
        scenario = capability.value

        for model in models:
            score = await self.score_manager.get_score(model.model_id, scenario)
            weighted = self.calculator.calculate_weighted_score(score, self.weights)
            scored.append((model, weighted))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    async def select_model(
        self,
        task_type: TaskType,
        preferred_models: Optional[list[str]] = None,
        exclude_models: Optional[list[str]] = None,
    ) -> RoutingDecision:
        """Select the best model for a task.

        Args:
            task_type: Type of task
            preferred_models: Optional list of preferred models (restricts selection)
            exclude_models: Optional list of models to exclude

        Returns:
            RoutingDecision with selected model and metadata
        """
        capability = self._task_to_capability(task_type)

        # Get candidate models
        if preferred_models:
            candidates = [
                self.registry.get(m) for m in preferred_models
                if self.registry.get(m) is not None
            ]
        else:
            candidates = self.registry.get_by_capability(capability)

        # Filter excluded models
        if exclude_models:
            candidates = [
                m for m in candidates
                if m.model_id not in exclude_models
            ]

        if not candidates:
            # Fallback to any available model
            candidates = self.registry.get_all()
            if not candidates:
                raise RuntimeError("No models available for routing")

        # Get scored candidates
        scored = await self._get_model_scores(candidates, capability)

        # Determine if this is an exploration request
        is_exploration = (
            len(scored) > 1 and
            random.random() < self.exploration_rate
        )

        if is_exploration:
            # Pick a random model from lower half for exploration
            lower_half = scored[len(scored) // 2:]
            if lower_half:
                selected_model, score = random.choice(lower_half)
            else:
                selected_model, score = scored[0]
        else:
            # Pick top model
            selected_model, score = scored[0]

        # Get alternatives for fallback
        alternatives = [m.model_id for m, _ in scored[1:4] if m.model_id != selected_model.model_id]

        logger.debug(
            f"Routed {task_type.value} task to {selected_model.model_id} "
            f"(score: {score:.3f}, exploration: {is_exploration})"
        )

        return RoutingDecision(
            selected_model=selected_model.model_id,
            task_type=task_type,
            capability=capability,
            score=score,
            is_exploration=is_exploration,
            alternatives=alternatives,
        )

    async def select_consensus_models(
        self,
        task_type: TaskType = TaskType.CONSENSUS,
        min_models: int = 3,
        preferred_models: Optional[list[str]] = None,
    ) -> tuple[list[str], str]:
        """Select multiple models for consensus.

        Args:
            task_type: Type of task
            min_models: Minimum number of models to select
            preferred_models: Optional preferred models

        Returns:
            Tuple of (model_ids, arbitrator_model_id)
        """
        capability = self._task_to_capability(task_type)

        # Get candidate models
        if preferred_models:
            candidates = [
                self.registry.get(m) for m in preferred_models
                if self.registry.get(m) is not None
            ]
        else:
            candidates = self.registry.get_by_capability(capability)

        # Ensure we have enough models
        if len(candidates) < min_models:
            # Add more models from all available
            all_models = self.registry.get_all()
            for model in all_models:
                if model not in candidates:
                    candidates.append(model)
                    if len(candidates) >= min_models:
                        break

        # Get scored candidates
        scored = await self._get_model_scores(candidates, capability)

        # Select top min_models
        selected = [m.model_id for m, _ in scored[:min_models]]

        # Top model becomes arbitrator
        arbitrator = selected[0] if selected else None

        logger.info(
            f"Selected {len(selected)} models for consensus: {selected}, "
            f"arbitrator: {arbitrator}"
        )

        return selected, arbitrator

    async def get_model_rankings(
        self,
        task_type: TaskType,
    ) -> list[dict]:
        """Get ranked list of models for a task type.

        Returns:
            List of dicts with model_id, score, rank
        """
        capability = self._task_to_capability(task_type)
        candidates = self.registry.get_by_capability(capability)
        scored = await self._get_model_scores(candidates, capability)

        return [
            {
                "rank": i + 1,
                "model_id": model.model_id,
                "display_name": model.display_name,
                "score": score,
            }
            for i, (model, score) in enumerate(scored)
        ]


# Global router instance
_router: Optional[ModelRouter] = None


def get_model_router() -> ModelRouter:
    """Get or create the global model router."""
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router