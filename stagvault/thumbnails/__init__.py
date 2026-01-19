"""Thumbnail generation and caching module."""

from stagvault.thumbnails.cache import ThumbnailCache, ThumbnailEntry, ThumbnailStats
from stagvault.thumbnails.config import (
    CheckerboardConfig,
    ThumbnailConfig,
    ThumbnailSize,
)
from stagvault.thumbnails.generator import GenerationResult, ThumbnailGenerator
from stagvault.thumbnails.insights import ColorInfo, ImageInsights
from stagvault.thumbnails.renderer import ThumbnailRenderer

__all__ = [
    "CheckerboardConfig",
    "ColorInfo",
    "GenerationResult",
    "ImageInsights",
    "ThumbnailCache",
    "ThumbnailConfig",
    "ThumbnailEntry",
    "ThumbnailGenerator",
    "ThumbnailRenderer",
    "ThumbnailSize",
    "ThumbnailStats",
]
