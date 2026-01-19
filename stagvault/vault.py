"""Main StagVault class - unified interface for the media database."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from stagvault.models.media import MediaGroup, MediaItem, Source
from stagvault.models.source import SourceConfig
from stagvault.models.source_info import SourceInfo, SourceStatus
from stagvault.search.indexer import SearchIndexer
from stagvault.search.query import (
    GroupedSearchResult,
    SearchPreferences,
    SearchQuery,
    SearchResult,
)
from stagvault.sources.api import ApiSourceHandler
from stagvault.sources.archive import ArchiveSourceHandler
from stagvault.sources.base import SourceHandler
from stagvault.sources.git import GitSourceHandler
from stagvault.thumbnails import ThumbnailConfig, ThumbnailGenerator


class StagVault:
    """Main interface for the StagVault media database."""

    def __init__(
        self,
        data_dir: str | Path,
        config_dir: str | Path,
        index_dir: str | Path | None = None,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.config_dir = Path(config_dir)
        self.index_dir = Path(index_dir) if index_dir else self.data_dir / "index"

        self._configs: dict[str, SourceConfig] | None = None
        self._indexer: SearchIndexer | None = None
        self._query: SearchQuery | None = None
        self._thumbnail_generator: ThumbnailGenerator | None = None

    @property
    def configs(self) -> dict[str, SourceConfig]:
        if self._configs is None:
            self._configs = SourceConfig.load_all(self.config_dir)
        return self._configs

    @property
    def indexer(self) -> SearchIndexer:
        if self._indexer is None:
            self._indexer = SearchIndexer(self.index_dir)
        return self._indexer

    @property
    def query(self) -> SearchQuery:
        if self._query is None:
            self._query = SearchQuery(self.index_dir / "stagvault.db")
        return self._query

    @property
    def thumbnail_generator(self) -> ThumbnailGenerator:
        if self._thumbnail_generator is None:
            self._thumbnail_generator = ThumbnailGenerator(self.data_dir)
        return self._thumbnail_generator

    def get_source(self, source_id: str) -> Source:
        config = self.configs.get(source_id)
        if config is None:
            raise KeyError(f"Source not found: {source_id}")
        return Source(
            id=config.id,
            name=config.name,
            description=config.description,
            type=config.source_type,
            license=config.license,
            homepage=config.metadata.homepage,
        )

    def get_handler(self, source_id: str) -> SourceHandler:
        config = self.configs.get(source_id)
        if config is None:
            raise KeyError(f"Source not found: {source_id}")

        if config.source_type == "git":
            return GitSourceHandler(config, self.data_dir)
        elif config.source_type == "api":
            return ApiSourceHandler(config, self.data_dir)
        elif config.source_type == "archive":
            return ArchiveSourceHandler(config, self.data_dir)
        else:
            raise ValueError(f"Unknown source type: {config.source_type}")

    async def sync(
        self,
        source_id: str | None = None,
        thumbnails: bool = True,
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> dict[str, int]:
        """Sync sources and optionally generate thumbnails.

        Args:
            source_id: Specific source to sync, or None for all
            thumbnails: Generate thumbnails for git sources (default True)
            progress_callback: Optional callback(source_id, current, total)

        Returns:
            Dict of source_id -> item count
        """
        results: dict[str, int] = {}
        sources = [source_id] if source_id else list(self.configs.keys())

        for sid in sources:
            config = self.configs.get(sid)
            if config is None:
                continue

            handler = self.get_handler(sid)
            await handler.sync()
            items = await handler.scan()
            results[sid] = len(items)

            # Only generate thumbnails for git sources
            if thumbnails and config.is_git_source:
                source_dir = self.data_dir / sid

                def thumb_progress(current: int, total: int) -> None:
                    if progress_callback:
                        progress_callback(sid, current, total)

                self.thumbnail_generator.generate_for_source(
                    sid, items, source_dir, progress_callback=thumb_progress
                )

        return results

    async def build_index(self, source_id: str | None = None) -> dict[str, int]:
        """Build search index. Returns dict of source_id -> items indexed."""
        results: dict[str, int] = {}
        sources = [source_id] if source_id else list(self.configs.keys())

        for sid in sources:
            handler = self.get_handler(sid)
            if not handler.is_synced():
                continue

            self.indexer.remove_source(sid)
            items = await handler.scan()
            count = self.indexer.add_items(items)
            results[sid] = count

        return results

    def search(
        self,
        query: str,
        *,
        source_id: str | None = None,
        tags: list[str] | None = None,
        formats: list[str] | None = None,
        styles: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Search for individual media items."""
        return self.query.search(
            query,
            source_id=source_id,
            tags=tags,
            formats=formats,
            styles=styles,
            limit=limit,
            offset=offset,
        )

    def search_grouped(
        self,
        query: str,
        *,
        source_id: str | None = None,
        tags: list[str] | None = None,
        formats: list[str] | None = None,
        preferences: SearchPreferences | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[GroupedSearchResult]:
        """Search with variants grouped together."""
        return self.query.search_grouped(
            query,
            source_id=source_id,
            tags=tags,
            formats=formats,
            preferences=preferences,
            limit=limit,
            offset=offset,
        )

    def get_variants(self, source_id: str, canonical_name: str) -> MediaGroup | None:
        """Get all style variants for an icon."""
        return self.query.get_variants(source_id, canonical_name)

    def get_item(self, item_id: str) -> MediaItem | None:
        return self.query.get_by_id(item_id)

    def get_file_path(self, item: MediaItem) -> Path:
        return self.data_dir / item.source_id / item.path

    # Source management methods

    def get_source_info(self, source_id: str) -> SourceInfo:
        """Get detailed information about a source."""
        config = self.configs.get(source_id)
        if config is None:
            raise KeyError(f"Source not found: {source_id}")

        handler = self.get_handler(source_id)
        is_synced = handler.is_synced()

        # Determine status
        if is_synced:
            status = SourceStatus.INSTALLED
        else:
            status = SourceStatus.AVAILABLE

        # Get item count from index if available
        item_count = None
        if is_synced:
            stats = self.indexer.get_stats()
            item_count = stats.get(source_id, 0)

        # Get thumbnail count for git sources
        thumbnail_count = None
        if config.is_git_source and is_synced:
            thumb_stats = self.thumbnail_generator.cache.get_stats()
            thumbnail_count = thumb_stats.sources.get(source_id, 0)

        # Calculate disk usage
        disk_usage = self._calculate_disk_usage(source_id)

        # Get last sync time from source directory mtime
        last_synced = None
        source_dir = self.data_dir / source_id
        if source_dir.exists():
            last_synced = datetime.fromtimestamp(source_dir.stat().st_mtime)

        return SourceInfo(
            id=config.id,
            name=config.name,
            source_type=config.source_type,
            status=status,
            item_count=item_count,
            thumbnail_count=thumbnail_count,
            disk_usage_bytes=disk_usage,
            last_synced=last_synced,
            description=config.description,
            homepage=config.metadata.homepage,
        )

    def list_sources(
        self, status: SourceStatus | None = None
    ) -> list[SourceInfo]:
        """List all sources with optional status filter.

        Args:
            status: Filter by status (available, installed, partial)

        Returns:
            List of SourceInfo objects
        """
        sources = []
        for sid in self.configs:
            info = self.get_source_info(sid)
            if status is None or info.status == status:
                sources.append(info)
        return sources

    async def add_source(
        self,
        source_id: str,
        sync: bool = True,
        thumbnails: bool = True,
    ) -> SourceInfo:
        """Add/enable a source and optionally sync it.

        Args:
            source_id: Source identifier
            sync: Whether to sync the source data (default True)
            thumbnails: Whether to generate thumbnails (default True)

        Returns:
            SourceInfo for the added source
        """
        if source_id not in self.configs:
            raise KeyError(f"Source not found: {source_id}")

        if sync:
            await self.sync(source_id, thumbnails=thumbnails)
            await self.build_index(source_id)

        return self.get_source_info(source_id)

    async def remove_source(
        self,
        source_id: str,
        purge_config: bool = False,
    ) -> None:
        """Remove a source's data and optionally its config.

        Args:
            source_id: Source identifier
            purge_config: Also remove the config file (default False)
        """
        if source_id not in self.configs:
            raise KeyError(f"Source not found: {source_id}")

        # Remove source data directory
        source_dir = self.data_dir / source_id
        if source_dir.exists():
            shutil.rmtree(source_dir)

        # Remove thumbnails
        thumb_dir = self.data_dir / "thumbnails" / source_id
        if thumb_dir.exists():
            shutil.rmtree(thumb_dir)
        self.thumbnail_generator.cache.remove_source(source_id)

        # Remove from index
        self.indexer.remove_source(source_id)

        # Optionally remove config file
        if purge_config:
            config_file = self.config_dir / "sources" / f"{source_id}.yaml"
            if config_file.exists():
                config_file.unlink()
            # Clear cached configs
            self._configs = None

    def _calculate_disk_usage(self, source_id: str) -> int | None:
        """Calculate total disk usage for a source."""
        total = 0

        # Source data directory
        source_dir = self.data_dir / source_id
        if source_dir.exists():
            total += self._dir_size(source_dir)

        # Thumbnail directory
        thumb_dir = self.data_dir / "thumbnails" / source_id
        if thumb_dir.exists():
            total += self._dir_size(thumb_dir)

        return total if total > 0 else None

    @staticmethod
    def _dir_size(path: Path) -> int:
        """Calculate total size of a directory."""
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                total += item.stat().st_size
        return total

    def list_styles(self, source_id: str | None = None) -> list[str]:
        return self.query.list_styles(source_id)

    def get_stats(self) -> dict[str, int]:
        return self.indexer.get_stats()

    def get_thumbnail_stats(self) -> dict[str, int | dict[str, int] | dict[int, int]]:
        """Get thumbnail cache statistics."""
        return self.thumbnail_generator.get_stats()

    def export_json(self, output_path: Path, grouped: bool = True) -> int:
        return self.indexer.export_json(output_path, grouped=grouped)

    def close(self) -> None:
        if self._indexer:
            self._indexer.close()
        if self._query:
            self._query.close()
        if self._thumbnail_generator:
            self._thumbnail_generator.close()
