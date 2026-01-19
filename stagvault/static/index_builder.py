"""Static index builder for client-side search."""

from __future__ import annotations

import json
import logging
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from stagvault.models.media import MediaItem

logger = logging.getLogger(__name__)

# Thumbnail sizes to include in static site
PREVIEW_THUMB_SIZE = 64   # For grid view
DETAIL_THUMB_SIZE = 256   # For modal/zoom view


class StaticIndexBuilder:
    """Builds static JSON index files for client-side search.

    Creates small files indexed by 2-character prefixes to enable
    efficient search without downloading large index files.

    Index structure:
        index/
        ├── meta.json           # Index metadata
        ├── sources.json        # Source list with counts
        ├── licenses.json       # License types
        ├── tags.json           # All tags
        └── search/
            ├── _manifest.json  # List of available prefix files
            ├── ar.json         # Items with "ar" in name
            ├── ti.json         # Items with "ti" in name
            └── ...
    """

    def __init__(self, output_dir: Path, data_dir: Path | None = None) -> None:
        self.output_dir = output_dir
        self.search_dir = output_dir / "search"
        self.data_dir = data_dir
        self.thumbs_dir = output_dir.parent / "thumbs"

    def build(
        self,
        items: list[MediaItem],
        sources: dict[str, dict],
        include_thumbnails: bool = False,
    ) -> dict[str, int]:
        """Build the complete static index.

        Args:
            items: All media items to index
            sources: Source metadata keyed by source_id
            include_thumbnails: Whether to copy thumbnails to static site

        Returns:
            Statistics about the generated index
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.search_dir.mkdir(parents=True, exist_ok=True)

        stats = {
            "total_items": len(items),
            "sources": 0,
            "licenses": 0,
            "tags": 0,
            "prefix_files": 0,
            "thumbnails_copied": 0,
        }

        # Copy thumbnails if requested
        thumb_map: dict[str, str] = {}
        if include_thumbnails and self.data_dir:
            stats["thumbnails_copied"], thumb_map = self._copy_thumbnails(items)

        # Build source index
        stats["sources"] = self._build_sources_index(items, sources)

        # Build license index
        stats["licenses"] = self._build_licenses_index(items)

        # Build tags index
        stats["tags"] = self._build_tags_index(items)

        # Build search prefix index
        stats["prefix_files"] = self._build_search_index(items, thumb_map)

        # Build metadata
        self._build_meta(stats)

        return stats

    def _copy_thumbnails(
        self,
        items: list[MediaItem],
    ) -> tuple[int, dict[str, str]]:
        """Copy thumbnails to static site directory.

        Copies both 64px (for grid) and 256px (for detail view) thumbnails.
        For PNG sources without generated thumbnails, copies/resizes the source PNG.

        Returns:
            Tuple of (count of thumbnails copied, mapping of item_id to thumb URL)
        """
        if not self.data_dir:
            return 0, {}

        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        thumb_map: dict[str, str] = {}
        copied = 0

        for item in items:
            prefix = item.id[:2] if len(item.id) >= 2 else item.id
            dest_dir = self.thumbs_dir / item.source_id / prefix
            dest_dir.mkdir(parents=True, exist_ok=True)

            has_thumbnail = False

            # Try to copy generated thumbnails first
            for size in [PREVIEW_THUMB_SIZE, DETAIL_THUMB_SIZE]:
                thumb_filename = f"{item.id}_{size}.jpg"
                src_path = (
                    self.data_dir / "thumbnails" / item.source_id / prefix / thumb_filename
                )

                if src_path.exists():
                    dest_path = dest_dir / thumb_filename
                    if not dest_path.exists():
                        shutil.copy(src_path, dest_path)
                        copied += 1
                    has_thumbnail = True

            # If no generated thumbnails and source is PNG, use source file
            if not has_thumbnail and item.format == "png":
                source_path = self.data_dir / item.source_id / item.path
                if source_path.exists():
                    # Copy as both 64 and 256 (they're usually small enough)
                    for size in [PREVIEW_THUMB_SIZE, DETAIL_THUMB_SIZE]:
                        dest_filename = f"{item.id}_{size}.png"
                        dest_path = dest_dir / dest_filename
                        if not dest_path.exists():
                            shutil.copy(source_path, dest_path)
                            copied += 1
                    has_thumbnail = True

            # Store relative URL for index (64px for grid view)
            if has_thumbnail:
                # Check for jpg first, then png
                for ext in ["jpg", "png"]:
                    preview_filename = f"{item.id}_{PREVIEW_THUMB_SIZE}.{ext}"
                    if (self.thumbs_dir / item.source_id / prefix / preview_filename).exists():
                        thumb_map[item.id] = f"thumbs/{item.source_id}/{prefix}/{preview_filename}"
                        break

        return copied, thumb_map

    def _build_sources_index(
        self,
        items: list[MediaItem],
        sources: dict[str, dict],
    ) -> int:
        """Build sources.json with source metadata and item counts."""
        source_counts: dict[str, int] = defaultdict(int)
        source_tags: dict[str, set] = defaultdict(set)

        for item in items:
            source_counts[item.source_id] += 1
            for tag in item.tags:
                source_tags[item.source_id].add(tag)

        source_list = []
        for source_id, count in sorted(source_counts.items()):
            meta = sources.get(source_id, {})
            source_list.append({
                "id": source_id,
                "name": meta.get("name", source_id),
                "count": count,
                "type": meta.get("type", "git"),
                "tags": sorted(source_tags[source_id]),
                "license": meta.get("license", "unknown"),
            })

        self._write_json(self.output_dir / "sources.json", source_list)
        return len(source_list)

    def _build_licenses_index(self, items: list[MediaItem]) -> int:
        """Build licenses.json with unique license types."""
        licenses: dict[str, int] = defaultdict(int)

        for item in items:
            if item.license:
                # Use SPDX identifier or display name
                license_key = item.license.spdx or item.license.name or "Unknown"
                licenses[license_key] += 1

        license_list = [
            {"type": license_type, "count": count}
            for license_type, count in sorted(licenses.items())
        ]

        self._write_json(self.output_dir / "licenses.json", license_list)
        return len(license_list)

    def _build_tags_index(self, items: list[MediaItem]) -> int:
        """Build tags.json with all unique tags and counts."""
        tags: dict[str, int] = defaultdict(int)

        for item in items:
            for tag in item.tags:
                tags[tag] += 1

        tag_list = [
            {"tag": tag, "count": count}
            for tag, count in sorted(tags.items(), key=lambda x: -x[1])
        ]

        self._write_json(self.output_dir / "tags.json", tag_list)
        return len(tag_list)

    def _build_search_index(
        self,
        items: list[MediaItem],
        thumb_map: dict[str, str] | None = None,
    ) -> int:
        """Build 2-character prefix search index files.

        For each unique 2-char substring in item names, creates a JSON file
        containing all items that match. This enables efficient search by
        fetching only the relevant prefix file.
        """
        thumb_map = thumb_map or {}

        # Group items by all 2-char substrings in their name
        prefix_items: dict[str, list[dict]] = defaultdict(list)

        for item in items:
            # Get the searchable name (lowercase, no special chars)
            name = item.name.lower()

            # Compact item representation for search results
            compact = {
                "id": item.id,
                "n": item.name,  # name
                "s": item.source_id,  # source
                "t": item.tags[:5] if item.tags else [],  # top 5 tags
            }

            # Add preview URL - prefer thumbnail, fall back to metadata
            thumb_url = thumb_map.get(item.id)
            if thumb_url:
                compact["p"] = thumb_url
            else:
                preview_url = item.metadata.get("preview_url") if item.metadata else None
                if preview_url:
                    compact["p"] = preview_url

            # Add style if present
            if item.style:
                compact["y"] = item.style  # style

            # Add per-item license if different from source
            if item.license:
                compact["l"] = item.license.spdx or item.license.name  # license

            # Build list of searchable terms (name + tags + aliases)
            search_terms = [name]

            # Add tags as searchable terms (e.g., "us" tag for US flag)
            if item.tags:
                search_terms.extend(tag.lower() for tag in item.tags)

            if item.metadata:
                # Add markdown short name (e.g., "us" for US flag)
                if markdown := item.metadata.get("markdown"):
                    search_terms.append(markdown.lower())
                # Add any aliases
                if aliases := item.metadata.get("aliases"):
                    if isinstance(aliases, list):
                        search_terms.extend(a.lower() for a in aliases)

            # Extract all 2-char substrings from all search terms
            seen_prefixes = set()
            for term in search_terms:
                for i in range(len(term) - 1):
                    prefix = term[i:i+2]
                    # Only alphanumeric prefixes
                    if prefix.isalnum() and prefix not in seen_prefixes:
                        seen_prefixes.add(prefix)
                        prefix_items[prefix].append(compact)

        # Write prefix files
        manifest = []
        for prefix, prefix_item_list in sorted(prefix_items.items()):
            # Skip very common prefixes that would create huge files
            # (they can search with 3+ chars instead)
            if len(prefix_item_list) > 5000:
                logger.info(f"Skipping prefix '{prefix}' with {len(prefix_item_list)} items (too common)")
                continue

            filename = f"{prefix}.json"
            self._write_json(
                self.search_dir / filename,
                prefix_item_list,
                compact=True,
            )
            manifest.append({
                "prefix": prefix,
                "count": len(prefix_item_list),
            })

        # Write manifest
        self._write_json(self.search_dir / "_manifest.json", manifest)

        return len(manifest)

    def _build_meta(self, stats: dict[str, int]) -> None:
        """Build meta.json with index metadata."""
        meta = {
            "version": 1,
            "generated": datetime.utcnow().isoformat() + "Z",
            "stats": stats,
        }
        self._write_json(self.output_dir / "meta.json", meta)

    def _write_json(
        self,
        path: Path,
        data: dict | list,
        compact: bool = False,
    ) -> None:
        """Write JSON data to file."""
        if compact:
            content = json.dumps(data, separators=(",", ":"))
        else:
            content = json.dumps(data, indent=2)
        path.write_text(content)
