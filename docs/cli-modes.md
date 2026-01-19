# CLI Testing Modes

StagVault maintains a CLI that can be tested in three different modes to ensure consistent behavior across all access methods.

## Overview

| Mode | Backend | Dynamic Sources | Use Case |
|------|---------|-----------------|----------|
| Python | Direct API | Yes | Development, full features |
| REST | FastAPI | Yes | API testing, production |
| Static | JSON files | No | Offline, static hosting |

## Mode 1: Python API (Direct)

Uses the StagVault Python API directly without any network layer.

**Characteristics:**
- No network overhead
- Full feature access including dynamic API providers (Pexels, Pixabay, Unsplash)
- Direct access to all internal methods
- Best for development and scripting

**Usage:**
```bash
stagvault search "arrow" --mode python
stagvault search "grinning face" --mode python --source noto-emoji
```

**Python equivalent:**
```python
from stagvault import StagVault

vault = StagVault("./data", "./configs")
results = vault.search("arrow", limit=20)
```

## Mode 2: REST API (FastAPI)

Tests the FastAPI endpoints, validating the full API contract.

**Characteristics:**
- Full HTTP request/response cycle
- Tests serialization and API contracts
- Includes dynamic providers (Pexels, Pixabay, Unsplash)
- Validates production deployment behavior

**Usage:**
```bash
stagvault search "arrow" --mode rest
stagvault search "sunset" --mode rest --source pixabay
```

**Equivalent REST call:**
```bash
curl "http://localhost:8000/svault/search?q=arrow&limit=20"
```

## Mode 3: Static Mode

Uses the exact same JSON files and search behavior as the static website.

**Characteristics:**
- Uses precomputed JSON index files
- Client-side filtering only
- **NO dynamic sources** (git sources only)
- Validates static deployment parity with web app

**Usage:**
```bash
stagvault search "arrow" --mode static
stagvault search "battery" --mode static --source heroicons
```

**Supported sources in static mode:**
- phosphor-icons
- lucide
- heroicons
- tabler-icons
- feather
- noto-emoji

**NOT supported in static mode:**
- Pexels (requires API key)
- Pixabay (requires API key)
- Unsplash (requires API key)

## CLI Commands with Mode Selection

### Search

```bash
# Default mode (python)
stagvault search "arrow"

# Explicit mode selection
stagvault search "arrow" --mode python
stagvault search "arrow" --mode rest
stagvault search "arrow" --mode static

# With filters
stagvault search "arrow" --mode static --source phosphor-icons --license MIT
```

### Source and License Filtering

All modes support the same filtering options:

```bash
# Include specific sources
stagvault search "arrow" --source phosphor-icons --source lucide

# Exclude sources
stagvault search "arrow" --exclude-source heroicons

# Filter by license
stagvault search "arrow" --license MIT

# Exclude license
stagvault search "arrow" --exclude-license GPL-3.0

# Combine filters
stagvault search "arrow" -s phosphor-icons --license MIT --mode static
```

## Behavior Parity

All three modes MUST produce identical results for the same query and filters (excluding dynamic sources in static mode). This is enforced by the test suite.

**Expected behavior examples:**
- Search "US" → US flag (waved and flat variants) as top results
- Search "DE" → German flag (waved and flat variants) as top results
- Search "arrow" → arrow icons from all sources, sorted by relevance

## When to Use Each Mode

| Scenario | Recommended Mode |
|----------|------------------|
| Local development | Python |
| Testing API contracts | REST |
| Testing static deployment | Static |
| CI/CD pipeline | All three |
| Production debugging | REST |
| Offline usage | Static |
