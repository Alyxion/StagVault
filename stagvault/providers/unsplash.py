"""Unsplash API provider.

API Documentation: https://unsplash.com/documentation

Rate Limits:
- Demo mode: 50 requests per hour
- Production mode: 5,000 requests per hour (after approval)
- Headers: X-Ratelimit-Limit, X-Ratelimit-Remaining

Authentication: Client-ID header (Authorization: Client-ID ACCESS_KEY)

Attribution Required:
- Must credit photographer and Unsplash
- Hotlinking is required (use returned URLs directly)
"""

from typing import Any

import httpx

from stagvault.providers.base import (
    APIProvider,
    MediaType,
    ProviderAuthType,
    ProviderConfig,
    ProviderImage,
    ProviderResult,
    ProviderTier,
    RateLimitInfo,
)
from stagvault.providers.cache import ProviderCache


UNSPLASH_CONFIG = ProviderConfig(
    id="unsplash",
    name="Unsplash",
    base_url="https://api.unsplash.com/",
    auth_type=ProviderAuthType.HEADER,
    auth_param="Authorization",
    api_key_env="UNSPLASH_API_KEY",
    rate_limit_window=3600,  # 1 hour
    rate_limit_requests=50,  # Demo mode - very conservative!
    cache_duration=86400,  # 24 hours
    requires_attribution=True,
    attribution_template="Photo by {author} on Unsplash",
    supports_images=True,
    supports_videos=False,  # Unsplash is photo-only
    hotlink_allowed=True,  # Required by Unsplash
    tier=ProviderTier.RESTRICTED,  # Low rate limit (50/hour demo), excluded from broad search
)


# Unsplash color filters
UNSPLASH_COLORS = [
    "black_and_white", "black", "white", "yellow", "orange",
    "red", "purple", "magenta", "green", "teal", "blue",
]

# Unsplash orientation options
UNSPLASH_ORIENTATIONS = ["landscape", "portrait", "squarish"]


class UnsplashProvider(APIProvider):
    """Unsplash API provider implementation.

    Note: Unsplash has very low rate limits in demo mode (50/hour).
    Caching is critical to avoid hitting limits.
    """

    def __init__(self, cache: ProviderCache | None = None) -> None:
        super().__init__(UNSPLASH_CONFIG, cache)
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with auth headers."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Authorization": f"Client-ID {self.api_key}"},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def update_rate_limit(self, headers: dict[str, str]) -> None:
        """Update rate limit from Unsplash headers."""
        self._rate_limit = RateLimitInfo(
            limit=int(headers.get("X-Ratelimit-Limit", 50)),
            remaining=int(headers.get("X-Ratelimit-Remaining", 50)),
            reset_seconds=3600,  # Unsplash resets hourly
            window_seconds=3600,
        )

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | list[Any], dict[str, str]]:
        """Make an API request with rate limit handling."""
        # Check rate limit - be extra conservative for Unsplash's low limits
        if self.rate_limit.should_wait:
            wait_time = self.rate_limit.wait_time()
            if wait_time > 0:
                import asyncio
                await asyncio.sleep(min(wait_time, 120))  # Cap wait at 2 min

        url = f"{self.config.base_url}{endpoint}"

        response = await self.client.get(url, params=params)

        # Handle rate limiting
        if response.status_code == 429:
            self.update_rate_limit(dict(response.headers))
            raise Exception("Rate limit exceeded. Unsplash has low limits (50/hour in demo mode).")

        response.raise_for_status()

        # Update rate limit from headers
        self.update_rate_limit(dict(response.headers))

        return response.json(), dict(response.headers)

    def _parse_image(self, photo: dict[str, Any]) -> ProviderImage:
        """Parse Unsplash photo response to unified format."""
        urls = photo.get("urls", {})
        user = photo.get("user", {})

        # Extract tags if available
        tags = []
        if photo.get("tags"):
            tags = [t.get("title", "") for t in photo.get("tags", []) if t.get("title")]

        return ProviderImage(
            id=photo["id"],
            provider="unsplash",
            source_url=photo.get("links", {}).get("html", ""),
            preview_url=urls.get("thumb", urls.get("small", "")),
            web_url=urls.get("regular", urls.get("small", "")),
            full_url=urls.get("full"),
            width=photo.get("width", 0),
            height=photo.get("height", 0),
            tags=tags,
            description=photo.get("description") or photo.get("alt_description"),
            author=user.get("name", user.get("username", "")),
            author_url=user.get("links", {}).get("html", ""),
            license="Unsplash License",
            media_type=MediaType.PHOTO,
            likes=photo.get("likes"),
            extra={
                "color": photo.get("color"),
                "blur_hash": photo.get("blur_hash"),
                "created_at": photo.get("created_at"),
                "urls": urls,  # All available sizes
                "user_id": user.get("id"),
                "username": user.get("username"),
            },
        )

    async def search_images(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 20,
        media_type: MediaType = MediaType.ALL,
        order_by: str = "relevant",  # relevant or latest
        orientation: str | None = None,  # landscape, portrait, squarish
        color: str | None = None,
        content_filter: str = "low",  # low or high
        **kwargs: Any,
    ) -> ProviderResult:
        """Search for photos on Unsplash.

        Args:
            query: Search term
            page: Page number (default 1)
            per_page: Results per page (max 30, default 20)
            order_by: Sort order - "relevant" or "latest"
            orientation: landscape, portrait, or squarish
            color: Color filter
            content_filter: "low" (default) or "high" (stricter)
        """
        # Check cache first - critical for Unsplash's low rate limits!
        cache_params = {
            "query": query, "page": page, "per_page": per_page,
            "order_by": order_by, "orientation": orientation,
            "color": color, "content_filter": content_filter,
        }

        if self.cache:
            cached = self.cache.get("unsplash", "search_images", cache_params)
            if cached:
                result = ProviderResult.model_validate(cached)
                result.cached = True
                return result

        # Build request params
        params: dict[str, Any] = {
            "query": query,
            "page": page,
            "per_page": min(per_page, 30),  # Max 30 per page
            "order_by": order_by,
            "content_filter": content_filter,
        }

        if orientation in UNSPLASH_ORIENTATIONS:
            params["orientation"] = orientation

        if color and color in UNSPLASH_COLORS:
            params["color"] = color

        # Make request
        data, headers = await self._request("search/photos", params)

        # Parse response
        photos = data.get("results", []) if isinstance(data, dict) else []
        images = [self._parse_image(photo) for photo in photos]

        result = ProviderResult(
            provider="unsplash",
            total=data.get("total", 0) if isinstance(data, dict) else 0,
            page=page,
            per_page=per_page,
            images=images,
            cached=False,
            rate_limit=self.rate_limit,
        )

        # Cache the result - important for low rate limits!
        if self.cache:
            self.cache.set(
                "unsplash",
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
        **kwargs: Any,
    ) -> ProviderResult:
        """Unsplash does not support videos."""
        return ProviderResult(
            provider="unsplash",
            total=0,
            page=page,
            per_page=per_page,
            videos=[],
            cached=True,  # No API call needed
        )

    async def get_image(self, image_id: str) -> ProviderImage | None:
        """Get a specific photo by ID."""
        cache_params = {"id": image_id}

        if self.cache:
            cached = self.cache.get("unsplash", "get_image", cache_params)
            if cached:
                return ProviderImage.model_validate(cached)

        try:
            data, _ = await self._request(f"photos/{image_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

        if not isinstance(data, dict):
            return None

        image = self._parse_image(data)

        if self.cache:
            self.cache.set(
                "unsplash",
                "get_image",
                cache_params,
                image.model_dump(),
                ttl=self.config.cache_duration,
            )

        return image

    async def get_random(
        self,
        query: str | None = None,
        count: int = 1,
        orientation: str | None = None,
    ) -> list[ProviderImage]:
        """Get random photos.

        Args:
            query: Optional search term to filter random photos
            count: Number of random photos (1-30)
            orientation: landscape, portrait, or squarish
        """
        cache_params = {"query": query, "count": count, "orientation": orientation}

        if self.cache:
            cached = self.cache.get("unsplash", "get_random", cache_params)
            if cached:
                return [ProviderImage.model_validate(img) for img in cached]

        params: dict[str, Any] = {"count": min(count, 30)}

        if query:
            params["query"] = query

        if orientation in UNSPLASH_ORIENTATIONS:
            params["orientation"] = orientation

        data, _ = await self._request("photos/random", params)

        # Response is a list when count > 1, single object when count = 1
        if isinstance(data, dict):
            photos = [data]
        else:
            photos = data

        images = [self._parse_image(photo) for photo in photos]

        if self.cache:
            self.cache.set(
                "unsplash",
                "get_random",
                cache_params,
                [img.model_dump() for img in images],
                ttl=3600,  # Shorter cache for random
            )

        return images

    async def track_download(self, image_id: str) -> bool:
        """Track a photo download (required by Unsplash guidelines).

        Call this when a user downloads a photo to properly credit
        the photographer.
        """
        try:
            await self._request(f"photos/{image_id}/download")
            return True
        except Exception:
            return False
