"""Tests for source configuration parsing."""

from __future__ import annotations

from pathlib import Path

import pytest

from stagvault.models.provider import (
    ProviderCapabilities,
    ProviderRestrictions,
    ProviderTier,
)
from stagvault.models.source import SourceConfig


class TestSourceConfigParsing:
    """Tests for parsing source YAML configurations."""

    @pytest.fixture
    def configs_dir(self) -> Path:
        return Path("configs/sources")

    def test_load_pixabay_config(self, configs_dir: Path):
        """Test loading Pixabay provider config."""
        config = SourceConfig.from_yaml(configs_dir / "pixabay.yaml")

        assert config.id == "pixabay"
        assert config.name == "Pixabay"
        assert config.source_type == "api"
        assert config.is_api_provider is True
        assert config.tier == ProviderTier.STANDARD

        # API config
        assert config.api is not None
        assert config.api.base_url == "https://pixabay.com/api/"
        assert config.api.auth_type == "query_param"
        assert config.api.api_key_env == "PIXABAY_API_KEY"
        assert config.api.rate_limit.requests == 100
        assert config.api.rate_limit.window_seconds == 60

        # License
        assert config.license.name == "Pixabay License"
        assert config.license.url is not None
        assert config.license.terms_url is not None
        assert config.license.attribution_required is False

        # Restrictions
        assert config.restrictions is not None
        assert config.restrictions.hotlink_allowed is False
        assert config.restrictions.no_resale is True

        # Capabilities
        assert config.capabilities is not None
        assert config.capabilities.images is True
        assert config.capabilities.videos is True

    def test_load_pexels_config(self, configs_dir: Path):
        """Test loading Pexels provider config."""
        config = SourceConfig.from_yaml(configs_dir / "pexels.yaml")

        assert config.id == "pexels"
        assert config.name == "Pexels"
        assert config.source_type == "api"
        assert config.tier == ProviderTier.STANDARD

        assert config.api.base_url == "https://api.pexels.com/v1/"
        assert config.api.auth_type == "header"
        assert config.api.rate_limit.requests == 200
        assert config.api.rate_limit.window_seconds == 3600

        assert config.restrictions.hotlink_allowed is True

    def test_load_unsplash_config(self, configs_dir: Path):
        """Test loading Unsplash provider config."""
        config = SourceConfig.from_yaml(configs_dir / "unsplash.yaml")

        assert config.id == "unsplash"
        assert config.name == "Unsplash"
        assert config.source_type == "api"
        assert config.tier == ProviderTier.RESTRICTED

        assert config.api.rate_limit.requests == 50
        assert config.api.rate_limit.window_seconds == 3600

        assert config.license.attribution_required is True
        assert config.restrictions.no_ads_alongside is True
        assert config.capabilities.videos is False

    def test_load_all_provider_configs(self, configs_dir: Path):
        """Test loading all provider configs."""
        provider_files = ["pixabay.yaml", "pexels.yaml", "unsplash.yaml"]

        for filename in provider_files:
            config = SourceConfig.from_yaml(configs_dir / filename)
            assert config.is_api_provider is True
            assert config.api is not None
            assert config.api.api_key_env is not None

    def test_git_source_not_api_provider(self, configs_dir: Path):
        """Test that git sources are not API providers."""
        config = SourceConfig.from_yaml(configs_dir / "heroicons.yaml")

        assert config.source_type == "git"
        assert config.is_git_source is True
        assert config.is_api_provider is False
        assert config.git is not None
        assert config.api is None


class TestProviderTier:
    """Tests for ProviderTier enum."""

    def test_enum_values(self):
        assert ProviderTier.STANDARD.value == "standard"
        assert ProviderTier.RESTRICTED.value == "restricted"


class TestProviderRestrictions:
    """Tests for ProviderRestrictions model."""

    def test_defaults(self):
        restrictions = ProviderRestrictions()

        assert restrictions.hotlink_allowed is False
        assert restrictions.no_ads_alongside is False
        assert restrictions.no_resale is True
        assert restrictions.no_database is True


class TestProviderCapabilities:
    """Tests for ProviderCapabilities model."""

    def test_defaults(self):
        capabilities = ProviderCapabilities()

        assert capabilities.images is True
        assert capabilities.videos is False
        assert capabilities.vectors is False
