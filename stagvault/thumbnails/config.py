"""Thumbnail configuration and size definitions."""

from __future__ import annotations

from enum import IntEnum
from pathlib import Path

from pydantic import BaseModel, Field


class ThumbnailSize(IntEnum):
    """Standard thumbnail sizes."""

    TINY = 24
    SMALL = 32
    ICON = 48
    MEDIUM = 64
    LARGE = 96
    XLARGE = 128
    PREVIEW = 256

    @classmethod
    def all_sizes(cls) -> list[int]:
        """Return all standard sizes as integers."""
        return [size.value for size in cls]

    @classmethod
    def from_int(cls, value: int) -> ThumbnailSize | None:
        """Get ThumbnailSize from integer value, or None if not standard."""
        for size in cls:
            if size.value == value:
                return size
        return None


class CheckerboardConfig(BaseModel):
    """Configuration for checkerboard transparency background (JPG only)."""

    light_color: str = Field(default="#ffffff", description="Light square color (hex)")
    dark_color: str = Field(default="#cccccc", description="Dark square color (hex)")
    square_size: int = Field(default=8, description="Size of each square in pixels")


class ThumbnailConfig(BaseModel):
    """Configuration for thumbnail generation."""

    sizes: list[int] = Field(
        default_factory=ThumbnailSize.all_sizes,
        description="Sizes to generate thumbnails for",
    )
    jpg_quality: int = Field(default=85, description="JPEG quality (1-100)")
    checkerboard: CheckerboardConfig = Field(
        default_factory=CheckerboardConfig,
        description="Checkerboard background settings for JPG",
    )
    storage_path: Path | None = Field(
        default=None, description="Custom storage path for thumbnails"
    )
    workers: int = Field(default=16, description="Number of parallel workers")
    insights_size: int = Field(default=128, description="Size at which to generate insights")

    @property
    def supported_input_formats(self) -> set[str]:
        """File formats that can be rendered as thumbnails."""
        return {"svg", "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico"}

    def get_thumbnail_path(
        self, base_dir: Path, source_id: str, item_id: str, size: int, ext: str = "png"
    ) -> Path:
        """Get the file path for a thumbnail.

        Uses sharding based on first 2 characters of item_id for better
        filesystem performance with large numbers of files.
        """
        prefix = item_id[:2] if len(item_id) >= 2 else item_id
        return (
            base_dir / "thumbnails" / source_id / prefix / f"{item_id}_{size}.{ext}"
        )

    def get_insights_path(
        self, base_dir: Path, source_id: str, item_id: str
    ) -> Path:
        """Get the file path for image insights JSON."""
        prefix = item_id[:2] if len(item_id) >= 2 else item_id
        return (
            base_dir / "thumbnails" / source_id / prefix / f"{item_id}_insights.json"
        )
