"""Tests for Unsplash provider."""

from __future__ import annotations

import pytest

from stagvault.providers.base import ProviderImage, ProviderResult


@pytest.mark.mock
class TestUnsplashProvider:
    """Tests for Unsplash API provider."""

    @pytest.mark.asyncio
    async def test_search_images(self, unsplash_provider, mock_unsplash_response):
        result = await unsplash_provider.search_images("mountains", page=1, per_page=20)

        assert isinstance(result, ProviderResult)
        assert result.provider == "unsplash"
        assert result.total == 500
        assert len(result.images) == 1

    @pytest.mark.asyncio
    async def test_search_images_caching(self, unsplash_provider):
        result1 = await unsplash_provider.search_images("mountains")
        assert result1.cached is False

        result2 = await unsplash_provider.search_images("mountains")
        assert result2.cached is True

    @pytest.mark.asyncio
    async def test_parse_image(self, unsplash_provider, mock_unsplash_response):
        result = await unsplash_provider.search_images("test")
        image = result.images[0]

        assert isinstance(image, ProviderImage)
        assert image.id == "abc123xyz"
        assert image.provider == "unsplash"
        assert image.author == "John Nature"
        assert image.description == "Beautiful mountain landscape"
        assert "mountain" in image.tags
        assert image.likes == 1234

    @pytest.mark.asyncio
    async def test_search_videos_not_supported(self, unsplash_provider):
        """Unsplash doesn't support videos."""
        result = await unsplash_provider.search_videos("test")

        assert result.total == 0
        assert len(result.videos) == 0
        assert result.cached is True

    @pytest.mark.asyncio
    async def test_rate_limit_tracking(self, unsplash_provider):
        await unsplash_provider.search_images("test")

        rate_limit = unsplash_provider.rate_limit
        assert rate_limit.limit == 50
        assert rate_limit.remaining == 45

    @pytest.mark.asyncio
    async def test_low_rate_limit_buffer(self, unsplash_provider):
        """Unsplash has low limits, so buffer should be 10%."""
        await unsplash_provider.search_images("test")

        rate_limit = unsplash_provider.rate_limit
        assert rate_limit.buffer == 5
