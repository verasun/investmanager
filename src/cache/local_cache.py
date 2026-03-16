"""Local in-memory cache with LRU eviction and TTL support."""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Generic, Optional, TypeVar
from threading import Lock

from loguru import logger

from config.settings import settings

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheEntry(Generic[V]):
    """Cache entry with value and expiration time."""

    value: V
    expires_at: float
    created_at: float = field(default_factory=time.time)
    access_count: int = 0

    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > self.expires_at

    def touch(self) -> None:
        """Update access count."""
        self.access_count += 1


class LocalCache(Generic[K, V]):
    """
    Thread-safe LRU cache with TTL support.

    This is a Redis replacement for single-container deployment.
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
    ):
        """
        Initialize local cache.

        Args:
            max_size: Maximum number of entries
            default_ttl: Default TTL in seconds
        """
        self._cache: OrderedDict[K, CacheEntry[V]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K) -> Optional[V]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                del self._cache[key]
                self._misses += 1
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.touch()
            self._hits += 1
            return entry.value

    def set(
        self,
        key: K,
        value: V,
        ttl: Optional[int] = None,
    ) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (defaults to default_ttl)
        """
        ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # Remove oldest entries if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            # Remove existing entry if present
            if key in self._cache:
                del self._cache[key]

            self._cache[key] = CacheEntry(
                value=value,
                expires_at=expires_at,
            )

    def delete(self, key: K) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def exists(self, key: K) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if exists and not expired
        """
        return self.get(key) is not None

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        count = 0
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
                count += 1
        return count

    def get_stats(self) -> dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with stats
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = self._hits / total_requests if total_requests > 0 else 0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
            }


class AsyncLocalCache(Generic[K, V]):
    """
    Async wrapper around LocalCache for async contexts.

    Provides Redis-like async interface.
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
    ):
        """Initialize async cache wrapper."""
        self._cache = LocalCache[K, V](max_size=max_size, default_ttl=default_ttl)

    async def get(self, key: K) -> Optional[V]:
        """Get value asynchronously."""
        return self._cache.get(key)

    async def set(
        self,
        key: K,
        value: V,
        ttl: Optional[int] = None,
    ) -> None:
        """Set value asynchronously."""
        self._cache.set(key, value, ttl)

    async def delete(self, key: K) -> bool:
        """Delete value asynchronously."""
        return self._cache.delete(key)

    async def exists(self, key: K) -> bool:
        """Check existence asynchronously."""
        return self._cache.exists(key)

    async def clear(self) -> None:
        """Clear cache asynchronously."""
        self._cache.clear()

    async def cleanup_expired(self) -> int:
        """Clean up expired entries asynchronously."""
        return self._cache.cleanup_expired()

    async def get_stats(self) -> dict[str, Any]:
        """Get statistics asynchronously."""
        return self._cache.get_stats()


class CacheManager:
    """
    Central cache manager for managing multiple cache namespaces.

    Provides a unified interface similar to Redis with namespaces.
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
    ):
        """
        Initialize cache manager.

        Args:
            max_size: Max entries per namespace
            default_ttl: Default TTL in seconds
        """
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._namespaces: dict[str, AsyncLocalCache] = {}
        self._lock = asyncio.Lock()

    async def _get_namespace(self, name: str) -> AsyncLocalCache:
        """Get or create a namespace cache."""
        async with self._lock:
            if name not in self._namespaces:
                self._namespaces[name] = AsyncLocalCache(
                    max_size=self._max_size,
                    default_ttl=self._default_ttl,
                )
            return self._namespaces[name]

    async def get(
        self,
        key: str,
        namespace: str = "default",
    ) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key
            namespace: Cache namespace

        Returns:
            Cached value or None
        """
        cache = await self._get_namespace(namespace)
        return await cache.get(key)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        namespace: str = "default",
    ) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds
            namespace: Cache namespace
        """
        cache = await self._get_namespace(namespace)
        await cache.set(key, value, ttl)

    async def delete(
        self,
        key: str,
        namespace: str = "default",
    ) -> bool:
        """
        Delete value from cache.

        Args:
            key: Cache key
            namespace: Cache namespace

        Returns:
            True if deleted
        """
        cache = await self._get_namespace(namespace)
        return await cache.delete(key)

    async def exists(
        self,
        key: str,
        namespace: str = "default",
    ) -> bool:
        """
        Check if key exists.

        Args:
            key: Cache key
            namespace: Cache namespace

        Returns:
            True if exists
        """
        cache = await self._get_namespace(namespace)
        return await cache.exists(key)

    async def clear_namespace(self, namespace: str) -> None:
        """Clear all entries in a namespace."""
        cache = await self._get_namespace(namespace)
        await cache.clear()

    async def clear_all(self) -> None:
        """Clear all namespaces."""
        async with self._lock:
            for cache in self._namespaces.values():
                await cache.clear()

    async def cleanup_all_expired(self) -> int:
        """Clean up expired entries in all namespaces."""
        total = 0
        async with self._lock:
            for cache in self._namespaces.values():
                total += await cache.cleanup_expired()
        return total

    async def get_all_stats(self) -> dict[str, dict[str, Any]]:
        """Get statistics for all namespaces."""
        stats = {}
        async with self._lock:
            for name, cache in self._namespaces.items():
                stats[name] = await cache.get_stats()
        return stats


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(
            max_size=settings.local_cache_max_size,
            default_ttl=settings.local_cache_ttl,
        )
        logger.info(
            f"Cache manager initialized (max_size={settings.local_cache_max_size}, "
            f"default_ttl={settings.local_cache_ttl}s)"
        )
    return _cache_manager