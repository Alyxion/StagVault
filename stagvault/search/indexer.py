"""Search index builder using SQLite FTS5."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stagvault.models.media import MediaItem


class SearchIndexer:
    """Builds and maintains the search index."""

    SCHEMA = """
    CREATE VIRTUAL TABLE IF NOT EXISTS media_fts USING fts5(
        id,
        source_id,
        name,
        canonical_name,
        path,
        format,
        tags,
        description,
        metadata,
        content='media_items',
        content_rowid='rowid'
    );

    CREATE TABLE IF NOT EXISTS media_items (
        rowid INTEGER PRIMARY KEY AUTOINCREMENT,
        id TEXT UNIQUE NOT NULL,
        source_id TEXT NOT NULL,
        name TEXT NOT NULL,
        canonical_name TEXT NOT NULL,
        path TEXT NOT NULL,
        format TEXT NOT NULL,
        style TEXT,
        tags TEXT,
        description TEXT,
        metadata TEXT,
        license_json TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_media_source ON media_items(source_id);
    CREATE INDEX IF NOT EXISTS idx_media_format ON media_items(format);
    CREATE INDEX IF NOT EXISTS idx_media_canonical ON media_items(source_id, canonical_name);
    CREATE INDEX IF NOT EXISTS idx_media_style ON media_items(style);

    CREATE TRIGGER IF NOT EXISTS media_ai AFTER INSERT ON media_items BEGIN
        INSERT INTO media_fts(rowid, id, source_id, name, canonical_name, path, format, tags, description, metadata)
        VALUES (new.rowid, new.id, new.source_id, new.name, new.canonical_name, new.path, new.format, new.tags, new.description, new.metadata);
    END;

    CREATE TRIGGER IF NOT EXISTS media_ad AFTER DELETE ON media_items BEGIN
        INSERT INTO media_fts(media_fts, rowid, id, source_id, name, canonical_name, path, format, tags, description, metadata)
        VALUES ('delete', old.rowid, old.id, old.source_id, old.name, old.canonical_name, old.path, old.format, old.tags, old.description, old.metadata);
    END;

    CREATE TRIGGER IF NOT EXISTS media_au AFTER UPDATE ON media_items BEGIN
        INSERT INTO media_fts(media_fts, rowid, id, source_id, name, canonical_name, path, format, tags, description, metadata)
        VALUES ('delete', old.rowid, old.id, old.source_id, old.name, old.canonical_name, old.path, old.format, old.tags, old.description, old.metadata);
        INSERT INTO media_fts(rowid, id, source_id, name, canonical_name, path, format, tags, description, metadata)
        VALUES (new.rowid, new.id, new.source_id, new.name, new.canonical_name, new.path, new.format, new.tags, new.description, new.metadata);
    END;
    """

    def __init__(self, index_dir: Path) -> None:
        self.index_dir = index_dir
        self.db_path = index_dir / "stagvault.db"
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        """Initialize the database schema."""
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def add_item(self, item: MediaItem) -> None:
        """Add a single item to the index."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO media_items
            (id, source_id, name, canonical_name, path, format, style, tags, description, metadata, license_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                item.source_id,
                item.name,
                item.canonical_name,
                item.path,
                item.format,
                item.style,
                " ".join(item.tags),
                item.description,
                json.dumps(item.metadata),
                json.dumps(item.license.model_dump()) if item.license else None,
            ),
        )

    def add_items(self, items: list[MediaItem]) -> int:
        """Add multiple items to the index. Returns count added."""
        for item in items:
            self.add_item(item)
        self.conn.commit()
        return len(items)

    def remove_source(self, source_id: str) -> int:
        """Remove all items from a source. Returns count removed."""
        cursor = self.conn.execute(
            "DELETE FROM media_items WHERE source_id = ?", (source_id,)
        )
        self.conn.commit()
        return cursor.rowcount

    def clear(self) -> None:
        """Clear all items from the index."""
        self.conn.execute("DELETE FROM media_items")
        self.conn.commit()

    def get_stats(self) -> dict[str, int]:
        """Get index statistics."""
        cursor = self.conn.execute(
            """
            SELECT source_id, COUNT(*) as count
            FROM media_items
            GROUP BY source_id
            """
        )
        stats = {row["source_id"]: row["count"] for row in cursor}
        stats["total"] = sum(stats.values())
        return stats

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def export_json(self, output_path: Path, grouped: bool = True) -> int:
        """Export index to JSON for JavaScript client. Returns item count."""
        cursor = self.conn.execute(
            """
            SELECT id, source_id, name, canonical_name, path, format, style, tags, description
            FROM media_items
            ORDER BY source_id, canonical_name, style
            """
        )

        if grouped:
            # Group items by source_id + canonical_name
            groups: dict[str, dict[str, list[dict[str, str | list[str] | None]]]] = {}
            for row in cursor:
                group_key = f"{row['source_id']}:{row['canonical_name']}"
                if group_key not in groups:
                    groups[group_key] = {
                        "canonical_name": row["canonical_name"],
                        "source_id": row["source_id"],
                        "tags": row["tags"].split() if row["tags"] else [],
                        "description": row["description"],
                        "variants": [],
                    }
                groups[group_key]["variants"].append(
                    {
                        "id": row["id"],
                        "style": row["style"],
                        "path": row["path"],
                        "format": row["format"],
                    }
                )

            output_data = {"groups": list(groups.values()), "count": len(groups)}
        else:
            items = []
            for row in cursor:
                items.append(
                    {
                        "id": row["id"],
                        "source_id": row["source_id"],
                        "name": row["name"],
                        "canonical_name": row["canonical_name"],
                        "path": row["path"],
                        "format": row["format"],
                        "style": row["style"],
                        "tags": row["tags"].split() if row["tags"] else [],
                        "description": row["description"],
                    }
                )
            output_data = {"items": items, "count": len(items)}

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output_data, f)

        return output_data["count"]
