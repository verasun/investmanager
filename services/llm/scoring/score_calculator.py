"""Score calculation logic for model performance.

Calculates quality, latency, and cost scores from execution results
with rolling average and decay for recent performance emphasis.
"""

from dataclasses import dataclass
from typing import Optional
from loguru import logger

from .score_manager import ModelScore, ExecutionRecord


@dataclass
class ScoreWeights:
    """Weights for score calculation."""
    quality: float = 0.5
    latency: float = 0.3
    cost: float = 0.2


# Score thresholds for normalization
LATENCY_THRESHOLDS = {
    "fast": 1000,      # < 1s is excellent
    "medium": 3000,    # 1-3s is acceptable
    "slow": 10000,     # 3-10s is slow
}

# Cost thresholds (per 1k tokens, USD)
COST_THRESHOLDS = {
    "cheap": 0.001,
    "medium": 0.005,
    "expensive": 0.01,
}

# Decay factor for rolling average (0-1, higher = more weight to recent)
DECAY_FACTOR = 0.7


class ScoreCalculator:
    """Calculates model scores from execution results."""

    def __init__(
        self,
        quality_weight: float = 0.5,
        latency_weight: float = 0.3,
        cost_weight: float = 0.2,
    ):
        self.weights = ScoreWeights(
            quality=quality_weight,
            latency=latency_weight,
            cost=cost_weight,
        )

    def calculate_quality_score(
        self,
        success: bool,
        explicit_feedback: Optional[int] = None,
        implicit_feedback: Optional[dict] = None,
    ) -> float:
        """Calculate quality score from feedback.

        Args:
            success: Whether the execution succeeded
            explicit_feedback: User rating 1-5 (or None)
            implicit_feedback: Behavioral signals {"reasked": bool, "followup_count": int}

        Returns:
            Quality score 0-1
        """
        base_score = 1.0 if success else 0.0

        # Explicit feedback (1-5 stars) -> 0-1 score
        if explicit_feedback is not None:
            # 5 stars = 1.0, 1 star = 0.0
            explicit_score = (explicit_feedback - 1) / 4.0
            # Weight explicit feedback heavily
            base_score = 0.3 * base_score + 0.7 * explicit_score

        # Implicit feedback adjustments
        if implicit_feedback:
            adjustments = []

            # Reask is negative signal
            if implicit_feedback.get("reasked"):
                adjustments.append(-0.2)

            # Positive acknowledgment is positive signal
            if implicit_feedback.get("positive_ack"):
                adjustments.append(+0.1)

            # Follow-up questions could be engagement (slight positive)
            followup_count = implicit_feedback.get("followup_count", 0)
            if followup_count > 0:
                # Up to +0.1 for engagement
                adjustments.append(min(0.1, followup_count * 0.02))

            # Time to next message (faster = more satisfied)
            time_to_next = implicit_feedback.get("time_to_next_ms", 0)
            if time_to_next > 0:
                # Very fast response (< 10s) might be reask, slow (> 5min) might be ignore
                if time_to_next < 10000:
                    # Could be reask - slight negative
                    adjustments.append(-0.05)
                elif time_to_next > 300000:
                    # Ignored - negative
                    adjustments.append(-0.1)

            # Apply adjustments
            for adj in adjustments:
                base_score += adj

        # Clamp to 0-1
        return max(0.0, min(1.0, base_score))

    def calculate_latency_score(
        self,
        latency_ms: int,
        expected_tier: str = "medium",
    ) -> float:
        """Calculate latency score based on response time.

        Args:
            latency_ms: Actual latency in milliseconds
            expected_tier: Expected performance tier (fast/medium/slow)

        Returns:
            Latency score 0-1
        """
        threshold = LATENCY_THRESHOLDS.get(expected_tier, LATENCY_THRESHOLDS["medium"])

        if latency_ms <= threshold * 0.5:
            # Much faster than expected - excellent
            return 1.0
        elif latency_ms <= threshold:
            # Within expected range
            return 0.8 + 0.2 * (threshold - latency_ms) / threshold
        elif latency_ms <= threshold * 2:
            # Slower than expected
            return 0.5 + 0.3 * (threshold * 2 - latency_ms) / threshold
        elif latency_ms <= threshold * 5:
            # Much slower
            return 0.2 + 0.3 * (threshold * 5 - latency_ms) / (threshold * 3)
        else:
            # Unacceptably slow
            return max(0.0, 0.1)

    def calculate_cost_score(
        self,
        tokens_used: int,
        cost_per_1k: float,
    ) -> float:
        """Calculate cost efficiency score.

        Args:
            tokens_used: Total tokens used
            cost_per_1k: Cost per 1000 tokens in USD

        Returns:
            Cost score 0-1 (higher = more cost efficient)
        """
        if cost_per_1k <= COST_THRESHOLDS["cheap"]:
            return 1.0
        elif cost_per_1k <= COST_THRESHOLDS["medium"]:
            return 0.8
        elif cost_per_1k <= COST_THRESHOLDS["expensive"]:
            return 0.5
        else:
            return 0.2

    def update_rolling_score(
        self,
        current_score: float,
        new_score: float,
        sample_count: int,
        decay_factor: float = DECAY_FACTOR,
    ) -> float:
        """Update score using rolling average with decay.

        Args:
            current_score: Current average score
            new_score: New score to incorporate
            sample_count: Number of previous samples
            decay_factor: Weight for new score (0-1)

        Returns:
            Updated average score
        """
        if sample_count == 0:
            return new_score

        # Exponential moving average
        return decay_factor * new_score + (1 - decay_factor) * current_score

    def calculate_updated_score(
        self,
        current: ModelScore,
        record: ExecutionRecord,
        cost_per_1k: float = 0.001,
        latency_tier: str = "medium",
    ) -> ModelScore:
        """Calculate updated model score from execution record.

        Args:
            current: Current model score
            record: New execution record
            cost_per_1k: Cost per 1k tokens
            latency_tier: Expected latency tier

        Returns:
            Updated model score
        """
        # Calculate individual scores
        new_quality = self.calculate_quality_score(
            success=record.success,
            explicit_feedback=record.explicit_feedback,
            implicit_feedback=record.implicit_feedback,
        )

        new_latency = self.calculate_latency_score(
            latency_ms=record.latency_ms,
            expected_tier=latency_tier,
        )

        new_cost = self.calculate_cost_score(
            tokens_used=record.tokens_used,
            cost_per_1k=cost_per_1k,
        )

        # Update with rolling average
        updated_quality = self.update_rolling_score(
            current.quality_score,
            new_quality,
            current.sample_count,
        )

        updated_latency = self.update_rolling_score(
            current.latency_score,
            new_latency,
            current.sample_count,
        )

        updated_cost = self.update_rolling_score(
            current.cost_score,
            new_cost,
            current.sample_count,
        )

        # Satisfaction follows quality
        updated_satisfaction = updated_quality

        return ModelScore(
            model_id=current.model_id,
            scenario=current.scenario,
            quality_score=updated_quality,
            latency_score=updated_latency,
            cost_score=updated_cost,
            satisfaction_score=updated_satisfaction,
            sample_count=current.sample_count + 1,
        )

    def calculate_weighted_score(
        self,
        score: ModelScore,
        custom_weights: Optional[ScoreWeights] = None,
    ) -> float:
        """Calculate overall weighted score.

        Args:
            score: Model score to evaluate
            custom_weights: Optional custom weights

        Returns:
            Weighted overall score 0-1
        """
        weights = custom_weights or self.weights
        return (
            score.quality_score * weights.quality +
            score.latency_score * weights.latency +
            score.cost_score * weights.cost
        )