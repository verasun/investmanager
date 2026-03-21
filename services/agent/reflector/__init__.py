"""Reflector module - Execution evaluation and retry logic.

This module provides:
- Reflector: Main class for evaluating execution results
- ReflectionResult: Result of reflection
- StepEvaluation: Evaluation of a single step
"""

from .evaluation import ReflectionResult, StepEvaluation
from .reflector import Reflector, get_reflector


__all__ = [
    # Result types
    "ReflectionResult",
    "StepEvaluation",
    # Reflector
    "Reflector",
    "get_reflector",
]