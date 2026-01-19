"""Source configuration models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from stagvault.models.archive import ArchiveConfig
from stagvault.models.git import GitConfig
from stagvault.models.media import License
from stagvault.models.provider import (
    ApiConfig,
    ProviderCapabilities,
    ProviderRestrictions,
    ProviderTier,
)


class LicenseOverride(BaseModel):
    """License override for specific paths within a source.

    Allows assigning different licenses to subsets of files.
    Example: flags might be public domain while other emojis are OFL.
    """

    pattern: str = Field(..., description="Glob pattern or path prefix to match")
    license: License = Field(..., description="License to apply to matching files")

    model_config = {"extra": "forbid"}


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
    api_docs: str | None = None
    icon_count: int | None = None
    styles: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    sizes: list[int] = Field(default_factory=list)
    size_estimate_mb: int | None = None

    model_config = {"extra": "allow"}


class SourceConfig(BaseModel):
    """Complete source configuration.

    Supports both git sources (icon libraries) and API sources (providers).
    """

    id: str = Field(..., description="Unique source identifier")
    name: str = Field(..., description="Display name")
    description: str | None = None
    source_type: str = Field(..., alias="type")

    # Git source config
    git: GitConfig | None = None
    paths: list[PathConfig] = Field(default_factory=list)

    # Archive source config
    archive: ArchiveConfig | None = None

    # API provider config
    api: ApiConfig | None = None
    restrictions: ProviderRestrictions | None = None
    capabilities: ProviderCapabilities | None = None
    tier: ProviderTier = Field(default=ProviderTier.STANDARD, description="Provider tier")

    # Common fields
    license: License
    license_overrides: list[LicenseOverride] = Field(
        default_factory=list,
        description="Per-path license overrides (pattern + license pairs)"
    )
    metadata: SourceMetadata = Field(default_factory=SourceMetadata)

    model_config = {"populate_by_name": True}

    @property
    def is_api_provider(self) -> bool:
        """Check if this is an API provider source."""
        return self.source_type == "api" and self.api is not None

    @property
    def is_git_source(self) -> bool:
        """Check if this is a git source."""
        return self.source_type == "git" and self.git is not None

    @property
    def is_archive_source(self) -> bool:
        """Check if this is an archive source."""
        return self.source_type == "archive" and self.archive is not None

    def get_license_for_path(self, path: str) -> License:
        """Get the license for a given file path.

        Checks license_overrides first (in order), then falls back to default license.
        Supports glob patterns and simple prefix matching.
        """
        from fnmatch import fnmatch

        for override in self.license_overrides:
            pattern = override.pattern
            # Try glob matching first
            if fnmatch(path, pattern):
                return override.license
            # Also try prefix matching (for subgroup patterns like "country-flag")
            if path.startswith(pattern) or pattern in path:
                return override.license
        return self.license

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
