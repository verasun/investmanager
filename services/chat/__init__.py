"""Chat Service - General conversation capability.

This service handles general chat messages with personalization
support and learning user preferences.
"""

from .main import create_app, run_chat_service

__all__ = ["create_app", "run_chat_service"]