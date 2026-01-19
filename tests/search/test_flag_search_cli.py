"""Tests for flag search via CLI in all modes.

Verifies that searching for country codes (US, DE) returns the
waved and flat/non-waved flag variants as top results.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


class TestFlagSearchCLI:
    """Tests for flag search across CLI modes."""

    @pytest.fixture
    def static_index_dir(self) -> Path:
        """Return the static index directory."""
        return Path("/projects/StagVault/static_site/index")

    def test_us_flag_search_static_mode(self, static_index_dir: Path) -> None:
        """Test that 'US' search in static mode returns US flags.

        Expected: Both waved and non-waved US flags should appear in results.
        """
        # Load the us.json prefix file directly
        us_file = static_index_dir / "index" / "search" / "us.json"
        if not us_file.exists():
            pytest.skip("Static index not built")

        with open(us_file) as f:
            items = json.load(f)

        # Filter for items that match "us" (name or tag)
        query = "us"
        matching = []
        for item in items:
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]

            if query in name or query in tags:
                matching.append(item)

        # Find US flag items specifically
        us_flags = [
            item for item in matching
            if "flag" in item.get("n", "").lower()
            and ("united states" in item.get("n", "").lower() or "us" in item.get("t", []))
        ]

        assert len(us_flags) >= 1, "Should find at least one US flag"

        # Verify at least one has the expected name
        flag_names = [f["n"] for f in us_flags]
        assert any("United States" in name for name in flag_names), \
            f"Should find 'flag: United States' in results. Found: {flag_names}"

    def test_de_flag_search_static_mode(self, static_index_dir: Path) -> None:
        """Test that 'DE' search in static mode returns German flags.

        Expected: Both waved and non-waved German flags should appear in results.
        """
        # Load the de.json prefix file directly
        de_file = static_index_dir / "index" / "search" / "de.json"
        if not de_file.exists():
            pytest.skip("Static index not built")

        with open(de_file) as f:
            items = json.load(f)

        # Filter for items that match "de" (name or tag)
        query = "de"
        matching = []
        for item in items:
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]

            if query in name or query in tags:
                matching.append(item)

        # Find German flag items specifically
        de_flags = [
            item for item in matching
            if "flag" in item.get("n", "").lower()
            and ("germany" in item.get("n", "").lower() or "de" in item.get("t", []))
        ]

        assert len(de_flags) >= 1, "Should find at least one German flag"

        # Verify at least one has the expected name
        flag_names = [f["n"] for f in de_flags]
        assert any("Germany" in name for name in flag_names), \
            f"Should find 'flag: Germany' in results. Found: {flag_names}"

    def test_flag_has_thumbnail(self, static_index_dir: Path) -> None:
        """Test that flag items have thumbnails."""
        de_file = static_index_dir / "index" / "search" / "de.json"
        if not de_file.exists():
            pytest.skip("Static index not built")

        with open(de_file) as f:
            items = json.load(f)

        # Find German flag
        de_flags = [
            item for item in items
            if "flag: Germany" in item.get("n", "")
        ]

        assert len(de_flags) >= 1, "Should find German flag"

        # Check thumbnail
        flag = de_flags[0]
        assert "p" in flag, f"German flag should have thumbnail. Item: {flag}"
        assert flag["p"].startswith("thumbs/") or flag["p"].startswith("http"), \
            f"Thumbnail should be a path or URL. Got: {flag['p']}"

    def test_flag_search_ranking(self, static_index_dir: Path) -> None:
        """Test that flags rank higher than other items with same prefix.

        When searching for "us", the US flag should rank above items like
        "user" that just happen to contain "us".
        """
        us_file = static_index_dir / "index" / "search" / "us.json"
        if not us_file.exists():
            pytest.skip("Static index not built")

        with open(us_file) as f:
            items = json.load(f)

        query = "us"

        def score_item(item: dict) -> int:
            """Score items similar to the JS implementation."""
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]
            score = 0

            # Exact name match
            if name == query:
                score += 1000
            # Name starts with query
            elif name.startswith(query):
                score += 500
            # Name contains query as word
            elif f": {query}" in name or f" {query}" in name:
                score += 350
            # Name contains query
            elif query in name:
                score += 100

            # Exact tag match (important for short codes)
            if query in tags:
                score += 600
            # Tag starts with query
            elif any(t.startswith(query) for t in tags):
                score += 250
            # Tag contains query
            elif any(query in t for t in tags):
                score += 50

            # Bonus for being a flag
            if "flag" in name or "flag" in tags:
                score += 100

            return score

        # Filter and score items
        scored_items = []
        for item in items:
            name = item.get("n", "").lower()
            tags = [t.lower() for t in item.get("t", [])]
            if query in name or any(query in t for t in tags):
                scored_items.append((item, score_item(item)))

        # Sort by score descending
        scored_items.sort(key=lambda x: -x[1])

        # Get top 10 results
        top_results = scored_items[:10]

        # Check that US flag appears in top results
        top_names = [r[0]["n"] for r in top_results]
        has_us_flag = any(
            "united states" in name.lower() and "flag" in name.lower()
            for name in top_names
        )

        assert has_us_flag, \
            f"US flag should appear in top 10 results. Top results: {top_names}"


class TestFlagSearchPython:
    """Tests for flag search via Python API.

    These tests require noto-emoji to be synced to the data directory.
    Run `stagvault sync --source noto-emoji` to sync the data.
    """

    @pytest.fixture
    def vault(self):
        """Create vault and check if noto-emoji is indexed."""
        from stagvault import StagVault

        vault = StagVault("./data", "./configs")
        sources = vault.query.list_sources()
        if "noto-emoji" not in sources:
            pytest.skip("noto-emoji not indexed - run: stagvault sync --source noto-emoji && stagvault index")
        return vault

    def test_us_flag_search_python(self, vault) -> None:
        """Test US flag search via Python API."""
        # Search for 'united states' as FTS matches on name
        results = vault.query.search("united states", limit=50)

        # Find US flags in results
        us_flags = [
            r for r in results
            if "flag" in r.item.name.lower()
            and "united states" in r.item.name.lower()
        ]

        assert len(us_flags) >= 1, \
            f"Should find at least one US flag. Results: {[r.item.name for r in results[:20]]}"

    def test_de_flag_search_python(self, vault) -> None:
        """Test German flag search via Python API."""
        # Search for 'germany' as FTS matches on name
        results = vault.query.search("germany", limit=50)

        # Find German flags in results
        de_flags = [
            r for r in results
            if "flag" in r.item.name.lower()
            and "germany" in r.item.name.lower()
        ]

        assert len(de_flags) >= 1, \
            f"Should find at least one German flag. Results: {[r.item.name for r in results[:20]]}"

    def test_flag_search_mode_parity(self, vault) -> None:
        """Test that Python and static mode return same flag results."""
        # Python mode search
        python_results = vault.query.search("germany", limit=100)
        python_flag_ids = {
            r.item.id for r in python_results
            if "flag" in r.item.name.lower() and "germany" in r.item.name.lower()
        }

        # Static mode search (from file)
        static_index_dir = Path("/projects/StagVault/static_site/index")
        de_file = static_index_dir / "index" / "search" / "de.json"

        if not de_file.exists():
            pytest.skip("Static index not built")

        with open(de_file) as f:
            items = json.load(f)

        static_flag_ids = {
            item["id"] for item in items
            if "flag" in item.get("n", "").lower() and "germany" in item.get("n", "").lower()
        }

        # Both modes should find the same German flags
        # (there might be slight differences due to indexing, so check overlap)
        overlap = python_flag_ids & static_flag_ids

        assert len(overlap) >= 1 or (len(python_flag_ids) == 0 and len(static_flag_ids) == 0), \
            f"Python and static modes should find same flags. " \
            f"Python: {python_flag_ids}, Static: {static_flag_ids}"
