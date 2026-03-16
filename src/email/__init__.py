"""Email module for OAuth2 authentication and sending."""

from src.email.oauth2_auth import (
    OAuth2Authenticator,
    OAuth2Config,
    OAuth2EmailAuth,
    OAuth2Token,
    setup_oauth2_email,
)

__all__ = [
    "OAuth2Authenticator",
    "OAuth2Config",
    "OAuth2EmailAuth",
    "OAuth2Token",
    "setup_oauth2_email",
]