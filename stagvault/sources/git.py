"""Git source handler for cloning repositories."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from stagvault.models.media import MediaItem
from stagvault.sources.base import SourceHandler

if TYPE_CHECKING:
    from stagvault.models.config import SourceConfig


class GitSourceHandler(SourceHandler):
    """Handler for git-based sources."""

    def __init__(self, config: SourceConfig, data_dir: Path) -> None:
        super().__init__(config, data_dir)
        if config.git is None:
            raise ValueError(f"Source {config.id} is not a git source")
        self.git_config = config.git

    def is_synced(self) -> bool:
        """Check if the repository has been cloned."""
        return (self.source_dir / ".git").exists()

    async def sync(self) -> None:
        """Clone or update the git repository."""
        if self.is_synced():
            await self._pull()
        else:
            await self._clone()

    async def _clone(self) -> None:
        """Clone the repository at locked commit if specified."""
        self.source_dir.parent.mkdir(parents=True, exist_ok=True)

        if self.git_config.commit:
            # Clone with full history to specific commit for reproducibility
            cmd = ["git", "clone", "--branch", self.git_config.branch]

            if self.git_config.sparse_paths:
                cmd.extend(["--filter=blob:none", "--sparse"])

            cmd.extend([self.git_config.clone_url, str(self.source_dir)])
            await self._run_command(cmd)

            # Checkout specific commit
            await self._run_command(
                ["git", "checkout", self.git_config.commit],
                cwd=self.source_dir,
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

            cmd.extend([self.git_config.clone_url, str(self.source_dir)])
            await self._run_command(cmd)

        if self.git_config.sparse_paths:
            await self._setup_sparse_checkout()

    async def _setup_sparse_checkout(self) -> None:
        """Configure sparse checkout for the repository."""
        cmd = ["git", "sparse-checkout", "set", "--no-cone"]
        cmd.extend(self.git_config.sparse_paths)
        await self._run_command(cmd, cwd=self.source_dir)

    async def _pull(self) -> None:
        """Pull latest changes."""
        cmd = ["git", "pull", "--depth", str(self.git_config.depth)]
        await self._run_command(cmd, cwd=self.source_dir)

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
        """Scan the repository for media files."""
        items: list[MediaItem] = []

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
