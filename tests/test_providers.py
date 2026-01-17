"""Unit tests for API providers.

These tests use mocked API responses by default to avoid hitting rate limits.
For integration tests with real APIs, run: pytest -m integration
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stagvault.providers.base import (
    MediaType,
    ProviderImage,
    ProviderResult,
    RateLimitInfo,
)
from stagvault.providers.cache import MemoryCache, DiskCache, ProviderCache


# =============================================================================
# Cache Tests
# =============================================================================

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
        cache.set("key1", "value1", ttl=0)  # Immediate expiration

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

        assert cache.get("key1") is not None  # Recently accessed
        assert cache.get("key2") is None  # Evicted
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

        # Write to cache
        cache1 = DiskCache(db_path)
        cache1.set("key1", {"data": "value1"}, ttl=3600)

        # New instance should read same data
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

        # Set value
        cache.set("pixabay", "search", {"q": "test"}, {"result": "data"})

        # Should be in both memory and disk
        result = cache.get("pixabay", "search", {"q": "test"})
        assert result == {"result": "data"}

    def test_cache_key_generation(self, temp_dir: Path):
        cache = ProviderCache(cache_dir=temp_dir)

        # Same params in different order should produce same key
        key1 = cache._make_key("pixabay", "search", {"a": 1, "b": 2})
        key2 = cache._make_key("pixabay", "search", {"b": 2, "a": 1})
        assert key1 == key2

        # Different params should produce different keys
        key3 = cache._make_key("pixabay", "search", {"a": 1, "b": 3})
        assert key1 != key3

    def test_invalidate(self, temp_dir: Path):
        cache = ProviderCache(cache_dir=temp_dir)

        cache.set("pixabay", "search", {"q": "test"}, {"result": "data"})
        cache.invalidate("pixabay", "search", {"q": "test"})

        result = cache.get("pixabay", "search", {"q": "test"})
        assert result is None


# =============================================================================
# Rate Limit Tests
# =============================================================================

class TestRateLimitInfo:
    """Tests for rate limit tracking."""

    def test_from_headers(self):
        headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "50",
            "X-RateLimit-Reset": "30"
        }
        info = RateLimitInfo.from_headers(headers)

        assert info.limit == 100
        assert info.remaining == 50
        assert info.reset_seconds == 30

    def test_is_exhausted(self):
        info = RateLimitInfo(limit=100, remaining=0)
        assert info.is_exhausted is True

        info = RateLimitInfo(limit=100, remaining=1)
        assert info.is_exhausted is False

    def test_should_wait(self):
        # For limit=100, buffer is 5% = 5
        info = RateLimitInfo(limit=100, remaining=4)
        assert info.should_wait is True

        info = RateLimitInfo(limit=100, remaining=10)
        assert info.should_wait is False

    def test_dynamic_buffer(self):
        # Low limit (< 100): 10% buffer
        info = RateLimitInfo(limit=50, remaining=50)
        assert info.buffer == 5  # 10% of 50

        # Medium limit (100-500): 5% buffer
        info = RateLimitInfo(limit=200, remaining=200)
        assert info.buffer == 10  # 5% of 200

        # High limit (> 500): 3% buffer
        info = RateLimitInfo(limit=1000, remaining=1000)
        assert info.buffer == 30  # 3% of 1000

        # Very low limit: minimum buffer of 3
        info = RateLimitInfo(limit=10, remaining=10)
        assert info.buffer == 3  # min buffer

    def test_is_critical(self):
        info = RateLimitInfo(limit=100, remaining=5)
        assert info.is_critical is True

        info = RateLimitInfo(limit=100, remaining=15)
        assert info.is_critical is False

    def test_wait_time(self):
        info = RateLimitInfo(limit=100, remaining=0, reset_seconds=60)

        # Should wait approximately reset_seconds
        wait = info.wait_time()
        assert 59 <= wait <= 60


# =============================================================================
# Pixabay Provider Tests
# =============================================================================

@pytest.mark.mock
class TestPixabayProvider:
    """Tests for Pixabay API provider."""

    @pytest.mark.asyncio
    async def test_search_images(self, pixabay_provider, mock_pixabay_response):
        result = await pixabay_provider.search_images("flowers", page=1, per_page=20)

        assert isinstance(result, ProviderResult)
        assert result.provider == "pixabay"
        assert result.total == 500
        assert len(result.images) == 2

    @pytest.mark.asyncio
    async def test_search_images_caching(self, pixabay_provider):
        # First call
        result1 = await pixabay_provider.search_images("flowers")
        assert result1.cached is False

        # Second call should be cached
        result2 = await pixabay_provider.search_images("flowers")
        assert result2.cached is True

    @pytest.mark.asyncio
    async def test_parse_image(self, pixabay_provider, mock_pixabay_response):
        result = await pixabay_provider.search_images("test")
        image = result.images[0]

        assert isinstance(image, ProviderImage)
        assert image.id == "195893"
        assert image.provider == "pixabay"
        assert "blossom" in image.tags
        assert image.author == "Josch13"
        assert image.preview_url is not None
        assert image.web_url is not None

    @pytest.mark.asyncio
    async def test_search_with_filters(self, pixabay_provider):
        result = await pixabay_provider.search_images(
            "nature",
            media_type=MediaType.PHOTO,
            category="nature",
            safesearch=True
        )

        assert isinstance(result, ProviderResult)

    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self, pixabay_provider):
        await pixabay_provider.search_images("test")

        rate_limit = pixabay_provider.rate_limit
        assert rate_limit.limit == 100
        assert rate_limit.remaining == 95


# =============================================================================
# Pexels Provider Tests
# =============================================================================

@pytest.mark.mock
class TestPexelsProvider:
    """Tests for Pexels API provider."""

    @pytest.mark.asyncio
    async def test_search_images(self, pexels_provider, mock_pexels_response):
        result = await pexels_provider.search_images("nature", page=1, per_page=20)

        assert isinstance(result, ProviderResult)
        assert result.provider == "pexels"
        assert result.total == 1000
        assert len(result.images) == 1

    @pytest.mark.asyncio
    async def test_search_images_caching(self, pexels_provider):
        result1 = await pexels_provider.search_images("nature")
        assert result1.cached is False

        result2 = await pexels_provider.search_images("nature")
        assert result2.cached is True

    @pytest.mark.asyncio
    async def test_parse_image(self, pexels_provider, mock_pexels_response):
        result = await pexels_provider.search_images("test")
        image = result.images[0]

        assert isinstance(image, ProviderImage)
        assert image.id == "2014422"
        assert image.provider == "pexels"
        assert image.author == "Joey Bautista"
        assert image.description == "Brown Rocks During Golden Hour"


# =============================================================================
# Provider Registry Tests
# =============================================================================

@pytest.mark.mock
class TestProviderRegistry:
    """Tests for multi-provider registry."""

    def test_list_providers(self, provider_registry):
        providers = provider_registry.list_providers()
        assert "pixabay" in providers
        assert "pexels" in providers

    def test_get_provider(self, provider_registry):
        pixabay = provider_registry.get("pixabay")
        assert pixabay is not None
        assert pixabay.config.id == "pixabay"

    def test_get_nonexistent_provider(self, provider_registry):
        result = provider_registry.get("nonexistent")
        assert result is None

    def test_js_configs(self, provider_registry):
        configs = provider_registry.js_configs()
        assert len(configs) >= 2

        config = configs[0]
        assert "id" in config
        assert "name" in config
        assert "baseUrl" in config
        # Should NOT contain API key
        assert "apiKey" not in config

    @pytest.mark.asyncio
    async def test_search_images_multi_provider(self, provider_registry, mock_httpx_client):
        # Mock the HTTP clients for all providers
        for provider in provider_registry._providers.values():
            provider._client = mock_httpx_client

        results = await provider_registry.search_images("nature")

        assert "pixabay" in results
        assert "pexels" in results
        assert isinstance(results["pixabay"], ProviderResult)
        assert isinstance(results["pexels"], ProviderResult)

    def test_cache_stats(self, provider_registry):
        stats = provider_registry.cache_stats()
        assert "memory" in stats

    def test_clear_cache(self, provider_registry):
        result = provider_registry.clear_cache()
        assert "memory" in result
        assert "disk" in result


# =============================================================================
# FastAPI Routes Tests
# =============================================================================

class TestProviderRoutes:
    """Tests for FastAPI provider routes."""

    def test_list_providers(self, api_client):
        response = api_client.get("/providers/")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_get_provider_config(self, api_client):
        response = api_client.get("/providers/pixabay")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == "pixabay"
        assert data["name"] == "Pixabay"

    def test_get_nonexistent_provider(self, api_client):
        response = api_client.get("/providers/nonexistent")
        assert response.status_code == 404

    def test_cache_stats(self, api_client):
        response = api_client.get("/providers/cache/stats")
        assert response.status_code == 200

        data = response.json()
        assert "memory" in data

    def test_clear_cache(self, api_client):
        response = api_client.post("/providers/cache/clear")
        assert response.status_code == 200


# =============================================================================
# Integration Tests (require real API keys)
# =============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestRealAPIIntegration:
    """Integration tests with real APIs.

    These tests are skipped by default. Run with:
    PIXABAY_API_KEY=xxx PEXELS_API_KEY=xxx pytest -m integration
    """

    @pytest.mark.asyncio
    async def test_pixabay_real_search(self):
        """Test real Pixabay API call."""
        import os
        if not os.environ.get("PIXABAY_API_KEY") or os.environ.get("PIXABAY_API_KEY") == "test_pixabay_key":
            pytest.skip("Real PIXABAY_API_KEY not set")

        from stagvault.providers.pixabay import PixabayProvider
        from stagvault.providers.cache import ProviderCache

        cache = ProviderCache()
        provider = PixabayProvider(cache=cache)

        result = await provider.search_images("sunset", per_page=5)

        assert result.total > 0
        assert len(result.images) <= 5
        assert result.images[0].preview_url.startswith("https://")

        await provider.close()

    @pytest.mark.asyncio
    async def test_pexels_real_search(self):
        """Test real Pexels API call."""
        import os
        if not os.environ.get("PEXELS_API_KEY") or os.environ.get("PEXELS_API_KEY") == "test_pexels_key":
            pytest.skip("Real PEXELS_API_KEY not set")

        from stagvault.providers.pexels import PexelsProvider
        from stagvault.providers.cache import ProviderCache

        cache = ProviderCache()
        provider = PexelsProvider(cache=cache)

        result = await provider.search_images("ocean", per_page=5)

        assert result.total > 0
        assert len(result.images) <= 5
        assert result.images[0].author is not None

        await provider.close()
