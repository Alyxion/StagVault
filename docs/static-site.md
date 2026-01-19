# Static Site Architecture

The static site provides offline-capable search without a backend server, using only precomputed JSON files and client-side JavaScript.

## Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Browser       │────▶│   Static Files   │────▶│   JSON Index    │
│   (app.js)      │     │   (HTTP server)  │     │   (search/)     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

No backend required - any HTTP server (nginx, Apache, GitHub Pages, S3) can serve the static site.

## Supported Sources

**Git sources only** - precomputed at build time:

| Source | Items | License |
|--------|-------|---------|
| phosphor-icons | 9,072 | MIT |
| tabler-icons | 5,986 | MIT |
| lucide | 1,667 | ISC |
| heroicons | 1,288 | MIT |
| feather | 287 | MIT |
| noto-emoji | 3,645 | OFL-1.1 |

**NOT supported in static mode:**

| Source | Reason |
|--------|--------|
| Pexels | Requires API key at runtime |
| Pixabay | Requires API key at runtime |
| Unsplash | Requires API key at runtime |

Dynamic API providers require a backend to proxy requests and manage API keys.

## Data Files

All data is precomputed as JSON:

```
static_site/index/
├── sources.json          # Source metadata with counts
├── licenses.json         # License types with counts
├── tags.json             # All tags with counts (1600+)
├── meta.json             # Index metadata and stats
├── search/               # Prefix-based search index
│   ├── ar.json          # Items matching "ar*"
│   ├── ba.json          # Items matching "ba*"
│   ├── ...              # ~700 prefix files
│   └── zz.json
└── thumbs/               # Thumbnail images
    └── {source_id}/
        └── {prefix}/
            └── {id}_64.jpg
```

### File Descriptions

| File | Size | Purpose |
|------|------|---------|
| `sources.json` | ~1KB | Source list with counts, licenses, tree structure |
| `licenses.json` | ~100B | License types with item counts |
| `tags.json` | ~80KB | All tags with counts for filtering |
| `meta.json` | ~200B | Build metadata (version, timestamp, stats) |
| `search/*.json` | ~50MB total | 700 prefix-based search files |

### Search Index Format

Each prefix file (`search/{prefix}.json`) contains items matching that prefix:

```json
[
  {
    "id": "ce0c31aeee067681",
    "n": "battery-100",
    "s": "heroicons",
    "t": ["icon", "ui", "outline"],
    "p": "thumbs/heroicons/ce/ce0c31aeee067681_64.jpg",
    "y": "outline",
    "l": "MIT"
  }
]
```

**Field key:**
- `id` - Unique item ID
- `n` - Name (display name)
- `s` - Source ID
- `t` - Tags array
- `p` - Preview/thumbnail path
- `y` - Style variant
- `l` - License (optional, inherits from source if missing)

## Search Algorithm

### Prefix Extraction

When building the index, 2-character prefixes are extracted from:
- Item name (`battery-100` → `ba`, `at`, `tt`, `te`, `er`, `ry`, `10`, `00`)
- Tags (`icon` → `ic`, `co`, `on`)
- Aliases (`grinning face` → `gr`, `ri`, `in`, `nn`, `ni`, `ng`, `fa`, `ac`, `ce`)

### Search Flow

1. User types query: `"arrow"`
2. Extract prefix: `"ar"`
3. Fetch `search/ar.json`
4. Filter results client-side by:
   - Full text match
   - Selected sources
   - Selected licenses
5. Sort by relevance
6. Display results

### Multi-word Search

For multi-word queries like `"arrow outline"`:
1. Extract prefixes: `ar`, `ou`
2. Fetch both `search/ar.json` and `search/ou.json`
3. Intersect results (items must match both)
4. Apply filters and display

## Python/JS Parity

The filtering logic MUST behave identically between:

| Aspect | Python | JavaScript |
|--------|--------|------------|
| Exclusion mode | `excludedSources` set | `excludedSources` Set |
| Source tree | 2-level hierarchy | 2-level hierarchy |
| License filter | Flat list | Flat list |
| Search ranking | Prefix match | Prefix match |

This parity is enforced by the test suite running identical queries in all three modes (Python, REST, Static).

## Building the Static Site

### Prerequisites

Before building the static site, you need:

1. **Synced data**: Download source files
   ```bash
   poetry run stagvault sync
   ```

2. **Built index**: Create search database
   ```bash
   poetry run stagvault index
   ```

3. **Generated thumbnails** (optional): Create preview images
   ```bash
   poetry run stagvault thumbnails generate
   ```

### Build Commands

```bash
# Quick build (no thumbnails - icons won't show preview images)
poetry run stagvault static build --output ./static_site/index

# Full build with thumbnails (recommended)
poetry run stagvault static build --output ./static_site/index --thumbnails

# Or use the convenience script
./scripts/build_static.sh           # Quick build
./scripts/build_static.sh --thumbs  # With existing thumbnails
./scripts/build_static.sh --full    # Generate thumbnails + build
```

### Source Files

The web application source files are tracked in git:
- `stagvault/static/web/app.js` - JavaScript application
- `stagvault/static/web/index.html` - HTML template

These are automatically copied to the output directory during build.

### Generated Files (gitignored)

The entire `static_site/` directory is generated and gitignored:
- `static_site/index/app.js` - Copied from source
- `static_site/index/index.html` - Copied from source
- `static_site/index/index/*.json` - Generated index files
- `static_site/index/index/search/*.json` - Generated search files
- `static_site/index/thumbs/` - Generated thumbnails

## Serving the Static Site

### Development

```bash
# Built-in server with CORS headers
stagvault static serve --port 8080

# Or use any HTTP server
python -m http.server 8080 --directory static_site
npx serve static_site
```

### Production

Deploy to any static hosting:
- GitHub Pages
- Netlify
- Vercel
- AWS S3 + CloudFront
- nginx / Apache

Example nginx config:
```nginx
server {
    listen 80;
    root /var/www/stagvault;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /search/ {
        add_header Cache-Control "public, max-age=86400";
    }

    location /thumbs/ {
        add_header Cache-Control "public, max-age=604800";
    }
}
```

## Limitations

1. **No dynamic sources**: Pexels, Pixabay, Unsplash require backend
2. **No real-time updates**: Index is built at deploy time
3. **Initial load size**: ~80KB for tags.json + search prefix files on demand
4. **No server-side filtering**: All filtering happens in browser

## When to Use Static vs REST

| Use Case | Recommendation |
|----------|----------------|
| Public demo | Static |
| Offline usage | Static |
| Full feature access | REST |
| Dynamic sources | REST |
| CDN-friendly deployment | Static |
| Real-time index updates | REST |
