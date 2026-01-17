"""FastAPI router for StagVault API.

Usage:
    from fastapi import FastAPI
    from stagvault.api import create_router
    from stagvault import StagVault

    app = FastAPI()
    vault = StagVault("./data", "./configs")

    # Mount with default prefix /svault
    app.include_router(create_router(vault))

    # Or with custom prefix
    app.include_router(create_router(vault, prefix="/media-api", tags=["media"]))
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from stagvault.models.media import License, MediaGroup, MediaItem
from stagvault.search.query import SearchPreferences
from stagvault.vault import StagVault


# Response models
class SourceResponse(BaseModel):
    id: str
    name: str
    description: str | None
    type: str
    license: License
    homepage: str | None


class VariantResponse(BaseModel):
    id: str
    style: str | None
    path: str
    format: str


class GroupResponse(BaseModel):
    canonical_name: str
    source_id: str
    styles: list[str]
    variants: list[VariantResponse]
    tags: list[str]
    description: str | None


class ItemResponse(BaseModel):
    id: str
    source_id: str
    name: str
    canonical_name: str
    path: str
    format: str
    style: str | None
    tags: list[str]
    description: str | None


class SearchGroupedResponse(BaseModel):
    groups: list[GroupResponse]
    total: int


class SearchItemsResponse(BaseModel):
    items: list[ItemResponse]
    total: int


class StatsResponse(BaseModel):
    sources: dict[str, int]
    total: int


class StagVaultAPI:
    """Encapsulates StagVault API with dependency injection support."""

    def __init__(self, vault: StagVault) -> None:
        self.vault = vault

    def get_vault(self) -> StagVault:
        return self.vault


def create_router(
    vault: StagVault,
    *,
    prefix: str = "/svault",
    tags: list[str] | None = None,
) -> APIRouter:
    """Create a FastAPI router for StagVault.

    Args:
        vault: StagVault instance to use
        prefix: URL prefix for all routes (default: /svault)
        tags: OpenAPI tags for the router

    Returns:
        APIRouter that can be included in a FastAPI app
    """
    if tags is None:
        tags = ["stagvault"]

    router = APIRouter(prefix=prefix, tags=tags)
    api = StagVaultAPI(vault)

    def get_vault() -> StagVault:
        return api.vault

    # --- Search endpoints ---

    @router.get("/search", response_model=SearchGroupedResponse | SearchItemsResponse)
    async def search(
        q: Annotated[str, Query(min_length=1, description="Search query")],
        vault: Annotated[StagVault, Depends(get_vault)],
        grouped: bool = True,
        source_id: str | None = None,
        tags: Annotated[list[str] | None, Query()] = None,
        formats: Annotated[list[str] | None, Query()] = None,
        styles: Annotated[list[str] | None, Query()] = None,
        preferred_styles: Annotated[list[str] | None, Query()] = None,
        limit: int = Query(default=50, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> SearchGroupedResponse | SearchItemsResponse:
        """Search for media items.

        By default returns grouped results (icons with all style variants together).
        Set grouped=false to get individual items.
        """
        if grouped:
            prefs = SearchPreferences(
                preferred_styles=preferred_styles or ["regular", "outline"]
            )
            results = vault.search_grouped(
                q,
                source_id=source_id,
                tags=tags,
                formats=formats,
                preferences=prefs,
                limit=limit,
                offset=offset,
            )
            groups = [
                GroupResponse(
                    canonical_name=r.group.canonical_name,
                    source_id=r.group.source_id,
                    styles=r.group.styles,
                    variants=[
                        VariantResponse(
                            id=item.id,
                            style=item.style,
                            path=item.path,
                            format=item.format,
                        )
                        for item in r.group.items
                    ],
                    tags=r.group.items[0].tags if r.group.items else [],
                    description=r.group.items[0].description if r.group.items else None,
                )
                for r in results
            ]
            return SearchGroupedResponse(groups=groups, total=len(groups))
        else:
            results = vault.search(
                q,
                source_id=source_id,
                tags=tags,
                formats=formats,
                styles=styles,
                limit=limit,
                offset=offset,
            )
            items = [
                ItemResponse(
                    id=r.item.id,
                    source_id=r.item.source_id,
                    name=r.item.name,
                    canonical_name=r.item.canonical_name,
                    path=r.item.path,
                    format=r.item.format,
                    style=r.item.style,
                    tags=r.item.tags,
                    description=r.item.description,
                )
                for r in results
            ]
            return SearchItemsResponse(items=items, total=len(items))

    # --- Source endpoints ---

    @router.get("/sources", response_model=list[SourceResponse])
    async def list_sources(
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> list[SourceResponse]:
        """List all configured sources."""
        sources = vault.list_sources()
        return [
            SourceResponse(
                id=s.id,
                name=s.name,
                description=s.description,
                type=s.source_type,
                license=s.license,
                homepage=s.homepage,
            )
            for s in sources
        ]

    @router.get("/sources/{source_id}", response_model=SourceResponse)
    async def get_source(
        source_id: str,
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> SourceResponse:
        """Get source details by ID."""
        try:
            s = vault.get_source(source_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
        return SourceResponse(
            id=s.id,
            name=s.name,
            description=s.description,
            type=s.source_type,
            license=s.license,
            homepage=s.homepage,
        )

    @router.get("/sources/{source_id}/styles", response_model=list[str])
    async def list_source_styles(
        source_id: str,
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> list[str]:
        """List available styles for a source."""
        if source_id not in vault.configs:
            raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
        return vault.list_styles(source_id)

    # --- Media item endpoints ---

    @router.get("/media/{item_id}", response_model=ItemResponse)
    async def get_media_item(
        item_id: str,
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> ItemResponse:
        """Get media item by ID."""
        item = vault.get_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
        return ItemResponse(
            id=item.id,
            source_id=item.source_id,
            name=item.name,
            canonical_name=item.canonical_name,
            path=item.path,
            format=item.format,
            style=item.style,
            tags=item.tags,
            description=item.description,
        )

    @router.get("/media/{item_id}/file")
    async def get_media_file(
        item_id: str,
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> FileResponse:
        """Download media file."""
        item = vault.get_item(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")

        file_path = vault.get_file_path(item)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")

        media_types = {
            "svg": "image/svg+xml",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "mp3": "audio/mpeg",
            "wav": "audio/wav",
            "ogg": "audio/ogg",
        }
        media_type = media_types.get(item.format, "application/octet-stream")

        return FileResponse(
            file_path,
            media_type=media_type,
            filename=f"{item.name}.{item.format}",
        )

    # --- Group endpoints ---

    @router.get("/groups/{source_id}/{canonical_name}", response_model=GroupResponse)
    async def get_variants(
        source_id: str,
        canonical_name: str,
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> GroupResponse:
        """Get all style variants for an icon."""
        group = vault.get_variants(source_id, canonical_name)
        if group is None:
            raise HTTPException(
                status_code=404,
                detail=f"Icon not found: {source_id}/{canonical_name}",
            )
        return GroupResponse(
            canonical_name=group.canonical_name,
            source_id=group.source_id,
            styles=group.styles,
            variants=[
                VariantResponse(
                    id=item.id,
                    style=item.style,
                    path=item.path,
                    format=item.format,
                )
                for item in group.items
            ],
            tags=group.items[0].tags if group.items else [],
            description=group.items[0].description if group.items else None,
        )

    # --- Stats endpoint ---

    @router.get("/stats", response_model=StatsResponse)
    async def get_stats(
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> StatsResponse:
        """Get index statistics."""
        stats = vault.get_stats()
        total = stats.pop("total", 0)
        return StatsResponse(sources=stats, total=total)

    # --- Styles endpoint ---

    @router.get("/styles", response_model=list[str])
    async def list_all_styles(
        vault: Annotated[StagVault, Depends(get_vault)],
    ) -> list[str]:
        """List all available styles across all sources."""
        return vault.list_styles()

    return router
