"""Pixabay API provider.

API Documentation: https://pixabay.com/api/docs/

Rate Limits:
- 100 requests per 60 seconds (default)
- Must cache results for 24 hours
- No mass automated downloads
- No permanent hotlinking (must download images)

Authentication: API key as query parameter
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

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


PIXABAY_CONFIG = ProviderConfig(
    id="pixabay",
    name="Pixabay",
    base_url="https://pixabay.com/api/",
    auth_type=ProviderAuthType.QUERY_PARAM,
    auth_param="key",
    api_key_env="PIXABAY_API_KEY",
    rate_limit_window=60,
    rate_limit_requests=100,
    cache_duration=86400,  # 24 hours required by Pixabay
    requires_attribution=False,  # Pixabay doesn't require attribution
    attribution_template="Image from Pixabay",
    supports_images=True,
    supports_videos=True,
    hotlink_allowed=False,  # Must download images
)


# Pixabay categories
PIXABAY_CATEGORIES = [
    "backgrounds", "fashion", "nature", "science", "education", "feelings",
    "health", "people", "religion", "places", "animals", "industry", "computer",
    "food", "sports", "transportation", "travel", "buildings", "business", "music",
]

# Pixabay color filters
PIXABAY_COLORS = [
    "grayscale", "transparent", "red", "orange", "yellow", "green", "turquoise",
    "blue", "lilac", "pink", "white", "gray", "black", "brown",
]


class PixabayProvider(APIProvider):
    """Pixabay API provider implementation."""

    def __init__(self, cache: ProviderCache | None = None) -> None:
        super().__init__(PIXABAY_CONFIG, cache)
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Make an API request with rate limit handling."""
        # Check rate limit
        if self.rate_limit.should_wait:
            wait_time = self.rate_limit.wait_time()
            if wait_time > 0:
                import asyncio
                await asyncio.sleep(wait_time)

        # Add authentication
        params = {**params, **self.get_auth_params()}

        url = f"{self.config.base_url}{endpoint}"
        if params:
            url = f"{url}?{urlencode(params)}"

        response = await self.client.get(url)
        response.raise_for_status()

        # Update rate limit from headers
        self.update_rate_limit(dict(response.headers))

        return response.json(), dict(response.headers)

    def _parse_image(self, hit: dict[str, Any]) -> ProviderImage:
        """Parse Pixabay image response to unified format."""
        tags = [t.strip() for t in hit.get("tags", "").split(",") if t.strip()]

        return ProviderImage(
            id=str(hit["id"]),
            provider="pixabay",
            source_url=hit["pageURL"],
            preview_url=hit["previewURL"],
            web_url=hit["webformatURL"],
            full_url=hit.get("largeImageURL"),
            width=hit["imageWidth"],
            height=hit["imageHeight"],
            tags=tags,
            description=hit.get("tags"),
            author=hit.get("user"),
            author_url=f"https://pixabay.com/users/{hit.get('user', '')}-{hit.get('user_id', '')}/",
            license="Pixabay License",
            media_type=MediaType(hit.get("type", "photo")),
            downloads=hit.get("downloads"),
            likes=hit.get("likes"),
            extra={
                "views": hit.get("views"),
                "comments": hit.get("comments"),
                "user_id": hit.get("user_id"),
            },
        )

    def _parse_video(self, hit: dict[str, Any]) -> ProviderVideo:
        """Parse Pixabay video response to unified format."""
        tags = [t.strip() for t in hit.get("tags", "").split(",") if t.strip()]

        # Extract video URLs by quality
        videos = hit.get("videos", {})
        video_urls = {}
        for quality, video_data in videos.items():
            if isinstance(video_data, dict) and "url" in video_data:
                video_urls[quality] = video_data["url"]

        return ProviderVideo(
            id=str(hit["id"]),
            provider="pixabay",
            source_url=hit["pageURL"],
            preview_url=hit.get("picture_id", ""),  # Video thumbnail
            video_urls=video_urls,
            width=hit.get("videos", {}).get("large", {}).get("width", 0),
            height=hit.get("videos", {}).get("large", {}).get("height", 0),
            duration=hit.get("duration", 0),
            tags=tags,
            description=hit.get("tags"),
            author=hit.get("user"),
            author_url=f"https://pixabay.com/users/{hit.get('user', '')}-{hit.get('user_id', '')}/",
            license="Pixabay License",
        )

    async def search_images(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 20,
        media_type: MediaType = MediaType.ALL,
        category: str | None = None,
        colors: list[str] | None = None,
        editors_choice: bool = False,
        safesearch: bool = True,
        orientation: str | None = None,  # horizontal, vertical
        min_width: int = 0,
        min_height: int = 0,
        **kwargs: Any,
    ) -> ProviderResult:
        """Search for images on Pixabay.

        Args:
            query: Search term (max 100 chars)
            page: Page number (default 1)
            per_page: Results per page (3-200, default 20)
            media_type: photo, illustration, vector, or all
            category: Filter by category
            colors: Filter by colors
            editors_choice: Only editor's choice images
            safesearch: Filter adult content
            orientation: horizontal or vertical
            min_width: Minimum image width
            min_height: Minimum image height
        """
        # Check cache first
        cache_params = {
            "q": query, "page": page, "per_page": per_page,
            "image_type": media_type.value, "category": category,
            "safesearch": safesearch,
        }

        if self.cache:
            cached = self.cache.get("pixabay", "search_images", cache_params)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        # Build request params
        params: dict[str, Any] = {
            "q": query[:100],  # Max 100 chars
            "page": page,
            "per_page": min(max(per_page, 3), 200),  # 3-200
            "safesearch": str(safesearch).lower(),
        }

        if media_type != MediaType.ALL:
            params["image_type"] = media_type.value

        if category and category in PIXABAY_CATEGORIES:
            params["category"] = category

        if colors:
            valid_colors = [c for c in colors if c in PIXABAY_COLORS]
            if valid_colors:
                params["colors"] = ",".join(valid_colors)

        if editors_choice:
            params["editors_choice"] = "true"

        if orientation in ("horizontal", "vertical"):
            params["orientation"] = orientation

        if min_width > 0:
            params["min_width"] = min_width

        if min_height > 0:
            params["min_height"] = min_height

        # Make request
        data, headers = await self._request("", params)

        # Parse response
        images = [self._parse_image(hit) for hit in data.get("hits", [])]

        result = ProviderResult(
            provider="pixabay",
            total=data.get("totalHits", 0),
            page=page,
            per_page=per_page,
            images=images,
            cached=False,
            rate_limit=self.rate_limit,
        )

        # Cache the result
        if self.cache:
            self.cache.set(
                "pixabay",
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
        category: str | None = None,
        editors_choice: bool = False,
        safesearch: bool = True,
        min_width: int = 0,
        min_height: int = 0,
        **kwargs: Any,
    ) -> ProviderResult:
        """Search for videos on Pixabay."""
        # Check cache first
        cache_params = {
            "q": query, "page": page, "per_page": per_page,
            "category": category, "safesearch": safesearch,
        }

        if self.cache:
            cached = self.cache.get("pixabay", "search_videos", cache_params)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        # Build request params
        params: dict[str, Any] = {
            "q": query[:100],
            "page": page,
            "per_page": min(max(per_page, 3), 200),
            "safesearch": str(safesearch).lower(),
        }

        if category and category in PIXABAY_CATEGORIES:
            params["category"] = category

        if editors_choice:
            params["editors_choice"] = "true"

        if min_width > 0:
            params["min_width"] = min_width

        if min_height > 0:
            params["min_height"] = min_height

        # Make request to videos endpoint
        data, headers = await self._request("videos/", params)

        # Parse response
        videos = [self._parse_video(hit) for hit in data.get("hits", [])]

        result = ProviderResult(
            provider="pixabay",
            total=data.get("totalHits", 0),
            page=page,
            per_page=per_page,
            videos=videos,
            cached=False,
            rate_limit=self.rate_limit,
        )

        # Cache the result
        if self.cache:
            self.cache.set(
                "pixabay",
                "search_videos",
                cache_params,
                result.model_dump(),
                ttl=self.config.cache_duration,
            )

        return result

    async def get_image(self, image_id: str) -> ProviderImage | None:
        """Get a specific image by ID."""
        cache_params = {"id": image_id}

        if self.cache:
            cached = self.cache.get("pixabay", "get_image", cache_params)
            if cached:
                return ProviderImage.model_validate(cached)

        params = {"id": image_id}
        data, _ = await self._request("", params)

        hits = data.get("hits", [])
        if not hits:
            return None

        image = self._parse_image(hits[0])

        if self.cache:
            self.cache.set(
                "pixabay",
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
            cached = self.cache.get("pixabay", "get_video", cache_params)
            if cached:
                return ProviderVideo.model_validate(cached)

        params = {"id": video_id}
        data, _ = await self._request("videos/", params)

        hits = data.get("hits", [])
        if not hits:
            return None

        video = self._parse_video(hits[0])

        if self.cache:
            self.cache.set(
                "pixabay",
                "get_video",
                cache_params,
                video.model_dump(),
                ttl=self.config.cache_duration,
            )

        return video
