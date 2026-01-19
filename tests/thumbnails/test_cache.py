"""Tests for thumbnail cache."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from stagvault.thumbnails import ThumbnailCache


class TestThumbnailCache:
    """Tests for ThumbnailCache class."""

    @pytest.fixture
    def cache(self, tmp_path: Path) -> ThumbnailCache:
        """Create a temporary cache for testing."""
        return ThumbnailCache(tmp_path)

    def test_add_and_get(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test adding and retrieving a thumbnail entry."""
        # Create a dummy thumbnail file
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy png data")

        cache.add(
            source_id="test-source",
            item_id="test-item",
            size=64,
            file_path=thumb_path,
            file_size=14,
        )

        entry = cache.get("test-source", "test-item", 64)
        assert entry is not None
        assert entry.source_id == "test-source"
        assert entry.item_id == "test-item"
        assert entry.size == 64
        assert entry.file_size == 14

    def test_exists(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test checking if a thumbnail exists."""
        assert not cache.exists("test-source", "test-item", 64)

        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        cache.add("test-source", "test-item", 64, thumb_path, 5)

        assert cache.exists("test-source", "test-item", 64)
        assert not cache.exists("test-source", "test-item", 128)
        assert not cache.exists("other-source", "test-item", 64)

    def test_get_sizes_for_item(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test getting all sizes for an item."""
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        cache.add("source", "item", 32, thumb_path, 5)
        cache.add("source", "item", 64, thumb_path, 10)
        cache.add("source", "item", 128, thumb_path, 20)

        sizes = cache.get_sizes_for_item("source", "item")
        assert sizes == [32, 64, 128]

    def test_remove_source(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test removing all thumbnails for a source."""
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        cache.add("source1", "item1", 64, thumb_path, 5)
        cache.add("source1", "item2", 64, thumb_path, 5)
        cache.add("source2", "item1", 64, thumb_path, 5)

        removed = cache.remove_source("source1")
        assert removed == 2

        assert not cache.exists("source1", "item1", 64)
        assert not cache.exists("source1", "item2", 64)
        assert cache.exists("source2", "item1", 64)

    def test_remove_item(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test removing all thumbnails for an item."""
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        cache.add("source", "item", 32, thumb_path, 5)
        cache.add("source", "item", 64, thumb_path, 5)
        cache.add("source", "other", 64, thumb_path, 5)

        removed = cache.remove_item("source", "item")
        assert removed == 2

        assert not cache.exists("source", "item", 32)
        assert not cache.exists("source", "item", 64)
        assert cache.exists("source", "other", 64)

    def test_clear(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test clearing all thumbnails."""
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        cache.add("source1", "item1", 64, thumb_path, 5)
        cache.add("source2", "item2", 64, thumb_path, 5)

        removed = cache.clear()
        assert removed == 2

        assert cache.count() == 0

    def test_count(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test counting thumbnails."""
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        assert cache.count() == 0
        assert cache.count("source") == 0

        cache.add("source", "item1", 64, thumb_path, 5)
        cache.add("source", "item2", 64, thumb_path, 5)
        cache.add("other", "item1", 64, thumb_path, 5)

        assert cache.count() == 3
        assert cache.count("source") == 2
        assert cache.count("other") == 1

    def test_get_stats(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test getting statistics."""
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        cache.add("source1", "item1", 32, thumb_path, 100)
        cache.add("source1", "item1", 64, thumb_path, 200)
        cache.add("source2", "item1", 64, thumb_path, 150)

        stats = cache.get_stats()

        assert stats.total_count == 3
        assert stats.total_size_bytes == 450
        assert stats.sources == {"source1": 2, "source2": 1}
        assert stats.sizes == {32: 1, 64: 2}

    def test_update_existing(self, cache: ThumbnailCache, tmp_path: Path) -> None:
        """Test updating an existing entry."""
        thumb_path = tmp_path / "test_thumb.png"
        thumb_path.write_bytes(b"dummy")

        cache.add("source", "item", 64, thumb_path, 100)
        cache.add("source", "item", 64, thumb_path, 200)  # Update

        entry = cache.get("source", "item", 64)
        assert entry is not None
        assert entry.file_size == 200

        # Should still be only one entry
        assert cache.count() == 1

    def test_close(self, cache: ThumbnailCache) -> None:
        """Test closing the cache."""
        cache.close()
        # After close, accessing conn should create a new connection
        cache.close()  # Should not raise


class TestThumbnailStats:
    """Tests for ThumbnailStats model."""

    def test_empty_stats(self, tmp_path: Path) -> None:
        """Test stats for empty cache."""
        cache = ThumbnailCache(tmp_path)
        stats = cache.get_stats()

        assert stats.total_count == 0
        assert stats.total_size_bytes == 0
        assert stats.sources == {}
        assert stats.sizes == {}
