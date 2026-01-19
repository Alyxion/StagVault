"""Tests for flag search behavior.

Verifies that searching for country codes (US, DE) returns the correct flags.
Expected: Search for "US" returns US flags, search for "DE" returns German flags.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


class TestFlagSearchCLI:
    """Tests for flag search via CLI in different modes."""

    @pytest.fixture
    def db_path(self) -> Path:
        """Get the database path."""
        return Path("/projects/StagVault/data/index/stagvault.db")

    def test_us_flag_exists_in_database(self, db_path: Path) -> None:
        """Verify US flag exists in the database with correct tags."""
        import sqlite3

        if not db_path.exists():
            pytest.skip("Database not found")

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name, tags FROM media_items WHERE name LIKE '%United States%' AND source_id='noto-emoji'"
        )
        rows = list(cursor)
        conn.close()

        assert len(rows) >= 1, "US flag should exist in database"
        name, tags = rows[0]
        assert "United States" in name
        assert "us" in tags.lower(), "US flag should have 'us' tag"

    def test_de_flag_exists_in_database(self, db_path: Path) -> None:
        """Verify German flag exists in the database with correct tags."""
        import sqlite3

        if not db_path.exists():
            pytest.skip("Database not found")

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name, tags FROM media_items WHERE name LIKE '%Germany%' AND source_id='noto-emoji'"
        )
        rows = list(cursor)
        conn.close()

        assert len(rows) >= 1, "German flag should exist in database"
        name, tags = rows[0]
        assert "Germany" in name
        assert "de" in tags.lower(), "German flag should have 'de' tag"

    def test_us_flag_in_static_index(self) -> None:
        """Verify US flag is in the static search index under 'us' prefix."""
        us_json = Path("/projects/StagVault/static_site/index/index/search/us.json")

        if not us_json.exists():
            pytest.skip("Static index not built")

        with open(us_json) as f:
            items = json.load(f)

        # Find US flag
        us_flags = [
            item for item in items
            if "united states" in item.get("n", "").lower()
            or ("flag" in item.get("n", "").lower() and "us" in item.get("t", []))
        ]

        assert len(us_flags) >= 1, "US flag should be in us.json"
        assert any("United States" in f["n"] for f in us_flags)

    def test_de_flag_in_static_index(self) -> None:
        """Verify German flag is in the static search index under 'de' prefix."""
        de_json = Path("/projects/StagVault/static_site/index/index/search/de.json")

        if not de_json.exists():
            pytest.skip("Static index not built")

        with open(de_json) as f:
            items = json.load(f)

        # Find German flag
        de_flags = [
            item for item in items
            if "germany" in item.get("n", "").lower()
            or ("flag" in item.get("n", "").lower() and "de" in item.get("t", []))
        ]

        assert len(de_flags) >= 1, "German flag should be in de.json"
        assert any("Germany" in f["n"] for f in de_flags)

    def test_flag_search_ranking_us(self) -> None:
        """Test that US flag ranks highly when searching for 'us'."""
        us_json = Path("/projects/StagVault/static_site/index/index/search/us.json")

        if not us_json.exists():
            pytest.skip("Static index not built")

        with open(us_json) as f:
            items = json.load(f)

        query = "us"

        def get_score(item: dict) -> int:
            """Score items similar to app.js ranking."""
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]
            score = 0

            # Exact name match
            if name == query:
                score += 1000
            elif name.startswith(query):
                score += 500
            elif f": {query}" in name:
                score += 350
            elif query in name:
                score += 100

            # Tag matches (important for country codes)
            if query in tags:
                score += 600
            elif any(t.startswith(query) for t in tags):
                score += 250

            # Flag bonus
            if "flag" in tags or "country-flag" in tags:
                score += 100

            return score

        # Score and sort items
        scored = [(item, get_score(item)) for item in items]
        scored.sort(key=lambda x: -x[1])

        # Get top 10 results
        top_10 = [item for item, _ in scored[:10]]

        # US flag should be in top 10
        us_flag_in_top = any(
            "united states" in item.get("n", "").lower()
            for item in top_10
        )
        assert us_flag_in_top, "US flag should be in top 10 results for 'us' search"

    def test_flag_search_ranking_de(self) -> None:
        """Test that German flag ranks highly when searching for 'de'."""
        de_json = Path("/projects/StagVault/static_site/index/index/search/de.json")

        if not de_json.exists():
            pytest.skip("Static index not built")

        with open(de_json) as f:
            items = json.load(f)

        query = "de"

        def get_score(item: dict) -> int:
            """Score items similar to app.js ranking."""
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]
            score = 0

            if name == query:
                score += 1000
            elif name.startswith(query):
                score += 500
            elif f": {query}" in name:
                score += 350
            elif query in name:
                score += 100

            if query in tags:
                score += 600
            elif any(t.startswith(query) for t in tags):
                score += 250

            if "flag" in tags or "country-flag" in tags:
                score += 100

            return score

        scored = [(item, get_score(item)) for item in items]
        scored.sort(key=lambda x: -x[1])

        top_10 = [item for item, _ in scored[:10]]

        de_flag_in_top = any(
            "germany" in item.get("n", "").lower()
            for item in top_10
        )
        assert de_flag_in_top, "German flag should be in top 10 results for 'de' search"


class TestStaticSearchFiltering:
    """Tests for static search filtering behavior."""

    def test_search_matches_by_tag(self) -> None:
        """Test that search matches items by tag, not just name."""
        items = [
            {"id": "1", "n": "flag: United States", "t": ["flag", "us", "country"]},
            {"id": "2", "n": "arrow", "t": ["arrow", "direction"]},
            {"id": "3", "n": "bus", "t": ["bus", "transport"]},
        ]

        query = "us"

        def matches(item: dict, q: str) -> bool:
            """Match by name or tags."""
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]
            return q in name or q in tags

        matching = [i for i in items if matches(i, query)]

        # Should match "flag: United States" (has "us" tag) and "bus" (has "us" in name)
        assert len(matching) == 2
        ids = {m["id"] for m in matching}
        assert "1" in ids  # US flag via tag
        assert "3" in ids  # bus via name

    def test_flag_tag_gives_higher_score(self) -> None:
        """Test that items with 'flag' tag get higher scores."""
        items = [
            {"id": "1", "n": "flag: United States", "t": ["flag", "us", "country-flag"]},
            {"id": "2", "n": "user", "t": ["us", "user"]},  # "us" tag but not a flag
            {"id": "3", "n": "bus", "t": ["bus"]},
        ]

        query = "us"

        def score(item: dict, q: str) -> int:
            s = 0
            tags = [t.lower() for t in item.get("t", [])]

            if q in tags:
                s += 600

            if "flag" in tags or "country-flag" in tags:
                s += 100

            return s

        scores = [(i["id"], score(i, query)) for i in items]
        scores.sort(key=lambda x: -x[1])

        # Flag should be first
        assert scores[0][0] == "1", "Flag item should rank first"
        assert scores[0][1] > scores[1][1], "Flag should have higher score"
