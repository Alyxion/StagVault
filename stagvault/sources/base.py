"""Base source handler interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stagvault.models.config import SourceConfig
    from stagvault.models.media import MediaItem


class SourceHandler(ABC):
    """Abstract base class for source handlers."""

    def __init__(self, config: SourceConfig, data_dir: Path) -> None:
        self.config = config
        self.data_dir = data_dir
        self.source_dir = data_dir / config.id

    @abstractmethod
    async def sync(self) -> None:
        """Sync (download/update) the source data."""
        ...

    @abstractmethod
    async def scan(self) -> list[MediaItem]:
        """Scan the source and return all media items."""
        ...

    @abstractmethod
    def is_synced(self) -> bool:
        """Check if the source has been synced."""
        ...

    def get_file_path(self, item: MediaItem) -> Path:
        """Get the full filesystem path for a media item."""
        return self.source_dir / item.path
