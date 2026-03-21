"""Service Registry Manager for Gateway.

This module implements the capability registry that:
- Accepts service registrations
- Tracks service health
- Provides capability discovery
- Supports forced mode for users

Architecture:
┌─────────────────────────────────────────────────────────────────────┐
│                         GATEWAY (:8000)                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐ │
│  │  Registry       │  │  Intent         │  │  Forced Mode        │ │
│  │  Manager        │  │  Router         │  │  Manager            │ │
│  └────────┬────────┘  └────────┬────────┘  └──────────┬──────────┘ │
│           │                    │                      │            │
│           ▼                    ▼                      ▼            │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                   Service Registry Store                     │  │
│  │  - capabilities: dict[service_id, CapabilityInfo]           │  │
│  │  - forced_modes: dict[user_id, service_id]                  │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
"""

import asyncio
import os
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Optional

import httpx
from loguru import logger

from services.capability_protocol import (
    CapabilityInfo,
    EndpointInfo,
    ForcedModeRequest,
    ForcedModeResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    RegisterRequest,
    RegisterResponse,
    ServiceStatus,
    ServiceListResponse,
    CapabilityListResponse,
    UnregisterRequest,
    UnregisterResponse,
)


# ============================================
# Message Deduplication
# ============================================

class MessageDeduplicator:
    """LRU cache for message deduplication to prevent duplicate processing."""

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._cache: OrderedDict[str, float] = OrderedDict()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def is_duplicate(self, message_id: str) -> bool:
        """Check if message was already processed."""
        self._cleanup()

        if message_id in self._cache:
            self._cache.move_to_end(message_id)
            return True
        return False

    def mark_processed(self, message_id: str):
        """Mark message as processed."""
        if message_id in self._cache:
            self._cache.move_to_end(message_id)
        else:
            self._cache[message_id] = time.time()
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def _cleanup(self):
        """Remove expired entries."""
        current_time = time.time()
        expired = [
            msg_id for msg_id, timestamp in self._cache.items()
            if current_time - timestamp > self._ttl_seconds
        ]
        for msg_id in expired:
            del self._cache[msg_id]


# ============================================
# Service Registry Manager
# ============================================

class ServiceRegistryManager:
    """Manages service registration, discovery, and health tracking."""

    def __init__(self):
        # Service registry
        self._capabilities: dict[str, CapabilityInfo] = {}

        # User forced modes (user_id -> service_id)
        self._forced_modes: dict[str, str] = {}

        # HTTP client for health checks
        self._http_client: Optional[httpx.AsyncClient] = None

        # Health check configuration
        self._health_check_interval: float = 30.0
        self._heartbeat_timeout: float = 90.0  # 3 * health_check_interval
        self._health_check_task: Optional[asyncio.Task] = None

        # Message deduplicator
        self._deduplicator = MessageDeduplicator()

        # Service API key for authentication
        self._service_api_key: str = os.getenv("SERVICE_API_KEY", "")

    # ========================================
    # Service Registration
    # ========================================

    async def register(self, request: RegisterRequest) -> RegisterResponse:
        """Register a service capability.

        Args:
            request: Registration request containing capability info

        Returns:
            Registration response
        """
        capability = request.capability
        service_id = capability.service_id

        # Check if service already registered
        existing = self._capabilities.get(service_id)

        # Update registration
        capability.registered_at = datetime.now()
        capability.last_heartbeat = datetime.now()
        capability.status = ServiceStatus.HEALTHY

        self._capabilities[service_id] = capability

        action = "Updated" if existing else "Registered"
        logger.info(f"{action} service: {service_id} ({capability.service_name}) at {capability.base_url}")

        return RegisterResponse(
            success=True,
            message=f"Service '{service_id}' registered successfully",
            service_id=service_id,
            registered_at=capability.registered_at,
        )

    async def unregister(self, request: UnregisterRequest) -> UnregisterResponse:
        """Unregister a service.

        Args:
            request: Unregistration request with service ID

        Returns:
            Unregistration response
        """
        service_id = request.service_id

        if service_id not in self._capabilities:
            return UnregisterResponse(
                success=False,
                message=f"Service '{service_id}' not found",
            )

        del self._capabilities[service_id]

        # Clear forced modes for this service
        users_to_clear = [
            user_id for user_id, svc_id in self._forced_modes.items()
            if svc_id == service_id
        ]
        for user_id in users_to_clear:
            del self._forced_modes[user_id]

        logger.info(f"Unregistered service: {service_id}")

        return UnregisterResponse(
            success=True,
            message=f"Service '{service_id}' unregistered",
        )

    async def heartbeat(self, request: HeartbeatRequest) -> HeartbeatResponse:
        """Process a heartbeat from a registered service.

        Args:
            request: Heartbeat request with service ID and status

        Returns:
            Heartbeat response
        """
        service_id = request.service_id

        if service_id not in self._capabilities:
            return HeartbeatResponse(
                success=False,
                message=f"Service '{service_id}' not registered",
            )

        capability = self._capabilities[service_id]
        capability.last_heartbeat = datetime.now()
        capability.status = request.status

        # Store metrics if provided
        if request.metrics:
            # Could store metrics for monitoring
            pass

        logger.debug(f"Heartbeat from {service_id}: {request.status.value}")

        return HeartbeatResponse(
            success=True,
            message="Heartbeat received",
        )

    # ========================================
    # Service Discovery
    # ========================================

    def get_service(self, service_id: str) -> Optional[CapabilityInfo]:
        """Get a registered service by ID.

        Args:
            service_id: Service identifier

        Returns:
            Capability info or None if not found
        """
        return self._capabilities.get(service_id)

    def list_services(self) -> ServiceListResponse:
        """List all registered services.

        Returns:
            List of all registered capabilities
        """
        services = list(self._capabilities.values())
        return ServiceListResponse(
            services=services,
            total=len(services),
        )

    def list_capabilities(self) -> CapabilityListResponse:
        """List all available capabilities across services.

        Returns:
            Aggregated capability information
        """
        capabilities = []

        for service in self._capabilities.values():
            for endpoint in service.endpoints:
                capabilities.append({
                    "service_id": service.service_id,
                    "service_name": service.service_name,
                    "endpoint": endpoint.path,
                    "description": endpoint.description,
                    "tags": endpoint.tags,
                    "method": endpoint.method,
                })

        return CapabilityListResponse(
            capabilities=capabilities,
            total=len(capabilities),
        )

    def get_capability_description(self) -> str:
        """Generate a capability description for LLM prompt.

        Returns:
            Formatted string describing all capabilities
        """
        if not self._capabilities:
            return "No services are currently registered."

        lines = ["可用服务："]

        for service in sorted(self._capabilities.values(), key=lambda x: x.priority, reverse=True):
            lines.append(f"\n## {service.service_id} ({service.service_name})")
            lines.append(f"描述：{service.description}")

            if service.endpoints:
                lines.append("功能：")
                for endpoint in service.endpoints:
                    tags_str = ", ".join(endpoint.tags) if endpoint.tags else ""
                    lines.append(f"  - {endpoint.path}: {endpoint.description}")
                    if tags_str:
                        lines.append(f"    标签: {tags_str}")

            if service.keywords:
                lines.append(f"关键词: {', '.join(service.keywords[:10])}")

        return "\n".join(lines)

    # ========================================
    # Forced Mode
    # ========================================

    def set_forced_mode(self, request: ForcedModeRequest) -> ForcedModeResponse:
        """Set forced mode for a user.

        Args:
            request: Forced mode request

        Returns:
            Forced mode response
        """
        user_id = request.user_id
        previous = self._forced_modes.get(user_id)

        if request.service_id is None:
            # Clear forced mode
            if user_id in self._forced_modes:
                del self._forced_modes[user_id]
                logger.info(f"Cleared forced mode for user {user_id}")
            return ForcedModeResponse(
                success=True,
                message="已取消强制模式，恢复智能路由",
                previous_service=previous,
                current_service=None,
            )

        # Validate service exists
        if request.service_id not in self._capabilities:
            return ForcedModeResponse(
                success=False,
                message=f"服务 '{request.service_id}' 不存在",
                previous_service=previous,
                current_service=previous,
            )

        self._forced_modes[user_id] = request.service_id
        logger.info(f"Set forced mode for user {user_id} to {request.service_id}")

        return ForcedModeResponse(
            success=True,
            message=f"已设置为使用 '{request.service_id}' 模块",
            previous_service=previous,
            current_service=request.service_id,
        )

    def get_forced_mode(self, user_id: str) -> Optional[str]:
        """Get forced mode for a user.

        Args:
            user_id: User identifier

        Returns:
            Service ID if forced mode is set, None otherwise
        """
        return self._forced_modes.get(user_id)

    def clear_forced_mode(self, user_id: str) -> bool:
        """Clear forced mode for a user.

        Args:
            user_id: User identifier

        Returns:
            True if forced mode was cleared
        """
        if user_id in self._forced_modes:
            del self._forced_modes[user_id]
            return True
        return False

    # ========================================
    # Health Check
    # ========================================

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            headers = {}
            if self._service_api_key:
                headers["X-Service-Key"] = self._service_api_key
            self._http_client = httpx.AsyncClient(timeout=10.0, headers=headers)
        return self._http_client

    async def check_health(self, service_id: str) -> ServiceStatus:
        """Check health of a specific service.

        Args:
            service_id: Service to check

        Returns:
            Service status
        """
        capability = self._capabilities.get(service_id)
        if not capability:
            return ServiceStatus.UNKNOWN

        client = await self.get_client()
        try:
            response = await client.get(
                f"{capability.base_url}/health",
                timeout=5.0,
            )
            if response.status_code == 200:
                capability.status = ServiceStatus.HEALTHY
                capability.last_heartbeat = datetime.now()
                return ServiceStatus.HEALTHY
            else:
                capability.status = ServiceStatus.UNHEALTHY
                return ServiceStatus.UNHEALTHY
        except Exception as e:
            logger.debug(f"Health check failed for {service_id}: {e}")
            capability.status = ServiceStatus.UNHEALTHY
            return ServiceStatus.UNHEALTHY

    async def check_all_health(self) -> dict[str, ServiceStatus]:
        """Check health of all registered services.

        Returns:
            Dictionary of service_id -> status
        """
        results = {}
        tasks = [
            self._check_and_record(service_id)
            for service_id in self._capabilities
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        for service_id, capability in self._capabilities.items():
            results[service_id] = capability.status

        return results

    async def _check_and_record(self, service_id: str):
        """Check health and record result."""
        await self.check_health(service_id)

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

                if not self._capabilities:
                    continue

                # Check heartbeat timeout for all services
                now = datetime.now()
                for service_id, capability in list(self._capabilities.items()):
                    if capability.last_heartbeat:
                        elapsed = (now - capability.last_heartbeat).total_seconds()
                        if elapsed > self._heartbeat_timeout:
                            logger.warning(
                                f"Service {service_id} heartbeat timeout "
                                f"(last: {elapsed:.0f}s ago, timeout: {self._heartbeat_timeout}s)"
                            )
                            capability.status = ServiceStatus.UNHEALTHY

                # Perform active health checks
                await self.check_all_health()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")

    # ========================================
    # Cleanup
    # ========================================

    async def close(self):
        """Close all connections."""
        await self.stop_health_monitor()
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# ============================================
# Global Instance
# ============================================

_registry_manager: Optional[ServiceRegistryManager] = None


def get_registry_manager() -> ServiceRegistryManager:
    """Get or create the global registry manager."""
    global _registry_manager
    if _registry_manager is None:
        _registry_manager = ServiceRegistryManager()
    return _registry_manager