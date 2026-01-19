# Project Structure

## Directory Layout

```
stagvault/
├── stagvault/              # Main Python package
│   ├── models/             # Data models (Pydantic)
│   ├── sources/            # Source handlers (git, api)
│   ├── search/             # Search/indexing
│   ├── providers/          # External API providers
│   └── api/                # FastAPI routes
├── configs/
│   └── sources/            # YAML source configurations
├── docs/                   # Documentation
├── tests/                  # Test suite
├── scripts/                # Utility scripts
├── static/                 # Static assets
│   ├── js/                 # JavaScript clients
│   └── metadata/           # Per-source descriptions
├── data/                   # Downloaded media (git-ignored)
├── index/                  # Search index (git-ignored)
└── cache/                  # Provider cache (git-ignored)
```

## Configuration Files

### Source Configurations (`configs/sources/*.yaml`)

Two types of sources:

#### Git Sources (icon libraries, assets)
```yaml
id: heroicons
name: Heroicons
type: git

git:
  repo: tailwindlabs/heroicons
  branch: master
  commit: abc123...     # Locked for reproducibility
  sparse_paths: [src/]

license:
  spdx: MIT
  attribution_required: false
  commercial_ok: true

paths:
  - pattern: "src/24/outline/*.svg"
    format: svg
    tags: [icon, ui, outline]
```

#### API Sources (external providers)
```yaml
id: pixabay
name: Pixabay
type: api

api:
  base_url: https://pixabay.com/api/
  auth_type: query_param
  api_key_env: PIXABAY_API_KEY
  rate_limit:
    requests: 100
    window_seconds: 60

license:
  name: Pixabay License
  url: https://pixabay.com/service/license-summary/
  terms_url: https://pixabay.com/service/terms/

tier: standard  # or "restricted" for low-limit providers

restrictions:
  hotlink_allowed: false
  no_ads_alongside: false
  no_resale: true
```

## Interface Types

### Models (`stagvault/models/`)

| Model | Purpose |
|-------|---------|
| `MediaItem` | Single media file with metadata |
| `MediaGroup` | Collection of style variants |
| `License` | License information (SPDX, restrictions) |
| `Source` | Media source definition |
| `SourceConfig` | Full source configuration from YAML |

### Provider Interfaces (`stagvault/providers/`)

| Interface | Purpose |
|-----------|---------|
| `APIProvider` | Base class for external APIs |
| `ProviderConfig` | Provider settings (auth, rate limits) |
| `ProviderImage` | Normalized image result |
| `ProviderVideo` | Normalized video result |
| `ProviderResult` | Search results container |
| `RateLimitInfo` | Rate limit tracking |
| `ProviderCache` | Dual-layer cache (memory + disk) |

### Provider Tiers

| Tier | Description | Default Behavior |
|------|-------------|------------------|
| `standard` | Reasonable rate limits | Included in broad searches |
| `restricted` | Low limits or strict terms | Excluded from broad searches |

Restricted providers require explicit selection to avoid exhausting rate limits.

## Key Files

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Development guidelines |
| `pyproject.toml` | Python dependencies (Poetry) |
| `.env` | API keys (git-ignored) |
| `static/index.json` | Pre-built search index |
