"""Base API provider with rate limiting and caching support.

Providers can be accessed via:
1. Pure JavaScript (direct browser calls with CORS)
2. Python (direct usage)
3. FastAPI routes (proxied through backend)
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MediaType(str, Enum):
    """Type of media returned by providers."""
    PHOTO = "photo"
    VIDEO = "video"
    VECTOR = "vector"
    ILLUSTRATION = "illustration"
    ALL = "all"


class ProviderAuthType(str, Enum):
    """How the provider authenticates requests."""
    QUERY_PARAM = "query_param"  # API key in URL query string
    HEADER = "header"  # API key in Authorization header
    BEARER = "bearer"  # Bearer token in Authorization header


# Re-export ProviderTier from models for convenience
from stagvault.models.provider import ProviderTier


@dataclass
class RateLimitInfo:
    """Rate limit status from provider response.

    Implements conservative rate limiting for APIs with low limits.
    For example, some providers only allow 50 requests per hour.
    """
    limit: int = 100  # Max requests per window
    remaining: int = 100  # Requests remaining
    reset_seconds: int = 60  # Seconds until window resets
    window_seconds: int = 60  # Window duration
    timestamp: float = field(default_factory=time.time)
    # Base buffer - minimum requests to keep in reserve
    base_buffer: int = 3

    @property
    def buffer(self) -> int:
        """Dynamic buffer based on limit size.

        Low-limit providers (< 100/window): Keep 10% in reserve
        Medium-limit providers (100-500): Keep 5% in reserve
        High-limit providers (> 500): Keep 3% in reserve
        """
        if self.limit < 100:
            # Very low limit (e.g., 50/hour) - keep 10% reserve
            return max(self.base_buffer, int(self.limit * 0.10))
        elif self.limit < 500:
            # Medium limit - keep 5% reserve
            return max(self.base_buffer, int(self.limit * 0.05))
        else:
            # High limit - keep 3% reserve
            return max(self.base_buffer, int(self.limit * 0.03))

    @property
    def is_exhausted(self) -> bool:
        """Check if rate limit is exhausted."""
        return self.remaining <= 0

    @property
    def should_wait(self) -> bool:
        """Check if we should wait before making a request.

        Be conservative - keep buffer requests in reserve for critical calls.
        """
        return self.remaining <= self.buffer

    @property
    def is_low(self) -> bool:
        """Check if rate limit is getting low (< 20% remaining)."""
        return self.remaining < (self.limit * 0.2)

    @property
    def is_critical(self) -> bool:
        """Check if rate limit is critically low (< 10% remaining)."""
        return self.remaining < (self.limit * 0.1)

    def wait_time(self) -> float:
        """Calculate how long to wait before next request."""
        if not self.should_wait:
            return 0
        elapsed = time.time() - self.timestamp
        return max(0, self.reset_seconds - elapsed)

    def estimate_requests_available(self) -> int:
        """Estimate how many more requests we can safely make."""
        return max(0, self.remaining - self.buffer)

    def time_until_request_available(self) -> float:
        """Estimate time until a request slot becomes available.

        Useful for low-limit providers where we need to space requests.
        """
        if self.remaining > self.buffer:
            return 0
        # Calculate average time between request slots
        elapsed = time.time() - self.timestamp
        time_left = max(0, self.reset_seconds - elapsed)
        if self.limit <= 0:
            return time_left
        # Space remaining requests evenly
        return time_left / max(1, self.limit)

    @classmethod
    def from_headers(
        cls,
        headers: dict[str, str],
        limit_key: str = "X-RateLimit-Limit",
        remaining_key: str = "X-RateLimit-Remaining",
        reset_key: str = "X-RateLimit-Reset",
    ) -> "RateLimitInfo":
        """Parse rate limit info from response headers."""
        return cls(
            limit=int(headers.get(limit_key, 100)),
            remaining=int(headers.get(remaining_key, 100)),
            reset_seconds=int(headers.get(reset_key, 60)),
            timestamp=time.time(),
        )


class ProviderImage(BaseModel):
    """Unified image result from any provider."""
    id: str
    provider: str
    source_url: str = Field(..., description="Original page URL")
    preview_url: str = Field(..., description="Small preview/thumbnail")
    web_url: str = Field(..., description="Web-sized image (640px)")
    full_url: str | None = Field(default=None, description="Full resolution if available")
    width: int
    height: int
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    author: str | None = None
    author_url: str | None = None
    license: str = "Provider License"
    media_type: MediaType = MediaType.PHOTO
    downloads: int | None = None
    likes: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ProviderVideo(BaseModel):
    """Unified video result from any provider."""
    id: str
    provider: str
    source_url: str
    preview_url: str  # Video thumbnail
    video_urls: dict[str, str] = Field(default_factory=dict)  # quality -> url
    width: int
    height: int
    duration: int  # seconds
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    author: str | None = None
    author_url: str | None = None
    license: str = "Provider License"


class ProviderResult(BaseModel):
    """Search result from a provider."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    provider: str
    total: int
    page: int
    per_page: int
    images: list[ProviderImage] = Field(default_factory=list)
    videos: list[ProviderVideo] = Field(default_factory=list)
    cached: bool = False
    cache_expires: float | None = None
    rate_limit: RateLimitInfo | None = None


class ProviderConfig(BaseModel):
    """Configuration for an API provider."""
    id: str
    name: str
    base_url: str
    auth_type: ProviderAuthType
    auth_param: str = "key"  # Query param name or header name
    api_key_env: str  # Environment variable name for API key
    rate_limit_window: int = 60  # seconds
    rate_limit_requests: int = 100
    cache_duration: int = 86400  # 24 hours in seconds
    requires_attribution: bool = True
    attribution_template: str = "Photo by {author} on {provider}"
    supports_images: bool = True
    supports_videos: bool = False
    hotlink_allowed: bool = False  # If false, must download images
    tier: ProviderTier = ProviderTier.STANDARD  # Provider classification


class APIProvider(ABC):
    """Abstract base class for API providers.

    Implementations must handle:
    - Authentication (from environment variables)
    - Rate limiting (tracking and respecting limits)
    - Caching integration
    - Response normalization to ProviderImage/ProviderVideo
    """

    def __init__(self, config: ProviderConfig, cache: "ProviderCache | None" = None) -> None:
        self.config = config
        self.cache = cache
        self._rate_limit = RateLimitInfo(
            limit=config.rate_limit_requests,
            remaining=config.rate_limit_requests,
            window_seconds=config.rate_limit_window,
        )
        self._api_key: str | None = None

    @property
    def api_key(self) -> str:
        """Get API key from environment. Never store in source."""
        if self._api_key is None:
            self._api_key = os.environ.get(self.config.api_key_env, "")
            if not self._api_key:
                raise ValueError(
                    f"API key not found. Set {self.config.api_key_env} environment variable."
                )
        return self._api_key

    @property
    def rate_limit(self) -> RateLimitInfo:
        """Current rate limit status."""
        return self._rate_limit

    def update_rate_limit(self, headers: dict[str, str]) -> None:
        """Update rate limit from response headers."""
        self._rate_limit = RateLimitInfo.from_headers(headers)

    def get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for requests."""
        if self.config.auth_type == ProviderAuthType.HEADER:
            return {self.config.auth_param: self.api_key}
        elif self.config.auth_type == ProviderAuthType.BEARER:
            return {"Authorization": f"Bearer {self.api_key}"}
        return {}

    def get_auth_params(self) -> dict[str, str]:
        """Get authentication query parameters."""
        if self.config.auth_type == ProviderAuthType.QUERY_PARAM:
            return {self.config.auth_param: self.api_key}
        return {}

    @abstractmethod
    async def search_images(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 20,
        media_type: MediaType = MediaType.ALL,
        **kwargs: Any,
    ) -> ProviderResult:
        """Search for images."""
        ...

    @abstractmethod
    async def search_videos(
        self,
        query: str,
        *,
        page: int = 1,
        per_page: int = 20,
        **kwargs: Any,
    ) -> ProviderResult:
        """Search for videos."""
        ...

    @abstractmethod
    async def get_image(self, image_id: str) -> ProviderImage | None:
        """Get a specific image by ID."""
        ...

    def get_cache_key(self, method: str, **params: Any) -> str:
        """Generate cache key for a request."""
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
        return f"{self.config.id}:{method}:{param_str}"

    def get_attribution(self, image: ProviderImage) -> str:
        """Generate attribution text for an image."""
        return self.config.attribution_template.format(
            author=image.author or "Unknown",
            provider=self.config.name,
            url=image.source_url,
        )

    def js_config(self) -> dict[str, Any]:
        """Get configuration for JavaScript client (excludes API key)."""
        return {
            "id": self.config.id,
            "name": self.config.name,
            "baseUrl": self.config.base_url,
            "authType": self.config.auth_type.value,
            "authParam": self.config.auth_param,
            "requiresAttribution": self.config.requires_attribution,
            "attributionTemplate": self.config.attribution_template,
            "supportsImages": self.config.supports_images,
            "supportsVideos": self.config.supports_videos,
            "hotlinkAllowed": self.config.hotlink_allowed,
            "cacheDuration": self.config.cache_duration,
            "rateLimitWindow": self.config.rate_limit_window,
            "rateLimitRequests": self.config.rate_limit_requests,
            "tier": self.config.tier.value,
        }


# Import here to avoid circular imports
from stagvault.providers.cache import ProviderCache  # noqa: E402
