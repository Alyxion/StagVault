#!/usr/bin/env python3
"""Fetch and generate descriptions for all emoji sources.

This script fetches emoji names and descriptions from:
1. Unicode CLDR data (official emoji names)
2. Source repository metadata files (if available)

It generates metadata.json files in static/metadata/{source_id}/ for each emoji source.

Usage:
    python scripts/fetch_emoji_descriptions.py                  # All emoji sources
    python scripts/fetch_emoji_descriptions.py --source twemoji # Specific source
    python scripts/fetch_emoji_descriptions.py --update         # Update existing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from stagvault.models.metadata import ItemMetadata, SourceMetadataIndex

PROJECT_ROOT = Path(__file__).parent.parent
METADATA_DIR = PROJECT_ROOT / "static" / "metadata"
CONFIGS_DIR = PROJECT_ROOT / "configs" / "sources"

# Unicode CLDR emoji data URL (annotations)
CLDR_EMOJI_URL = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json/cldr-annotations-full/annotations/en/annotations.json"

# Emoji sources we handle
EMOJI_SOURCES = ["noto-emoji", "twemoji", "fluent-emoji", "openmoji"]


def fetch_cldr_emoji_data() -> dict[str, dict]:
    """Fetch Unicode CLDR emoji annotations."""
    print("Fetching Unicode CLDR emoji data...")
    try:
        with urllib.request.urlopen(CLDR_EMOJI_URL, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        annotations = data.get("annotations", {}).get("annotations", {})
        print(f"  Loaded {len(annotations)} emoji annotations")
        return annotations
    except Exception as e:
        print(f"  Warning: Could not fetch CLDR data: {e}", file=sys.stderr)
        return {}


def codepoint_to_emoji(codepoint: str) -> str:
    """Convert codepoint string (e.g., '1f600' or '1f1e6-1f1e8') to emoji character."""
    parts = codepoint.lower().replace("_", "-").split("-")
    try:
        return "".join(chr(int(p, 16)) for p in parts if p)
    except ValueError:
        return ""


def emoji_to_codepoint(emoji: str) -> str:
    """Convert emoji character to codepoint string."""
    return "-".join(f"{ord(c):x}" for c in emoji)


def parse_filename_codepoint(filename: str) -> str | None:
    """Extract codepoint from various emoji filename formats.

    Handles:
    - 1f600.svg (noto, twemoji)
    - emoji_u1f600.svg (noto alternate)
    - 1F600.svg (case variations)
    - 1f1e6-1f1e8.svg (flag sequences)
    """
    stem = Path(filename).stem.lower()

    # Remove common prefixes
    stem = re.sub(r"^(emoji_u|u\+?|e)", "", stem)

    # Check if it looks like a codepoint
    if re.match(r"^[0-9a-f]+(-[0-9a-f]+)*$", stem):
        return stem

    return None


def get_emoji_description(emoji: str, cldr_data: dict) -> tuple[str | None, list[str]]:
    """Get description and keywords for an emoji from CLDR data.

    Returns: (description, keywords)
    """
    if emoji in cldr_data:
        entry = cldr_data[emoji]
        # CLDR format: {"default": ["keyword1", "keyword2"], "tts": ["description"]}
        description = None
        keywords = []

        if isinstance(entry, dict):
            tts = entry.get("tts", [])
            if tts:
                description = tts[0] if isinstance(tts, list) else tts

            default = entry.get("default", [])
            if isinstance(default, list):
                keywords = default

        return description, keywords

    return None, []


def generate_noto_metadata(cldr_data: dict) -> SourceMetadataIndex:
    """Generate metadata for Noto Emoji."""
    index = SourceMetadataIndex(source_id="noto-emoji")

    # Noto uses filenames like emoji_u1f600.svg or just codepoints
    # We'll generate entries for all known Unicode emoji
    for emoji, entry in cldr_data.items():
        if not emoji or len(emoji) > 20:  # Skip non-emoji entries
            continue

        codepoint = emoji_to_codepoint(emoji)
        description, keywords = get_emoji_description(emoji, cldr_data)

        if description:
            # Common filename patterns for Noto
            for filename in [codepoint, f"emoji_u{codepoint.replace('-', '_')}"]:
                index.items[filename] = ItemMetadata(
                    name=filename,
                    description=description,
                    keywords=keywords,
                    unicode=emoji,
                )

    return index


def generate_twemoji_metadata(cldr_data: dict) -> SourceMetadataIndex:
    """Generate metadata for Twemoji."""
    index = SourceMetadataIndex(source_id="twemoji")

    for emoji, entry in cldr_data.items():
        if not emoji or len(emoji) > 20:
            continue

        codepoint = emoji_to_codepoint(emoji)
        description, keywords = get_emoji_description(emoji, cldr_data)

        if description:
            # Twemoji uses lowercase codepoints
            index.items[codepoint] = ItemMetadata(
                name=codepoint,
                description=description,
                keywords=keywords,
                unicode=emoji,
            )

    return index


def generate_openmoji_metadata(cldr_data: dict) -> SourceMetadataIndex:
    """Generate metadata for OpenMoji."""
    index = SourceMetadataIndex(source_id="openmoji")

    for emoji, entry in cldr_data.items():
        if not emoji or len(emoji) > 20:
            continue

        # OpenMoji uses uppercase codepoints
        codepoint = emoji_to_codepoint(emoji).upper()
        description, keywords = get_emoji_description(emoji, cldr_data)

        if description:
            index.items[codepoint] = ItemMetadata(
                name=codepoint,
                description=description,
                keywords=keywords,
                unicode=emoji,
            )

    return index


def generate_fluent_metadata(cldr_data: dict) -> SourceMetadataIndex:
    """Generate metadata for Fluent Emoji.

    Fluent uses folder structure with emoji names, not codepoints.
    We create mappings based on CLDR descriptions.
    """
    index = SourceMetadataIndex(source_id="fluent-emoji")

    # Fluent emoji uses descriptive folder names
    # We'll create a reverse mapping from description to metadata
    for emoji, entry in cldr_data.items():
        if not emoji or len(emoji) > 20:
            continue

        description, keywords = get_emoji_description(emoji, cldr_data)

        if description:
            # Fluent uses names like "grinning face" as folder names
            # Normalize to match their format
            name_key = description.lower().replace(" ", "_").replace("-", "_")
            codepoint = emoji_to_codepoint(emoji)

            index.items[name_key] = ItemMetadata(
                name=name_key,
                description=description,
                keywords=keywords,
                unicode=emoji,
                extra={"codepoint": codepoint},
            )

            # Also add codepoint mapping
            index.items[codepoint] = ItemMetadata(
                name=codepoint,
                description=description,
                keywords=keywords,
                unicode=emoji,
            )

    return index


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch emoji descriptions")
    parser.add_argument("--source", "-s", help="Specific emoji source to process")
    parser.add_argument("--update", "-u", action="store_true", help="Update existing metadata")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Don't write files")
    args = parser.parse_args()

    sources = [args.source] if args.source else EMOJI_SOURCES

    # Validate sources
    for source in sources:
        if source not in EMOJI_SOURCES:
            print(f"Unknown emoji source: {source}", file=sys.stderr)
            print(f"Available: {', '.join(EMOJI_SOURCES)}")
            sys.exit(1)

    # Fetch CLDR data
    cldr_data = fetch_cldr_emoji_data()
    if not cldr_data:
        print("Warning: No CLDR data available, descriptions will be limited")

    # Generate metadata for each source
    generators = {
        "noto-emoji": generate_noto_metadata,
        "twemoji": generate_twemoji_metadata,
        "openmoji": generate_openmoji_metadata,
        "fluent-emoji": generate_fluent_metadata,
    }

    for source in sources:
        print(f"\nProcessing {source}...")

        output_path = METADATA_DIR / source / "metadata.json"

        # Check if exists and skip if not updating
        if output_path.exists() and not args.update:
            print(f"  Skipping (exists, use --update to refresh)")
            continue

        generator = generators.get(source)
        if not generator:
            print(f"  No generator for {source}")
            continue

        index = generator(cldr_data)
        print(f"  Generated {len(index.items)} entries")

        if not args.dry_run:
            index.save(output_path)
            print(f"  Saved to {output_path}")
        else:
            print(f"  Would save to {output_path}")

    print("\nDone!")
    print(f"Metadata files are in: {METADATA_DIR}")


if __name__ == "__main__":
    main()
