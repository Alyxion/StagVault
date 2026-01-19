# Filtering System

StagVault uses a simple, consistent filtering system across CLI, REST API, and static web interface.

## Sidebar Filters (Pre-configured)

The sidebar provides exactly **two** pre-configured filter types:

### 1. Source Tree Filter

A hierarchical tree of sources with maximum 2 levels of nesting.

**Structure:**
```
Category/
└── Subcategory/
    └── Source (with item count)
```

**Example:**
```
[✓] Vector (18,300)
    [✓] Icons (18,300)
        [✓] Phosphor Icons (9,072)
        [✓] Tabler Icons (5,986)
        [✓] Lucide (1,667)
        [✓] Heroicons (1,288)
        [✓] Feather (287)
    [✓] Emoji (3,645)
        [✓] Noto Emoji (3,645)
```

**Behavior:**
- Checkbox at each level enables/disables all children
- Shows item count per node (updates based on other filters)
- Unchecking "Icons" hides all icon sources at once
- Indeterminate state shows when children have mixed selection

### 2. License Filter

A flat list of license types.

**Example:**
```
[✓] MIT (17,320)
[✓] ISC (1,667)
[✓] OFL-1.1 (3,645)
[✓] Apache-2.0 (0)
[✓] CC0-1.0 (261)
```

**Behavior:**
- Simple checkboxes (no hierarchy)
- Shows item count per license
- Multiple licenses can be selected/deselected

## Category Filtering (via Search)

**Important:** Categories are **NOT** a sidebar filter.

Instead, categories and tags are filtered through the search box:

```
Search: "outline arrow"     → Arrow icons with outline style
Search: "bold home"         → Bold home icons
Search: "emoji smile"       → Smiling emoji
Search: "flag waved"        → Waved flag variants
```

**Why no category sidebar?**
- Reduces UI clutter
- Tags are too numerous for a sidebar (1600+ tags)
- Search provides more flexible filtering
- Categories overlap significantly (an icon can be both "ui" and "navigation")

## CLI Filtering

The CLI provides explicit flags for filtering:

### Source Filtering

```bash
# Include specific sources (can repeat)
stagvault search "arrow" --source phosphor-icons --source lucide
stagvault search "arrow" -s phosphor-icons -s lucide

# Exclude specific sources
stagvault search "arrow" --exclude-source heroicons
stagvault search "arrow" -xs heroicons

# Filter by category/subcategory
stagvault search "arrow" --category Vector
stagvault search "arrow" --subcategory Icons
```

### License Filtering

```bash
# Include specific licenses
stagvault search "arrow" --license MIT
stagvault search "arrow" --license MIT --license ISC

# Exclude specific licenses
stagvault search "arrow" --exclude-license GPL-3.0
stagvault search "arrow" -xl GPL-3.0
```

### Combined Filtering

```bash
# Multiple filter types
stagvault search "arrow" \
    --source phosphor-icons \
    --source lucide \
    --license MIT \
    --mode static

# Exclusion mode
stagvault search "arrow" \
    --exclude-source heroicons \
    --exclude-license CC-BY-4.0
```

## REST API Filtering

```
GET /svault/search?q=arrow&sources=phosphor-icons,lucide&license=MIT
GET /svault/search?q=arrow&exclude_sources=heroicons
GET /svault/search?q=arrow&category=Vector&subcategory=Icons
```

## Exclusion Mode (Default)

All filters use **exclusion mode** by default:

- All items are **included** unless explicitly excluded
- Unchecking a filter **excludes** those items
- This is more intuitive: "show everything except X"

**Example flow:**
1. Initial state: All sources checked, all items visible
2. User unchecks "Heroicons"
3. Result: All items except Heroicons are shown
4. User unchecks "MIT license"
5. Result: All items except Heroicons and MIT-licensed items

## Filter Count Updates

Filter counts update dynamically to show remaining items:

```
Before any filtering:
[✓] Phosphor Icons (9,072)
[✓] MIT (17,320)

After excluding MIT license:
[✓] Phosphor Icons (0)      ← No non-MIT Phosphor icons
[✓] ISC (1,667)
[ ] MIT (0)                  ← Excluded
```

## Python/JS Parity

The filtering logic MUST behave identically in:
- Python API (`stagvault.search()`)
- JavaScript client (`app.js`)
- Static mode (`--mode static`)

This is enforced through parameterized tests that run the same queries across all modes.
