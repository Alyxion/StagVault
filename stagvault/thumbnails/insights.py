"""Image insights extraction and model."""

from __future__ import annotations

from pydantic import BaseModel, Field
from PIL import Image


class ColorInfo(BaseModel):
    """RGB color information."""

    r: int = Field(..., ge=0, le=255)
    g: int = Field(..., ge=0, le=255)
    b: int = Field(..., ge=0, le=255)

    @property
    def hex(self) -> str:
        """Get hex representation."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @classmethod
    def from_tuple(cls, rgb: tuple[int, int, int]) -> "ColorInfo":
        return cls(r=rgb[0], g=rgb[1], b=rgb[2])


class ImageInsights(BaseModel):
    """Insights extracted from an image at render time."""

    # Color analysis
    avg_color: ColorInfo = Field(..., description="Average color (RGB)")
    min_color: ColorInfo = Field(..., description="Minimum color values (RGB)")
    max_color: ColorInfo = Field(..., description="Maximum color values (RGB)")

    # Transparency
    has_transparency: bool = Field(..., description="True if any pixels are transparent")
    fully_opaque: bool = Field(..., description="True if all pixels are fully opaque")
    alpha_min: int = Field(default=255, ge=0, le=255, description="Minimum alpha value")
    alpha_max: int = Field(default=255, ge=0, le=255, description="Maximum alpha value")

    # Dimensions
    original_width: int | None = Field(default=None, description="Original image width")
    original_height: int | None = Field(default=None, description="Original image height")
    rendered_size: int = Field(..., description="Size at which insights were extracted")

    # Source metadata (from SVG viewBox or image dimensions)
    native_size: int | None = Field(default=None, description="Native/intended size if known")
    is_square: bool = Field(default=True, description="Whether original is square")

    @classmethod
    def from_image(
        cls,
        image: Image.Image,
        rendered_size: int,
        original_width: int | None = None,
        original_height: int | None = None,
        native_size: int | None = None,
    ) -> "ImageInsights":
        """Extract insights from a PIL Image."""
        # Ensure RGBA for alpha analysis
        if image.mode != "RGBA":
            rgba = image.convert("RGBA")
        else:
            rgba = image

        pixels = list(rgba.getdata())

        # Separate channels
        reds = [p[0] for p in pixels]
        greens = [p[1] for p in pixels]
        blues = [p[2] for p in pixels]
        alphas = [p[3] for p in pixels]

        # Color stats
        avg_r = sum(reds) // len(reds)
        avg_g = sum(greens) // len(greens)
        avg_b = sum(blues) // len(blues)

        min_r, max_r = min(reds), max(reds)
        min_g, max_g = min(greens), max(greens)
        min_b, max_b = min(blues), max(blues)

        # Alpha stats
        alpha_min = min(alphas)
        alpha_max = max(alphas)
        has_transparency = alpha_min < 255
        fully_opaque = alpha_min == 255

        # Check if square
        is_square = True
        if original_width and original_height:
            is_square = original_width == original_height

        return cls(
            avg_color=ColorInfo(r=avg_r, g=avg_g, b=avg_b),
            min_color=ColorInfo(r=min_r, g=min_g, b=min_b),
            max_color=ColorInfo(r=max_r, g=max_g, b=max_b),
            has_transparency=has_transparency,
            fully_opaque=fully_opaque,
            alpha_min=alpha_min,
            alpha_max=alpha_max,
            original_width=original_width,
            original_height=original_height,
            rendered_size=rendered_size,
            native_size=native_size,
            is_square=is_square,
        )
