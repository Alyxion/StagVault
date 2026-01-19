"""Tests for source management."""

from __future__ import annotations

import pytest
from datetime import datetime

from stagvault.models.source_info import SourceInfo, SourceStatus


class TestSourceStatus:
    """Tests for SourceStatus enum."""

    def test_status_values(self) -> None:
        """Test status enum values."""
        assert SourceStatus.AVAILABLE.value == "available"
        assert SourceStatus.INSTALLED.value == "installed"
        assert SourceStatus.PARTIAL.value == "partial"

    def test_status_comparison(self) -> None:
        """Test status comparisons."""
        assert SourceStatus.AVAILABLE == SourceStatus.AVAILABLE
        assert SourceStatus.AVAILABLE != SourceStatus.INSTALLED


class TestSourceInfo:
    """Tests for SourceInfo model."""

    def test_minimal_source_info(self) -> None:
        """Test creating SourceInfo with minimal fields."""
        info = SourceInfo(
            id="test",
            name="Test Source",
            source_type="git",
            status=SourceStatus.AVAILABLE,
        )

        assert info.id == "test"
        assert info.name == "Test Source"
        assert info.source_type == "git"
        assert info.status == SourceStatus.AVAILABLE
        assert info.item_count is None
        assert info.thumbnail_count is None

    def test_full_source_info(self) -> None:
        """Test creating SourceInfo with all fields."""
        now = datetime.now()
        info = SourceInfo(
            id="heroicons",
            name="Heroicons",
            source_type="git",
            status=SourceStatus.INSTALLED,
            item_count=592,
            thumbnail_count=4736,
            disk_usage_bytes=2500000,
            last_synced=now,
            description="Beautiful icons",
            homepage="https://heroicons.com",
        )

        assert info.id == "heroicons"
        assert info.item_count == 592
        assert info.thumbnail_count == 4736
        assert info.disk_usage_bytes == 2500000
        assert info.last_synced == now
        assert info.description == "Beautiful icons"
        assert info.homepage == "https://heroicons.com"

    def test_is_installed_property(self) -> None:
        """Test is_installed property."""
        available = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.AVAILABLE,
        )
        installed = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.INSTALLED,
        )

        assert not available.is_installed
        assert installed.is_installed

    def test_is_git_source_property(self) -> None:
        """Test is_git_source property."""
        git_source = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.AVAILABLE,
        )
        api_source = SourceInfo(
            id="test",
            name="Test",
            source_type="api",
            status=SourceStatus.AVAILABLE,
        )

        assert git_source.is_git_source
        assert not git_source.is_api_source
        assert not api_source.is_git_source
        assert api_source.is_api_source

    def test_disk_usage_formatted(self) -> None:
        """Test disk_usage_formatted property."""
        # No disk usage
        info = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.AVAILABLE,
        )
        assert info.disk_usage_formatted == "N/A"

        # Bytes
        info = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.INSTALLED,
            disk_usage_bytes=500,
        )
        assert info.disk_usage_formatted == "500.0 B"

        # Kilobytes
        info = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.INSTALLED,
            disk_usage_bytes=2048,
        )
        assert info.disk_usage_formatted == "2.0 KB"

        # Megabytes
        info = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.INSTALLED,
            disk_usage_bytes=5 * 1024 * 1024,
        )
        assert info.disk_usage_formatted == "5.0 MB"

        # Gigabytes
        info = SourceInfo(
            id="test",
            name="Test",
            source_type="git",
            status=SourceStatus.INSTALLED,
            disk_usage_bytes=2 * 1024 * 1024 * 1024,
        )
        assert info.disk_usage_formatted == "2.0 GB"


class TestThumbnailConfig:
    """Tests for ThumbnailConfig."""

    def test_default_config(self) -> None:
        """Test default thumbnail configuration."""
        from stagvault.thumbnails import ThumbnailConfig, ThumbnailSize

        config = ThumbnailConfig()

        assert config.sizes == ThumbnailSize.all_sizes()
        assert config.jpg_quality == 85
        assert config.workers == 16
        assert config.insights_size == 128
        assert config.checkerboard.light_color == "#ffffff"
        assert config.checkerboard.dark_color == "#cccccc"
        assert config.checkerboard.square_size == 8

    def test_supported_formats(self) -> None:
        """Test supported input formats."""
        from stagvault.thumbnails import ThumbnailConfig

        config = ThumbnailConfig()
        supported = config.supported_input_formats

        assert "svg" in supported
        assert "png" in supported
        assert "jpg" in supported
        assert "jpeg" in supported
        assert "gif" in supported
        assert "webp" in supported

    def test_get_thumbnail_path(self) -> None:
        """Test thumbnail path generation."""
        from pathlib import Path
        from stagvault.thumbnails import ThumbnailConfig

        config = ThumbnailConfig()
        base_dir = Path("/data")

        path = config.get_thumbnail_path(
            base_dir, "heroicons", "arrow-right", 64
        )

        # Should use sharding based on first 2 chars
        assert path == Path("/data/thumbnails/heroicons/ar/arrow-right_64.png")

    def test_get_thumbnail_path_short_id(self) -> None:
        """Test thumbnail path with short item ID."""
        from pathlib import Path
        from stagvault.thumbnails import ThumbnailConfig

        config = ThumbnailConfig()
        base_dir = Path("/data")

        # ID shorter than 2 characters
        path = config.get_thumbnail_path(
            base_dir, "source", "x", 64
        )

        assert path == Path("/data/thumbnails/source/x/x_64.png")


class TestThumbnailSize:
    """Tests for ThumbnailSize enum."""

    def test_all_sizes(self) -> None:
        """Test all_sizes returns correct values."""
        from stagvault.thumbnails import ThumbnailSize

        sizes = ThumbnailSize.all_sizes()

        assert 24 in sizes
        assert 32 in sizes
        assert 48 in sizes
        assert 64 in sizes
        assert 96 in sizes
        assert 128 in sizes
        assert 256 in sizes
        # 512 was removed - max size is now 256

    def test_from_int(self) -> None:
        """Test from_int conversion."""
        from stagvault.thumbnails import ThumbnailSize

        assert ThumbnailSize.from_int(24) == ThumbnailSize.TINY
        assert ThumbnailSize.from_int(64) == ThumbnailSize.MEDIUM
        assert ThumbnailSize.from_int(128) == ThumbnailSize.XLARGE
        assert ThumbnailSize.from_int(999) is None

    def test_enum_values(self) -> None:
        """Test enum values are correct."""
        from stagvault.thumbnails import ThumbnailSize

        assert ThumbnailSize.TINY == 24
        assert ThumbnailSize.SMALL == 32
        assert ThumbnailSize.ICON == 48
        assert ThumbnailSize.MEDIUM == 64
        assert ThumbnailSize.LARGE == 96
        assert ThumbnailSize.XLARGE == 128
        assert ThumbnailSize.PREVIEW == 256
        # FULL (512) was removed - max size is now 256 (PREVIEW)
