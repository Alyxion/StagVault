"""Batch thumbnail generator with parallel processing."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from stagvault.thumbnails.cache import ThumbnailCache
from stagvault.thumbnails.config import ThumbnailConfig, ThumbnailSize
from stagvault.thumbnails.insights import ImageInsights
from stagvault.thumbnails.renderer import ThumbnailRenderer

if TYPE_CHECKING:
    from stagvault.models.media import MediaItem

logger = logging.getLogger(__name__)


@dataclass
class ItemTask:
    """Task for processing a single item."""

    source_id: str
    item_id: str
    item_path: str
    item_format: str
    source_dir: str
    data_dir: str
    sizes: list[int]
    insights_size: int
    jpg_quality: int
    force: bool


def _process_item(task: ItemTask) -> dict:
    """Process a single item (runs in worker process)."""
    from stagvault.thumbnails.config import ThumbnailConfig
    from stagvault.thumbnails.renderer import ThumbnailRenderer

    result = {
        "item_id": task.item_id,
        "generated_png": 0,
        "generated_jpg": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }

    source_path = Path(task.source_dir) / task.item_path
    if not source_path.exists():
        result["failed"] = len(task.sizes) * 2
        result["errors"].append(f"Source file not found: {source_path}")
        return result

    config = ThumbnailConfig()
    renderer = ThumbnailRenderer(
        checkerboard=config.checkerboard,
        jpg_quality=task.jpg_quality,
    )

    source_data: bytes | None = None
    insights_extracted = False

    for size in task.sizes:
        try:
            # Check if files exist
            png_path = config.get_thumbnail_path(
                Path(task.data_dir), task.source_id, task.item_id, size, "png"
            )
            jpg_path = config.get_thumbnail_path(
                Path(task.data_dir), task.source_id, task.item_id, size, "jpg"
            )

            png_exists = png_path.exists() and not task.force
            jpg_exists = jpg_path.exists() and not task.force

            if png_exists and jpg_exists:
                result["skipped"] += 2
                # Still need insights even if thumbnails exist
                if size == task.insights_size and not insights_extracted:
                    insights_path = config.get_insights_path(
                        Path(task.data_dir), task.source_id, task.item_id
                    )
                    if not insights_path.exists() or task.force:
                        if source_data is None:
                            source_data = source_path.read_bytes()
                        render_result = renderer.render(source_data, size, format=task.item_format)
                        insights = renderer.extract_insights(render_result, size)
                        insights_path.parent.mkdir(parents=True, exist_ok=True)
                        insights_path.write_text(insights.model_dump_json(indent=2))
                        insights_extracted = True
                continue

            # Lazy load source data
            if source_data is None:
                source_data = source_path.read_bytes()

            # Render at this size
            render_result = renderer.render(source_data, size, format=task.item_format)

            # Save PNG (transparent)
            if not png_exists:
                png_data = renderer.to_png(render_result.image)
                png_path.parent.mkdir(parents=True, exist_ok=True)
                png_path.write_bytes(png_data)
                result["generated_png"] += 1

            # Save JPG (with checkerboard)
            if not jpg_exists:
                jpg_data = renderer.to_jpg(render_result.image)
                jpg_path.parent.mkdir(parents=True, exist_ok=True)
                jpg_path.write_bytes(jpg_data)
                result["generated_jpg"] += 1

            # Extract insights at insights_size
            if size == task.insights_size and not insights_extracted:
                insights = renderer.extract_insights(render_result, size)
                insights_path = config.get_insights_path(
                    Path(task.data_dir), task.source_id, task.item_id
                )
                insights_path.parent.mkdir(parents=True, exist_ok=True)
                insights_path.write_text(insights.model_dump_json(indent=2))
                insights_extracted = True

        except Exception as e:
            result["failed"] += 2
            result["errors"].append(f"Size {size}: {e}")
            logger.warning(f"Failed to generate thumbnail for {task.item_id} at {size}px: {e}")

    return result


class GenerationResult:
    """Result of thumbnail generation batch."""

    def __init__(self) -> None:
        self.generated_png: int = 0
        self.generated_jpg: int = 0
        self.skipped: int = 0
        self.failed: int = 0
        self.errors: list[tuple[str, str]] = []

    @property
    def total(self) -> int:
        return self.generated_png + self.generated_jpg + self.skipped + self.failed


class ThumbnailGenerator:
    """Generates thumbnails for media items in batch with parallel processing."""

    def __init__(
        self,
        data_dir: Path,
        config: ThumbnailConfig | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.config = config or ThumbnailConfig()
        self.cache = ThumbnailCache(data_dir)
        self.renderer = ThumbnailRenderer(
            self.config.checkerboard,
            jpg_quality=self.config.jpg_quality,
        )

    def generate_for_item(
        self,
        item: MediaItem,
        source_dir: Path,
        sizes: list[int] | None = None,
        force: bool = False,
    ) -> GenerationResult:
        """Generate thumbnails for a single media item (non-parallel)."""
        result = GenerationResult()
        sizes = sizes or self.config.sizes

        if item.format.lower() not in self.config.supported_input_formats:
            result.skipped += len(sizes) * 2
            return result

        task = ItemTask(
            source_id=item.source_id,
            item_id=item.id,
            item_path=item.path,
            item_format=item.format.lower(),
            source_dir=str(source_dir),
            data_dir=str(self.data_dir),
            sizes=sizes,
            insights_size=self.config.insights_size,
            jpg_quality=self.config.jpg_quality,
            force=force,
        )

        task_result = _process_item(task)

        result.generated_png = task_result["generated_png"]
        result.generated_jpg = task_result["generated_jpg"]
        result.skipped = task_result["skipped"]
        result.failed = task_result["failed"]
        for error in task_result["errors"]:
            result.errors.append((item.id, error))

        # Update cache
        self._update_cache_for_item(item.source_id, item.id, sizes)

        return result

    def generate_for_source(
        self,
        source_id: str,
        items: list[MediaItem],
        source_dir: Path,
        sizes: list[int] | None = None,
        force: bool = False,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> GenerationResult:
        """Generate thumbnails for all items from a source using parallel processing."""
        result = GenerationResult()
        sizes = sizes or self.config.sizes

        # Filter items for this source and supported formats
        tasks = []
        for item in items:
            if item.source_id != source_id:
                continue
            if item.format.lower() not in self.config.supported_input_formats:
                result.skipped += len(sizes) * 2
                continue

            tasks.append(ItemTask(
                source_id=item.source_id,
                item_id=item.id,
                item_path=item.path,
                item_format=item.format.lower(),
                source_dir=str(source_dir),
                data_dir=str(self.data_dir),
                sizes=sizes,
                insights_size=self.config.insights_size,
                jpg_quality=self.config.jpg_quality,
                force=force,
            ))

        if not tasks:
            return result

        total = len(tasks)
        completed = 0

        # Process in parallel
        with ProcessPoolExecutor(max_workers=self.config.workers) as executor:
            futures = {executor.submit(_process_item, task): task for task in tasks}

            for future in as_completed(futures):
                task = futures[future]
                try:
                    task_result = future.result()
                    result.generated_png += task_result["generated_png"]
                    result.generated_jpg += task_result["generated_jpg"]
                    result.skipped += task_result["skipped"]
                    result.failed += task_result["failed"]
                    for error in task_result["errors"]:
                        result.errors.append((task_result["item_id"], error))

                    # Update cache
                    self._update_cache_for_item(task.source_id, task.item_id, sizes)

                except Exception as e:
                    result.failed += len(sizes) * 2
                    result.errors.append((task.item_id, str(e)))

                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        return result

    def _update_cache_for_item(
        self,
        source_id: str,
        item_id: str,
        sizes: list[int],
    ) -> None:
        """Update cache entries for an item's thumbnails."""
        for size in sizes:
            for ext in ["png", "jpg"]:
                path = self.config.get_thumbnail_path(
                    self.data_dir, source_id, item_id, size, ext
                )
                if path.exists():
                    self.cache.add(
                        source_id=source_id,
                        item_id=item_id,
                        size=size,
                        file_path=path,
                        file_size=path.stat().st_size,
                    )

    def get_thumbnail(
        self,
        source_id: str,
        item_id: str,
        size: int,
        format: str = "png",
    ) -> bytes | None:
        """Get a thumbnail from cache."""
        path = self.config.get_thumbnail_path(
            self.data_dir, source_id, item_id, size, format
        )
        if not path.exists():
            return None
        return path.read_bytes()

    def get_thumbnail_path(
        self,
        source_id: str,
        item_id: str,
        size: int,
        format: str = "png",
    ) -> Path | None:
        """Get path to a cached thumbnail."""
        path = self.config.get_thumbnail_path(
            self.data_dir, source_id, item_id, size, format
        )
        if not path.exists():
            return None
        return path

    def get_insights(
        self,
        source_id: str,
        item_id: str,
    ) -> ImageInsights | None:
        """Get insights for an item."""
        path = self.config.get_insights_path(self.data_dir, source_id, item_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return ImageInsights.model_validate(data)
        except Exception:
            return None

    def get_available_sizes(self, source_id: str, item_id: str) -> list[int]:
        """Get all available thumbnail sizes for an item."""
        return self.cache.get_sizes_for_item(source_id, item_id)

    def clear_source(self, source_id: str) -> int:
        """Clear all thumbnails for a source."""
        import shutil

        thumb_dir = self.data_dir / "thumbnails" / source_id
        if thumb_dir.exists():
            shutil.rmtree(thumb_dir)
        return self.cache.remove_source(source_id)

    def clear_all(self) -> int:
        """Clear all thumbnails."""
        import shutil

        thumb_dir = self.data_dir / "thumbnails"
        if thumb_dir.exists():
            for item in thumb_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
        return self.cache.clear()

    def get_stats(self) -> dict[str, int | dict[str, int] | dict[int, int]]:
        """Get thumbnail cache statistics."""
        stats = self.cache.get_stats()
        return {
            "total_count": stats.total_count,
            "total_size_bytes": stats.total_size_bytes,
            "sources": stats.sources,
            "sizes": stats.sizes,
        }

    def close(self) -> None:
        """Close the generator and release resources."""
        self.cache.close()
