"""Tests for OAuth2 email authentication."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.email.oauth2_auth import (
    OAuth2Authenticator,
    OAuth2Config,
    OAuth2EmailAuth,
    OAuth2Token,
    PROVIDER_CONFIGS,
)


class TestOAuth2Config:
    """Test cases for OAuth2Config."""

    def test_provider_configs_exist(self):
        """Test that provider configs are defined."""
        assert "gmail" in PROVIDER_CONFIGS
        assert "outlook" in PROVIDER_CONFIGS
        assert "qq" in PROVIDER_CONFIGS

    def test_gmail_config(self):
        """Test Gmail configuration."""
        config = PROVIDER_CONFIGS["gmail"]
        assert "google" in config.auth_url
        assert "google" in config.token_url
        assert "mail.google.com" in config.scope


class TestOAuth2Token:
    """Test cases for OAuth2Token."""

    def test_is_expired(self):
        """Test expiration check."""
        import time

        # Not expired
        token = OAuth2Token(
            access_token="test",
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        )
        assert not token.is_expired()

        # Expired
        token = OAuth2Token(
            access_token="test",
            refresh_token="refresh",
            expires_at=time.time() - 1,
        )
        assert token.is_expired()


class TestOAuth2Authenticator:
    """Test cases for OAuth2Authenticator."""

    def test_init_with_provider(self):
        """Test initialization with provider name."""
        auth = OAuth2Authenticator(provider="gmail")
        assert auth.provider == "gmail"
        assert auth._config.auth_url != ""

    def test_init_with_invalid_provider(self):
        """Test initialization with invalid provider."""
        with pytest.raises(ValueError):
            OAuth2Authenticator(provider="invalid_provider")

    def test_get_authorization_url(self):
        """Test generating authorization URL."""
        auth = OAuth2Authenticator(provider="gmail")
        auth._config.client_id = "test_client_id"

        url = auth.get_authorization_url(state="test_state")

        assert "accounts.google.com" in url
        assert "test_client_id" in url
        assert "test_state" in url

    def test_generate_pkce_verifier(self):
        """Test PKCE verifier generation."""
        auth = OAuth2Authenticator(provider="gmail")

        verifier, challenge = auth.generate_pkce_verifier()

        assert len(verifier) > 0
        assert len(challenge) > 0
        assert verifier != challenge

    def test_parse_token_response(self):
        """Test parsing token response."""
        auth = OAuth2Authenticator(provider="gmail")

        response = {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        token = auth._parse_token_response(response)

        assert token.access_token == "test_access"
        assert token.refresh_token == "test_refresh"
        assert token.token_type == "Bearer"


class TestOAuth2EmailAuth:
    """Test cases for OAuth2EmailAuth."""

    def test_init(self):
        """Test initialization."""
        auth = OAuth2EmailAuth(provider="gmail")
        assert auth.provider == "gmail"

    @pytest.mark.asyncio
    async def test_start_authorization_flow(self):
        """Test starting authorization flow."""
        auth = OAuth2EmailAuth(provider="gmail")
        auth._authenticator._config.client_id = "test_id"

        flow_info = await auth.start_authorization_flow()

        assert "authorization_url" in flow_info
        assert "state" in flow_info
        assert "code_verifier" in flow_info

    def test_generate_xoauth2_string(self):
        """Test XOAUTH2 string generation."""
        auth = OAuth2EmailAuth(provider="gmail")

        result = auth.generate_xoauth2_string("user@gmail.com", "test_token")

        assert "user=user@gmail.com" in result
        assert "Bearer test_token" in result