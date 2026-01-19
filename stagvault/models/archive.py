"""Archive configuration model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ArchiveConfig(BaseModel):
    """Configuration for ZIP archive sources."""

    url: str = Field(..., description="URL to download the archive from")
    md5: str | None = Field(default=None, description="Expected MD5 hash for verification")
    extract_paths: list[str] = Field(
        default_factory=list, description="Specific paths to extract (empty = all)"
    )

    # For emoji-specific handling
    emoji_db: str | None = Field(
        default=None, description="Path to emoji database JSON within archive"
    )
    images_dir: str | None = Field(
        default=None, description="Path to images directory within archive"
    )
