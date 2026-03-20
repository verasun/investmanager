"""Gateway Service - Message routing and mode dispatch.

This service handles:
- Feishu webhook endpoints
- User work mode management
- Message routing to capability service
"""

from .main import create_app, run_gateway

__all__ = ["create_app", "run_gateway"]