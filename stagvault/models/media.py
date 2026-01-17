"""Core media data models."""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field, computed_field


class License(BaseModel):
    """License information for a media item or source."""

    spdx: str = Field(..., description="SPDX license identifier")
    attribution_required: bool = Field(default=False)
    attribution_notice: str | None = Field(default=None)
    commercial_ok: bool = Field(default=True)
    modification_ok: bool = Field(default=True)
    share_alike: bool = Field(default=False)
    notes: str | None = Field(default=None)

    @property
    def requires_attribution(self) -> bool:
        """Check if attribution is required for use."""
        return self.attribution_required or self.share_alike


class Source(BaseModel):
    """A media source (repository or API)."""

    id: str = Field(..., description="Unique source identifier")
    name: str = Field(..., description="Display name")
    description: str | None = Field(default=None)
    source_type: str = Field(..., alias="type", description="Source type: git or api")
    license: License
    homepage: str | None = Field(default=None)

    model_config = {"populate_by_name": True}


class MediaItem(BaseModel):
    """A single media item (icon, image, audio, etc.)."""

    source_id: str = Field(..., description="Source identifier")
    path: str = Field(..., description="Path within source")
    name: str = Field(..., description="Display name (derived from filename)")
    format: str = Field(..., description="File format (svg, png, mp3, etc.)")
    tags: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None)
    license: License | None = Field(
        default=None, description="Per-item license (if different from source)"
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    style: str | None = Field(
        default=None, description="Style variant (thin, regular, bold, fill, etc.)"
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> str:
        """Generate unique item ID from source and path."""
        key = f"{self.source_id}:{self.path}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def canonical_name(self) -> str:
        """Base name for grouping variants (strips style suffixes)."""
        return self.name

    @computed_field  # type: ignore[prop-decorator]
    @property
    def group_key(self) -> str:
        """Key for grouping variants: source_id:canonical_name."""
        return f"{self.source_id}:{self.canonical_name}"

    def get_license(self, source_license: License) -> License:
        """Get the effective license (per-item or inherited from source)."""
        return self.license if self.license is not None else source_license


class MediaGroup(BaseModel):
    """A group of related media items (same icon in different styles)."""

    canonical_name: str = Field(..., description="Base name of the icon/media")
    source_id: str = Field(..., description="Source identifier")
    items: list[MediaItem] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list, description="Available styles")
    default_style: str | None = Field(default=None, description="Preferred default style")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def group_key(self) -> str:
        """Unique key for this group."""
        return f"{self.source_id}:{self.canonical_name}"

    def get_item(self, style: str | None = None) -> MediaItem | None:
        """Get item by style, or default/first available."""
        if not self.items:
            return None
        if style:
            for item in self.items:
                if item.style == style:
                    return item
        # Return default style or first item
        if self.default_style:
            for item in self.items:
                if item.style == self.default_style:
                    return item
        return self.items[0]


class MediaItemWithSource(MediaItem):
    """Media item with resolved source information."""

    source: Source
    full_path: str = Field(..., description="Full filesystem path to the file")

    def get_effective_license(self) -> License:
        """Get the effective license for this item."""
        return self.get_license(self.source.license)
