"""Service Registration Helper.

This module provides utilities for services to register with the Gateway.
"""

import asyncio
from typing import Optional

import httpx
from loguru import logger

from services.capability_protocol import (
    CapabilityInfo,
    RegisterRequest,
    RegisterResponse,
)


class ServiceRegistrar:
    """Handles service registration with Gateway."""

    def __init__(
        self,
        gateway_url: str,
        capability: CapabilityInfo,
        retry_count: int = 5,
        retry_delay: float = 2.0,
    ):
        """Initialize registrar.

        Args:
            gateway_url: URL of the Gateway service
            capability: Capability info to register
            retry_count: Number of registration retries
            retry_delay: Delay between retries in seconds
        """
        self.gateway_url = gateway_url.rstrip("/")
        self.capability = capability
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self._client: Optional[httpx.AsyncClient] = None
        self._registered = False

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def register(self) -> bool:
        """Register service with Gateway.

        Returns:
            True if registration successful
        """
        client = await self._get_client()

        for attempt in range(self.retry_count):
            try:
                response = await client.post(
                    f"{self.gateway_url}/registry/register",
                    json={"capability": self.capability.model_dump()},
                )
                response.raise_for_status()

                data = response.json()
                if data.get("success"):
                    logger.info(
                        f"Successfully registered with Gateway: "
                        f"{self.capability.service_id} ({self.capability.service_name})"
                    )
                    self._registered = True
                    return True
                else:
                    logger.warning(
                        f"Registration failed: {data.get('message', 'Unknown error')}"
                    )

            except httpx.HTTPError as e:
                logger.warning(
                    f"Registration attempt {attempt + 1}/{self.retry_count} failed: {e}"
                )

            if attempt < self.retry_count - 1:
                await asyncio.sleep(self.retry_delay)

        logger.error("Failed to register with Gateway after all retries")
        return False

    async def unregister(self) -> bool:
        """Unregister service from Gateway.

        Returns:
            True if unregistration successful
        """
        if not self._registered:
            return True

        client = await self._get_client()

        try:
            response = await client.post(
                f"{self.gateway_url}/registry/unregister",
                json={"service_id": self.capability.service_id},
            )
            response.raise_for_status()

            data = response.json()
            if data.get("success"):
                logger.info(f"Unregistered from Gateway: {self.capability.service_id}")
                self._registered = False
                return True
            else:
                logger.warning(f"Unregistration failed: {data.get('message')}")
                return False

        except httpx.HTTPError as e:
            logger.error(f"Unregistration failed: {e}")
            return False

    async def close(self):
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


async def register_service(
    gateway_url: str,
    capability: CapabilityInfo,
    retry_count: int = 5,
    retry_delay: float = 2.0,
) -> bool:
    """Convenience function to register a service.

    Args:
        gateway_url: URL of the Gateway service
        capability: Capability info to register
        retry_count: Number of registration retries
        retry_delay: Delay between retries in seconds

    Returns:
        True if registration successful
    """
    registrar = ServiceRegistrar(
        gateway_url=gateway_url,
        capability=capability,
        retry_count=retry_count,
        retry_delay=retry_delay,
    )
    return await registrar.register()