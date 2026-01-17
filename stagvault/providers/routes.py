"""FastAPI routes for API providers.

Provides a unified REST API for accessing external providers like Pixabay and Pexels.
Can be mounted alongside the main StagVault routes.

Usage:
    from fastapi import FastAPI
    from stagvault.providers.routes import create_provider_router

    app = FastAPI()
    app.include_router(create_provider_router(prefix="/providers"))
"""

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from stagvault.providers.base import MediaType, ProviderImage, ProviderResult
from stagvault.providers.registry import ProviderRegistry, get_registry


# Global registry dependency - must be at module level for FastAPI annotation resolution
_cache_dir: Path | None = None


def get_provider_registry() -> ProviderRegistry:
    """Get or create the global provider registry."""
    return get_registry(_cache_dir)


# Response models
class ProviderConfigResponse(BaseModel):
    """Provider configuration (no API keys)."""
    id: str
    name: str
    baseUrl: str
    authType: str
    authParam: str
    requiresAttribution: bool
    attributionTemplate: str
    supportsImages: bool
    supportsVideos: bool
    hotlinkAllowed: bool
    cacheDuration: int
    rateLimitWindow: int
    rateLimitRequests: int


class RateLimitResponse(BaseModel):
    """Rate limit status."""
    limit: int
    remaining: int
    reset_seconds: int
    is_exhausted: bool


class CacheStatsResponse(BaseModel):
    """Cache statistics."""
    memory: dict[str, Any]
    disk: dict[str, Any] | None


class ProviderSearchResponse(BaseModel):
    """Search response from a single provider."""
    provider: str
    total: int
    page: int
    per_page: int
    images: list[dict[str, Any]]
    videos: list[dict[str, Any]]
    cached: bool
    rate_limit: RateLimitResponse | None


class MultiProviderSearchResponse(BaseModel):
    """Search response from multiple providers."""
    query: str
    providers: list[str]
    results: dict[str, ProviderSearchResponse]
    total_images: int
    total_videos: int


def create_provider_router(
    prefix: str = "/providers",
    tags: list[str] | None = None,
    cache_dir: Path | None = None,
) -> APIRouter:
    """Create FastAPI router for provider API.

    Args:
        prefix: URL prefix for routes (default: /providers)
        tags: OpenAPI tags
        cache_dir: Directory for persistent cache

    Returns:
        APIRouter to include in FastAPI app
    """
    global _cache_dir
    _cache_dir = cache_dir

    if tags is None:
        tags = ["providers"]

    router = APIRouter(prefix=prefix, tags=tags)

    # --- Cache management (must be before dynamic routes) ---

    @router.get("/cache/stats", response_model=CacheStatsResponse)
    async def get_cache_stats(
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    ) -> CacheStatsResponse:
        """Get cache statistics."""
        stats = registry.cache_stats()
        return CacheStatsResponse(
            memory=stats["memory"],
            disk=stats.get("disk"),
        )

    @router.post("/cache/clear")
    async def clear_cache(
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
        provider_id: str | None = None,
    ) -> dict[str, int]:
        """Clear the cache (optionally for specific provider)."""
        return registry.clear_cache(provider_id)

    # --- Provider info endpoints ---

    @router.get("/", response_model=list[ProviderConfigResponse])
    async def list_providers(
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    ) -> list[ProviderConfigResponse]:
        """List all available providers and their configurations."""
        return [
            ProviderConfigResponse(**p.js_config())
            for p in [registry.get(pid) for pid in registry.list_providers()]
            if p is not None
        ]

    @router.get("/{provider_id}", response_model=ProviderConfigResponse)
    async def get_provider_config(
        provider_id: str,
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    ) -> ProviderConfigResponse:
        """Get configuration for a specific provider."""
        provider = registry.get(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
        return ProviderConfigResponse(**provider.js_config())

    @router.get("/{provider_id}/rate-limit", response_model=RateLimitResponse)
    async def get_rate_limit(
        provider_id: str,
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    ) -> RateLimitResponse:
        """Get current rate limit status for a provider."""
        provider = registry.get(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")
        rl = provider.rate_limit
        return RateLimitResponse(
            limit=rl.limit,
            remaining=rl.remaining,
            reset_seconds=rl.reset_seconds,
            is_exhausted=rl.is_exhausted,
        )

    # --- Search endpoints ---

    @router.get("/search/images", response_model=MultiProviderSearchResponse)
    async def search_images(
        q: Annotated[str, Query(min_length=1, description="Search query")],
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
        providers: Annotated[list[str] | None, Query(description="Provider IDs")] = None,
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=20, ge=1, le=100),
        media_type: MediaType = MediaType.ALL,
        orientation: str | None = None,
        color: str | None = None,
        safesearch: bool = True,
    ) -> MultiProviderSearchResponse:
        """Search for images across providers.

        Searches all enabled providers (or specified ones) and returns combined results.
        """
        results = await registry.search_images(
            q,
            providers=providers,
            page=page,
            per_page=per_page,
            media_type=media_type,
            orientation=orientation,
            color=color,
            safesearch=safesearch,
        )

        total_images = sum(r.total for r in results.values())

        return MultiProviderSearchResponse(
            query=q,
            providers=list(results.keys()),
            results={
                pid: ProviderSearchResponse(
                    provider=pid,
                    total=r.total,
                    page=r.page,
                    per_page=r.per_page,
                    images=[img.model_dump() for img in r.images],
                    videos=[],
                    cached=r.cached,
                    rate_limit=RateLimitResponse(
                        limit=r.rate_limit.limit,
                        remaining=r.rate_limit.remaining,
                        reset_seconds=r.rate_limit.reset_seconds,
                        is_exhausted=r.rate_limit.is_exhausted,
                    ) if r.rate_limit else None,
                )
                for pid, r in results.items()
            },
            total_images=total_images,
            total_videos=0,
        )

    @router.get("/search/videos", response_model=MultiProviderSearchResponse)
    async def search_videos(
        q: Annotated[str, Query(min_length=1, description="Search query")],
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
        providers: Annotated[list[str] | None, Query(description="Provider IDs")] = None,
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=20, ge=1, le=100),
    ) -> MultiProviderSearchResponse:
        """Search for videos across providers."""
        results = await registry.search_videos(
            q,
            providers=providers,
            page=page,
            per_page=per_page,
        )

        total_videos = sum(r.total for r in results.values())

        return MultiProviderSearchResponse(
            query=q,
            providers=list(results.keys()),
            results={
                pid: ProviderSearchResponse(
                    provider=pid,
                    total=r.total,
                    page=r.page,
                    per_page=r.per_page,
                    images=[],
                    videos=[vid.model_dump() for vid in r.videos],
                    cached=r.cached,
                    rate_limit=RateLimitResponse(
                        limit=r.rate_limit.limit,
                        remaining=r.rate_limit.remaining,
                        reset_seconds=r.rate_limit.reset_seconds,
                        is_exhausted=r.rate_limit.is_exhausted,
                    ) if r.rate_limit else None,
                )
                for pid, r in results.items()
            },
            total_images=0,
            total_videos=total_videos,
        )

    # --- Single provider search ---

    @router.get("/{provider_id}/search/images", response_model=ProviderSearchResponse)
    async def search_provider_images(
        provider_id: str,
        q: Annotated[str, Query(min_length=1)],
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=20, ge=1, le=100),
        media_type: MediaType = MediaType.ALL,
        category: str | None = None,
        orientation: str | None = None,
        color: str | None = None,
        safesearch: bool = True,
    ) -> ProviderSearchResponse:
        """Search for images on a specific provider."""
        provider = registry.get(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

        if not provider.config.supports_images:
            raise HTTPException(status_code=400, detail=f"{provider_id} does not support images")

        result = await provider.search_images(
            q,
            page=page,
            per_page=per_page,
            media_type=media_type,
            category=category,
            orientation=orientation,
            color=color,
            safesearch=safesearch,
        )

        return ProviderSearchResponse(
            provider=provider_id,
            total=result.total,
            page=result.page,
            per_page=result.per_page,
            images=[img.model_dump() for img in result.images],
            videos=[],
            cached=result.cached,
            rate_limit=RateLimitResponse(
                limit=result.rate_limit.limit,
                remaining=result.rate_limit.remaining,
                reset_seconds=result.rate_limit.reset_seconds,
                is_exhausted=result.rate_limit.is_exhausted,
            ) if result.rate_limit else None,
        )

    @router.get("/{provider_id}/search/videos", response_model=ProviderSearchResponse)
    async def search_provider_videos(
        provider_id: str,
        q: Annotated[str, Query(min_length=1)],
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=20, ge=1, le=100),
    ) -> ProviderSearchResponse:
        """Search for videos on a specific provider."""
        provider = registry.get(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail=f"Provider not found: {provider_id}")

        if not provider.config.supports_videos:
            raise HTTPException(status_code=400, detail=f"{provider_id} does not support videos")

        result = await provider.search_videos(q, page=page, per_page=per_page)

        return ProviderSearchResponse(
            provider=provider_id,
            total=result.total,
            page=result.page,
            per_page=result.per_page,
            images=[],
            videos=[vid.model_dump() for vid in result.videos],
            cached=result.cached,
            rate_limit=RateLimitResponse(
                limit=result.rate_limit.limit,
                remaining=result.rate_limit.remaining,
                reset_seconds=result.rate_limit.reset_seconds,
                is_exhausted=result.rate_limit.is_exhausted,
            ) if result.rate_limit else None,
        )

    # --- Item retrieval ---

    @router.get("/{provider_id}/images/{image_id}")
    async def get_image(
        provider_id: str,
        image_id: str,
        registry: Annotated[ProviderRegistry, Depends(get_provider_registry)],
    ) -> dict[str, Any]:
        """Get a specific image by ID."""
        image = await registry.get_image(provider_id, image_id)
        if not image:
            raise HTTPException(status_code=404, detail="Image not found")
        return image.model_dump()

    return router
