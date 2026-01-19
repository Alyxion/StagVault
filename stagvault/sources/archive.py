"""Archive source handler for ZIP-based sources."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.request import urlretrieve

from stagvault.models.media import MediaItem
from stagvault.sources.base import SourceHandler

if TYPE_CHECKING:
    from stagvault.models.source import SourceConfig

SYNC_MARKER = ".stagvault_sync"


class ArchiveSourceHandler(SourceHandler):
    """Handler for ZIP archive-based sources.

    Downloads and extracts ZIP archives containing media files.
    """

    def __init__(self, config: SourceConfig, data_dir: Path) -> None:
        super().__init__(config, data_dir)
        if config.archive is None:
            raise ValueError(f"Source {config.id} is not an archive source")
        self.archive_config = config.archive

    def is_synced(self) -> bool:
        """Check if the source has been synced."""
        marker = self.source_dir / SYNC_MARKER
        return marker.exists()

    def _get_sync_info(self) -> dict | None:
        """Get sync metadata from marker file."""
        marker = self.source_dir / SYNC_MARKER
        if not marker.exists():
            return None
        try:
            return json.loads(marker.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def _write_sync_marker(self, url: str, md5: str | None = None) -> None:
        """Write sync marker with metadata."""
        marker = self.source_dir / SYNC_MARKER
        info = {
            "synced_at": datetime.now().isoformat(),
            "url": url,
            "md5": md5,
        }
        marker.write_text(json.dumps(info, indent=2))

    async def sync(self) -> None:
        """Download and extract the archive."""
        if self.is_synced():
            return

        await self._download_and_extract()

    async def _download_and_extract(self) -> None:
        """Download the archive and extract it."""
        self.source_dir.parent.mkdir(parents=True, exist_ok=True)

        url = self.archive_config.url

        # Download to temp file
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            # Download with progress
            def download():
                urlretrieve(url, tmp_path)

            await asyncio.to_thread(download)

            # Calculate MD5 for verification
            md5 = hashlib.md5(tmp_path.read_bytes()).hexdigest()

            # Extract only needed files
            self.source_dir.mkdir(parents=True, exist_ok=True)

            with zipfile.ZipFile(tmp_path, "r") as zf:
                # Extract all files
                for member in zf.namelist():
                    # Skip directories
                    if member.endswith("/"):
                        continue

                    # Determine output path
                    out_path = self.source_dir / member
                    out_path.parent.mkdir(parents=True, exist_ok=True)

                    # Extract file
                    with zf.open(member) as src, open(out_path, "wb") as dst:
                        dst.write(src.read())

            # Write sync marker
            self._write_sync_marker(url, md5)

        finally:
            # Cleanup temp file
            if tmp_path.exists():
                tmp_path.unlink()

    async def scan(self) -> list[MediaItem]:
        """Scan the archive for media files."""
        items: list[MediaItem] = []

        # Check for emoji database (special handling for noto-emoji)
        emoji_db_path = self.source_dir / "data" / "emoji" / "emoji_db.json"
        if emoji_db_path.exists():
            items = await self._scan_emoji_db(emoji_db_path)
        else:
            # Generic file scanning using paths config
            items = await self._scan_files()

        return items

    async def _scan_emoji_db(self, db_path: Path) -> list[MediaItem]:
        """Scan using emoji database for names and metadata."""
        items: list[MediaItem] = []

        with open(db_path) as f:
            emoji_db = json.load(f)

        images_dir = self.source_dir / "images" / "noto" / "cpngs"

        for code, info in emoji_db.items():
            # Build image filename
            code_lower = code.lower().replace("_", "_")
            # Handle codes like "263A_FE0F" -> "263a_fe0f"
            image_name = f"emoji_u{code_lower}.png"
            image_path = images_dir / image_name

            if not image_path.exists():
                # Try without variation selector
                code_base = code_lower.split("_")[0]
                image_name = f"emoji_u{code_base}.png"
                image_path = images_dir / image_name

            if not image_path.exists():
                continue

            relative_path = image_path.relative_to(self.source_dir)

            # Build tags from group and subgroup
            tags = ["emoji", "noto"]
            group = info.get("group", "")
            subgroup = info.get("subgroup", "")

            if group:
                # Convert "Smileys & Emotion" to "smileys-emotion"
                tag = group.lower().replace(" & ", "-").replace(" ", "-")
                tags.append(tag)

            if subgroup:
                tag = subgroup.lower().replace(" ", "-")
                tags.append(tag)

            # Add markdown name as tag if available
            markdown_name = info.get("markdownName")
            if markdown_name:
                tags.append(markdown_name)

            # Get license for this item (checks overrides based on subgroup/path)
            # Use subgroup as match key for license overrides
            item_license = self.config.get_license_for_path(subgroup or "")
            # Only set per-item license if different from source default
            per_item_license = None
            if item_license != self.config.license:
                per_item_license = item_license

            # Build item
            item = MediaItem(
                source_id=self.config.id,
                path=str(relative_path),
                name=info.get("name", code),
                format="png",
                tags=tags,
                style=subgroup,
                license=per_item_license,
                metadata={
                    "unicode": code,
                    "group": group,
                    "subgroup": subgroup,
                    "markdown": markdown_name,
                },
            )
            items.append(item)

        return items

    async def _scan_files(self) -> list[MediaItem]:
        """Generic file scanning using path patterns."""
        items: list[MediaItem] = []
        seen_paths: set[Path] = set()

        for path_config in self.config.paths:
            pattern = path_config.pattern
            matched_files = list(self.source_dir.glob(pattern))

            for file_path in matched_files:
                if file_path in seen_paths:
                    continue
                seen_paths.add(file_path)

                relative_path = file_path.relative_to(self.source_dir)
                name = file_path.stem

                item = MediaItem(
                    source_id=self.config.id,
                    path=str(relative_path),
                    name=name,
                    format=path_config.format,
                    tags=path_config.tags.copy(),
                    metadata=path_config.metadata.copy(),
                )
                items.append(item)

        return items
