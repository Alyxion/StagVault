"""Source information and status models for source management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class SourceStatus(str, Enum):
    """Status of a data source."""

    AVAILABLE = "available"  # Config exists, data not synced
    INSTALLED = "installed"  # Config exists, data synced
    PARTIAL = "partial"  # Partially synced or outdated


class SourceInfo(BaseModel):
    """Detailed information about a data source."""

    id: str = Field(..., description="Unique source identifier")
    name: str = Field(..., description="Display name")
    source_type: str = Field(..., description="Source type: git or api")
    status: SourceStatus = Field(..., description="Current sync status")
    item_count: int | None = Field(default=None, description="Number of indexed items")
    thumbnail_count: int | None = Field(
        default=None, description="Number of generated thumbnails (git sources only)"
    )
    disk_usage_bytes: int | None = Field(
        default=None, description="Total disk usage in bytes"
    )
    last_synced: datetime | None = Field(
        default=None, description="Last sync timestamp"
    )
    description: str | None = Field(default=None, description="Source description")
    homepage: str | None = Field(default=None, description="Source homepage URL")

    @property
    def is_installed(self) -> bool:
        """Check if source has synced data."""
        return self.status == SourceStatus.INSTALLED

    @property
    def is_git_source(self) -> bool:
        """Check if this is a git-based source."""
        return self.source_type == "git"

    @property
    def is_api_source(self) -> bool:
        """Check if this is an API-based source."""
        return self.source_type == "api"

    @property
    def disk_usage_formatted(self) -> str:
        """Get human-readable disk usage."""
        if self.disk_usage_bytes is None:
            return "N/A"

        size = self.disk_usage_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
