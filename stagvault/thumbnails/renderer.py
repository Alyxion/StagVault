"""Thumbnail renderer using Pillow and resvg."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
import resvg_py

from stagvault.thumbnails.insights import ImageInsights

if TYPE_CHECKING:
    from stagvault.thumbnails.config import CheckerboardConfig


class RenderResult:
    """Result of rendering a thumbnail."""

    def __init__(
        self,
        image: Image.Image,
        original_width: int | None = None,
        original_height: int | None = None,
        native_size: int | None = None,
    ) -> None:
        self.image = image
        self.original_width = original_width
        self.original_height = original_height
        self.native_size = native_size


class ThumbnailRenderer:
    """Renders thumbnails from various image formats."""

    def __init__(
        self,
        checkerboard: CheckerboardConfig | None = None,
        jpg_quality: int = 85,
    ) -> None:
        from stagvault.thumbnails.config import CheckerboardConfig

        self.checkerboard = checkerboard or CheckerboardConfig()
        self.jpg_quality = jpg_quality

    def render(
        self,
        source: bytes | Path,
        size: int,
        format: str | None = None,
    ) -> RenderResult:
        """Render a thumbnail from source data or file.

        Args:
            source: Image data as bytes or path to file
            size: Target size (square thumbnail)
            format: Source format hint (e.g., 'svg', 'png'). Auto-detected if None.

        Returns:
            RenderResult with the rendered PIL Image and metadata
        """
        if isinstance(source, Path):
            data = source.read_bytes()
            if format is None:
                format = source.suffix.lstrip(".").lower()
        else:
            data = source

        if format == "svg":
            return self._render_svg(data, size)
        else:
            return self._render_raster(data, size)

    def to_png(self, image: Image.Image) -> bytes:
        """Convert image to PNG (transparent, no checkerboard)."""
        # Keep transparency for PNG
        if image.mode not in ("RGBA", "RGB"):
            image = image.convert("RGBA")

        output = BytesIO()
        image.save(output, format="PNG", optimize=True)
        return output.getvalue()

    def to_jpg(self, image: Image.Image) -> bytes:
        """Convert image to JPG (with checkerboard for transparency)."""
        # Apply checkerboard background if image has transparency
        if image.mode in ("RGBA", "LA", "PA"):
            background = self._create_checkerboard(image.width, image.height)
            background.paste(image, (0, 0), image)
            image = background

        # Convert to RGB for JPEG
        if image.mode != "RGB":
            image = image.convert("RGB")

        output = BytesIO()
        image.save(output, format="JPEG", quality=self.jpg_quality, optimize=True)
        return output.getvalue()

    def extract_insights(
        self,
        result: RenderResult,
        rendered_size: int,
    ) -> ImageInsights:
        """Extract insights from a rendered image."""
        return ImageInsights.from_image(
            result.image,
            rendered_size=rendered_size,
            original_width=result.original_width,
            original_height=result.original_height,
            native_size=result.native_size,
        )

    def _render_svg(self, data: bytes, size: int) -> RenderResult:
        """Render SVG to PIL Image at specified size."""
        # Parse SVG to get original dimensions
        svg_string = data.decode("utf-8")

        # Try to extract viewBox or width/height
        original_width = None
        original_height = None
        native_size = None

        # Simple parsing for viewBox
        import re
        viewbox_match = re.search(r'viewBox=["\']([^"\']+)["\']', svg_string)
        if viewbox_match:
            parts = viewbox_match.group(1).split()
            if len(parts) >= 4:
                try:
                    original_width = int(float(parts[2]))
                    original_height = int(float(parts[3]))
                    if original_width == original_height:
                        native_size = original_width
                except (ValueError, IndexError):
                    pass

        # Use resvg to render SVG
        png_data = resvg_py.svg_to_bytes(
            svg_string=svg_string,
            width=size,
            height=size,
        )
        image = Image.open(BytesIO(png_data))

        return RenderResult(
            image=image,
            original_width=original_width,
            original_height=original_height,
            native_size=native_size,
        )

    def _render_raster(self, data: bytes, size: int) -> RenderResult:
        """Render raster image to PIL Image at specified size."""
        image = Image.open(BytesIO(data))
        original_width = image.width
        original_height = image.height

        # Calculate aspect-preserving size
        ratio = min(size / image.width, size / image.height)
        new_size = (int(image.width * ratio), int(image.height * ratio))

        # Resize with high quality
        image = image.resize(new_size, Image.Resampling.LANCZOS)

        # Create square canvas and center the image
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        offset = ((size - new_size[0]) // 2, (size - new_size[1]) // 2)

        # Handle paste with or without alpha
        if image.mode == "RGBA":
            canvas.paste(image, offset, image)
        else:
            canvas.paste(image.convert("RGBA"), offset)

        return RenderResult(
            image=canvas,
            original_width=original_width,
            original_height=original_height,
            native_size=original_width if original_width == original_height else None,
        )

    def _create_checkerboard(self, width: int, height: int) -> Image.Image:
        """Create a checkerboard pattern background."""
        light = self._hex_to_rgb(self.checkerboard.light_color)
        dark = self._hex_to_rgb(self.checkerboard.dark_color)
        square = self.checkerboard.square_size

        image = Image.new("RGB", (width, height))
        pixels = image.load()

        for y in range(height):
            for x in range(width):
                is_light = ((x // square) + (y // square)) % 2 == 0
                pixels[x, y] = light if is_light else dark

        return image

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
