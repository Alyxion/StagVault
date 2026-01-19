"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure test environment
os.environ.setdefault("PIXABAY_API_KEY", "test_pixabay_key")
os.environ.setdefault("PEXELS_API_KEY", "test_pexels_key")
os.environ.setdefault("UNSPLASH_API_KEY", "test_unsplash_key")


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy for async tests."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_pixabay_response() -> dict:
    """Sample Pixabay API response."""
    return {
        "total": 500,
        "totalHits": 500,
        "hits": [
            {
                "id": 195893,
                "pageURL": "https://pixabay.com/photos/blossom-bloom-flower-195893/",
                "type": "photo",
                "tags": "blossom, bloom, flower",
                "previewURL": "https://cdn.pixabay.com/photo/preview.jpg",
                "previewWidth": 150,
                "previewHeight": 84,
                "webformatURL": "https://cdn.pixabay.com/photo/webformat.jpg",
                "webformatWidth": 640,
                "webformatHeight": 360,
                "largeImageURL": "https://cdn.pixabay.com/photo/large.jpg",
                "imageWidth": 4000,
                "imageHeight": 2250,
                "imageSize": 4731420,
                "views": 7671,
                "downloads": 6439,
                "likes": 5,
                "comments": 2,
                "user_id": 48777,
                "user": "Josch13",
                "userImageURL": "https://cdn.pixabay.com/user/avatar.jpg"
            },
            {
                "id": 195894,
                "pageURL": "https://pixabay.com/photos/nature-landscape-195894/",
                "type": "photo",
                "tags": "nature, landscape, mountain",
                "previewURL": "https://cdn.pixabay.com/photo/preview2.jpg",
                "previewWidth": 150,
                "previewHeight": 100,
                "webformatURL": "https://cdn.pixabay.com/photo/webformat2.jpg",
                "webformatWidth": 640,
                "webformatHeight": 427,
                "largeImageURL": "https://cdn.pixabay.com/photo/large2.jpg",
                "imageWidth": 5000,
                "imageHeight": 3333,
                "imageSize": 5000000,
                "views": 10000,
                "downloads": 8000,
                "likes": 100,
                "comments": 10,
                "user_id": 12345,
                "user": "NatureLover",
                "userImageURL": "https://cdn.pixabay.com/user/avatar2.jpg"
            }
        ]
    }


@pytest.fixture
def mock_pexels_response() -> dict:
    """Sample Pexels API response."""
    return {
        "total_results": 1000,
        "page": 1,
        "per_page": 20,
        "photos": [
            {
                "id": 2014422,
                "width": 3024,
                "height": 4032,
                "url": "https://www.pexels.com/photo/2014422/",
                "photographer": "Joey Bautista",
                "photographer_url": "https://www.pexels.com/@joey-bautista",
                "photographer_id": 680914,
                "avg_color": "#978E82",
                "src": {
                    "original": "https://images.pexels.com/photos/original.jpeg",
                    "large2x": "https://images.pexels.com/photos/large2x.jpeg",
                    "large": "https://images.pexels.com/photos/large.jpeg",
                    "medium": "https://images.pexels.com/photos/medium.jpeg",
                    "small": "https://images.pexels.com/photos/small.jpeg",
                    "portrait": "https://images.pexels.com/photos/portrait.jpeg",
                    "landscape": "https://images.pexels.com/photos/landscape.jpeg",
                    "tiny": "https://images.pexels.com/photos/tiny.jpeg"
                },
                "liked": False,
                "alt": "Brown Rocks During Golden Hour"
            }
        ],
        "next_page": "https://api.pexels.com/v1/search/?page=2&per_page=20&query=nature"
    }


@pytest.fixture
def mock_unsplash_response() -> dict:
    """Sample Unsplash API response."""
    return {
        "total": 500,
        "total_pages": 25,
        "results": [
            {
                "id": "abc123xyz",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T12:00:00Z",
                "width": 4000,
                "height": 3000,
                "color": "#4A90D9",
                "blur_hash": "LKO2?U%2Tw=w]~RBVZRi};RPxuwH",
                "description": "Beautiful mountain landscape",
                "alt_description": "snow covered mountain under blue sky",
                "urls": {
                    "raw": "https://images.unsplash.com/photo-abc123?ixlib=rb-4.0.3",
                    "full": "https://images.unsplash.com/photo-abc123?q=85&w=2000",
                    "regular": "https://images.unsplash.com/photo-abc123?q=80&w=1080",
                    "small": "https://images.unsplash.com/photo-abc123?q=80&w=400",
                    "thumb": "https://images.unsplash.com/photo-abc123?q=80&w=200"
                },
                "links": {
                    "self": "https://api.unsplash.com/photos/abc123xyz",
                    "html": "https://unsplash.com/photos/abc123xyz",
                    "download": "https://unsplash.com/photos/abc123xyz/download"
                },
                "likes": 1234,
                "user": {
                    "id": "user123",
                    "username": "naturephotographer",
                    "name": "John Nature",
                    "links": {
                        "self": "https://api.unsplash.com/users/naturephotographer",
                        "html": "https://unsplash.com/@naturephotographer"
                    }
                },
                "tags": [
                    {"title": "mountain"},
                    {"title": "landscape"},
                    {"title": "nature"}
                ]
            }
        ]
    }


@pytest.fixture
def mock_rate_limit_headers() -> dict:
    """Mock rate limit response headers."""
    return {
        "X-RateLimit-Limit": "100",
        "X-RateLimit-Remaining": "95",
        "X-RateLimit-Reset": "60"
    }


@pytest.fixture
def mock_unsplash_rate_limit_headers() -> dict:
    """Mock Unsplash rate limit headers."""
    return {
        "X-Ratelimit-Limit": "50",
        "X-Ratelimit-Remaining": "45"
    }


@pytest.fixture
def provider_cache(temp_dir: Path):
    """Create a test provider cache."""
    from stagvault.providers.cache import ProviderCache
    return ProviderCache(cache_dir=temp_dir, memory_max_size=100)


@pytest.fixture
def mock_httpx_client(mock_pixabay_response, mock_pexels_response, mock_unsplash_response, mock_rate_limit_headers, mock_unsplash_rate_limit_headers):
    """Create a mock httpx client for API tests."""
    mock_response = MagicMock()
    mock_response.status_code = 200

    async def mock_get(url, **kwargs):
        mock_response.raise_for_status = MagicMock()
        if "pixabay" in url:
            mock_response.headers = mock_rate_limit_headers
            mock_response.json = MagicMock(return_value=mock_pixabay_response)
        elif "pexels" in url:
            mock_response.headers = mock_rate_limit_headers
            mock_response.json = MagicMock(return_value=mock_pexels_response)
        elif "unsplash" in url:
            mock_response.headers = mock_unsplash_rate_limit_headers
            mock_response.json = MagicMock(return_value=mock_unsplash_response)
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = mock_get
    return mock_client


@pytest.fixture
def pixabay_provider(provider_cache, mock_httpx_client):
    """Create a Pixabay provider with mocked HTTP client."""
    from stagvault.providers.pixabay import PixabayProvider

    provider = PixabayProvider(cache=provider_cache)
    provider._client = mock_httpx_client
    return provider


@pytest.fixture
def pexels_provider(provider_cache, mock_httpx_client):
    """Create a Pexels provider with mocked HTTP client."""
    from stagvault.providers.pexels import PexelsProvider

    provider = PexelsProvider(cache=provider_cache)
    provider._client = mock_httpx_client
    return provider


@pytest.fixture
def unsplash_provider(provider_cache, mock_httpx_client):
    """Create an Unsplash provider with mocked HTTP client."""
    from stagvault.providers.unsplash import UnsplashProvider

    provider = UnsplashProvider(cache=provider_cache)
    provider._client = mock_httpx_client
    return provider


@pytest.fixture
def provider_registry(temp_dir: Path):
    """Create a provider registry for testing."""
    from stagvault.providers.registry import ProviderRegistry
    return ProviderRegistry(cache_dir=temp_dir)


@pytest.fixture
def fastapi_app(provider_registry) -> FastAPI:
    """Create a FastAPI app with provider routes for testing."""
    from stagvault.providers.routes import create_provider_router

    app = FastAPI()
    app.include_router(create_provider_router(prefix="/providers"))
    return app


@pytest.fixture
def api_client(fastapi_app: FastAPI) -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(fastapi_app)


# Markers for test categories
def pytest_configure(config):
    config.addinivalue_line("markers", "mock: tests using mocked API responses")
    config.addinivalue_line("markers", "integration: tests requiring real API keys")
    config.addinivalue_line("markers", "slow: slow running tests")
