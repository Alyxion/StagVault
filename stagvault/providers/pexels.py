"""Pexels API provider.

API Documentation: https://www.pexels.com/api/documentation/

Rate Limits:
- 200 requests per hour (default)
- 20,000 requests per month

Authentication: API key in Authorization header

Attribution Required:
- Must show "Photos provided by Pexels" with link
- Credit photographers when possible
"""

from __future__ import annotations

from typing import Any

import httpx

from stagvault.providers.base import (
    APIProvider,
    MediaType,
    ProviderAuthType,
    ProviderConfig,
    ProviderImage,
    ProviderResult,
    ProviderVideo,
    RateLimitInfo,
)
from stagvault.providers.cache import ProviderCache


PEXELS_CONFIG = ProviderConfig(
    id="pexels",
    name="Pexels",
    base_url="https://api.pexels.com/",
    auth_type=ProviderAuthType.HEADER,
    auth_param="Authorization",
    api_key_env="PEXELS_API_KEY",
    rate_limit_window=3600,  # 1 hour
    rate_limit_requests=200,
    cache_duration=86400,  # 24 hours
    requires_attribution=True,
    attribution_template="Photo by {author} on Pexels",
    supports_images=True,
    supports_videos=True,
    hotlink_allowed=True,  # Pexels allows hotlinking
)


class PexelsProvider(APIProvider):
    """Pexels API provider implementation."""

    def __init__(self, cache: ProviderCache | None = None) -> None:
        super().__init__(PEXELS_CONFIG, cache)
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers=self.get_auth_headers(),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def update_rate_limit(self, headers: dict[str, str]) -> None:
        """Update rate limit from Pexels headers."""
        # Pexels uses different header names
        self._rate_limit = RateLimitInfo(
            limit=int(headers.get("X-Ratelimit-Limit", 200)),
            remaining=int(headers.get("X-Ratelimit-Remaining", 200)),
            reset_seconds=int(headers.get("X-Ratelimit-Reset", 3600)),
            window_seconds=3600,
        )

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Make an API request with rate limit handling."""
        # Check rate limit
        if self.rate_limit.should_wait:
            wait_time = self.rate_limit.wait_time()
            if wait_time > 0:
                import asyncio
                await asyncio.sleep(min(wait_time, 60))  # Cap wait at 60s

        url = f"{self.config.base_url}{endpoint}"

        response = await self.client.get(url, params=params)

        # Handle rate limiting
        if response.status_code == 429:
            self.update_rate_limit(dict(response.headers))
            raise Exception("Rate limit exceeded. Try again later.")

        response.raise_for_status()

        # Update rate limit from headers
        self.update_rate_limit(dict(response.headers))

        return response.json(), dict(response.headers)

    def _parse_image(self, photo: dict[str, Any]) -> ProviderImage:
        """Parse Pexels photo response to unified format."""
        src = photo.get("src", {})

        return ProviderImage(
            id=str(photo["id"]),
            provider="pexels",
            source_url=photo["url"],
            preview_url=src.get("tiny", src.get("small", "")),
            web_url=src.get("medium", src.get("large", "")),
            full_url=src.get("original"),
            width=photo["width"],
            height=photo["height"],
            tags=[],  # Pexels doesn't provide tags
            description=photo.get("alt", ""),
            author=photo.get("photographer", ""),
            author_url=photo.get("photographer_url", ""),
            license="Pexels License",
            media_type=MediaType.PHOTO,
            extra={
                "avg_color": photo.get("avg_color"),
                "liked": photo.get("liked", False),
                "src": src,  # All available sizes
            },
        )

    def _parse_video(self, video: dict[str, Any]) -> ProviderVideo:
        """Parse Pexels video response to unified format."""
        video_files = video.get("video_files", [])
        video_urls = {}

        for vf in video_files:
            quality = vf.get("quality", "unknown")
            if "link" in vf:
                # Use quality and resolution as key
                key = f"{quality}_{vf.get('width', 0)}x{vf.get('height', 0)}"
                video_urls[key] = vf["link"]

        # Get best quality dimensions
        width = height = 0
        for vf in video_files:
            if vf.get("width", 0) > width:
                width = vf.get("width", 0)
                height = vf.get("height", 0)

        return ProviderVideo(
            id=str(video["id"]),
            provider="pexels",
            source_url=video["url"],
            preview_url=video.get("image", ""),  # Video thumbnail
            video_urls=video_urls,
            width=width,
            height=height,
            duration=video.get("duration", 0),
            tags=[],
            description="",
            author=video.get("user", {}).get("name", ""),
            author_url=video.get("user", {}).get("url", ""),
            license="Pexels License",
        )

    async def search_images(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 20,
        media_type: MediaType = MediaType.ALL,
        orientation: str | None = None,  # landscape, portrait, square
        size: str | None = None,  # large, medium, small
        color: str | None = None,  # hex color or color name
        locale: str = "en-US",
        **kwargs: Any,
    ) -> ProviderResult:
        """Search for photos on Pexels.

        Args:
            query: Search term
            page: Page number (default 1)
            per_page: Results per page (max 80, default 20)
            orientation: landscape, portrait, or square
            size: large, medium, or small
            color: Filter by color (hex or name)
            locale: Locale for search (default en-US)
        """
        # Check cache first
        cache_params = {
            "query": query, "page": page, "per_page": per_page,
            "orientation": orientation, "size": size, "color": color,
        }

        if self.cache:
            cached = self.cache.get("pexels", "search_images", cache_params)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        # Build request params
        params: dict[str, Any] = {
            "query": query,
            "page": page,
            "per_page": min(per_page, 80),  # Max 80
            "locale": locale,
        }

        if orientation in ("landscape", "portrait", "square"):
            params["orientation"] = orientation

        if size in ("large", "medium", "small"):
            params["size"] = size

        if color:
            params["color"] = color

        # Make request
        data, headers = await self._request("v1/search", params)

        # Parse response
        images = [self._parse_image(photo) for photo in data.get("photos", [])]

        result = ProviderResult(
            provider="pexels",
            total=data.get("total_results", 0),
            page=page,
            per_page=per_page,
            images=images,
            cached=False,
            rate_limit=self.rate_limit,
        )

        # Cache the result
        if self.cache:
            self.cache.set(
                "pexels",
                "search_images",
                cache_params,
                result.model_dump(),
                ttl=self.config.cache_duration,
            )

        return result

    async def search_videos(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 20,
        orientation: str | None = None,
        size: str | None = None,
        locale: str = "en-US",
        **kwargs: Any,
    ) -> ProviderResult:
        """Search for videos on Pexels."""
        # Check cache first
        cache_params = {
            "query": query, "page": page, "per_page": per_page,
            "orientation": orientation, "size": size,
        }

        if self.cache:
            cached = self.cache.get("pexels", "search_videos", cache_params)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        # Build request params
        params: dict[str, Any] = {
            "query": query,
            "page": page,
            "per_page": min(per_page, 80),
            "locale": locale,
        }

        if orientation in ("landscape", "portrait", "square"):
            params["orientation"] = orientation

        if size in ("large", "medium", "small"):
            params["size"] = size

        # Make request
        data, headers = await self._request("videos/search", params)

        # Parse response
        videos = [self._parse_video(video) for video in data.get("videos", [])]

        result = ProviderResult(
            provider="pexels",
            total=data.get("total_results", 0),
            page=page,
            per_page=per_page,
            videos=videos,
            cached=False,
            rate_limit=self.rate_limit,
        )

        # Cache the result
        if self.cache:
            self.cache.set(
                "pexels",
                "search_videos",
                cache_params,
                result.model_dump(),
                ttl=self.config.cache_duration,
            )

        return result

    async def get_image(self, image_id: str) -> ProviderImage | None:
        """Get a specific photo by ID."""
        cache_params = {"id": image_id}

        if self.cache:
            cached = self.cache.get("pexels", "get_image", cache_params)
            if cached:
                return ProviderImage.model_validate(cached)

        try:
            data, _ = await self._request(f"v1/photos/{image_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

        image = self._parse_image(data)

        if self.cache:
            self.cache.set(
                "pexels",
                "get_image",
                cache_params,
                image.model_dump(),
                ttl=self.config.cache_duration,
            )

        return image

    async def get_video(self, video_id: str) -> ProviderVideo | None:
        """Get a specific video by ID."""
        cache_params = {"id": video_id}

        if self.cache:
            cached = self.cache.get("pexels", "get_video", cache_params)
            if cached:
                return ProviderVideo.model_validate(cached)

        try:
            data, _ = await self._request(f"videos/videos/{video_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

        video = self._parse_video(data)

        if self.cache:
            self.cache.set(
                "pexels",
                "get_video",
                cache_params,
                video.model_dump(),
                ttl=self.config.cache_duration,
            )

        return video

    async def curated(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> ProviderResult:
        """Get curated photos (trending/editor's picks)."""
        cache_params = {"page": page, "per_page": per_page}

        if self.cache:
            cached = self.cache.get("pexels", "curated", cache_params)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        params = {"page": page, "per_page": min(per_page, 80)}
        data, _ = await self._request("v1/curated", params)

        images = [self._parse_image(photo) for photo in data.get("photos", [])]

        result = ProviderResult(
            provider="pexels",
            total=data.get("total_results", 0),
            page=page,
            per_page=per_page,
            images=images,
            cached=False,
            rate_limit=self.rate_limit,
        )

        if self.cache:
            # Shorter cache for curated (updates hourly)
            self.cache.set(
                "pexels",
                "curated",
                cache_params,
                result.model_dump(),
                ttl=3600,  # 1 hour
            )

        return result

    async def popular_videos(
        self,
        page: int = 1,
        per_page: int = 20,
    ) -> ProviderResult:
        """Get popular videos."""
        cache_params = {"page": page, "per_page": per_page}

        if self.cache:
            cached = self.cache.get("pexels", "popular_videos", cache_params)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        params = {"page": page, "per_page": min(per_page, 80)}
        data, _ = await self._request("videos/popular", params)

        videos = [self._parse_video(video) for video in data.get("videos", [])]

        result = ProviderResult(
            provider="pexels",
            total=data.get("total_results", 0),
            page=page,
            per_page=per_page,
            videos=videos,
            cached=False,
            rate_limit=self.rate_limit,
        )

        if self.cache:
            self.cache.set(
                "pexels",
                "popular_videos",
                cache_params,
                result.model_dump(),
                ttl=3600,
            )

        return result
