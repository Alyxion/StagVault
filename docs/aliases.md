# Alias System

The alias system provides a generic way to map file identifiers (filenames, IDs, codepoints) to human-readable names, search aliases, and additional metadata. This is source-agnostic and can be used for any media source.

## Overview

Many media sources use technical identifiers as filenames that aren't human-friendly:
- **Emojis**: `emoji_u1f600.svg` (Unicode codepoint) → "grinning face"
- **Icons**: `ic_action_done_24px.svg` → "done", "check", "complete"
- **Stock photos**: `pexels-12345.jpg` → "sunset over mountains"

The alias system decouples name resolution from source handlers, keeping handlers simple and focused on file discovery.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Source Handler │────▶│   Alias Loader   │────▶│  Search Index   │
│   (git.py)      │     │  (aliases.py)    │     │  (indexer.py)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │
        │ MediaItem              │ AliasEntry
        │ (path, raw name)       │ (display_name, aliases, tags)
        ▼                        ▼
   Files on disk            Alias databases
                           (JSON, YAML, etc.)
```

**Key principle**: Source handlers know nothing about aliases. They return raw `MediaItem` objects with filenames as names. The `AliasLoader` enriches items with human-readable names during indexing.

## Alias Database Format

Alias databases are JSON files mapping identifiers to metadata:

```json
{
  "1F600": {
    "name": "grinning face",
    "aliases": ["grin", "smile", "happy"],
    "group": "Smileys & Emotion",
    "subgroup": "face-smiling",
    "tags": ["emotion", "positive"]
  },
  "1F1FA_1F1F8": {
    "name": "flag: United States",
    "aliases": ["us", "usa", "american flag"],
    "group": "Flags",
    "subgroup": "country-flag",
    "tags": ["country", "north america"],
    "country_code": "US"
  }
}
```

### Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Display name shown in search results |
| `aliases` | No | Alternative search terms (all searchable) |
| `group` | No | High-level category |
| `subgroup` | No | Subcategory (becomes `category` tag if set) |
| `tags` | No | Additional searchable tags |
| `*` | No | Any extra fields preserved in metadata |

## Configuration

Alias databases are configured per-source in the YAML config:

```yaml
id: noto-emoji
name: Noto Emoji
type: git

git:
  repo: googlefonts/noto-emoji
  # ...

# Alias configuration
aliases:
  # Path to alias database (relative to project root or absolute)
  database: stagvault/data/emojis/emoji_db.json

  # How to extract the lookup key from filenames
  key_pattern: "emoji_u(?P<key>[0-9a-fA-F_]+)"
  key_transform: uppercase  # none, lowercase, uppercase

  # Optional: different databases for different path patterns
  databases:
    - pattern: "svg/*.svg"
      database: stagvault/data/emojis/emoji_db.json
      key_pattern: "emoji_u(?P<key>[0-9a-fA-F_]+)"
    - pattern: "third_party/region-flags/**/*.svg"
      database: stagvault/data/emojis/emoji_db.json
      key_pattern: "(?P<key>[A-Z]{2})"  # Country codes like US, DE
```

### Key Extraction

The `key_pattern` is a regex with a named group `key` that extracts the lookup key from filenames:

| Filename | Pattern | Extracted Key |
|----------|---------|---------------|
| `emoji_u1f600.svg` | `emoji_u(?P<key>[0-9a-fA-F_]+)` | `1f600` |
| `US.svg` | `(?P<key>[A-Z]{2})` | `US` |
| `arrow-right.svg` | `(?P<key>.+)` | `arrow-right` |

The `key_transform` normalizes the key before lookup:
- `none`: Use as-is
- `lowercase`: Convert to lowercase
- `uppercase`: Convert to uppercase (for hex codepoints)

## Usage

### AliasLoader Class

```python
from stagvault.aliases import AliasLoader, AliasConfig

# Load alias configuration
config = AliasConfig(
    database="stagvault/data/emojis/emoji_db.json",
    key_pattern=r"emoji_u(?P<key>[0-9a-fA-F_]+)",
    key_transform="uppercase"
)
loader = AliasLoader(config)

# Resolve a single item
alias = loader.resolve("emoji_u1f600")
print(alias.name)      # "grinning face"
print(alias.aliases)   # ["grin", "smile", "happy"]
print(alias.tags)      # ["emotion", "positive", "face-smiling"]

# Enrich a MediaItem
item = MediaItem(name="emoji_u1f600", path="svg/emoji_u1f600.svg", ...)
enriched = loader.enrich(item)
print(enriched.name)   # "grinning face"
print(enriched.tags)   # [...original tags..., "emotion", "positive", ...]
```

### Integration with Indexing

The alias loader is used during index building, not during scanning:

```python
# In stagvault/search/indexer.py
class SearchIndexer:
    def __init__(self, vault: StagVault):
        self.vault = vault
        self.alias_loaders: dict[str, AliasLoader] = {}

    def _get_alias_loader(self, source_id: str) -> AliasLoader | None:
        """Get or create alias loader for a source."""
        if source_id in self.alias_loaders:
            return self.alias_loaders[source_id]

        config = self.vault.get_config(source_id)
        if config.aliases is None:
            return None

        loader = AliasLoader(config.aliases)
        self.alias_loaders[source_id] = loader
        return loader

    def index_item(self, item: MediaItem) -> IndexEntry:
        """Index a media item, enriching with aliases if available."""
        loader = self._get_alias_loader(item.source_id)
        if loader:
            item = loader.enrich(item)

        return IndexEntry(
            id=item.id,
            name=item.name,
            searchable_text=self._build_searchable_text(item),
            # ...
        )
```

## Creating Alias Databases

### For Emojis

The emoji database at `stagvault/data/emojis/emoji_db.json` was generated from Unicode CLDR data. To regenerate or update:

```bash
python scripts/fetch_emoji_data.py --output stagvault/data/emojis/emoji_db.json
```

### For Other Sources

Create a JSON file mapping identifiers to names:

```python
# Example: Generate alias database for icon set with numeric IDs
import json

aliases = {}
for icon_file in icons_dir.glob("*.svg"):
    icon_id = icon_file.stem  # e.g., "12345"
    # Look up name from your data source
    name = get_icon_name(icon_id)
    aliases[icon_id] = {
        "name": name,
        "aliases": generate_aliases(name),
        "tags": categorize(name)
    }

with open("aliases.json", "w") as f:
    json.dump(aliases, f, indent=2)
```

## Best Practices

1. **Keep alias databases in version control** - They're part of the project's metadata
2. **Use descriptive names** - "grinning face" is better than "emoji_1f600"
3. **Include common aliases** - Users might search "usa" not "united states"
4. **Add semantic tags** - "positive", "emotion" help with related searches
5. **Normalize keys consistently** - Pick uppercase or lowercase and stick with it
6. **Document the source** - Note where the alias data came from

## File Locations

- Emoji database: `stagvault/data/emojis/emoji_db.json`
- Custom alias databases: `stagvault/data/aliases/{source_id}.json`
- Scripts: `scripts/fetch_emoji_data.py`, `scripts/generate_aliases.py`
