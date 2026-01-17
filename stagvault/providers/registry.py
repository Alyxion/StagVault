"""Provider registry and unified search interface.

Manages all API providers and provides a unified interface for searching
across local data and external APIs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from stagvault.providers.base import (
    APIProvider,
    MediaType,
    ProviderConfig,
    ProviderImage,
    ProviderResult,
)
from stagvault.providers.cache import ProviderCache
from stagvault.providers.pixabay import PixabayProvider
from stagvault.providers.pexels import PexelsProvider


class ProviderRegistry:
    """Registry of all available API providers.

    Provides unified access to multiple image/video APIs with:
    - Automatic provider discovery
    - Shared caching
    - Combined search across providers
    - Rate limit coordination
    """

    # Built-in providers
    PROVIDER_CLASSES: dict[str, type[APIProvider]] = {
        "pixabay": PixabayProvider,
        "pexels": PexelsProvider,
    }

    def __init__(
        self,
        cache_dir: Path | None = None,
        enabled_providers: list[str] | None = None,
    ) -> None:
        """Initialize registry.

        Args:
            cache_dir: Directory for persistent cache
            enabled_providers: List of provider IDs to enable (None = all)
        """
        self.cache = ProviderCache(cache_dir) if cache_dir else ProviderCache()
        self._providers: dict[str, APIProvider] = {}
        self._enabled = enabled_providers

        # Initialize enabled providers
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize all enabled providers."""
        for provider_id, provider_class in self.PROVIDER_CLASSES.items():
            if self._enabled is None or provider_id in self._enabled:
                try:
                    self._providers[provider_id] = provider_class(cache=self.cache)
                except ValueError:
                    # API key not configured, skip provider
                    pass

    def get(self, provider_id: str) -> APIProvider | None:
        """Get a specific provider by ID."""
        return self._providers.get(provider_id)

    def list_providers(self) -> list[str]:
        """List all available provider IDs."""
        return list(self._providers.keys())

    def list_configs(self) -> list[ProviderConfig]:
        """List configurations for all available providers."""
        return [p.config for p in self._providers.values()]

    def js_configs(self) -> list[dict[str, Any]]:
        """Get provider configs for JavaScript client (no API keys)."""
        return [p.js_config() for p in self._providers.values()]

    async def search_images(
        self,
        query: str,
        *,
        providers: list[str] | None = None,
        page: int = 1,
        per_page: int = 20,
        media_type: MediaType = MediaType.ALL,
        **kwargs: Any,
    ) -> dict[str, ProviderResult]:
        """Search for images across multiple providers.

        Args:
            query: Search term
            providers: List of provider IDs (None = all)
            page: Page number
            per_page: Results per page
            media_type: Filter by media type
            **kwargs: Provider-specific parameters

        Returns:
            Dict mapping provider ID to results
        """
        target_providers = providers or list(self._providers.keys())

        tasks = []
        provider_ids = []

        for pid in target_providers:
            provider = self._providers.get(pid)
            if provider and provider.config.supports_images:
                tasks.append(
                    provider.search_images(
                        query,
                        page=page,
                        per_page=per_page,
                        media_type=media_type,
                        **kwargs,
                    )
                )
                provider_ids.append(pid)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            pid: result if not isinstance(result, Exception) else ProviderResult(
                provider=pid,
                total=0,
                page=page,
                per_page=per_page,
                images=[],
            )
            for pid, result in zip(provider_ids, results)
        }

    async def search_videos(
        self,
        query: str,
        *,
        providers: list[str] | None = None,
        page: int = 1,
        per_page: int = 20,
        **kwargs: Any,
    ) -> dict[str, ProviderResult]:
        """Search for videos across multiple providers."""
        target_providers = providers or list(self._providers.keys())

        tasks = []
        provider_ids = []

        for pid in target_providers:
            provider = self._providers.get(pid)
            if provider and provider.config.supports_videos:
                tasks.append(
                    provider.search_videos(
                        query,
                        page=page,
                        per_page=per_page,
                        **kwargs,
                    )
                )
                provider_ids.append(pid)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            pid: result if not isinstance(result, Exception) else ProviderResult(
                provider=pid,
                total=0,
                page=page,
                per_page=per_page,
                videos=[],
            )
            for pid, result in zip(provider_ids, results)
        }

    async def search_all(
        self,
        query: str,
        *,
        providers: list[str] | None = None,
        page: int = 1,
        per_page: int = 20,
        **kwargs: Any,
    ) -> UnifiedSearchResult:
        """Search for both images and videos across all providers.

        Returns combined results from all providers.
        """
        image_results, video_results = await asyncio.gather(
            self.search_images(query, providers=providers, page=page, per_page=per_page, **kwargs),
            self.search_videos(query, providers=providers, page=page, per_page=per_page, **kwargs),
        )

        # Combine all images
        all_images: list[ProviderImage] = []
        total_images = 0
        for result in image_results.values():
            all_images.extend(result.images)
            total_images += result.total

        # Combine all videos
        all_videos = []
        total_videos = 0
        for result in video_results.values():
            all_videos.extend(result.videos)
            total_videos += result.total

        return UnifiedSearchResult(
            query=query,
            page=page,
            per_page=per_page,
            total_images=total_images,
            total_videos=total_videos,
            images=all_images,
            videos=all_videos,
            by_provider={
                **{f"{k}_images": v for k, v in image_results.items()},
                **{f"{k}_videos": v for k, v in video_results.items()},
            },
        )

    async def get_image(
        self,
        provider_id: str,
        image_id: str,
    ) -> ProviderImage | None:
        """Get a specific image from a provider."""
        provider = self._providers.get(provider_id)
        if not provider:
            return None
        return await provider.get_image(image_id)

    def cache_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        return self.cache.stats()

    def clear_cache(self, provider_id: str | None = None) -> dict[str, int]:
        """Clear cache for a provider or all providers."""
        return self.cache.clear(provider_id)

    async def close(self) -> None:
        """Close all provider connections."""
        for provider in self._providers.values():
            if hasattr(provider, "close"):
                await provider.close()


class UnifiedSearchResult:
    """Combined search results from multiple providers."""

    def __init__(
        self,
        query: str,
        page: int,
        per_page: int,
        total_images: int,
        total_videos: int,
        images: list[ProviderImage],
        videos: list,
        by_provider: dict[str, ProviderResult],
    ) -> None:
        self.query = query
        self.page = page
        self.per_page = per_page
        self.total_images = total_images
        self.total_videos = total_videos
        self.images = images
        self.videos = videos
        self.by_provider = by_provider

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "query": self.query,
            "page": self.page,
            "per_page": self.per_page,
            "total_images": self.total_images,
            "total_videos": self.total_videos,
            "images": [img.model_dump() for img in self.images],
            "videos": [vid.model_dump() for vid in self.videos],
        }


# Global registry instance
_registry: ProviderRegistry | None = None


def get_registry(
    cache_dir: Path | None = None,
    enabled_providers: list[str] | None = None,
) -> ProviderRegistry:
    """Get or create the global provider registry."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry(cache_dir, enabled_providers)
    return _registry


def get_provider(provider_id: str) -> APIProvider | None:
    """Get a provider from the global registry."""
    return get_registry().get(provider_id)
