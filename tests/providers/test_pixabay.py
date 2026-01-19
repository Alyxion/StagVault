"""Tests for Pixabay provider."""

from __future__ import annotations

import pytest

from stagvault.providers.base import MediaType, ProviderImage, ProviderResult


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
        result1 = await pixabay_provider.search_images("flowers")
        assert result1.cached is False

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
