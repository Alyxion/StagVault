"""Git source handler for cloning repositories."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from stagvault.models.media import MediaItem
from stagvault.sources.base import SourceHandler

if TYPE_CHECKING:
    from stagvault.models.source import SourceConfig

SYNC_MARKER = ".stagvault_sync"


class GitSourceHandler(SourceHandler):
    """Handler for git-based sources.

    Clones repositories as data-only (no .git directory) to minimize disk usage.
    """

    def __init__(self, config: SourceConfig, data_dir: Path) -> None:
        super().__init__(config, data_dir)
        if config.git is None:
            raise ValueError(f"Source {config.id} is not a git source")
        self.git_config = config.git

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

    def _write_sync_marker(self, commit: str | None = None) -> None:
        """Write sync marker with metadata."""
        marker = self.source_dir / SYNC_MARKER
        info = {
            "synced_at": datetime.now().isoformat(),
            "repo": self.git_config.repo,
            "branch": self.git_config.branch,
            "commit": commit or self.git_config.commit,
        }
        marker.write_text(json.dumps(info, indent=2))

    async def sync(self) -> None:
        """Clone or update the git repository (data only, no .git)."""
        if self.is_synced():
            # For data-only clones, we re-download to update
            # Could optimize with conditional requests or version checking
            pass
        await self._clone()

    async def _clone(self) -> None:
        """Clone the repository and extract data only (no .git directory)."""
        self.source_dir.parent.mkdir(parents=True, exist_ok=True)

        # Use a temporary directory for cloning
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / "repo"

            # Build clone command
            if self.git_config.commit:
                # Need full history to checkout specific commit
                cmd = ["git", "clone", "--branch", self.git_config.branch]
                if self.git_config.sparse_paths:
                    cmd.extend(["--filter=blob:none", "--sparse"])
                cmd.extend([self.git_config.clone_url, str(tmp_path)])
                await self._run_command(cmd)

                # Checkout specific commit
                await self._run_command(
                    ["git", "checkout", self.git_config.commit],
                    cwd=tmp_path,
                )
            else:
                # Shallow clone to latest
                cmd = [
                    "git",
                    "clone",
                    "--depth",
                    str(self.git_config.depth),
                    "--branch",
                    self.git_config.branch,
                ]
                if self.git_config.sparse_paths:
                    cmd.extend(["--filter=blob:none", "--sparse"])
                cmd.extend([self.git_config.clone_url, str(tmp_path)])
                await self._run_command(cmd)

            # Setup sparse checkout if needed
            if self.git_config.sparse_paths:
                await self._setup_sparse_checkout(tmp_path)

            # Get the actual commit hash for the marker
            result = await self._run_command(
                ["git", "rev-parse", "HEAD"],
                cwd=tmp_path,
            )
            actual_commit = result.stdout.strip()

            # Remove .git directory
            git_dir = tmp_path / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir)

            # Remove existing target and move new data
            if self.source_dir.exists():
                shutil.rmtree(self.source_dir)
            shutil.move(str(tmp_path), str(self.source_dir))

            # Write sync marker
            self._write_sync_marker(actual_commit)

    async def _setup_sparse_checkout(self, repo_path: Path) -> None:
        """Configure sparse checkout for the repository."""
        cmd = ["git", "sparse-checkout", "set", "--no-cone"]
        cmd.extend(self.git_config.sparse_paths)
        await self._run_command(cmd, cwd=repo_path)

    async def _run_command(
        self, cmd: list[str], cwd: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a command asynchronously."""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(
                process.returncode, cmd, stdout.decode(), stderr.decode()
            )

        return subprocess.CompletedProcess(
            cmd, process.returncode, stdout.decode(), stderr.decode()
        )

    async def scan(self) -> list[MediaItem]:
        """Scan the repository for media files.

        Files are matched against patterns in order. Each file is only included
        once, using the first matching pattern's configuration.
        """
        items: list[MediaItem] = []
        seen_paths: set[Path] = set()

        for path_config in self.config.paths:
            pattern = path_config.pattern
            matched_files = list(self.source_dir.glob(pattern))

            # Extract style from path config (stored as extra field)
            path_dict = path_config.model_dump()
            style = path_dict.get("style") or path_dict.get("weight")

            extra_metadata = {
                k: v
                for k, v in path_dict.items()
                if k not in ("pattern", "format", "tags", "metadata", "style", "weight")
            }

            for file_path in matched_files:
                # Skip files already matched by earlier patterns
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
                    style=style,
                    metadata={**path_config.metadata, **extra_metadata},
                )
                items.append(item)

        return items
