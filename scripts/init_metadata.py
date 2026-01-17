#!/usr/bin/env python3
"""Initialize metadata folders for all configured sources.

Creates the folder structure:
    static/metadata/{source_id}/
        metadata.json   # Main metadata index
        README.md       # Source-specific notes

Usage:
    python scripts/init_metadata.py              # Initialize all sources
    python scripts/init_metadata.py --source X  # Initialize specific source
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parent.parent
METADATA_DIR = PROJECT_ROOT / "static" / "metadata"
CONFIGS_DIR = PROJECT_ROOT / "configs" / "sources"


def load_source_config(config_path: Path) -> dict:
    """Load a source config YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def init_source_metadata(source_id: str, config: dict) -> None:
    """Initialize metadata folder for a source."""
    source_dir = METADATA_DIR / source_id
    source_dir.mkdir(parents=True, exist_ok=True)

    # Create metadata.json if it doesn't exist
    metadata_path = source_dir / "metadata.json"
    if not metadata_path.exists():
        import json

        metadata = {
            "source_id": source_id,
            "version": "1.0",
            "items": {},
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        print(f"  Created {metadata_path}")
    else:
        print(f"  Exists: {metadata_path}")

    # Create README.md with source info
    readme_path = source_dir / "README.md"
    if not readme_path.exists():
        license_info = config.get("license", {})
        git_info = config.get("git", {})

        readme_content = f"""# {config.get('name', source_id)} Metadata

Source: `{source_id}`
Repository: {git_info.get('repo', 'N/A')}
License: {license_info.get('spdx', 'Unknown')}

## Description

{config.get('description', 'No description available.')}

## Metadata Format

The `metadata.json` file contains descriptions for individual items:

```json
{{
  "source_id": "{source_id}",
  "version": "1.0",
  "items": {{
    "icon-name": {{
      "name": "icon-name",
      "description": "Human-readable description",
      "keywords": ["keyword1", "keyword2"],
      "category": "optional-category"
    }}
  }}
}}
```

## Adding Descriptions

To add or update descriptions, edit the `metadata.json` file directly
or use the metadata management scripts:

```bash
# Add single item
python scripts/add_metadata.py {source_id} icon-name "Description here"

# Bulk import from CSV
python scripts/import_metadata.py {source_id} descriptions.csv
```
"""
        with open(readme_path, "w") as f:
            f.write(readme_content)
        print(f"  Created {readme_path}")
    else:
        print(f"  Exists: {readme_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize metadata folders")
    parser.add_argument("--source", "-s", help="Specific source to initialize")
    args = parser.parse_args()

    if not CONFIGS_DIR.exists():
        print(f"Config directory not found: {CONFIGS_DIR}", file=sys.stderr)
        sys.exit(1)

    config_files = sorted(CONFIGS_DIR.glob("*.yaml"))

    if args.source:
        config_files = [f for f in config_files if f.stem == args.source]
        if not config_files:
            print(f"Source not found: {args.source}", file=sys.stderr)
            sys.exit(1)

    print(f"Initializing metadata folders in: {METADATA_DIR}\n")

    for config_path in config_files:
        config = load_source_config(config_path)
        source_id = config.get("id", config_path.stem)
        print(f"{source_id}:")
        init_source_metadata(source_id, config)

    print(f"\nDone! Metadata folders created in {METADATA_DIR}")


if __name__ == "__main__":
    main()
