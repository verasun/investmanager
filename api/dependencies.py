"""API dependencies."""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """
    Get current user from authorization header.

    This is a placeholder for authentication.
    In production, implement proper JWT or API key validation.
    """
    if credentials is None:
        # For development, allow anonymous access
        return "anonymous"

    # TODO: Implement proper authentication
    token = credentials.credentials

    # Simple API key check (for development)
    if hasattr(settings, "API_KEY") and settings.API_KEY:
        if token == settings.API_KEY:
            return "api_user"

    return "anonymous"


def require_auth(
    user: str = Depends(get_current_user),
) -> str:
    """
    Require authentication.

    Raises 401 if not authenticated.
    """
    if user == "anonymous":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return user


class RateLimiter:
    """Simple rate limiter for API endpoints."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self._requests: dict[str, list[float]] = {}

    def check(self, client_id: str) -> bool:
        """Check if client is within rate limit."""
        import time

        now = time.time()
        minute_ago = now - 60

        # Clean old requests
        if client_id in self._requests:
            self._requests[client_id] = [
                t for t in self._requests[client_id] if t > minute_ago
            ]
        else:
            self._requests[client_id] = []

        # Check limit
        if len(self._requests[client_id]) >= self.requests_per_minute:
            return False

        # Add request
        self._requests[client_id].append(now)
        return True


# Global rate limiter
rate_limiter = RateLimiter(requests_per_minute=100)


async def check_rate_limit(
    user: str = Depends(get_current_user),
) -> str:
    """Check rate limit for user."""
    if not rate_limiter.check(user):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
    return user