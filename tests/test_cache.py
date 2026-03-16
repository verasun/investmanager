"""Tests for local cache module."""

import asyncio
import time

import pytest

from src.cache.local_cache import LocalCache, AsyncLocalCache, CacheManager


class TestLocalCache:
    """Test cases for LocalCache."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = LocalCache[str, str](max_size=10, default_ttl=60)

        cache.set("key1", "value1")
        result = cache.get("key1")

        assert result == "value1"

    def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist."""
        cache = LocalCache[str, str]()
        result = cache.get("nonexistent")
        assert result is None

    def test_delete(self):
        """Test deleting a key."""
        cache = LocalCache[str, str]()
        cache.set("key1", "value1")

        deleted = cache.delete("key1")
        assert deleted is True

        result = cache.get("key1")
        assert result is None

    def test_delete_nonexistent(self):
        """Test deleting a nonexistent key."""
        cache = LocalCache[str, str]()
        deleted = cache.delete("nonexistent")
        assert deleted is False

    def test_exists(self):
        """Test exists check."""
        cache = LocalCache[str, str]()
        cache.set("key1", "value1")

        assert cache.exists("key1") is True
        assert cache.exists("nonexistent") is False

    def test_ttl_expiration(self):
        """Test TTL expiration."""
        cache = LocalCache[str, str](default_ttl=1)

        cache.set("key1", "value1", ttl=1)

        # Should exist immediately
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.5)

        # Should be expired
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """Test LRU eviction when max_size is reached."""
        cache = LocalCache[str, str](max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_lru_order_on_access(self):
        """Test that access updates LRU order."""
        cache = LocalCache[str, str](max_size=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it most recently used
        cache.get("key1")

        # Add new key, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None

    def test_clear(self):
        """Test clearing all entries."""
        cache = LocalCache[str, str]()
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = LocalCache[str, str](default_ttl=1)

        cache.set("key1", "value1", ttl=1)
        cache.set("key2", "value2", ttl=10)

        time.sleep(1.5)

        count = cache.cleanup_expired()

        assert count == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"

    def test_get_stats(self):
        """Test getting cache statistics."""
        cache = LocalCache[str, str]()
        cache.set("key1", "value1")

        cache.get("key1")  # hit
        cache.get("key1")  # hit
        cache.get("nonexistent")  # miss

        stats = cache.get_stats()

        assert stats["size"] == 1
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert 0 < stats["hit_rate"] < 1


class TestAsyncLocalCache:
    """Test cases for AsyncLocalCache."""

    @pytest.mark.asyncio
    async def test_async_set_and_get(self):
        """Test async set and get operations."""
        cache = AsyncLocalCache[str, str]()

        await cache.set("key1", "value1")
        result = await cache.get("key1")

        assert result == "value1"

    @pytest.mark.asyncio
    async def test_async_delete(self):
        """Test async delete operation."""
        cache = AsyncLocalCache[str, str]()
        await cache.set("key1", "value1")

        deleted = await cache.delete("key1")
        assert deleted is True

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_async_get_stats(self):
        """Test async get stats."""
        cache = AsyncLocalCache[str, str]()
        await cache.set("key1", "value1")
        await cache.get("key1")

        stats = await cache.get_stats()
        assert stats["hits"] == 1


class TestCacheManager:
    """Test cases for CacheManager."""

    @pytest.mark.asyncio
    async def test_namespace_isolation(self):
        """Test that namespaces are isolated."""
        manager = CacheManager()

        await manager.set("key1", "value1", namespace="ns1")
        await manager.set("key1", "value2", namespace="ns2")

        result1 = await manager.get("key1", namespace="ns1")
        result2 = await manager.get("key1", namespace="ns2")

        assert result1 == "value1"
        assert result2 == "value2"

    @pytest.mark.asyncio
    async def test_clear_namespace(self):
        """Test clearing a specific namespace."""
        manager = CacheManager()

        await manager.set("key1", "value1", namespace="ns1")
        await manager.set("key2", "value2", namespace="ns1")
        await manager.set("key1", "value3", namespace="ns2")

        await manager.clear_namespace("ns1")

        assert await manager.get("key1", namespace="ns1") is None
        assert await manager.get("key2", namespace="ns1") is None
        assert await manager.get("key1", namespace="ns2") == "value3"

    @pytest.mark.asyncio
    async def test_get_all_stats(self):
        """Test getting stats for all namespaces."""
        manager = CacheManager()

        await manager.set("key1", "value1", namespace="ns1")
        await manager.set("key1", "value1", namespace="ns2")

        stats = await manager.get_all_stats()

        assert "ns1" in stats
        assert "ns2" in stats