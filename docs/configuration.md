# Configuration Reference

## Source Configuration Schema

All sources are configured via YAML files in `configs/sources/`.

### Common Fields

```yaml
id: string          # Unique identifier (required)
name: string        # Display name (required)
description: string # Brief description
type: git | api     # Source type (required)
```

### Git Sources

For cloning icon/asset repositories:

```yaml
type: git

git:
  repo: owner/repo          # GitHub repo (required)
  branch: main              # Branch name
  commit: abc123...         # Locked commit hash
  depth: 1                  # Clone depth
  sparse_paths:             # Paths for sparse checkout
    - src/
    - assets/

license:
  spdx: MIT                 # SPDX identifier (required)
  attribution_required: false
  commercial_ok: true
  modification_ok: true
  share_alike: false

paths:                      # File patterns to index
  - pattern: "src/**/*.svg"
    format: svg
    tags: [icon, ui]
    style: regular          # Style variant name
    size: 24                # Additional metadata

metadata:
  homepage: https://example.com
  icon_count: 1000
  styles: [outline, solid]
```

### API Sources

For external media providers:

```yaml
type: api

api:
  base_url: https://api.example.com/
  auth_type: query_param | header | bearer
  auth_param: key           # Param/header name
  auth_prefix: "Client-ID " # Optional prefix for header
  api_key_env: API_KEY_VAR  # Environment variable name

  rate_limit:
    requests: 100           # Max requests per window
    window_seconds: 60      # Window duration

  cache_duration: 86400     # Cache TTL in seconds

  endpoints:
    search_images: /search
    search_videos: /videos/search

license:
  name: Provider License
  url: https://example.com/license
  terms_url: https://example.com/terms
  attribution_required: true
  commercial_ok: true

restrictions:
  hotlink_allowed: true     # Can link directly to images
  no_ads_alongside: false   # Ads restriction
  no_resale: true           # Cannot sell images
  no_database: true         # Cannot build competing DB
  download_required: false  # Must download vs hotlink
  download_trigger_required: false  # Must call download endpoint

tier: standard | restricted # Provider tier

capabilities:
  images: true
  videos: false
  vectors: false
  illustrations: false

metadata:
  homepage: https://example.com
  api_docs: https://example.com/docs
```

## Provider Tiers

| Tier | Meaning | Default Search Behavior |
|------|---------|------------------------|
| `standard` | Normal rate limits, reasonable terms | Included |
| `restricted` | Low limits or strict requirements | Excluded |

## Environment Variables

API keys should be stored in `.env` (git-ignored):

```bash
# .env
PIXABAY_API_KEY=your_key
PEXELS_API_KEY=your_key
UNSPLASH_API_KEY=your_key
```

Load with python-dotenv or export directly:

```bash
export $(cat .env | xargs)
```

## Validation

Source configs are validated with Pydantic models on load. Invalid configs will raise errors with specific field information.

```python
from stagvault.models.source import SourceConfig
from pathlib import Path

config = SourceConfig.from_yaml(Path("configs/sources/pixabay.yaml"))
```
