"""SQLite thumbnail cache for metadata and statistics."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from stagvault.thumbnails.config import ThumbnailConfig


class ThumbnailEntry(BaseModel):
    """Metadata entry for a cached thumbnail."""

    source_id: str
    item_id: str
    size: int
    file_path: str
    file_size: int
    created_at: datetime


class ThumbnailStats(BaseModel):
    """Statistics for thumbnail cache."""

    total_count: int
    total_size_bytes: int
    sources: dict[str, int]
    sizes: dict[int, int]


class ThumbnailCache:
    """SQLite-based cache for thumbnail metadata."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.db_path = data_dir / "thumbnails" / "thumbnails.db"
        self._conn: sqlite3.Connection | None = None
        self._ensure_tables()

    @property
    def conn(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _ensure_tables(self) -> None:
        """Create database tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS thumbnails (
                source_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                size INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_id, item_id, size)
            );

            CREATE INDEX IF NOT EXISTS idx_thumbnails_source
                ON thumbnails(source_id);

            CREATE INDEX IF NOT EXISTS idx_thumbnails_item
                ON thumbnails(source_id, item_id);
        """)
        self.conn.commit()

    def add(
        self,
        source_id: str,
        item_id: str,
        size: int,
        file_path: Path,
        file_size: int,
    ) -> None:
        """Add or update a thumbnail entry."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO thumbnails
                (source_id, item_id, size, file_path, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (source_id, item_id, size, str(file_path), file_size, datetime.now()),
        )
        self.conn.commit()

    def get(self, source_id: str, item_id: str, size: int) -> ThumbnailEntry | None:
        """Get a thumbnail entry."""
        row = self.conn.execute(
            """
            SELECT * FROM thumbnails
            WHERE source_id = ? AND item_id = ? AND size = ?
            """,
            (source_id, item_id, size),
        ).fetchone()

        if row is None:
            return None

        return ThumbnailEntry(
            source_id=row["source_id"],
            item_id=row["item_id"],
            size=row["size"],
            file_path=row["file_path"],
            file_size=row["file_size"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def exists(self, source_id: str, item_id: str, size: int) -> bool:
        """Check if a thumbnail exists in the cache."""
        row = self.conn.execute(
            """
            SELECT 1 FROM thumbnails
            WHERE source_id = ? AND item_id = ? AND size = ?
            """,
            (source_id, item_id, size),
        ).fetchone()
        return row is not None

    def get_sizes_for_item(self, source_id: str, item_id: str) -> list[int]:
        """Get all available sizes for an item."""
        rows = self.conn.execute(
            """
            SELECT size FROM thumbnails
            WHERE source_id = ? AND item_id = ?
            ORDER BY size
            """,
            (source_id, item_id),
        ).fetchall()
        return [row["size"] for row in rows]

    def remove_source(self, source_id: str) -> int:
        """Remove all thumbnails for a source. Returns count removed."""
        cursor = self.conn.execute(
            "DELETE FROM thumbnails WHERE source_id = ?",
            (source_id,),
        )
        self.conn.commit()
        return cursor.rowcount

    def remove_item(self, source_id: str, item_id: str) -> int:
        """Remove all thumbnails for an item. Returns count removed."""
        cursor = self.conn.execute(
            "DELETE FROM thumbnails WHERE source_id = ? AND item_id = ?",
            (source_id, item_id),
        )
        self.conn.commit()
        return cursor.rowcount

    def clear(self) -> int:
        """Clear all thumbnail entries. Returns count removed."""
        cursor = self.conn.execute("DELETE FROM thumbnails")
        self.conn.commit()
        return cursor.rowcount

    def count(self, source_id: str | None = None) -> int:
        """Get count of thumbnails, optionally filtered by source."""
        if source_id:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM thumbnails WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM thumbnails"
            ).fetchone()
        return row["cnt"] if row else 0

    def get_stats(self) -> ThumbnailStats:
        """Get comprehensive statistics about the thumbnail cache."""
        total = self.conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(file_size), 0) as size FROM thumbnails"
        ).fetchone()

        sources = self.conn.execute(
            "SELECT source_id, COUNT(*) as cnt FROM thumbnails GROUP BY source_id"
        ).fetchall()

        sizes = self.conn.execute(
            "SELECT size, COUNT(*) as cnt FROM thumbnails GROUP BY size"
        ).fetchall()

        return ThumbnailStats(
            total_count=total["cnt"] if total else 0,
            total_size_bytes=total["size"] if total else 0,
            sources={row["source_id"]: row["cnt"] for row in sources},
            sizes={row["size"]: row["cnt"] for row in sizes},
        )

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
