"""API source handler for remote API access."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from stagvault.models.media import MediaItem
from stagvault.sources.base import SourceHandler

if TYPE_CHECKING:
    from stagvault.models.config import SourceConfig


class ApiSourceHandler(SourceHandler):
    """Handler for API-based sources."""

    def __init__(self, config: SourceConfig, data_dir: Path) -> None:
        super().__init__(config, data_dir)
        if config.api is None:
            raise ValueError(f"Source {config.id} is not an API source")
        self.api_config = config.api
        self._client: httpx.AsyncClient | None = None

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.api_config.base_url,
                timeout=30.0,
            )
        return self._client

    def is_synced(self) -> bool:
        """API sources are always considered synced."""
        return True

    async def sync(self) -> None:
        """API sources don't need syncing - they fetch on demand."""
        pass

    async def scan(self) -> list[MediaItem]:
        """Scan the API source for available items."""
        items: list[MediaItem] = []

        list_endpoint = self.api_config.endpoints.get("list")
        if list_endpoint is None:
            return items

        response = await self.client.get(list_endpoint)
        response.raise_for_status()

        data = response.json()
        items = self._parse_items(data)

        return items

    def _parse_items(self, data: Any) -> list[MediaItem]:
        """Parse API response into media items. Override for custom formats."""
        items: list[MediaItem] = []

        if isinstance(data, list):
            for item_data in data:
                if isinstance(item_data, dict):
                    item = self._parse_single_item(item_data)
                    if item:
                        items.append(item)

        return items

    def _parse_single_item(self, data: dict[str, Any]) -> MediaItem | None:
        """Parse a single item from API response. Override for custom formats."""
        name = data.get("name") or data.get("id")
        path = data.get("path") or data.get("url") or name
        file_format = data.get("format", "svg")

        if not name or not path:
            return None

        return MediaItem(
            source_id=self.config.id,
            path=str(path),
            name=str(name),
            format=file_format,
            tags=data.get("tags", []),
            description=data.get("description"),
            metadata=data.get("metadata", {}),
        )

    async def fetch_file(self, item: MediaItem) -> bytes:
        """Fetch a file from the API."""
        file_endpoint = self.api_config.endpoints.get("file", "/{path}")
        url = file_endpoint.format(path=item.path, id=item.id, name=item.name)
        response = await self.client.get(url)
        response.raise_for_status()
        return response.content

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
