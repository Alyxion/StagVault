"""Tests for provider caching system."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from stagvault.providers.cache import MemoryCache, DiskCache, ProviderCache


class TestMemoryCache:
    """Tests for in-memory LRU cache."""

    def test_set_and_get(self):
        cache = MemoryCache(max_size=10)
        cache.set("key1", {"data": "value1"}, ttl=3600)

        result = cache.get("key1")
        assert result == {"data": "value1"}

    def test_get_missing_key(self):
        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        cache = MemoryCache()
        cache.set("key1", "value1", ttl=0)

        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        cache = MemoryCache(max_size=3)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add key4, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") is not None
        assert cache.get("key2") is None
        assert cache.get("key3") is not None
        assert cache.get("key4") is not None

    def test_delete(self):
        cache = MemoryCache()
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("key1") is False

    def test_clear_all(self):
        cache = MemoryCache()
        cache.set("key1", "value1", provider="p1")
        cache.set("key2", "value2", provider="p2")

        count = cache.clear()
        assert count == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_clear_by_provider(self):
        cache = MemoryCache()
        cache.set("key1", "value1", provider="pixabay")
        cache.set("key2", "value2", provider="pexels")

        count = cache.clear("pixabay")
        assert count == 1
        assert cache.get("key1") is None
        assert cache.get("key2") is not None

    def test_stats(self):
        cache = MemoryCache(max_size=100)
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key2")  # Miss

        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["max_size"] == 100


class TestDiskCache:
    """Tests for SQLite disk cache."""

    def test_set_and_get(self, temp_dir: Path):
        cache = DiskCache(temp_dir / "cache.db")
        cache.set("key1", {"data": "value1"}, ttl=3600)

        result = cache.get("key1")
        assert result == {"data": "value1"}

    def test_persistence(self, temp_dir: Path):
        db_path = temp_dir / "cache.db"

        cache1 = DiskCache(db_path)
        cache1.set("key1", {"data": "value1"}, ttl=3600)

        cache2 = DiskCache(db_path)
        result = cache2.get("key1")
        assert result == {"data": "value1"}

    def test_ttl_expiration(self, temp_dir: Path):
        cache = DiskCache(temp_dir / "cache.db")
        cache.set("key1", "value1", ttl=0)

        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_cleanup_expired(self, temp_dir: Path):
        cache = DiskCache(temp_dir / "cache.db")
        cache.set("key1", "value1", ttl=0)
        cache.set("key2", "value2", ttl=3600)

        time.sleep(0.01)
        count = cache.cleanup_expired()

        assert count == 1
        assert cache.get("key1") is None
        assert cache.get("key2") is not None


class TestProviderCache:
    """Tests for combined memory + disk cache."""

    def test_cache_lookup_order(self, temp_dir: Path):
        cache = ProviderCache(cache_dir=temp_dir)

        cache.set("pixabay", "search", {"q": "test"}, {"result": "data"})

        result = cache.get("pixabay", "search", {"q": "test"})
        assert result == {"result": "data"}

    def test_cache_key_generation(self, temp_dir: Path):
        cache = ProviderCache(cache_dir=temp_dir)

        key1 = cache._make_key("pixabay", "search", {"a": 1, "b": 2})
        key2 = cache._make_key("pixabay", "search", {"b": 2, "a": 1})
        assert key1 == key2

        key3 = cache._make_key("pixabay", "search", {"a": 1, "b": 3})
        assert key1 != key3

    def test_invalidate(self, temp_dir: Path):
        cache = ProviderCache(cache_dir=temp_dir)

        cache.set("pixabay", "search", {"q": "test"}, {"result": "data"})
        cache.invalidate("pixabay", "search", {"q": "test"})

        result = cache.get("pixabay", "search", {"q": "test"})
        assert result is None
