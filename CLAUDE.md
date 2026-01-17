# StagVault - Development Guidelines

## Project Overview

StagVault is an accessible media database for vector files, images, audio, textures, and other media assets. It provides unified access to multiple open-source media repositories with proper license tracking.

## Tech Stack

- **Python**: 3.13 with Poetry for dependency management
- **API Server**: FastAPI (optional deployment)
- **Static Deployment**: Pure file access via any HTTP server + JavaScript
- **Search**: Local search index (SQLite FTS5 or similar) for fast name/topic lookup
- **Data Format**: JSON for metadata, configuration files in YAML

## Project Structure

```
stagvault/
├── stagvault/              # Python package
│   ├── __init__.py
│   ├── models/             # Data models (Pydantic)
│   │   ├── media.py        # MediaItem, License, Source
│   │   ├── config.py       # SourceConfig models
│   │   └── metadata.py     # ItemMetadata, SourceMetadataIndex
│   ├── sources/            # Source handlers
│   │   ├── base.py         # Abstract base source
│   │   ├── git.py          # Git clone handler
│   │   └── api.py          # API access handler
│   ├── search/             # Search functionality
│   │   ├── indexer.py      # Index builder
│   │   └── query.py        # Search queries
│   ├── api/                # FastAPI routes
│   │   └── routes.py
│   └── cli.py              # CLI commands
├── configs/                # Source configurations (YAML)
│   └── sources/            # One file per source
├── scripts/                # Utility scripts
│   ├── lock_commits.py     # Lock git commit IDs
│   ├── fetch_emoji_descriptions.py
│   ├── init_metadata.py    # Initialize metadata folders
│   └── add_metadata.py     # Add item descriptions
├── data/                   # Downloaded media (git-ignored)
│   └── .gitkeep
├── index/                  # Search index files (git-ignored)
│   └── .gitkeep
├── static/
│   ├── js/
│   │   └── stagvault.js    # JavaScript API client
│   ├── metadata/           # Per-source item descriptions
│   │   └── {source_id}/
│   │       ├── metadata.json
│   │       └── README.md
│   └── index.json          # Pre-built searchable index (git-ignored)
├── tests/
├── pyproject.toml
└── CLAUDE.md
```

## Key Concepts

### Media Items

Every media item must have:
- **id**: Unique identifier (source:path hash)
- **name**: Display name
- **canonical_name**: Base name for grouping variants (e.g., "arrow" groups arrow-thin, arrow-bold)
- **source_id**: Reference to source configuration
- **path**: Path within source
- **style**: Style variant (thin, regular, bold, fill, outline, etc.)
- **license**: License information (inherited from source or per-item)
- **description**: Optional description/tags
- **format**: File format (svg, png, mp3, etc.)

### Style Variants & Grouping

Many icon libraries provide the same icon in multiple styles (thin, light, regular, bold, fill, duotone, etc.). StagVault groups these automatically:

- **MediaGroup**: Groups items by `source_id` + `canonical_name`
- **Search returns groups by default**: An "eraser" search returns one result with all style variants
- **Style preferences**: Users can set preferred styles (e.g., prefer "regular" over "thin")
- **Variant access**: `group.get_item(style="bold")` or `group.items` for all variants

```python
# Grouped search (default) - returns MediaGroups
results = vault.search_grouped("eraser", limit=10)
for result in results:
    print(f"{result.group.canonical_name}: {result.group.styles}")
    # eraser: ['thin', 'light', 'regular', 'bold', 'fill', 'duotone']

    # Get specific style
    bold_eraser = result.group.get_item(style="bold")

# Raw search - returns individual MediaItems
results = vault.search("eraser", styles=["regular"], limit=10)
```

### Licenses

Licenses can be:
1. **Repository-level**: All items inherit from source config
2. **Per-item**: Individual license per file (stored in metadata)

License info includes:
- SPDX identifier (MIT, Apache-2.0, CC-BY-4.0, etc.)
- Attribution requirements
- Commercial use allowed
- Modification allowed
- Share-alike requirements

### Source Configurations

Each source has a YAML config in `configs/sources/`:

```yaml
id: phosphor-icons
name: Phosphor Icons
type: git  # or 'api'
git:
  repo: phosphor-icons/core
  branch: main
  commit: abc123def456...  # Locked commit for reproducibility (set by lock_commits.py)
  sparse_paths:
    - assets/
license:
  spdx: MIT
  attribution_required: false
  commercial_ok: true
paths:
  - pattern: "assets/{weight}/*.svg"
    format: svg
    tags: [icon, ui]
    style: regular  # Style variant for grouping
metadata:
  homepage: https://phosphoricons.com
  icon_count: 9000
```

## Commands

```bash
# Install dependencies
poetry install

# Sync sources (download/update)
poetry run stagvault sync [--source SOURCE_ID]

# Build search index
poetry run stagvault index

# Export static index for JS client
poetry run stagvault export --output static/index.json

# Start API server
poetry run stagvault serve --port 8000

# Search from CLI
poetry run stagvault search "arrow icon"
```

## Scripts

### Commit Locking (Reproducibility)

Lock sources to specific git commits to ensure everyone uses the same data:

```bash
# Lock all sources to current HEAD commits
python scripts/lock_commits.py

# Update all to latest commits
python scripts/lock_commits.py --update

# Verify locks match remote
python scripts/lock_commits.py --verify

# List current locks
python scripts/lock_commits.py --list

# Lock specific source
python scripts/lock_commits.py --source phosphor-icons
```

### Emoji Descriptions

Fetch descriptions for all emoji from Unicode CLDR data:

```bash
# Fetch descriptions for all emoji sources
python scripts/fetch_emoji_descriptions.py

# Update existing descriptions
python scripts/fetch_emoji_descriptions.py --update

# Specific source only
python scripts/fetch_emoji_descriptions.py --source twemoji
```

### Static Metadata Management

Each source can have per-item descriptions stored in `static/metadata/{source_id}/`:

```bash
# Initialize metadata folders for all sources
python scripts/init_metadata.py

# Add single item description
python scripts/add_metadata.py phosphor-icons arrow-right "Right arrow navigation icon" -k arrow -k navigation -c ui

# Bulk import from pipe-delimited file
python scripts/add_metadata.py phosphor-icons --file descriptions.txt
```

**Metadata file format** (`descriptions.txt`):
```
name|description|keywords(comma-sep)|category
arrow-right|Right arrow icon|arrow,direction,right|navigation
home|Home/house icon|home,house,main|navigation
```

## External API Providers

StagVault supports external image/video APIs (Pixabay, Pexels) with intelligent caching and rate limiting.

### Access Modes

Providers can be accessed in **three ways**:

1. **Pure JavaScript** (direct browser calls)
   - Requires API key in client code (use only for local/trusted environments)
   - Client-side caching via localStorage
   - Direct CORS requests to provider APIs

2. **Python** (direct usage)
   - Server-side caching (memory + SQLite)
   - Rate limit tracking
   - API keys from environment variables

3. **FastAPI Routes** (proxied through backend)
   - API keys stored server-side (recommended for production)
   - Server-side caching shared across clients
   - Single rate limit pool per API key

### Provider Configuration

API keys are stored in environment variables (never in source code):

```bash
# .env file (git-ignored)
PIXABAY_API_KEY=your_pixabay_key
PEXELS_API_KEY=your_pexels_key
```

### Rate Limits & Caching

| Provider | Rate Limit | Cache Requirement | Hotlinking |
|----------|------------|-------------------|------------|
| Pixabay  | 100/60s    | 24 hours          | Not allowed (must download) |
| Pexels   | 200/hour   | Recommended       | Allowed |

The caching system automatically:
- Respects provider-mandated cache durations (24h for Pixabay)
- Tracks rate limits via response headers (X-RateLimit-*)
- Waits automatically when rate limit is nearly exhausted
- Uses LRU eviction for memory cache

### Python Usage

```python
from stagvault.providers import PixabayProvider, PexelsProvider, ProviderCache, get_registry

# Single provider with cache
cache = ProviderCache(cache_dir=Path("./cache"))
pixabay = PixabayProvider(cache=cache)

results = await pixabay.search_images("mountains", page=1, per_page=20)
print(f"Found {results.total} images, cached: {results.cached}")

# Multi-provider search
registry = get_registry(cache_dir=Path("./cache"))
results = await registry.search_images("sunset", providers=["pixabay", "pexels"])

for provider, result in results.items():
    print(f"{provider}: {len(result.images)} images")
```

### FastAPI Integration

```python
from fastapi import FastAPI
from stagvault.providers import create_provider_router

app = FastAPI()

# Mount provider routes with custom prefix
app.include_router(create_provider_router(prefix="/api/providers"))

# Endpoints:
# GET /api/providers/                    - List providers
# GET /api/providers/search/images       - Multi-provider search
# GET /api/providers/{id}/search/images  - Single provider search
# GET /api/providers/{id}/images/{imgId} - Get specific image
# GET /api/providers/cache/stats         - Cache statistics
```

### JavaScript Usage

```javascript
import { ProviderClient } from './providers.js';

// Via FastAPI backend (recommended - API keys server-side)
const providers = new ProviderClient({ backendUrl: '/api/providers' });

// Or direct API access (requires API keys)
const providers = new ProviderClient({
    mode: 'direct',
    apiKeys: { pixabay: 'KEY', pexels: 'KEY' }
});

// Search
const results = await providers.searchImages('mountains', {
    providers: ['pixabay', 'pexels'],
    page: 1,
    perPage: 20
});

console.log(`Found ${results.total_images} images`);
console.log(`From cache: ${results.cached}`);

// Rate limit status
const rateLimit = providers.getRateLimit('pixabay');
console.log(`Remaining: ${rateLimit?.remaining}`);
```

### Adding New Providers

1. Create provider class in `stagvault/providers/{name}.py`:
   - Inherit from `APIProvider`
   - Define `ProviderConfig` with auth type, rate limits
   - Implement `search_images()`, `search_videos()`, `get_image()`
   - Parse responses to unified `ProviderImage`/`ProviderVideo` format

2. Register in `stagvault/providers/registry.py`:
   ```python
   PROVIDER_CLASSES["newprovider"] = NewProvider
   ```

3. Add JS config in `static/js/providers.js`:
   ```javascript
   PROVIDER_CONFIGS.newprovider = { id: 'newprovider', ... }
   ```

## API Design

### Python API

```python
from stagvault import StagVault
from stagvault.search.query import SearchPreferences

vault = StagVault("./data", "./configs")

# Grouped search (default) - icons grouped by name, one result per icon
prefs = SearchPreferences(preferred_styles=["regular", "outline"])
results = vault.search_grouped("arrow", tags=["icon"], limit=20, preferences=prefs)

for result in results:
    group = result.group
    print(f"{group.canonical_name} ({group.source_id})")
    print(f"  Styles: {group.styles}")
    print(f"  License: {group.items[0].get_license(vault.get_source(group.source_id).license).spdx}")

    # Get specific style variant
    regular = group.get_item(style="regular")
    print(f"  Path: {regular.path}")

# Raw search - returns individual items (all style variants)
results = vault.search("arrow", styles=["bold"], limit=20)
```

### JavaScript API (Static)

```javascript
import { StagVault } from './stagvault.js';

const vault = new StagVault('/static/index.json');
await vault.load();

// Grouped search (default)
const results = vault.searchGrouped('arrow', {
    tags: ['icon'],
    limit: 20,
    preferredStyles: ['regular', 'outline']
});

results.forEach(group => {
    console.log(`${group.canonical_name} - styles: ${group.variants.map(v => v.style).join(', ')}`);

    // Get specific variant
    const regular = group.variants.find(v => v.style === 'regular');
    console.log(`  Path: ${regular?.path}`);
});

// Raw search (individual items)
const items = vault.search('arrow', { styles: ['bold'], limit: 20 });
```

### REST API (FastAPI Router)

The API is provided as a FastAPI router that can be mounted on any existing app:

```python
from fastapi import FastAPI
from stagvault import StagVault
from stagvault.api import create_router

app = FastAPI()
vault = StagVault("./data", "./configs")

# Mount with default prefix /svault
app.include_router(create_router(vault))

# Or with custom prefix and tags
app.include_router(create_router(vault, prefix="/media-api", tags=["media"]))
```

**Endpoints (default prefix /svault):**

```
GET /svault/search?q=arrow&tags=icon&limit=20&grouped=true&preferred_styles=regular,outline
GET /svault/search?q=arrow&grouped=false&styles=bold  # Individual items
GET /svault/sources
GET /svault/sources/{source_id}
GET /svault/sources/{source_id}/styles
GET /svault/styles  # All styles across sources
GET /svault/media/{item_id}
GET /svault/media/{item_id}/file
GET /svault/groups/{source_id}/{canonical_name}  # All variants
GET /svault/stats
```

## Development Guidelines

### Adding New Sources

1. Create YAML config in `configs/sources/{source-id}.yaml`
2. Run `poetry run stagvault sync --source {source-id}`
3. Rebuild index: `poetry run stagvault index`

### Code Style

- Use type hints everywhere
- Pydantic models for data validation
- Async where beneficial (API routes, downloads)
- Keep functions focused and testable

### Testing

Tests cover 4 integration scenarios using pytest (Python) and Playwright (JavaScript):

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=stagvault

# Run specific test suites
poetry run pytest tests/test_python_api.py      # Python-to-Python
poetry run pytest tests/test_fastapi.py         # FastAPI endpoints
poetry run pytest tests/test_js_fastapi.py      # JS client via FastAPI
poetry run pytest tests/test_js_static.py       # JS client via static files
```

**Test Scenarios:**

1. **Python-to-Python** (`tests/test_python_api.py`)
   - Direct StagVault class usage
   - Search (grouped and ungrouped)
   - Source/config loading
   - Index building and querying
   - Metadata loading

2. **FastAPI Endpoints** (`tests/test_fastapi.py`)
   - All `/svault/*` endpoints
   - Search with filters and pagination
   - Source listing and details
   - Media item retrieval
   - File serving

3. **JavaScript via FastAPI** (`tests/test_js_fastapi.py`)
   - Playwright tests running `stagvault.js` against live FastAPI server
   - Search functionality (grouped/ungrouped)
   - Style preferences
   - Source/variant listing

4. **JavaScript via Static Hosting** (`tests/test_js_static.py`)
   - Playwright tests running `stagvault.js` against static `index.json`
   - Client-side search without backend
   - Verifies static deployment scenario

**Test Fixtures:**
- `tests/fixtures/` - Sample source configs and test data
- `tests/conftest.py` - Shared pytest fixtures (vault instance, FastAPI test client, Playwright browser)

### License Compliance

- Always preserve license information
- Include attribution when required
- Document any share-alike requirements
- Never strip license metadata from files

## Initial Sources (Recommended)

Based on the icon datasets summary, prioritize:

1. **phosphor-icons** - MIT, 9000 icons, 6 weights
2. **lucide** - ISC, 1500 icons, clean
3. **material-design** - Apache 2.0, 7000 icons
4. **tabler-icons** - MIT, 5000 icons
5. **simple-icons** - CC0, 3000 brand icons
6. **noto-emoji** - OFL 1.1, full Unicode emoji

## File Locations

- Source configs: `configs/sources/*.yaml`
- Downloaded data: `data/{source-id}/` (git-ignored)
- Search index: `index/stagvault.db` (git-ignored)
- Static export: `static/index.json`
