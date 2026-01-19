"""External API providers for StagVault.

Providers can be accessed in three ways:
1. Pure JavaScript (direct API calls from browser with client-side caching)
2. Python (direct usage in Python code)
3. FastAPI routes (proxied through backend)

All providers implement intelligent caching and rate limit handling.
"""

from stagvault.providers.base import (
    APIProvider,
    MediaType,
    ProviderConfig,
    ProviderImage,
    ProviderResult,
    ProviderTier,
    ProviderVideo,
    RateLimitInfo,
)
from stagvault.providers.cache import ProviderCache
from stagvault.providers.pixabay import PixabayProvider
from stagvault.providers.pexels import PexelsProvider
from stagvault.providers.unsplash import UnsplashProvider
from stagvault.providers.registry import ProviderRegistry, get_provider, get_registry
from stagvault.providers.routes import create_provider_router

__all__ = [
    # Base classes
    "APIProvider",
    "MediaType",
    "ProviderConfig",
    "ProviderImage",
    "ProviderTier",
    "ProviderVideo",
    "ProviderResult",
    "RateLimitInfo",
    # Cache
    "ProviderCache",
    # Providers
    "PixabayProvider",
    "PexelsProvider",
    "UnsplashProvider",
    # Registry
    "ProviderRegistry",
    "get_provider",
    "get_registry",
    # FastAPI
    "create_provider_router",
]
