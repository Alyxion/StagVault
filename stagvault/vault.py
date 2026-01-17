"""Main StagVault class - unified interface for the media database."""

from __future__ import annotations

from pathlib import Path

from stagvault.models.config import SourceConfig
from stagvault.models.media import MediaGroup, MediaItem, Source
from stagvault.search.indexer import SearchIndexer
from stagvault.search.query import (
    GroupedSearchResult,
    SearchPreferences,
    SearchQuery,
    SearchResult,
)
from stagvault.sources.api import ApiSourceHandler
from stagvault.sources.base import SourceHandler
from stagvault.sources.git import GitSourceHandler


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
        else:
            raise ValueError(f"Unknown source type: {config.source_type}")

    async def sync(self, source_id: str | None = None) -> dict[str, int]:
        """Sync sources. Returns dict of source_id -> item count."""
        results: dict[str, int] = {}
        sources = [source_id] if source_id else list(self.configs.keys())

        for sid in sources:
            handler = self.get_handler(sid)
            await handler.sync()
            items = await handler.scan()
            results[sid] = len(items)

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

    def list_sources(self) -> list[Source]:
        return [self.get_source(sid) for sid in self.configs]

    def list_styles(self, source_id: str | None = None) -> list[str]:
        return self.query.list_styles(source_id)

    def get_stats(self) -> dict[str, int]:
        return self.indexer.get_stats()

    def export_json(self, output_path: Path, grouped: bool = True) -> int:
        return self.indexer.export_json(output_path, grouped=grouped)

    def close(self) -> None:
        if self._indexer:
            self._indexer.close()
        if self._query:
            self._query.close()
