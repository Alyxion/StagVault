#!/usr/bin/env python3
"""Add or update metadata for individual items.

Usage:
    # Add single item
    python scripts/add_metadata.py phosphor-icons arrow-right "Right arrow icon"

    # With keywords
    python scripts/add_metadata.py phosphor-icons arrow-right "Right arrow" -k arrow -k direction -k right

    # With category
    python scripts/add_metadata.py phosphor-icons arrow-right "Right arrow" -c navigation

    # Bulk from file (one per line: name|description|keywords|category)
    python scripts/add_metadata.py phosphor-icons --file descriptions.txt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from stagvault.models.metadata import ItemMetadata, SourceMetadataIndex

PROJECT_ROOT = Path(__file__).parent.parent
METADATA_DIR = PROJECT_ROOT / "static" / "metadata"


def add_single_item(
    source_id: str,
    name: str,
    description: str,
    keywords: list[str] | None = None,
    category: str | None = None,
) -> None:
    """Add or update a single item's metadata."""
    metadata_path = METADATA_DIR / source_id / "metadata.json"

    index = SourceMetadataIndex.load_or_create(metadata_path, source_id)

    item = ItemMetadata(
        name=name,
        description=description,
        keywords=keywords or [],
        category=category,
    )

    index.set(name, item)
    index.save(metadata_path)

    print(f"Added: {name} -> {description}")


def add_from_file(source_id: str, file_path: Path) -> int:
    """Add items from a file. Returns count added.

    File format (pipe-delimited):
        name|description|keywords(comma-sep)|category
        arrow-right|Right arrow icon|arrow,direction,right|navigation
    """
    metadata_path = METADATA_DIR / source_id / "metadata.json"
    index = SourceMetadataIndex.load_or_create(metadata_path, source_id)

    count = 0
    with open(file_path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("|")
            if len(parts) < 2:
                print(f"Warning: Line {line_num}: Invalid format, skipping")
                continue

            name = parts[0].strip()
            description = parts[1].strip()
            keywords = [k.strip() for k in parts[2].split(",")] if len(parts) > 2 and parts[2] else []
            category = parts[3].strip() if len(parts) > 3 else None

            item = ItemMetadata(
                name=name,
                description=description,
                keywords=keywords,
                category=category,
            )
            index.set(name, item)
            count += 1

    index.save(metadata_path)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Add metadata for items")
    parser.add_argument("source_id", help="Source identifier")
    parser.add_argument("name", nargs="?", help="Item name (filename without extension)")
    parser.add_argument("description", nargs="?", help="Item description")
    parser.add_argument("-k", "--keyword", action="append", dest="keywords", help="Add keyword (can repeat)")
    parser.add_argument("-c", "--category", help="Item category")
    parser.add_argument("-f", "--file", type=Path, help="Bulk import from file")
    args = parser.parse_args()

    # Ensure metadata directory exists
    source_dir = METADATA_DIR / args.source_id
    if not source_dir.exists():
        print(f"Metadata folder not found: {source_dir}")
        print("Run: python scripts/init_metadata.py first")
        sys.exit(1)

    if args.file:
        if not args.file.exists():
            print(f"File not found: {args.file}", file=sys.stderr)
            sys.exit(1)
        count = add_from_file(args.source_id, args.file)
        print(f"Added {count} items to {args.source_id}")
    elif args.name and args.description:
        add_single_item(
            args.source_id,
            args.name,
            args.description,
            keywords=args.keywords,
            category=args.category,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
