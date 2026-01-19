# Source Hierarchy

Sources in StagVault are organized in a **maximum 2-level hierarchy** for filtering purposes.

## Structure

```
Category/
└── Subcategory/
    └── Source
```

The hierarchy is intentionally shallow (max 2 levels) to:
- Keep the filtering UI simple and fast
- Enable batch enable/disable at any hierarchy level
- Maintain consistency between CLI and web UI

## Current Hierarchy

```
Vector/
├── Icons/
│   ├── phosphor-icons    (9,072 items)
│   ├── tabler-icons      (5,986 items)
│   ├── lucide            (1,667 items)
│   ├── heroicons         (1,288 items)
│   └── feather           (287 items)
└── Emoji/
    └── noto-emoji        (3,000+ items)
```

## Configuration

The hierarchy is defined in source configuration files under `configs/sources/`:

```yaml
# configs/sources/phosphor-icons.yaml
id: phosphor-icons
name: Phosphor Icons
type: git
category: Vector
subcategory: Icons
# ...
```

```yaml
# configs/sources/noto-emoji.yaml
id: noto-emoji
name: Noto Emoji
type: git
category: Vector
subcategory: Emoji
# ...
```

## Tree Behavior

### Checkbox States

Each level in the tree has a checkbox with three states:

| State | Meaning |
|-------|---------|
| Checked | All items in this branch are included |
| Unchecked | All items in this branch are excluded |
| Indeterminate | Some items included, some excluded |

### Hierarchy Actions

- **Check parent** → Includes all children
- **Uncheck parent** → Excludes all children
- **Check/uncheck child** → Parent updates to reflect mixed state

### Example

```
[✓] Vector                    ← All vector sources included
    [✓] Icons                 ← All icon sources included
        [✓] phosphor-icons
        [✓] lucide
        [✓] heroicons
    [-] Emoji                 ← Some emoji sources (indeterminate)
        [✓] noto-emoji
        [ ] twemoji           ← Excluded
```

## CLI Usage

The hierarchy maps to CLI filtering:

```bash
# Include entire category
stagvault search "arrow" --category Vector

# Include subcategory
stagvault search "arrow" --subcategory Icons

# Include specific source
stagvault search "arrow" --source phosphor-icons

# Exclude at any level
stagvault search "arrow" --exclude-subcategory Emoji
```

## Static Site Mapping

The hierarchy is precomputed in `sources.json`:

```json
{
  "sources": [
    {
      "id": "phosphor-icons",
      "name": "Phosphor Icons",
      "category": "Vector",
      "subcategory": "Icons",
      "count": 9072,
      "license": "MIT"
    }
  ],
  "tree": {
    "Vector": {
      "Icons": ["phosphor-icons", "lucide", "heroicons", "tabler-icons", "feather"],
      "Emoji": ["noto-emoji"]
    }
  }
}
```

## Why Not Deeper?

Deeper hierarchies (3+ levels) were considered but rejected:

1. **UI Complexity**: Deeply nested trees are hard to navigate on mobile
2. **Diminishing Returns**: Most sources fit naturally into 2 levels
3. **Performance**: Flatter trees are faster to render and filter
4. **Consistency**: Same structure works for CLI, REST, and static modes

If finer categorization is needed, use tags and search instead of deeper hierarchy.
