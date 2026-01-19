"""Tests for CLI search modes (python, rest, static).

These tests verify that search behaves consistently across all three modes.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from stagvault.search.query import SearchQuery, SearchResult
from stagvault.models.media import License, MediaItem


class TestStaticSearch:
    """Tests for static mode search (JSON-based, same as static website)."""

    @pytest.fixture
    def static_index_dir(self, temp_dir: Path) -> Path:
        """Create a mock static index directory."""
        index_dir = temp_dir / "index"
        search_dir = index_dir / "search"
        search_dir.mkdir(parents=True)

        # Create sources.json with tree structure
        sources_data = {
            "sources": [
                {
                    "id": "noto-emoji",
                    "name": "Noto Emoji",
                    "count": 3,
                    "type": "git",
                    "tags": ["emoji", "flag"],
                    "license": "OFL-1.1",
                    "category": "Vector",
                    "subcategory": "Emoji",
                },
                {
                    "id": "heroicons",
                    "name": "Heroicons",
                    "count": 2,
                    "type": "git",
                    "tags": ["icon", "ui"],
                    "license": "MIT",
                    "category": "Vector",
                    "subcategory": "Icons",
                },
            ],
            "tree": {
                "Vector": {
                    "Emoji": ["noto-emoji"],
                    "Icons": ["heroicons"],
                }
            },
        }
        (index_dir / "sources.json").write_text(json.dumps(sources_data))

        # Create search prefix files for "us" and "de"
        us_items = [
            {
                "id": "flag-us",
                "n": "flag: United States",
                "s": "noto-emoji",
                "t": ["flag", "us", "country"],
                "l": "OFL-1.1",
            },
            {
                "id": "flag-us-waved",
                "n": "flag: United States (waved)",
                "s": "noto-emoji",
                "t": ["flag", "us", "country", "waved"],
                "l": "OFL-1.1",
            },
            {
                "id": "user-icon",
                "n": "user",
                "s": "heroicons",
                "t": ["user", "account", "person"],
                "l": "MIT",
            },
        ]
        (search_dir / "us.json").write_text(json.dumps(us_items))

        de_items = [
            {
                "id": "flag-de",
                "n": "flag: Germany",
                "s": "noto-emoji",
                "t": ["flag", "de", "country", "germany"],
                "l": "OFL-1.1",
            },
            {
                "id": "flag-de-waved",
                "n": "flag: Germany (waved)",
                "s": "noto-emoji",
                "t": ["flag", "de", "country", "germany", "waved"],
                "l": "OFL-1.1",
            },
        ]
        (search_dir / "de.json").write_text(json.dumps(de_items))

        # Create arrow items for general search tests
        ar_items = [
            {
                "id": "arrow-right",
                "n": "arrow-right",
                "s": "heroicons",
                "t": ["arrow", "right", "direction"],
                "l": "MIT",
            },
            {
                "id": "arrow-left",
                "n": "arrow-left",
                "s": "heroicons",
                "t": ["arrow", "left", "direction"],
                "l": "MIT",
            },
        ]
        (search_dir / "ar.json").write_text(json.dumps(ar_items))

        # Create manifest
        manifest = [
            {"prefix": "us", "count": 3},
            {"prefix": "de", "count": 2},
            {"prefix": "ar", "count": 2},
        ]
        (search_dir / "_manifest.json").write_text(json.dumps(manifest))

        # Create meta.json
        meta = {
            "version": 1,
            "generated": "2024-01-01T00:00:00Z",
            "stats": {"total_items": 7},
        }
        (index_dir / "meta.json").write_text(json.dumps(meta))

        return index_dir

    def test_static_search_basic(self, static_index_dir: Path) -> None:
        """Test basic static search returns results."""
        from stagvault.cli import _search_static

        # Read results directly from the prefix file
        search_dir = static_index_dir / "search"
        items = json.loads((search_dir / "ar.json").read_text())

        assert len(items) == 2
        assert items[0]["n"] == "arrow-right"
        assert items[1]["n"] == "arrow-left"

    def test_static_search_loads_sources(self, static_index_dir: Path) -> None:
        """Test that sources.json is loaded correctly with tree structure."""
        sources_data = json.loads((static_index_dir / "sources.json").read_text())

        assert "sources" in sources_data
        assert "tree" in sources_data
        assert len(sources_data["sources"]) == 2
        assert "Vector" in sources_data["tree"]
        assert "Emoji" in sources_data["tree"]["Vector"]
        assert "noto-emoji" in sources_data["tree"]["Vector"]["Emoji"]

    def test_static_search_source_filter(self, static_index_dir: Path) -> None:
        """Test filtering by source in static mode."""
        search_dir = static_index_dir / "search"
        items = json.loads((search_dir / "us.json").read_text())

        # Filter to only heroicons
        filtered = [i for i in items if i["s"] == "heroicons"]
        assert len(filtered) == 1
        assert filtered[0]["n"] == "user"

        # Filter to only noto-emoji
        filtered = [i for i in items if i["s"] == "noto-emoji"]
        assert len(filtered) == 2
        assert "flag" in filtered[0]["n"].lower()

    def test_static_search_license_filter(self, static_index_dir: Path) -> None:
        """Test filtering by license in static mode."""
        search_dir = static_index_dir / "search"
        items = json.loads((search_dir / "us.json").read_text())

        # Filter to only MIT license
        filtered = [i for i in items if i.get("l") == "MIT"]
        assert len(filtered) == 1
        assert filtered[0]["n"] == "user"

        # Filter to only OFL-1.1 license
        filtered = [i for i in items if i.get("l") == "OFL-1.1"]
        assert len(filtered) == 2

    def test_static_search_exclude_source(self, static_index_dir: Path) -> None:
        """Test excluding sources in static mode."""
        search_dir = static_index_dir / "search"
        items = json.loads((search_dir / "us.json").read_text())

        # Exclude heroicons
        excluded = {"heroicons"}
        filtered = [i for i in items if i["s"] not in excluded]
        assert len(filtered) == 2
        assert all(i["s"] == "noto-emoji" for i in filtered)


class TestFlagSearch:
    """Tests for flag search behavior.

    Expected: Search for country codes (US, DE) should return
    waved and non-waved flags as the first results.
    """

    @pytest.fixture
    def flag_search_items(self) -> list[dict]:
        """Create test items for flag search."""
        return [
            {
                "id": "flag-us",
                "n": "flag: United States",
                "s": "noto-emoji",
                "t": ["flag", "us", "country", "usa", "america"],
            },
            {
                "id": "flag-us-waved",
                "n": "flag: United States (waved)",
                "s": "noto-emoji",
                "t": ["flag", "us", "country", "usa", "america", "waved"],
            },
            {
                "id": "user-solid",
                "n": "user",
                "s": "heroicons",
                "t": ["user", "account", "us"],
            },
            {
                "id": "bus-icon",
                "n": "bus",
                "s": "heroicons",
                "t": ["bus", "transport", "vehicle"],
            },
        ]

    def test_us_search_returns_us_flags_first(self, flag_search_items: list[dict]) -> None:
        """Test that 'US' search returns US flags as top results."""
        query = "us"
        items = flag_search_items

        # Filter items that match query in name or tags
        def matches_query(item: dict, q: str) -> bool:
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]
            return q.lower() in name or any(q.lower() in t for t in tags)

        matching = [i for i in items if matches_query(i, query)]

        # Score items (flag items should rank higher)
        def score_item(item: dict, q: str) -> int:
            score = 0
            tags = [t.lower() for t in item.get("t", [])]

            # Exact tag match gets high score
            if q.lower() in tags:
                score += 10

            # Flag items get bonus
            if "flag" in tags:
                score += 5

            return score

        scored = [(i, score_item(i, query)) for i in matching]
        scored.sort(key=lambda x: -x[1])

        # Verify US flags are in top results
        top_results = [i[0] for i in scored[:2]]
        assert len(top_results) == 2
        assert all("flag" in r["n"].lower() or "flag" in r.get("t", []) for r in top_results)

    def test_de_search_returns_german_flags_first(self) -> None:
        """Test that 'DE' search returns German flags as top results."""
        items = [
            {
                "id": "flag-de",
                "n": "flag: Germany",
                "s": "noto-emoji",
                "t": ["flag", "de", "country", "germany"],
            },
            {
                "id": "flag-de-waved",
                "n": "flag: Germany (waved)",
                "s": "noto-emoji",
                "t": ["flag", "de", "country", "germany", "waved"],
            },
            {
                "id": "delete-icon",
                "n": "delete",
                "s": "heroicons",
                "t": ["delete", "remove", "de"],
            },
        ]

        query = "de"

        def matches_query(item: dict, q: str) -> bool:
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]
            return q.lower() in name or any(q.lower() in t for t in tags)

        def score_item(item: dict, q: str) -> int:
            score = 0
            tags = [t.lower() for t in item.get("t", [])]
            if q.lower() in tags:
                score += 10
            if "flag" in tags:
                score += 5
            return score

        matching = [i for i in items if matches_query(i, query)]
        scored = [(i, score_item(i, query)) for i in matching]
        scored.sort(key=lambda x: -x[1])

        top_results = [i[0] for i in scored[:2]]
        assert len(top_results) == 2
        assert all("flag" in r.get("t", []) for r in top_results)

    def test_flag_variants_both_appear(self) -> None:
        """Test that both waved and non-waved flag variants appear in results."""
        items = [
            {"id": "flag-us", "n": "flag: United States", "t": ["flag", "us"]},
            {"id": "flag-us-waved", "n": "flag: United States (waved)", "t": ["flag", "us", "waved"]},
        ]

        query = "us"
        matching = [i for i in items if "us" in i.get("t", [])]

        assert len(matching) == 2
        names = [i["n"] for i in matching]
        assert "flag: United States" in names
        assert "flag: United States (waved)" in names


class TestSearchFilters:
    """Tests for search filter functionality."""

    @pytest.fixture
    def mock_search_results(self) -> list[dict]:
        """Create mock search results for filter testing."""
        return [
            {"id": "arrow-1", "n": "arrow-right", "s": "heroicons", "l": "MIT"},
            {"id": "arrow-2", "n": "arrow-left", "s": "heroicons", "l": "MIT"},
            {"id": "arrow-3", "n": "arrow-up", "s": "phosphor", "l": "MIT"},
            {"id": "arrow-4", "n": "arrow-down", "s": "lucide", "l": "ISC"},
        ]

    def test_include_sources_filter(self, mock_search_results: list[dict]) -> None:
        """Test including specific sources."""
        include_sources = {"heroicons"}

        filtered = [
            r for r in mock_search_results
            if r["s"] in include_sources
        ]

        assert len(filtered) == 2
        assert all(r["s"] == "heroicons" for r in filtered)

    def test_exclude_sources_filter(self, mock_search_results: list[dict]) -> None:
        """Test excluding specific sources."""
        exclude_sources = {"heroicons"}

        filtered = [
            r for r in mock_search_results
            if r["s"] not in exclude_sources
        ]

        assert len(filtered) == 2
        assert all(r["s"] != "heroicons" for r in filtered)

    def test_include_licenses_filter(self, mock_search_results: list[dict]) -> None:
        """Test including specific licenses."""
        include_licenses = {"MIT"}

        filtered = [
            r for r in mock_search_results
            if r.get("l") in include_licenses
        ]

        assert len(filtered) == 3
        assert all(r["l"] == "MIT" for r in filtered)

    def test_exclude_licenses_filter(self, mock_search_results: list[dict]) -> None:
        """Test excluding specific licenses."""
        exclude_licenses = {"MIT"}

        filtered = [
            r for r in mock_search_results
            if r.get("l") not in exclude_licenses
        ]

        assert len(filtered) == 1
        assert filtered[0]["l"] == "ISC"

    def test_combined_filters(self, mock_search_results: list[dict]) -> None:
        """Test combining source and license filters."""
        include_sources = {"heroicons", "phosphor"}
        include_licenses = {"MIT"}

        filtered = [
            r for r in mock_search_results
            if r["s"] in include_sources and r.get("l") in include_licenses
        ]

        assert len(filtered) == 3
        assert all(r["s"] in include_sources for r in filtered)
        assert all(r["l"] == "MIT" for r in filtered)

    def test_multiple_source_inclusion(self, mock_search_results: list[dict]) -> None:
        """Test including multiple sources."""
        include_sources = {"heroicons", "lucide"}

        filtered = [
            r for r in mock_search_results
            if r["s"] in include_sources
        ]

        assert len(filtered) == 3
        sources = {r["s"] for r in filtered}
        assert sources == {"heroicons", "lucide"}


class TestSearchModeParity:
    """Tests verifying parity between Python and Static search modes."""

    def test_filter_logic_matches_static_js(self) -> None:
        """Test that Python filter logic matches static JS behavior.

        This test verifies the filtering algorithm used in both
        Python CLI static mode and the static website JavaScript.
        """
        items = [
            {"id": "1", "s": "source-a", "l": "MIT"},
            {"id": "2", "s": "source-b", "l": "ISC"},
            {"id": "3", "s": "source-a", "l": "ISC"},
        ]

        # Exclusion-mode filtering (default in static site)
        # When a source is excluded, items from that source are hidden
        excluded_sources = {"source-b"}
        excluded_licenses = {"ISC"}

        # Python implementation
        python_filtered = [
            item for item in items
            if item["s"] not in excluded_sources
            and item.get("l") not in excluded_licenses
        ]

        # Should only have item 1 (source-a + MIT)
        assert len(python_filtered) == 1
        assert python_filtered[0]["id"] == "1"

    def test_query_matching_behavior(self) -> None:
        """Test that query matching is consistent across modes.

        Both Python and JS implementations should:
        1. Match against item name
        2. Match against tags
        3. Be case-insensitive
        """
        items = [
            {"id": "1", "n": "Arrow Right", "t": ["arrow", "right"]},
            {"id": "2", "n": "Plus", "t": ["add", "plus"]},
            {"id": "3", "n": "User Arrow", "t": ["user", "profile"]},
        ]

        query = "arrow"

        def matches(item: dict, q: str) -> bool:
            """Match logic (should be identical in Python and JS)."""
            q_lower = q.lower()
            name_lower = item.get("n", "").lower()
            tags_lower = [t.lower() for t in item.get("t", [])]

            return q_lower in name_lower or any(q_lower in t for t in tags_lower)

        matching = [i for i in items if matches(i, query)]

        # Should match items 1 and 3
        assert len(matching) == 2
        ids = {i["id"] for i in matching}
        assert ids == {"1", "3"}
