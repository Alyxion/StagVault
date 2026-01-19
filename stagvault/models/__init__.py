"""Data models for StagVault."""

from stagvault.models.git import GitConfig
from stagvault.models.media import License, MediaGroup, MediaItem, Source
from stagvault.models.metadata import ItemMetadata, SourceMetadataIndex
from stagvault.models.provider import (
    ApiConfig,
    ProviderCapabilities,
    ProviderRestrictions,
    ProviderTier,
    RateLimitConfig,
)
from stagvault.models.source import PathConfig, SourceConfig, SourceMetadata

__all__ = [
    # Media models
    "License",
    "MediaItem",
    "MediaGroup",
    "Source",
    # Git config
    "GitConfig",
    # Provider config
    "ApiConfig",
    "RateLimitConfig",
    "ProviderRestrictions",
    "ProviderCapabilities",
    "ProviderTier",
    # Source config
    "SourceConfig",
    "PathConfig",
    "SourceMetadata",
    # Metadata models
    "ItemMetadata",
    "SourceMetadataIndex",
]
