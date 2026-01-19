#!/bin/bash
# Build the static site from scratch
#
# Usage:
#   ./scripts/build_static.sh              # Quick build (no thumbnails)
#   ./scripts/build_static.sh --full       # Full build with thumbnails
#   ./scripts/build_static.sh --thumbs     # Rebuild with existing thumbnails
#
# Prerequisites:
#   - Data must be synced: poetry run stagvault sync
#   - Index must be built: poetry run stagvault index

set -e

OUTPUT_DIR="${OUTPUT_DIR:-static_site/index}"
FULL_BUILD=false
WITH_THUMBS=false

# Parse arguments
for arg in "$@"; do
    case $arg in
        --full)
            FULL_BUILD=true
            WITH_THUMBS=true
            ;;
        --thumbs)
            WITH_THUMBS=true
            ;;
    esac
done

echo "=== StagVault Static Site Builder ==="
echo "Output: $OUTPUT_DIR"
echo ""

# Check prerequisites
if [ ! -f "index/stagvault.db" ] || [ ! -s "index/stagvault.db" ]; then
    echo "Error: Search index not found or empty."
    echo "Run: poetry run stagvault index"
    exit 1
fi

# Generate thumbnails if full build
if [ "$FULL_BUILD" = true ]; then
    echo "=== Generating thumbnails ==="
    poetry run stagvault thumbnails generate
    echo ""
fi

# Build static site
echo "=== Building static site ==="
if [ "$WITH_THUMBS" = true ]; then
    poetry run stagvault static build --output "$OUTPUT_DIR" --thumbnails
else
    poetry run stagvault static build --output "$OUTPUT_DIR"
fi

echo ""
echo "=== Build complete ==="
echo ""
echo "To serve locally:"
echo "  poetry run stagvault static serve -d $OUTPUT_DIR"
echo "  # or"
echo "  python -m http.server 8000 -d $OUTPUT_DIR"
echo ""
echo "Files are in: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR"
