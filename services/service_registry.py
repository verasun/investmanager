"""Service Registry for dynamic service discovery and health tracking.

This module provides:
- Lazy initialization of service clients
- Automatic health checking
- Retry mechanism for transient failures
- Circuit breaker pattern for failed services
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import httpx
from loguru import logger


class ServiceStatus(str, Enum):
    """Service health status."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ServiceEndpoint:
    """Service endpoint configuration."""
    name: str
    url: str
    health_path: str = "/health"
    timeout: float = 5.0
    retry_count: int = 3
    retry_delay: float = 1.0
    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_time: float = 60.0

    # Runtime state
    _status: ServiceStatus = field(default=ServiceStatus.UNKNOWN, init=False)
    _last_check: float = field(default=0.0, init=False)
    _failure_count: int = field(default=0, init=False)
    _circuit_open: bool = field(default=False, init=False)
    _circuit_open_time: float = field(default=0.0, init=False)

    @property
    def is_available(self) -> bool:
        """Check if service is available for requests."""
        if self._circuit_open:
            # Check if circuit should be reset
            if time.time() - self._circuit_open_time > self.circuit_breaker_reset_time:
                logger.info(f"Circuit breaker reset for {self.name}, attempting retry")
                self._circuit_open = False
                self._failure_count = 0
                return True
            return False
        return True

    def record_success(self):
        """Record a successful request."""
        self._failure_count = 0
        self._circuit_open = False
        self._status = ServiceStatus.HEALTHY
        self._last_check = time.time()

    def record_failure(self):
        """Record a failed request."""
        self._failure_count += 1
        self._status = ServiceStatus.UNHEALTHY
        self._last_check = time.time()

        if self._failure_count >= self.circuit_breaker_threshold:
            self._circuit_open = True
            self._circuit_open_time = time.time()
            logger.warning(f"Circuit breaker opened for {self.name}")


class ServiceRegistry:
    """Registry for all microservices with health tracking."""

    def __init__(self):
        self._services: dict[str, ServiceEndpoint] = {}
        self._http_client: Optional[httpx.AsyncClient] = None
        self._health_check_interval: float = 30.0
        self._health_check_task: Optional[asyncio.Task] = None

    def register(self, endpoint: ServiceEndpoint):
        """Register a service endpoint."""
        self._services[endpoint.name] = endpoint
        logger.info(f"Registered service: {endpoint.name} at {endpoint.url}")

    def get(self, name: str) -> Optional[ServiceEndpoint]:
        """Get a service endpoint by name."""
        return self._services.get(name)

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def check_health(self, endpoint: ServiceEndpoint) -> ServiceStatus:
        """Check health of a single service."""
        client = await self.get_client()
        try:
            response = await client.get(
                f"{endpoint.url}{endpoint.health_path}",
                timeout=endpoint.timeout,
            )
            if response.status_code == 200:
                endpoint.record_success()
                return ServiceStatus.HEALTHY
            else:
                endpoint.record_failure()
                return ServiceStatus.UNHEALTHY
        except Exception as e:
            logger.debug(f"Health check failed for {endpoint.name}: {e}")
            endpoint.record_failure()
            return ServiceStatus.UNHEALTHY

    async def check_all_health(self) -> dict[str, ServiceStatus]:
        """Check health of all registered services."""
        results = {}
        tasks = []
        for name, endpoint in self._services.items():
            tasks.append(self._check_and_record(name, endpoint))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for name, endpoint in self._services.items():
            results[name] = endpoint._status

        return results

    async def _check_and_record(self, name: str, endpoint: ServiceEndpoint):
        """Check health and record result."""
        await self.check_health(endpoint)

    async def start_health_monitor(self):
        """Start background health monitoring."""
        if self._health_check_task is None:
            self._health_check_task = asyncio.create_task(self._health_monitor_loop())
            logger.info("Health monitor started")

    async def stop_health_monitor(self):
        """Stop background health monitoring."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
            logger.info("Health monitor stopped")

    async def _health_monitor_loop(self):
        """Background health check loop."""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self.check_all_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    async def close(self):
        """Close all connections."""
        await self.stop_health_monitor()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


class ResilientClient:
    """HTTP client with retry and circuit breaker support."""

    def __init__(
        self,
        registry: ServiceRegistry,
        service_name: str,
    ):
        self._registry = registry
        self._service_name = service_name

    @property
    def endpoint(self) -> Optional[ServiceEndpoint]:
        """Get the service endpoint."""
        return self._registry.get(self._service_name)

    async def request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> httpx.Response:
        """Make a resilient HTTP request with retry logic."""
        endpoint = self.endpoint
        if not endpoint:
            raise RuntimeError(f"Service '{self._service_name}' not registered")

        if not endpoint.is_available:
            raise RuntimeError(
                f"Service '{self._service_name}' circuit breaker is open"
            )

        client = await self._registry.get_client()
        url = f"{endpoint.url}{path}"

        last_error = None
        for attempt in range(endpoint.retry_count):
            try:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                endpoint.record_success()
                return response
            except httpx.HTTPStatusError as e:
                # Don't retry on 4xx errors (client errors)
                if 400 <= e.response.status_code < 500:
                    endpoint.record_failure()
                    raise
                last_error = e
                logger.warning(
                    f"Request to {self._service_name} failed (attempt {attempt + 1}): {e}"
                )
            except httpx.HTTPError as e:
                last_error = e
                logger.warning(
                    f"Request to {self._service_name} failed (attempt {attempt + 1}): {e}"
                )

            if attempt < endpoint.retry_count - 1:
                await asyncio.sleep(endpoint.retry_delay * (attempt + 1))

        endpoint.record_failure()
        raise last_error or RuntimeError(f"Request to {self._service_name} failed")

    async def get(self, path: str, **kwargs) -> httpx.Response:
        """GET request."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        """POST request."""
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        """PUT request."""
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """DELETE request."""
        return await self.request("DELETE", path, **kwargs)


# Global registry instance
_service_registry: Optional[ServiceRegistry] = None


def get_service_registry() -> ServiceRegistry:
    """Get or create the global service registry."""
    global _service_registry
    if _service_registry is None:
        _service_registry = ServiceRegistry()
    return _service_registry


def get_resilient_client(service_name: str) -> ResilientClient:
    """Get a resilient client for a service."""
    return ResilientClient(get_service_registry(), service_name)


def register_service(
    name: str,
    url: str,
    health_path: str = "/health",
    **kwargs,
) -> ServiceEndpoint:
    """Register a service endpoint."""
    endpoint = ServiceEndpoint(
        name=name,
        url=url,
        health_path=health_path,
        **kwargs,
    )
    get_service_registry().register(endpoint)
    return endpoint