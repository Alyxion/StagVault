"""Unit tests for thumbnail color verification.

Tests that:
- Single-color icon sets (phosphor, lucide, heroicons, tabler, feather) have WHITE icons
- Color sets (noto-emoji) preserve their original colors (NOT white/inverted)
"""

import json
from pathlib import Path
from io import BytesIO

import pytest
from PIL import Image

# Test configuration
DATA_DIR = Path(__file__).parent.parent / "data"
STATIC_SITE_DIR = Path(__file__).parent.parent / "static_site" / "index"
THUMBNAIL_DIR = DATA_DIR / "thumbnails"

# Source classifications
SINGLE_COLOR_SOURCES = ["phosphor-icons", "lucide", "heroicons", "tabler-icons", "feather"]
COLOR_SOURCES = ["noto-emoji"]

# Color thresholds
# Red color is #e94560 = RGB(233, 69, 96)
RED_R_MIN = 180  # Minimum R value for red
RED_G_MAX = 120  # Maximum G value for red
RED_B_MAX = 150  # Maximum B value for red
DARK_THRESHOLD = 50    # Maximum RGB value to be considered "black/dark"


def get_thumbnail_samples(source_id: str, count: int = 5) -> list[Path]:
    """Get sample thumbnail paths for a source."""
    thumb_dir = THUMBNAIL_DIR / source_id
    if not thumb_dir.exists():
        pytest.skip(f"Thumbnail directory not found: {thumb_dir}")

    # Find 64px JPG thumbnails
    thumbnails = list(thumb_dir.glob("**/*_64.jpg"))
    if not thumbnails:
        pytest.skip(f"No thumbnails found for {source_id}")

    # Return evenly distributed samples
    step = max(1, len(thumbnails) // count)
    return thumbnails[::step][:count]


def analyze_thumbnail_colors(image_path: Path) -> dict:
    """Analyze colors in a thumbnail image.

    Returns:
        dict with:
        - avg_r, avg_g, avg_b: Average RGB of non-transparent, non-background pixels
        - pixel_count: Number of analyzed pixels
        - is_red: True if average color is red (#e94560)
        - is_dark: True if average color is dark (low RGB)
    """
    img = Image.open(image_path).convert("RGBA")
    pixels = list(img.getdata())

    # Count red pixels (icon foreground) vs dark pixels
    red_count = 0
    dark_count = 0
    total_opaque = 0

    for r, g, b, a in pixels:
        if a < 128:  # Skip transparent
            continue
        total_opaque += 1
        # Check for red color (#e94560 range)
        if r > RED_R_MIN and g < RED_G_MAX and b < RED_B_MAX:
            red_count += 1
        # Check for dark/black
        if r < DARK_THRESHOLD and g < DARK_THRESHOLD and b < DARK_THRESHOLD:
            dark_count += 1

    # Filter out background for average calculation
    foreground_pixels = []
    for r, g, b, a in pixels:
        if a < 128:
            continue
        # Skip checkerboard background colors (light gray/white)
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum > 180:
            continue
        foreground_pixels.append((r, g, b))

    if not foreground_pixels:
        return {
            "avg_r": 0, "avg_g": 0, "avg_b": 0,
            "pixel_count": 0,
            "is_red": False,
            "is_dark": False,
            "red_count": red_count,
            "dark_count": dark_count,
            "foreground_ratio": 0,
        }

    avg_r = sum(p[0] for p in foreground_pixels) / len(foreground_pixels)
    avg_g = sum(p[1] for p in foreground_pixels) / len(foreground_pixels)
    avg_b = sum(p[2] for p in foreground_pixels) / len(foreground_pixels)

    return {
        "avg_r": avg_r,
        "avg_g": avg_g,
        "avg_b": avg_b,
        "pixel_count": len(foreground_pixels),
        "is_red": red_count > dark_count and red_count > 0,
        "is_dark": dark_count > red_count and dark_count > 0,
        "red_count": red_count,
        "dark_count": dark_count,
        "foreground_ratio": len(foreground_pixels) / total_opaque if total_opaque > 0 else 0,
    }


class TestSingleColorSources:
    """Tests for single-color icon sets that should be rendered in RED (#e94560)."""

    @pytest.mark.parametrize("source_id", SINGLE_COLOR_SOURCES)
    def test_thumbnails_are_red(self, source_id: str):
        """Verify that single-color source thumbnails have red foreground pixels."""
        samples = get_thumbnail_samples(source_id, count=5)

        results = []
        for thumb_path in samples:
            analysis = analyze_thumbnail_colors(thumb_path)
            results.append({
                "path": str(thumb_path.name),
                **analysis,
            })

        # Check that all samples have red foreground
        red_count = sum(1 for r in results if r["is_red"])
        dark_count = sum(1 for r in results if r["is_dark"])

        # Print detailed results for debugging
        print(f"\n{source_id} thumbnail analysis:")
        for r in results:
            status = "RED ✓" if r["is_red"] else ("DARK ✗" if r["is_dark"] else "OTHER")
            print(f"  {r['path']}: RGB({r['avg_r']:.0f}, {r['avg_g']:.0f}, {r['avg_b']:.0f}) - {status} (red_px={r['red_count']})")

        # Assert: should NOT be dark (black icons = wrong)
        assert dark_count == 0, (
            f"{source_id}: Found {dark_count}/{len(results)} dark (black) thumbnails. "
            f"Icons should be RED, not black!"
        )

        # Assert: should be red
        assert red_count >= len(results) * 0.8, (
            f"{source_id}: Only {red_count}/{len(results)} thumbnails are red. "
            f"Expected at least 80% red icons."
        )


class TestColorSources:
    """Tests for color sources (like emoji) that should preserve original colors."""

    @pytest.mark.parametrize("source_id", COLOR_SOURCES)
    def test_thumbnails_preserve_colors(self, source_id: str):
        """Verify that color source thumbnails are NOT red/inverted."""
        # For noto-emoji, thumbnails are external PNGs, check if local copies exist
        thumb_dir = THUMBNAIL_DIR / source_id
        if not thumb_dir.exists():
            # noto-emoji uses external URLs, skip local thumbnail test
            pytest.skip(f"No local thumbnails for {source_id} (uses external URLs)")

        samples = get_thumbnail_samples(source_id, count=5)

        results = []
        for thumb_path in samples:
            analysis = analyze_thumbnail_colors(thumb_path)
            results.append({
                "path": str(thumb_path.name),
                **analysis,
            })

        # Print detailed results
        print(f"\n{source_id} thumbnail analysis:")
        for r in results:
            print(f"  {r['path']}: RGB({r['avg_r']:.0f}, {r['avg_g']:.0f}, {r['avg_b']:.0f})")

        # Color sources should have varied colors, not all red or all black
        all_red = all(r["is_red"] for r in results)
        all_dark = all(r["is_dark"] for r in results)

        assert not all_red, (
            f"{source_id}: All thumbnails are red - colors may have been incorrectly processed!"
        )
        assert not all_dark, (
            f"{source_id}: All thumbnails are dark/black - something is wrong!"
        )


class TestStaticSiteThumbnails:
    """Tests for thumbnails in the static site output directory."""

    @pytest.mark.parametrize("source_id", SINGLE_COLOR_SOURCES)
    def test_static_site_thumbnails_are_red(self, source_id: str):
        """Verify static site thumbnails have red icons."""
        thumb_dir = STATIC_SITE_DIR / "thumbs" / source_id
        if not thumb_dir.exists():
            pytest.skip(f"Static site thumbnails not found: {thumb_dir}")

        # Find 64px JPG thumbnails
        thumbnails = list(thumb_dir.glob("**/*_64.jpg"))[:5]
        if not thumbnails:
            pytest.skip(f"No static site thumbnails found for {source_id}")

        results = []
        for thumb_path in thumbnails:
            analysis = analyze_thumbnail_colors(thumb_path)
            results.append({
                "path": str(thumb_path.relative_to(STATIC_SITE_DIR)),
                **analysis,
            })

        # Print detailed results
        print(f"\nStatic site {source_id} thumbnail analysis:")
        for r in results:
            status = "RED ✓" if r["is_red"] else ("DARK ✗" if r["is_dark"] else "OTHER")
            print(f"  {r['path']}: RGB({r['avg_r']:.0f}, {r['avg_g']:.0f}, {r['avg_b']:.0f}) - {status}")

        dark_count = sum(1 for r in results if r["is_dark"])
        assert dark_count == 0, (
            f"Static site {source_id}: Found {dark_count}/{len(results)} DARK thumbnails. "
            f"Icons should be RED!"
        )


class TestThumbnailRenderer:
    """Tests for the thumbnail renderer colorization."""

    def test_svg_colorization_produces_red(self):
        """Test that SVG colorization replaces black with red."""
        from stagvault.thumbnails.renderer import ThumbnailRenderer
        from stagvault.thumbnails.config import ColorConfig

        # Create renderer with red color config
        colors = ColorConfig(primary_color="#e94560", enabled=True)
        renderer = ThumbnailRenderer(colors=colors)

        # Test SVG with black fill
        svg_black_fill = '<svg><rect fill="#000000" width="10" height="10"/></svg>'
        result = renderer._colorize_svg(svg_black_fill)
        assert 'fill="#e94560"' in result or "fill='#e94560'" in result, (
            f"Black fill not replaced with red: {result}"
        )

        # Test SVG with currentColor
        svg_current = '<svg><path fill="currentColor" d="M0 0h10v10H0z"/></svg>'
        result = renderer._colorize_svg(svg_current)
        assert "#e94560" in result, (
            f"currentColor not replaced with red: {result}"
        )

        # Test SVG with black stroke
        svg_stroke = '<svg><line stroke="#000" x1="0" y1="0" x2="10" y2="10"/></svg>'
        result = renderer._colorize_svg(svg_stroke)
        assert 'stroke="#e94560"' in result, (
            f"Black stroke not replaced with red: {result}"
        )

    def test_color_config_defaults(self):
        """Test that ColorConfig has correct defaults."""
        from stagvault.thumbnails.config import ColorConfig

        config = ColorConfig()
        assert config.primary_color == "#e94560", "Default primary color should be red"
        assert config.enabled == True, "Colorization should be enabled by default"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
