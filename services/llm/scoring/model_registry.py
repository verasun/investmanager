"""Model capability registry.

Defines available models and their capabilities for intelligent routing.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from loguru import logger


class Capability(str, Enum):
    """Model capability types."""
    TEXT = "text"                    # General text generation
    DEEP_THINKING = "deep_thinking"  # Complex reasoning, analysis
    VISUAL = "visual"                # Image understanding
    CODING = "coding"                # Code generation/analysis


@dataclass
class ModelCapability:
    """Model capability and metadata."""
    model_id: str
    display_name: str
    capabilities: list[Capability]
    max_tokens: int = 4096
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0
    supports_tools: bool = True
    supports_vision: bool = False
    latency_tier: str = "medium"  # fast, medium, slow

    def has_capability(self, capability: Capability) -> bool:
        """Check if model has a specific capability."""
        return capability in self.capabilities

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "model_id": self.model_id,
            "display_name": self.display_name,
            "capabilities": [c.value for c in self.capabilities],
            "max_tokens": self.max_tokens,
            "cost_per_1k_input_tokens": self.cost_per_1k_input_tokens,
            "cost_per_1k_output_tokens": self.cost_per_1k_output_tokens,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
            "latency_tier": self.latency_tier,
        }


# Default models available on Alibaba Bailian platform
DEFAULT_MODELS: list[ModelCapability] = [
    ModelCapability(
        model_id="qwen3.5-plus",
        display_name="Qwen 3.5 Plus",
        capabilities=[Capability.TEXT, Capability.DEEP_THINKING, Capability.VISUAL],
        max_tokens=32768,
        cost_per_1k_input_tokens=0.0004,
        cost_per_1k_output_tokens=0.002,
        supports_vision=True,
        latency_tier="fast",
    ),
    ModelCapability(
        model_id="qwen3-max-2026-01-23",
        display_name="Qwen 3 Max",
        capabilities=[Capability.TEXT, Capability.DEEP_THINKING],
        max_tokens=32768,
        cost_per_1k_input_tokens=0.002,
        cost_per_1k_output_tokens=0.006,
        latency_tier="medium",
    ),
    ModelCapability(
        model_id="qwen3-coder-next",
        display_name="Qwen 3 Coder Next",
        capabilities=[Capability.TEXT, Capability.CODING],
        max_tokens=32768,
        cost_per_1k_input_tokens=0.0005,
        cost_per_1k_output_tokens=0.002,
        latency_tier="fast",
    ),
    ModelCapability(
        model_id="qwen3-coder-plus",
        display_name="Qwen 3 Coder Plus",
        capabilities=[Capability.TEXT, Capability.CODING],
        max_tokens=16384,
        cost_per_1k_input_tokens=0.0003,
        cost_per_1k_output_tokens=0.001,
        latency_tier="fast",
    ),
    ModelCapability(
        model_id="glm-5",
        display_name="GLM-5",
        capabilities=[Capability.TEXT, Capability.DEEP_THINKING],
        max_tokens=8192,
        cost_per_1k_input_tokens=0.001,
        cost_per_1k_output_tokens=0.001,
        latency_tier="medium",
    ),
    ModelCapability(
        model_id="kimi-k2.5",
        display_name="Kimi K2.5",
        capabilities=[Capability.TEXT, Capability.DEEP_THINKING, Capability.VISUAL],
        max_tokens=128000,
        cost_per_1k_input_tokens=0.0005,
        cost_per_1k_output_tokens=0.002,
        supports_vision=True,
        latency_tier="medium",
    ),
    ModelCapability(
        model_id="MiniMax-M2.5",
        display_name="MiniMax M2.5",
        capabilities=[Capability.TEXT, Capability.DEEP_THINKING],
        max_tokens=16384,
        cost_per_1k_input_tokens=0.001,
        cost_per_1k_output_tokens=0.002,
        latency_tier="medium",
    ),
]


class ModelRegistry:
    """Registry for available models and their capabilities."""

    def __init__(self):
        self._models: dict[str, ModelCapability] = {}
        self._load_default_models()

    def _load_default_models(self):
        """Load default model configurations."""
        for model in DEFAULT_MODELS:
            self._models[model.model_id] = model
        logger.info(f"Loaded {len(self._models)} default models")

    def register(self, model: ModelCapability):
        """Register a new model."""
        self._models[model.model_id] = model
        logger.debug(f"Registered model: {model.model_id}")

    def unregister(self, model_id: str) -> bool:
        """Unregister a model."""
        if model_id in self._models:
            del self._models[model_id]
            return True
        return False

    def get(self, model_id: str) -> Optional[ModelCapability]:
        """Get model by ID."""
        return self._models.get(model_id)

    def get_all(self) -> list[ModelCapability]:
        """Get all registered models."""
        return list(self._models.values())

    def get_by_capability(self, capability: Capability) -> list[ModelCapability]:
        """Get models that have a specific capability."""
        return [m for m in self._models.values() if m.has_capability(capability)]

    def get_for_task_type(self, task_type: str) -> list[ModelCapability]:
        """Get models suitable for a task type."""
        capability_map = {
            "text": Capability.TEXT,
            "deep_thinking": Capability.DEEP_THINKING,
            "visual": Capability.VISUAL,
            "coding": Capability.CODING,
        }
        capability = capability_map.get(task_type, Capability.TEXT)
        return self.get_by_capability(capability)

    def list_model_ids(self) -> list[str]:
        """List all model IDs."""
        return list(self._models.keys())


# Global registry instance
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get or create the global model registry."""
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry