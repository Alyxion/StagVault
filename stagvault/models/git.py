"""Git repository configuration model."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GitConfig(BaseModel):
    """Git repository configuration."""

    repo: str = Field(..., description="GitHub repo in format owner/repo")
    branch: str = Field(default="main")
    commit: str | None = Field(default=None, description="Locked commit hash for reproducibility")
    depth: int = Field(default=1, description="Clone depth (1 for shallow)")
    sparse_paths: list[str] = Field(
        default_factory=list, description="Paths for sparse checkout"
    )

    @property
    def clone_url(self) -> str:
        """Get the full clone URL."""
        return f"https://github.com/{self.repo}.git"
