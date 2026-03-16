"""OAuth2 authentication for email services."""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

import httpx
from loguru import logger

from config.settings import settings


@dataclass
class OAuth2Token:
    """OAuth2 token data."""

    access_token: str
    refresh_token: str
    expires_at: float
    token_type: str = "Bearer"
    scope: str = ""

    def is_expired(self) -> bool:
        """Check if token has expired."""
        return time.time() > self.expires_at


@dataclass
class OAuth2Config:
    """OAuth2 provider configuration."""

    client_id: str
    client_secret: str
    auth_url: str
    token_url: str
    scope: str
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob"


# Provider configurations
PROVIDER_CONFIGS = {
    "gmail": OAuth2Config(
        client_id="",  # Set from settings
        client_secret="",  # Set from settings
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scope="https://mail.google.com/",
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    ),
    "outlook": OAuth2Config(
        client_id="",
        client_secret="",
        auth_url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        token_url="https://login.microsoftonline.com/common/oauth2/v2.0/token",
        scope="https://outlook.office.com/SMTP.Send offline_access",
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    ),
    "qq": OAuth2Config(
        client_id="",
        client_secret="",
        auth_url="https://graph.qq.com/oauth2.0/authorize",
        token_url="https://graph.qq.com/oauth2.0/token",
        scope="get_user_info",
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    ),
}


class OAuth2Authenticator:
    """OAuth2 authenticator for email services."""

    def __init__(
        self,
        provider: str = "gmail",
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """
        Initialize OAuth2 authenticator.

        Args:
            provider: Email provider (gmail, outlook, qq)
            client_id: OAuth2 client ID
            client_secret: OAuth2 client secret
        """
        self.provider = provider
        self._config = self._get_provider_config(provider)

        # Override with provided credentials
        if client_id:
            self._config.client_id = client_id
        if client_secret:
            self._config.client_secret = client_secret

        self._token: Optional[OAuth2Token] = None

    def _get_provider_config(self, provider: str) -> OAuth2Config:
        """Get provider configuration."""
        if provider not in PROVIDER_CONFIGS:
            raise ValueError(f"Unknown OAuth2 provider: {provider}")

        config = PROVIDER_CONFIGS[provider]
        # Use settings if available
        if settings.email_oauth2_client_id:
            config.client_id = settings.email_oauth2_client_id
        if settings.email_oauth2_client_secret:
            config.client_secret = settings.email_oauth2_client_secret
        if settings.email_oauth2_token_url:
            config.token_url = settings.email_oauth2_token_url

        return config

    def get_authorization_url(
        self,
        state: Optional[str] = None,
        code_challenge: Optional[str] = None,
    ) -> str:
        """
        Generate OAuth2 authorization URL.

        Args:
            state: Optional state parameter for CSRF protection
            code_challenge: Optional PKCE code challenge

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "response_type": "code",
            "scope": self._config.scope,
        }

        if state:
            params["state"] = state
        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        return f"{self._config.auth_url}?{urlencode(params)}"

    def generate_pkce_verifier(self) -> tuple[str, str]:
        """
        Generate PKCE code verifier and challenge.

        Returns:
            Tuple of (verifier, challenge)
        """
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        return verifier, challenge

    async def exchange_code_for_token(
        self,
        authorization_code: str,
        code_verifier: Optional[str] = None,
    ) -> OAuth2Token:
        """
        Exchange authorization code for tokens.

        Args:
            authorization_code: Code from authorization callback
            code_verifier: PKCE code verifier if used

        Returns:
            OAuth2Token with access and refresh tokens
        """
        data = {
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "code": authorization_code,
            "redirect_uri": self._config.redirect_uri,
            "grant_type": "authorization_code",
        }

        if code_verifier:
            data["code_verifier"] = code_verifier

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._config.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

        self._token = self._parse_token_response(token_data)
        logger.info(f"OAuth2 token obtained for {self.provider}")
        return self._token

    async def refresh_access_token(
        self,
        refresh_token: Optional[str] = None,
    ) -> OAuth2Token:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Refresh token (uses stored token if not provided)

        Returns:
            New OAuth2Token
        """
        refresh_token = refresh_token or self._token.refresh_token
        if not refresh_token:
            raise ValueError("No refresh token available")

        data = {
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._config.token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()

        # Some providers don't return refresh_token in refresh response
        if "refresh_token" not in token_data and self._token:
            token_data["refresh_token"] = self._token.refresh_token

        self._token = self._parse_token_response(token_data)
        logger.info(f"OAuth2 token refreshed for {self.provider}")
        return self._token

    def _parse_token_response(self, data: dict) -> OAuth2Token:
        """Parse token response into OAuth2Token."""
        expires_in = data.get("expires_in", 3600)
        return OAuth2Token(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=time.time() + expires_in,
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", ""),
        )

    async def get_valid_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.

        Returns:
            Valid access token
        """
        if not self._token:
            # Try to use refresh token from settings
            if settings.email_oauth2_refresh_token:
                self._token = OAuth2Token(
                    access_token="",
                    refresh_token=settings.email_oauth2_refresh_token,
                    expires_at=0,
                )
            else:
                raise ValueError("No OAuth2 token available. Run authorization first.")

        # Check if token needs refresh (with 5 minute buffer)
        if time.time() > (self._token.expires_at - 300):
            await self.refresh_access_token()

        return self._token.access_token

    def set_token(self, token: OAuth2Token) -> None:
        """Set the OAuth2 token."""
        self._token = token

    def get_token(self) -> Optional[OAuth2Token]:
        """Get the current OAuth2 token."""
        return self._token


class OAuth2EmailAuth:
    """
    High-level OAuth2 email authentication helper.

    Provides easy-to-use methods for OAuth2 email setup.
    """

    def __init__(self, provider: str = "gmail"):
        """Initialize OAuth2 email auth helper."""
        self.provider = provider
        self._authenticator = OAuth2Authenticator(provider)

    async def start_authorization_flow(self) -> dict:
        """
        Start OAuth2 authorization flow.

        Returns:
            Dict with authorization URL and state/verifier for later use
        """
        state = secrets.token_urlsafe(16)
        verifier, challenge = self._authenticator.generate_pkce_verifier()

        auth_url = self._authenticator.get_authorization_url(
            state=state,
            code_challenge=challenge,
        )

        return {
            "authorization_url": auth_url,
            "state": state,
            "code_verifier": verifier,
        }

    async def complete_authorization_flow(
        self,
        authorization_code: str,
        code_verifier: str,
    ) -> OAuth2Token:
        """
        Complete OAuth2 authorization flow.

        Args:
            authorization_code: Code from callback
            code_verifier: PKCE verifier from start flow

        Returns:
            OAuth2Token with tokens
        """
        return await self._authenticator.exchange_code_for_token(
            authorization_code,
            code_verifier,
        )

    async def get_access_token(self) -> str:
        """Get valid access token."""
        return await self._authenticator.get_valid_access_token()

    def generate_xoauth2_string(
        self,
        email: str,
        access_token: Optional[str] = None,
    ) -> str:
        """
        Generate XOAUTH2 authentication string.

        Args:
            email: Email address
            access_token: Access token (fetches fresh one if not provided)

        Returns:
            XOAUTH2 string for SMTP authentication
        """
        if access_token is None:
            raise ValueError("Access token required")
        auth_string = f"user={email}\x01auth=Bearer {access_token}\x01\x01"
        return auth_string


# Utility function for command-line setup
async def setup_oauth2_email(provider: str = "gmail") -> dict:
    """
    Interactive OAuth2 email setup.

    Args:
        provider: Email provider

    Returns:
        Dict with token information for saving
    """
    auth = OAuth2EmailAuth(provider)

    # Start authorization
    flow_info = await auth.start_authorization_flow()

    print("\n" + "=" * 60)
    print("OAuth2 Email Authorization Setup")
    print("=" * 60)
    print(f"\nProvider: {provider}")
    print(f"\nPlease visit this URL to authorize:\n")
    print(flow_info["authorization_url"])
    print("\n")

    # In a real CLI, you'd prompt for the code
    # For programmatic use, return the flow info
    return {
        "provider": provider,
        "state": flow_info["state"],
        "code_verifier": flow_info["code_verifier"],
        "message": "Visit the authorization URL and get the code",
    }