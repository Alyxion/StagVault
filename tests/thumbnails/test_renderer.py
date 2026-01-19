"""Tests for thumbnail renderer."""

from __future__ import annotations

import pytest
from PIL import Image
from io import BytesIO

from stagvault.thumbnails import ThumbnailRenderer, CheckerboardConfig
from stagvault.thumbnails.renderer import RenderResult


class TestThumbnailRenderer:
    """Tests for ThumbnailRenderer class."""

    def test_render_svg_basic(self) -> None:
        """Test rendering a basic SVG."""
        renderer = ThumbnailRenderer()

        svg_data = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <rect width="24" height="24" fill="red"/>
        </svg>'''

        result = renderer.render(svg_data, 64, format="svg")

        # Result should be RenderResult
        assert isinstance(result, RenderResult)
        assert result.image is not None
        assert result.image.size == (64, 64)
        assert result.original_width == 24
        assert result.original_height == 24

    def test_render_svg_to_png(self) -> None:
        """Test rendering SVG to PNG bytes."""
        renderer = ThumbnailRenderer()

        svg_data = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <rect width="24" height="24" fill="red"/>
        </svg>'''

        result = renderer.render(svg_data, 64, format="svg")
        png_bytes = renderer.to_png(result.image)

        # Verify it's a valid PNG
        assert isinstance(png_bytes, bytes)
        assert len(png_bytes) > 0
        image = Image.open(BytesIO(png_bytes))
        assert image.format == "PNG"
        assert image.size == (64, 64)

    def test_render_svg_with_transparency(self) -> None:
        """Test rendering SVG with transparency."""
        renderer = ThumbnailRenderer()

        # SVG with transparent background
        svg_data = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" fill="blue"/>
        </svg>'''

        result = renderer.render(svg_data, 64, format="svg")

        # PNG should preserve transparency
        png_bytes = renderer.to_png(result.image)
        png_image = Image.open(BytesIO(png_bytes))
        assert png_image.mode == "RGBA"

        # JPG should have checkerboard
        jpg_bytes = renderer.to_jpg(result.image)
        jpg_image = Image.open(BytesIO(jpg_bytes))
        assert jpg_image.mode == "RGB"

    def test_render_png(self) -> None:
        """Test rendering a PNG image."""
        renderer = ThumbnailRenderer()

        # Create a simple PNG
        source_image = Image.new("RGB", (100, 100), color="green")
        buffer = BytesIO()
        source_image.save(buffer, format="PNG")
        png_data = buffer.getvalue()

        result = renderer.render(png_data, 48, format="png")

        assert result.image.size == (48, 48)
        assert result.original_width == 100
        assert result.original_height == 100

    def test_render_png_with_alpha(self) -> None:
        """Test rendering PNG with alpha channel."""
        renderer = ThumbnailRenderer()

        # Create PNG with transparency
        source_image = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        buffer = BytesIO()
        source_image.save(buffer, format="PNG")
        png_data = buffer.getvalue()

        result = renderer.render(png_data, 64, format="png")

        assert result.image.size == (64, 64)
        assert result.image.mode == "RGBA"

    def test_to_jpg_adds_checkerboard(self) -> None:
        """Test that JPG output adds checkerboard for transparent images."""
        config = CheckerboardConfig(
            light_color="#ffffff",
            dark_color="#cccccc",
            square_size=8,
        )
        renderer = ThumbnailRenderer(checkerboard=config)

        # Create fully transparent PNG
        source_image = Image.new("RGBA", (64, 64), color=(0, 0, 0, 0))
        buffer = BytesIO()
        source_image.save(buffer, format="PNG")
        png_data = buffer.getvalue()

        result = renderer.render(png_data, 64, format="png")
        jpg_bytes = renderer.to_jpg(result.image)

        jpg_image = Image.open(BytesIO(jpg_bytes))
        assert jpg_image.mode == "RGB"

        # Check checkerboard pattern is visible
        pixels = list(jpg_image.getdata())
        # First pixel should be light (#ffffff)
        assert pixels[0] == (255, 255, 255)
        # Pixel at offset 8 should be dark (#cccccc)
        assert pixels[8] == (204, 204, 204)

    def test_render_maintains_aspect_ratio(self) -> None:
        """Test that non-square images maintain aspect ratio."""
        renderer = ThumbnailRenderer()

        # Create wide image
        source_image = Image.new("RGB", (200, 100), color="blue")
        buffer = BytesIO()
        source_image.save(buffer, format="PNG")
        png_data = buffer.getvalue()

        result = renderer.render(png_data, 64, format="png")

        # Output should be square canvas
        assert result.image.size == (64, 64)
        assert result.original_width == 200
        assert result.original_height == 100

    def test_hex_to_rgb(self) -> None:
        """Test hex color conversion."""
        assert ThumbnailRenderer._hex_to_rgb("#ffffff") == (255, 255, 255)
        assert ThumbnailRenderer._hex_to_rgb("#000000") == (0, 0, 0)
        assert ThumbnailRenderer._hex_to_rgb("#ff0000") == (255, 0, 0)
        assert ThumbnailRenderer._hex_to_rgb("cccccc") == (204, 204, 204)

    def test_extract_insights(self) -> None:
        """Test extracting insights from rendered image."""
        renderer = ThumbnailRenderer()

        # Create PNG with known colors
        source_image = Image.new("RGBA", (100, 100), color=(128, 64, 192, 200))
        buffer = BytesIO()
        source_image.save(buffer, format="PNG")
        png_data = buffer.getvalue()

        result = renderer.render(png_data, 128, format="png")
        insights = renderer.extract_insights(result, 128)

        assert insights.rendered_size == 128
        assert insights.original_width == 100
        assert insights.original_height == 100
        assert insights.is_square
        assert not insights.fully_opaque  # alpha < 255
        assert insights.has_transparency  # alpha < 255


class TestCheckerboardConfig:
    """Tests for CheckerboardConfig."""

    def test_default_values(self) -> None:
        """Test default checkerboard configuration."""
        config = CheckerboardConfig()
        assert config.light_color == "#ffffff"
        assert config.dark_color == "#cccccc"
        assert config.square_size == 8

    def test_custom_values(self) -> None:
        """Test custom checkerboard configuration."""
        config = CheckerboardConfig(
            light_color="#f0f0f0",
            dark_color="#d0d0d0",
            square_size=12,
        )
        assert config.light_color == "#f0f0f0"
        assert config.dark_color == "#d0d0d0"
        assert config.square_size == 12
