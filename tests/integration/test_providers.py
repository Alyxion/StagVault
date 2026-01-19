"""Integration tests with real APIs.

These tests require real API keys and are skipped by default.
Run with: pytest -m integration
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.integration
@pytest.mark.slow
class TestRealAPIIntegration:
    """Integration tests with real APIs."""

    @pytest.mark.asyncio
    async def test_pixabay_real_search(self):
        """Test real Pixabay API call."""
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

    @pytest.mark.asyncio
    async def test_unsplash_real_search(self):
        """Test real Unsplash API call."""
        if not os.environ.get("UNSPLASH_API_KEY") or os.environ.get("UNSPLASH_API_KEY") == "test_unsplash_key":
            pytest.skip("Real UNSPLASH_API_KEY not set")

        from stagvault.providers.unsplash import UnsplashProvider
        from stagvault.providers.cache import ProviderCache

        cache = ProviderCache()
        provider = UnsplashProvider(cache=cache)

        result = await provider.search_images("mountains", per_page=5)

        assert result.total > 0
        assert len(result.images) <= 5
        assert result.images[0].author is not None
        assert result.images[0].preview_url.startswith("https://")

        await provider.close()
