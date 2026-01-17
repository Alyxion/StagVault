"""Models for per-item static metadata."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ItemMetadata(BaseModel):
    """Metadata for a single media item (icon, emoji, etc.)."""

    name: str = Field(..., description="Filename without extension")
    description: str | None = Field(default=None, description="Human-readable description")
    keywords: list[str] = Field(default_factory=list, description="Search keywords/aliases")
    category: str | None = Field(default=None, description="Category/group")
    unicode: str | None = Field(default=None, description="Unicode codepoint (for emoji)")
    extra: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SourceMetadataIndex(BaseModel):
    """Index of all metadata for a source."""

    source_id: str
    version: str = "1.0"
    items: dict[str, ItemMetadata] = Field(
        default_factory=dict, description="Map of filename -> metadata"
    )

    @classmethod
    def load(cls, path: Path) -> "SourceMetadataIndex":
        """Load metadata index from JSON file."""
        if not path.exists():
            raise FileNotFoundError(f"Metadata file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        """Save metadata index to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)

    def get(self, filename: str) -> ItemMetadata | None:
        """Get metadata for a file."""
        # Try exact match first
        if filename in self.items:
            return self.items[filename]
        # Try without extension
        stem = Path(filename).stem
        return self.items.get(stem)

    def set(self, filename: str, metadata: ItemMetadata) -> None:
        """Set metadata for a file."""
        self.items[filename] = metadata

    @classmethod
    def load_or_create(cls, path: Path, source_id: str) -> "SourceMetadataIndex":
        """Load existing or create new metadata index."""
        if path.exists():
            return cls.load(path)
        return cls(source_id=source_id)


def get_metadata_path(metadata_dir: Path, source_id: str) -> Path:
    """Get the path to a source's metadata index file."""
    return metadata_dir / source_id / "metadata.json"


def load_source_metadata(metadata_dir: Path, source_id: str) -> SourceMetadataIndex | None:
    """Load metadata for a source, or None if not found."""
    path = get_metadata_path(metadata_dir, source_id)
    if not path.exists():
        return None
    return SourceMetadataIndex.load(path)
