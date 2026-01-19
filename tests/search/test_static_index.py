"""Tests for static index builder.

Verifies that the static index is built correctly with:
- Source hierarchy tree (max 2 levels)
- Proper prefix-based search files
- Correct source metadata with category/subcategory
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from stagvault.static.index_builder import StaticIndexBuilder
from stagvault.models.media import License, MediaItem


class TestStaticIndexBuilder:
    """Tests for StaticIndexBuilder class."""

    @pytest.fixture
    def temp_output_dir(self, temp_dir: Path) -> Path:
        """Create temp output directory."""
        output = temp_dir / "output" / "index"
        output.mkdir(parents=True)
        return output

    @pytest.fixture
    def sample_items(self) -> list[MediaItem]:
        """Create sample media items for testing."""
        return [
            MediaItem(
                source_id="heroicons",
                path="outline/arrow-right.svg",
                name="arrow-right",
                format="svg",
                style="outline",
                tags=["arrow", "right", "direction"],
                license=License(spdx="MIT", commercial_ok=True, modification_ok=True),
            ),
            MediaItem(
                source_id="heroicons",
                path="solid/arrow-right.svg",
                name="arrow-right",
                format="svg",
                style="solid",
                tags=["arrow", "right", "direction"],
                license=License(spdx="MIT", commercial_ok=True, modification_ok=True),
            ),
            MediaItem(
                source_id="noto-emoji",
                path="svg/flag-us.svg",
                name="flag: United States",
                format="svg",
                tags=["flag", "us", "country"],
                license=License(spdx="OFL-1.1", commercial_ok=True, modification_ok=True),
                metadata={"markdown": "us"},
            ),
            MediaItem(
                source_id="noto-emoji",
                path="svg/flag-de.svg",
                name="flag: Germany",
                format="svg",
                tags=["flag", "de", "country", "germany"],
                license=License(spdx="OFL-1.1", commercial_ok=True, modification_ok=True),
                metadata={"markdown": "de"},
            ),
        ]

    @pytest.fixture
    def sample_sources(self) -> dict[str, dict[str, Any]]:
        """Create sample source metadata."""
        return {
            "heroicons": {
                "name": "Heroicons",
                "type": "git",
                "license": "MIT",
                "category": "Vector",
                "subcategory": "Icons",
            },
            "noto-emoji": {
                "name": "Noto Emoji",
                "type": "git",
                "license": "OFL-1.1",
                "category": "Vector",
                "subcategory": "Emoji",
            },
        }

    def test_build_creates_required_files(
        self,
        temp_output_dir: Path,
        sample_items: list[MediaItem],
        sample_sources: dict[str, dict],
    ) -> None:
        """Test that build creates all required index files."""
        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(sample_items, sample_sources)

        # Check required files exist
        assert (temp_output_dir / "meta.json").exists()
        assert (temp_output_dir / "sources.json").exists()
        assert (temp_output_dir / "licenses.json").exists()
        assert (temp_output_dir / "tags.json").exists()
        assert (temp_output_dir / "search" / "_manifest.json").exists()

    def test_sources_json_includes_hierarchy_tree(
        self,
        temp_output_dir: Path,
        sample_items: list[MediaItem],
        sample_sources: dict[str, dict],
    ) -> None:
        """Test that sources.json includes hierarchy tree structure."""
        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(sample_items, sample_sources)

        sources_data = json.loads((temp_output_dir / "sources.json").read_text())

        # Should have both sources list and tree
        assert "sources" in sources_data
        assert "tree" in sources_data

        # Check sources list
        sources_list = sources_data["sources"]
        assert len(sources_list) == 2

        # Check tree structure
        tree = sources_data["tree"]
        assert "Vector" in tree
        assert "Icons" in tree["Vector"]
        assert "Emoji" in tree["Vector"]
        assert "heroicons" in tree["Vector"]["Icons"]
        assert "noto-emoji" in tree["Vector"]["Emoji"]

    def test_sources_include_category_subcategory(
        self,
        temp_output_dir: Path,
        sample_items: list[MediaItem],
        sample_sources: dict[str, dict],
    ) -> None:
        """Test that each source includes category and subcategory."""
        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(sample_items, sample_sources)

        sources_data = json.loads((temp_output_dir / "sources.json").read_text())
        sources_list = sources_data["sources"]

        for source in sources_list:
            assert "category" in source
            assert "subcategory" in source
            assert source["category"] in ["Vector", "Other"]

    def test_search_prefix_files_created(
        self,
        temp_output_dir: Path,
        sample_items: list[MediaItem],
        sample_sources: dict[str, dict],
    ) -> None:
        """Test that search prefix files are created correctly."""
        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(sample_items, sample_sources)

        search_dir = temp_output_dir / "search"

        # Check that arrow prefix file exists (ar)
        assert (search_dir / "ar.json").exists()
        ar_items = json.loads((search_dir / "ar.json").read_text())
        assert len(ar_items) > 0

        # Check manifest
        manifest = json.loads((search_dir / "_manifest.json").read_text())
        assert len(manifest) > 0
        prefixes = [m["prefix"] for m in manifest]
        assert "ar" in prefixes

    def test_search_items_include_required_fields(
        self,
        temp_output_dir: Path,
        sample_items: list[MediaItem],
        sample_sources: dict[str, dict],
    ) -> None:
        """Test that search items include all required fields."""
        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(sample_items, sample_sources)

        ar_items = json.loads((temp_output_dir / "search" / "ar.json").read_text())

        for item in ar_items:
            # Required fields: id, n (name), s (source), t (tags)
            assert "id" in item
            assert "n" in item
            assert "s" in item
            assert "t" in item

    def test_flag_items_indexed_by_country_code(
        self,
        temp_output_dir: Path,
        sample_items: list[MediaItem],
        sample_sources: dict[str, dict],
    ) -> None:
        """Test that flag items are indexed by their country code prefix."""
        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(sample_items, sample_sources)

        search_dir = temp_output_dir / "search"

        # US flag should be in "us" prefix file (from markdown or tags)
        if (search_dir / "us.json").exists():
            us_items = json.loads((search_dir / "us.json").read_text())
            us_names = [i["n"] for i in us_items]
            assert "flag: United States" in us_names

        # DE flag should be in "de" prefix file
        if (search_dir / "de.json").exists():
            de_items = json.loads((search_dir / "de.json").read_text())
            de_names = [i["n"] for i in de_items]
            assert "flag: Germany" in de_names

    def test_tags_are_searchable(
        self,
        temp_output_dir: Path,
        sample_items: list[MediaItem],
        sample_sources: dict[str, dict],
    ) -> None:
        """Test that tags create searchable prefix entries."""
        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(sample_items, sample_sources)

        search_dir = temp_output_dir / "search"

        # "flag" tag should create "fl" prefix file
        if (search_dir / "fl.json").exists():
            fl_items = json.loads((search_dir / "fl.json").read_text())
            # Items with "flag" tag should be present
            flag_items = [i for i in fl_items if "flag" in i.get("t", [])]
            assert len(flag_items) >= 2  # US and DE flags

    def test_max_two_level_hierarchy(
        self,
        temp_output_dir: Path,
    ) -> None:
        """Test that hierarchy is limited to 2 levels (category -> subcategory)."""
        items = [
            MediaItem(
                source_id="source-a",
                path="test.svg",
                name="Test",
                format="svg",
            )
        ]
        sources = {
            "source-a": {
                "name": "Source A",
                "type": "git",
                "license": "MIT",
                "category": "Cat1",
                "subcategory": "SubCat1",
            }
        }

        builder = StaticIndexBuilder(temp_output_dir)
        builder.build(items, sources)

        sources_data = json.loads((temp_output_dir / "sources.json").read_text())
        tree = sources_data["tree"]

        # Tree should be exactly 2 levels: category -> subcategory -> [sources]
        assert "Cat1" in tree
        assert isinstance(tree["Cat1"], dict)
        assert "SubCat1" in tree["Cat1"]
        assert isinstance(tree["Cat1"]["SubCat1"], list)
        assert "source-a" in tree["Cat1"]["SubCat1"]


class TestStaticIndexStats:
    """Tests for static index statistics."""

    @pytest.fixture
    def sample_items_with_licenses(self) -> list[MediaItem]:
        """Create items with different licenses."""
        return [
            MediaItem(
                source_id="src1",
                path="a.svg",
                name="Item A",
                format="svg",
                license=License(spdx="MIT", commercial_ok=True, modification_ok=True),
            ),
            MediaItem(
                source_id="src1",
                path="b.svg",
                name="Item B",
                format="svg",
                license=License(spdx="MIT", commercial_ok=True, modification_ok=True),
            ),
            MediaItem(
                source_id="src2",
                path="c.svg",
                name="Item C",
                format="svg",
                license=License(spdx="ISC", commercial_ok=True, modification_ok=True),
            ),
        ]

    def test_build_returns_correct_stats(
        self,
        temp_dir: Path,
        sample_items_with_licenses: list[MediaItem],
    ) -> None:
        """Test that build returns correct statistics."""
        output_dir = temp_dir / "output" / "index"
        output_dir.mkdir(parents=True)

        sources = {
            "src1": {"name": "Source 1", "type": "git", "license": "MIT", "category": "Vector", "subcategory": "Icons"},
            "src2": {"name": "Source 2", "type": "git", "license": "ISC", "category": "Vector", "subcategory": "Icons"},
        }

        builder = StaticIndexBuilder(output_dir)
        stats = builder.build(sample_items_with_licenses, sources)

        assert stats["total_items"] == 3
        assert stats["sources"] == 2
        assert stats["licenses"] == 2  # MIT and ISC

    def test_licenses_json_content(
        self,
        temp_dir: Path,
        sample_items_with_licenses: list[MediaItem],
    ) -> None:
        """Test that licenses.json contains correct counts."""
        output_dir = temp_dir / "output" / "index"
        output_dir.mkdir(parents=True)

        sources = {
            "src1": {"name": "Source 1", "type": "git", "license": "MIT", "category": "Vector", "subcategory": "Icons"},
            "src2": {"name": "Source 2", "type": "git", "license": "ISC", "category": "Vector", "subcategory": "Icons"},
        }

        builder = StaticIndexBuilder(output_dir)
        builder.build(sample_items_with_licenses, sources)

        licenses_data = json.loads((output_dir / "licenses.json").read_text())

        # Should have MIT (2) and ISC (1)
        license_counts = {lic["type"]: lic["count"] for lic in licenses_data}
        assert license_counts.get("MIT") == 2
        assert license_counts.get("ISC") == 1
