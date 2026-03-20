"""Capability Service - Business logic processing.

This service handles:
- Message processing for different work modes
- User work mode persistence
- LLM and Claude Code integration
"""

from .main import create_app, run_capability_service

__all__ = ["create_app", "run_capability_service"]