"""Tests for Pexels provider."""

from __future__ import annotations

import pytest

from stagvault.providers.base import ProviderImage, ProviderResult


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
