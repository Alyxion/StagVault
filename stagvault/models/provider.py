"""API provider configuration models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ProviderTier(str, Enum):
    """Provider tier classification.

    standard: Normal rate limits, included in broad searches by default
    restricted: Low rate limits or strict terms, excluded from broad searches
    """
    STANDARD = "standard"
    RESTRICTED = "restricted"


class RateLimitConfig(BaseModel):
    """Rate limit configuration for API providers."""

    requests: int = Field(..., description="Maximum requests per window")
    window_seconds: int = Field(..., description="Time window in seconds")


class ApiConfig(BaseModel):
    """API source configuration."""

    base_url: str = Field(..., description="Base URL for API")
    auth_type: str = Field(..., description="Authentication type: query_param, header, bearer")
    auth_param: str = Field(default="key", description="Query param or header name for auth")
    auth_prefix: str | None = Field(default=None, description="Prefix for header auth (e.g., 'Client-ID ')")
    api_key_env: str = Field(..., description="Environment variable name for API key")
    rate_limit: RateLimitConfig = Field(..., description="Rate limit configuration")
    cache_duration: int = Field(default=86400, description="Cache TTL in seconds")
    endpoints: dict[str, str] = Field(default_factory=dict, description="API endpoint paths")


class ProviderRestrictions(BaseModel):
    """Usage restrictions for API providers."""

    hotlink_allowed: bool = Field(default=False, description="Can link directly to images")
    no_ads_alongside: bool = Field(default=False, description="Ads prohibited alongside content")
    no_resale: bool = Field(default=True, description="Cannot sell images")
    no_database: bool = Field(default=True, description="Cannot build competing database")
    download_required: bool = Field(default=False, description="Must download vs hotlink")
    download_trigger_required: bool = Field(default=False, description="Must call download endpoint")


class ProviderCapabilities(BaseModel):
    """Content capabilities for API providers."""

    images: bool = Field(default=True, description="Supports image search")
    videos: bool = Field(default=False, description="Supports video search")
    vectors: bool = Field(default=False, description="Supports vector graphics")
    illustrations: bool = Field(default=False, description="Supports illustrations")
