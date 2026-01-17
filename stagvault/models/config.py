"""Configuration models for sources."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from stagvault.models.media import License


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


class ApiConfig(BaseModel):
    """API source configuration."""

    base_url: str = Field(..., description="Base URL for API")
    auth_type: str | None = Field(default=None, description="Authentication type")
    endpoints: dict[str, str] = Field(default_factory=dict)


class PathConfig(BaseModel):
    """Configuration for a path pattern within a source."""

    pattern: str = Field(..., description="Glob pattern for files")
    format: str = Field(..., description="File format (svg, png, etc.)")
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class SourceMetadata(BaseModel):
    """Optional metadata about a source."""

    homepage: str | None = None
    icon_count: int | None = None
    styles: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    size_estimate_mb: int | None = None

    model_config = {"extra": "allow"}


class SourceConfig(BaseModel):
    """Complete source configuration."""

    id: str = Field(..., description="Unique source identifier")
    name: str = Field(..., description="Display name")
    description: str | None = None
    source_type: str = Field(..., alias="type")
    git: GitConfig | None = None
    api: ApiConfig | None = None
    license: License
    paths: list[PathConfig] = Field(default_factory=list)
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)

    model_config = {"populate_by_name": True}

    @classmethod
    def from_yaml(cls, path: Path) -> "SourceConfig":
        """Load source configuration from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    @classmethod
    def load_all(cls, config_dir: Path) -> dict[str, "SourceConfig"]:
        """Load all source configurations from a directory."""
        configs: dict[str, SourceConfig] = {}
        sources_dir = config_dir / "sources"
        if sources_dir.exists():
            for yaml_file in sources_dir.glob("*.yaml"):
                config = cls.from_yaml(yaml_file)
                configs[config.id] = config
        return configs
