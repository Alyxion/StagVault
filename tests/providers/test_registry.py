"""Tests for provider registry."""

from __future__ import annotations

import pytest

from stagvault.providers.base import ProviderResult, ProviderTier


@pytest.mark.mock
class TestProviderRegistry:
    """Tests for multi-provider registry."""

    def test_list_providers(self, provider_registry):
        providers = provider_registry.list_providers()
        assert "pixabay" in providers
        assert "pexels" in providers
        assert "unsplash" in providers

    def test_get_provider(self, provider_registry):
        pixabay = provider_registry.get("pixabay")
        assert pixabay is not None
        assert pixabay.config.id == "pixabay"

    def test_get_nonexistent_provider(self, provider_registry):
        result = provider_registry.get("nonexistent")
        assert result is None

    def test_js_configs(self, provider_registry):
        configs = provider_registry.js_configs()
        assert len(configs) >= 3

        config = configs[0]
        assert "id" in config
        assert "name" in config
        assert "baseUrl" in config
        assert "apiKey" not in config

    @pytest.mark.asyncio
    async def test_search_images_multi_provider(self, provider_registry, mock_httpx_client):
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

    def test_provider_tiers(self, provider_registry):
        """Test that providers have correct tiers."""
        pixabay = provider_registry.get("pixabay")
        pexels = provider_registry.get("pexels")
        unsplash = provider_registry.get("unsplash")

        assert pixabay.config.tier == ProviderTier.STANDARD
        assert pexels.config.tier == ProviderTier.STANDARD
        assert unsplash.config.tier == ProviderTier.RESTRICTED

    def test_list_standard_providers(self, provider_registry):
        """Test listing only standard-tier providers."""
        standard = provider_registry.list_standard_providers()
        all_providers = provider_registry.list_providers()

        assert "pixabay" in standard
        assert "pexels" in standard
        assert "unsplash" not in standard

        assert "unsplash" in all_providers
        assert len(standard) < len(all_providers)

    def test_list_providers_include_restricted(self, provider_registry):
        """Test list_providers with include_restricted flag."""
        with_restricted = provider_registry.list_providers(include_restricted=True)
        without_restricted = provider_registry.list_providers(include_restricted=False)

        assert "unsplash" in with_restricted
        assert "unsplash" not in without_restricted

    @pytest.mark.asyncio
    async def test_search_excludes_restricted_by_default(self, provider_registry, mock_httpx_client):
        """Test that broad search excludes restricted providers by default."""
        for provider in provider_registry._providers.values():
            provider._client = mock_httpx_client

        # Default search should exclude Unsplash
        results = await provider_registry.search_images("nature")

        assert "pixabay" in results
        assert "pexels" in results
        assert "unsplash" not in results

    @pytest.mark.asyncio
    async def test_search_includes_restricted_when_explicit(self, provider_registry, mock_httpx_client):
        """Test that explicitly specified restricted providers are included."""
        for provider in provider_registry._providers.values():
            provider._client = mock_httpx_client

        # Explicit provider list should include Unsplash
        results = await provider_registry.search_images("nature", providers=["unsplash"])

        assert "unsplash" in results
        assert "pixabay" not in results

    @pytest.mark.asyncio
    async def test_search_includes_restricted_with_flag(self, provider_registry, mock_httpx_client):
        """Test that include_restricted flag includes restricted providers."""
        for provider in provider_registry._providers.values():
            provider._client = mock_httpx_client

        results = await provider_registry.search_images("nature", include_restricted=True)

        assert "pixabay" in results
        assert "pexels" in results
        assert "unsplash" in results
