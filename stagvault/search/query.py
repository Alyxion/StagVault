"""Search query interface."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from stagvault.models.media import License, MediaGroup, MediaItem


@dataclass
class SearchResult:
    """A search result with relevance score."""

    item: MediaItem
    score: float


@dataclass
class GroupedSearchResult:
    """A grouped search result with relevance score."""

    group: MediaGroup
    score: float


@dataclass
class SearchPreferences:
    """User preferences for search results."""

    preferred_styles: list[str] = field(default_factory=lambda: ["regular", "outline"])
    group_variants: bool = True
    default_style: str = "regular"


class SearchQuery:
    """Execute search queries against the index."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

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
        """Search for media items (returns individual items, not grouped).

        Args:
            query: Search query (supports FTS5 syntax)
            source_id: Filter by source ID
            tags: Filter by tags (any match)
            formats: Filter by file formats
            styles: Filter by style variants
            limit: Maximum results to return
            offset: Number of results to skip

        Returns:
            List of search results with scores
        """
        conditions = []
        params: list[str | int] = []

        fts_query = self._build_fts_query(query)
        base_sql = """
            SELECT m.*, bm25(media_fts) as score
            FROM media_fts
            JOIN media_items m ON media_fts.rowid = m.rowid
            WHERE media_fts MATCH ?
        """
        params.append(fts_query)

        if source_id:
            conditions.append("m.source_id = ?")
            params.append(source_id)

        if tags:
            tag_conditions = " OR ".join(["m.tags LIKE ?" for _ in tags])
            conditions.append(f"({tag_conditions})")
            params.extend([f"%{tag}%" for tag in tags])

        if formats:
            format_placeholders = ",".join(["?" for _ in formats])
            conditions.append(f"m.format IN ({format_placeholders})")
            params.extend(formats)

        if styles:
            style_placeholders = ",".join(["?" for _ in styles])
            conditions.append(f"m.style IN ({style_placeholders})")
            params.extend(styles)

        if conditions:
            base_sql += " AND " + " AND ".join(conditions)

        base_sql += " ORDER BY score LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = self.conn.execute(base_sql, params)
        return [self._row_to_result(row) for row in cursor]

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
        """Search for media items and group variants together.

        Args:
            query: Search query (supports FTS5 syntax)
            source_id: Filter by source ID
            tags: Filter by tags (any match)
            formats: Filter by file formats
            preferences: Style preferences for grouping
            limit: Maximum groups to return
            offset: Number of groups to skip

        Returns:
            List of grouped search results
        """
        if preferences is None:
            preferences = SearchPreferences()

        # Get more results than needed to account for grouping
        raw_results = self.search(
            query,
            source_id=source_id,
            tags=tags,
            formats=formats,
            limit=limit * 10,  # Fetch extra to have enough after grouping
            offset=0,
        )

        # Group by canonical_name + source_id
        groups: dict[str, list[tuple[MediaItem, float]]] = defaultdict(list)
        group_scores: dict[str, float] = {}

        for result in raw_results:
            key = result.item.group_key
            groups[key].append((result.item, result.score))
            # Keep the best score for the group
            if key not in group_scores or result.score > group_scores[key]:
                group_scores[key] = result.score

        # Convert to MediaGroups
        grouped_results: list[GroupedSearchResult] = []
        for key, items_with_scores in groups.items():
            items = [item for item, _ in items_with_scores]
            if not items:
                continue

            styles = list({item.style for item in items if item.style})
            group = MediaGroup(
                canonical_name=items[0].canonical_name,
                source_id=items[0].source_id,
                items=items,
                styles=styles,
                default_style=self._select_default_style(styles, preferences),
            )
            grouped_results.append(
                GroupedSearchResult(group=group, score=group_scores[key])
            )

        # Sort by score and apply pagination
        grouped_results.sort(key=lambda r: r.score, reverse=True)
        return grouped_results[offset : offset + limit]

    def _select_default_style(
        self, available_styles: list[str], preferences: SearchPreferences
    ) -> str | None:
        """Select the default style based on preferences."""
        if not available_styles:
            return None

        for preferred in preferences.preferred_styles:
            if preferred in available_styles:
                return preferred

        return available_styles[0] if available_styles else None

    def search_by_name(
        self,
        name: str,
        *,
        source_id: str | None = None,
        style: str | None = None,
        limit: int = 50,
    ) -> list[MediaItem]:
        """Search for items by exact or partial name match."""
        sql = "SELECT * FROM media_items WHERE canonical_name LIKE ?"
        params: list[str | int] = [f"%{name}%"]

        if source_id:
            sql += " AND source_id = ?"
            params.append(source_id)

        if style:
            sql += " AND style = ?"
            params.append(style)

        sql += " ORDER BY canonical_name LIMIT ?"
        params.append(limit)

        cursor = self.conn.execute(sql, params)
        return [self._row_to_item(row) for row in cursor]

    def get_by_id(self, item_id: str) -> MediaItem | None:
        """Get a single item by ID."""
        cursor = self.conn.execute(
            "SELECT * FROM media_items WHERE id = ?", (item_id,)
        )
        row = cursor.fetchone()
        return self._row_to_item(row) if row else None

    def get_variants(self, source_id: str, canonical_name: str) -> MediaGroup | None:
        """Get all style variants for an icon."""
        cursor = self.conn.execute(
            """
            SELECT * FROM media_items
            WHERE source_id = ? AND canonical_name = ?
            ORDER BY style
            """,
            (source_id, canonical_name),
        )
        items = [self._row_to_item(row) for row in cursor]
        if not items:
            return None

        styles = list({item.style for item in items if item.style})
        return MediaGroup(
            canonical_name=canonical_name,
            source_id=source_id,
            items=items,
            styles=styles,
        )

    def list_sources(self) -> list[str]:
        """List all source IDs in the index."""
        cursor = self.conn.execute(
            "SELECT DISTINCT source_id FROM media_items ORDER BY source_id"
        )
        return [row["source_id"] for row in cursor]

    def list_styles(self, source_id: str | None = None) -> list[str]:
        """List all available styles, optionally for a specific source."""
        if source_id:
            cursor = self.conn.execute(
                """
                SELECT DISTINCT style FROM media_items
                WHERE source_id = ? AND style IS NOT NULL
                ORDER BY style
                """,
                (source_id,),
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT DISTINCT style FROM media_items
                WHERE style IS NOT NULL
                ORDER BY style
                """
            )
        return [row["style"] for row in cursor]

    def count(self, source_id: str | None = None, grouped: bool = False) -> int:
        """Count items, optionally filtered by source."""
        if grouped:
            if source_id:
                cursor = self.conn.execute(
                    """
                    SELECT COUNT(DISTINCT canonical_name) FROM media_items
                    WHERE source_id = ?
                    """,
                    (source_id,),
                )
            else:
                cursor = self.conn.execute(
                    "SELECT COUNT(DISTINCT source_id || ':' || canonical_name) FROM media_items"
                )
        else:
            if source_id:
                cursor = self.conn.execute(
                    "SELECT COUNT(*) FROM media_items WHERE source_id = ?", (source_id,)
                )
            else:
                cursor = self.conn.execute("SELECT COUNT(*) FROM media_items")
        return cursor.fetchone()[0]

    def _build_fts_query(self, query: str) -> str:
        """Build an FTS5 query from user input."""
        terms = query.split()
        if len(terms) == 1:
            return f"{terms[0]}*"
        return " OR ".join(f"{term}*" for term in terms)

    def _row_to_item(self, row: sqlite3.Row) -> MediaItem:
        """Convert a database row to a MediaItem."""
        license_data = row["license_json"]
        license_obj = (
            License.model_validate(json.loads(license_data)) if license_data else None
        )

        return MediaItem(
            source_id=row["source_id"],
            path=row["path"],
            name=row["name"],
            format=row["format"],
            style=row["style"],
            tags=row["tags"].split() if row["tags"] else [],
            description=row["description"],
            license=license_obj,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    def _row_to_result(self, row: sqlite3.Row) -> SearchResult:
        """Convert a database row to a SearchResult."""
        return SearchResult(
            item=self._row_to_item(row),
            score=abs(row["score"]),
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
