# Source Management

StagVault supports managing multiple data sources - both git-based icon libraries and API providers.

## Source Types

### Git Sources

Local icon/asset repositories cloned from GitHub:

- **Examples**: Heroicons, Tabler Icons, Phosphor Icons
- **Storage**: Cloned to `data/{source_id}/`
- **Thumbnails**: Generated automatically during sync

### API Sources

External media providers accessed via API:

- **Examples**: Pixabay, Pexels, Unsplash
- **Storage**: No local storage (cached responses only)
- **Thumbnails**: Provider supplies preview URLs

## Source Status

| Status | Description |
|--------|-------------|
| `available` | Config exists, data not synced |
| `installed` | Config exists, data synced |
| `partial` | Partially synced or outdated |

## CLI Commands

### List Sources

```bash
# List all configured sources
stagvault sources list

# Only installed sources (have data)
stagvault sources list --installed

# Only available sources (not synced)
stagvault sources list --available
```

Output:
```
┏━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ ID            ┃ Name           ┃ Type  ┃ Status    ┃ Items ┃ Thumbnails ┃ Disk Usage ┃
┡━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ heroicons     │ Heroicons      │ git   │ installed │ 592   │ 4736       │ 2.3 MB     │
│ tabler-icons  │ Tabler Icons   │ git   │ installed │ 4500  │ 36000      │ 15.2 MB    │
│ pixabay       │ Pixabay        │ api   │ installed │ -     │ -          │ N/A        │
│ unsplash      │ Unsplash       │ api   │ available │ -     │ -          │ N/A        │
└───────────────┴────────────────┴───────┴───────────┴───────┴────────────┴────────────┘
```

### Add/Install a Source

```bash
# Add source, sync data, and generate thumbnails
stagvault sources add heroicons

# Add without syncing (just register)
stagvault sources add heroicons --no-sync

# Add without generating thumbnails
stagvault sources add heroicons --no-thumbnails
```

### Remove a Source

```bash
# Remove source data (keep config)
stagvault sources remove heroicons

# Remove data AND config file
stagvault sources remove heroicons --purge

# Skip confirmation
stagvault sources remove heroicons -y
```

### View Source Details

```bash
stagvault sources info heroicons
```

Output:
```
Heroicons (heroicons)
  Type: git
  Status: installed
  Description: Beautiful hand-crafted SVG icons
  Homepage: https://heroicons.com
  Items: 592
  Thumbnails: 4736
  Disk usage: 2.3 MB
  Last synced: 2024-01-15T10:30:00
```

## Library Interface

### List Sources

```python
from stagvault import StagVault
from stagvault.models.source_info import SourceStatus

vault = StagVault("./data", "./configs")

# All sources
sources = vault.list_sources()

# Only installed sources
installed = vault.list_sources(status=SourceStatus.INSTALLED)

# Only available sources
available = vault.list_sources(status=SourceStatus.AVAILABLE)
```

### Get Source Info

```python
info = vault.get_source_info("heroicons")

print(f"Name: {info.name}")
print(f"Status: {info.status.value}")
print(f"Items: {info.item_count}")
print(f"Thumbnails: {info.thumbnail_count}")
print(f"Disk usage: {info.disk_usage_formatted}")
```

### Add a Source

```python
# Add with sync and thumbnails
info = await vault.add_source("heroicons")

# Add without sync
info = await vault.add_source("heroicons", sync=False)

# Add without thumbnails
info = await vault.add_source("heroicons", thumbnails=False)
```

### Remove a Source

```python
# Remove data only
await vault.remove_source("heroicons")

# Remove data and config
await vault.remove_source("heroicons", purge_config=True)
```

## SourceInfo Model

```python
class SourceInfo(BaseModel):
    id: str                           # Unique identifier
    name: str                         # Display name
    source_type: str                  # "git" or "api"
    status: SourceStatus              # available, installed, partial
    item_count: int | None            # Number of indexed items
    thumbnail_count: int | None       # Number of thumbnails (git only)
    disk_usage_bytes: int | None      # Total disk usage
    last_synced: datetime | None      # Last sync timestamp
    description: str | None           # Source description
    homepage: str | None              # Source homepage URL

    @property
    def is_installed(self) -> bool: ...
    @property
    def is_git_source(self) -> bool: ...
    @property
    def is_api_source(self) -> bool: ...
    @property
    def disk_usage_formatted(self) -> str: ...
```

## Storage Layout

```
data/
├── heroicons/                    # Git source data
│   ├── .git/
│   └── src/
│       └── *.svg
├── tabler-icons/                 # Git source data
│   └── ...
├── thumbnails/                   # Generated thumbnails
│   ├── thumbnails.db
│   ├── heroicons/
│   └── tabler-icons/
└── index/                        # Search index
    └── stagvault.db

configs/
└── sources/
    ├── heroicons.yaml
    ├── tabler-icons.yaml
    ├── pixabay.yaml
    └── unsplash.yaml
```

## Adding Custom Sources

Create a YAML config in `configs/sources/`:

### Git Source Example

```yaml
id: my-icons
name: My Custom Icons
description: Custom icon set
type: git

git:
  repo: username/my-icons
  branch: main
  depth: 1

license:
  spdx: MIT
  attribution_required: false
  commercial_ok: true

paths:
  - pattern: "icons/**/*.svg"
    format: svg
    tags: [icon, custom]

metadata:
  homepage: https://github.com/username/my-icons
```

### API Source Example

```yaml
id: my-api
name: My API Provider
type: api

api:
  base_url: https://api.example.com/
  auth_type: header
  auth_param: Authorization
  auth_prefix: "Bearer "
  api_key_env: MY_API_KEY
  rate_limit:
    requests: 100
    window_seconds: 60

license:
  name: Provider License
  url: https://example.com/license
  attribution_required: true

tier: standard

capabilities:
  images: true
  vectors: false

metadata:
  homepage: https://example.com
  api_docs: https://example.com/docs
```

## Best Practices

1. **Start with a few sources**: Don't sync everything at once
2. **Use specific sources for searches**: `vault.search("arrow", source_id="heroicons")`
3. **Remove unused sources**: Free up disk space with `sources remove`
4. **Keep configs in version control**: Store `configs/` in your repository
5. **Use `.env` for API keys**: Never commit API keys to version control
