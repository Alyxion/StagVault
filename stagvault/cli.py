"""CLI commands for StagVault."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from stagvault.models.source_info import SourceStatus
from stagvault.thumbnails import ThumbnailSize
from stagvault.vault import StagVault

console = Console()


def get_vault(data_dir: str, config_dir: str, index_dir: str | None) -> StagVault:
    return StagVault(data_dir, config_dir, index_dir)


@click.group()
@click.option("--data-dir", default="./data", help="Data directory")
@click.option("--config-dir", default="./configs", help="Config directory")
@click.option("--index-dir", default=None, help="Index directory")
@click.pass_context
def main(ctx: click.Context, data_dir: str, config_dir: str, index_dir: str | None) -> None:
    """StagVault - Media database CLI."""
    ctx.ensure_object(dict)
    ctx.obj["vault"] = get_vault(data_dir, config_dir, index_dir)


@main.command()
@click.option("--source", "-s", default=None, help="Specific source to sync")
@click.option("--thumbnails", is_flag=True, help="Generate thumbnails (disabled by default)")
@click.pass_context
def sync(ctx: click.Context, source: str | None, thumbnails: bool) -> None:
    """Sync (download/update) media sources."""
    vault: StagVault = ctx.obj["vault"]

    async def run() -> dict[str, int]:
        return await vault.sync(source, thumbnails=thumbnails)

    with console.status("Syncing sources..."):
        results = asyncio.run(run())

    table = Table(title="Sync Results")
    table.add_column("Source", style="cyan")
    table.add_column("Items", justify="right", style="green")

    for source_id, count in results.items():
        table.add_row(source_id, str(count))

    console.print(table)

    if thumbnails:
        # Show thumbnail stats for synced git sources
        thumb_stats = vault.get_thumbnail_stats()
        if thumb_stats.get("total_count", 0) > 0:
            console.print(
                f"[dim]Thumbnails: {thumb_stats['total_count']} generated[/dim]"
            )


@main.command()
@click.option("--source", "-s", default=None, help="Specific source to index")
@click.pass_context
def index(ctx: click.Context, source: str | None) -> None:
    """Build or rebuild the search index."""
    vault: StagVault = ctx.obj["vault"]

    async def run() -> dict[str, int]:
        return await vault.build_index(source)

    with console.status("Building index..."):
        results = asyncio.run(run())

    table = Table(title="Index Results")
    table.add_column("Source", style="cyan")
    table.add_column("Items Indexed", justify="right", style="green")

    for source_id, count in results.items():
        table.add_row(source_id, str(count))

    console.print(table)


@main.command()
@click.option("--output", "-o", default="./static/index.json", help="Output path")
@click.option("--grouped/--no-grouped", default=True, help="Export grouped format")
@click.pass_context
def export(ctx: click.Context, output: str, grouped: bool) -> None:
    """Export index to JSON for static deployment."""
    vault: StagVault = ctx.obj["vault"]

    count = vault.export_json(Path(output), grouped=grouped)
    console.print(
        f"[green]Exported {count} {'groups' if grouped else 'items'} to {output}[/green]"
    )


@main.command()
@click.argument("query")
@click.option("--mode", "-m", type=click.Choice(["python", "rest", "static"]), default="python",
              help="Search mode: python (direct API), rest (FastAPI), static (JSON files)")
@click.option("--source", "-s", multiple=True, help="Include specific sources (can repeat)")
@click.option("--exclude-source", "-xs", multiple=True, help="Exclude specific sources")
@click.option("--license", "-l", "licenses", multiple=True, help="Include specific licenses")
@click.option("--exclude-license", "-xl", multiple=True, help="Exclude specific licenses")
@click.option("--style", default=None, help="Filter by style")
@click.option("--limit", "-n", default=20, help="Max results")
@click.option("--grouped/--no-grouped", default=True, help="Group variants")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    mode: str,
    source: tuple[str, ...],
    exclude_source: tuple[str, ...],
    licenses: tuple[str, ...],
    exclude_license: tuple[str, ...],
    style: str | None,
    limit: int,
    grouped: bool,
) -> None:
    """Search for media items.

    Supports three modes:
    - python: Direct Python API (default, full features)
    - rest: Via FastAPI endpoints
    - static: Using same JSON files as static website (git sources only)
    """
    vault: StagVault = ctx.obj["vault"]

    # Convert tuples to sets for filtering
    include_sources = set(source) if source else None
    exclude_sources = set(exclude_source) if exclude_source else None
    include_licenses = set(licenses) if licenses else None
    exclude_licenses = set(exclude_license) if exclude_license else None

    if mode == "static":
        # Static mode uses precomputed JSON files
        _search_static(ctx, query, include_sources, exclude_sources,
                       include_licenses, exclude_licenses, limit, grouped)
        return

    if mode == "rest":
        # REST mode uses FastAPI endpoints
        _search_rest(ctx, query, include_sources, exclude_sources,
                     include_licenses, exclude_licenses, style, limit, grouped)
        return

    # Python mode (default)
    if grouped:
        results = vault.search_grouped(query, source_id=list(source)[0] if len(source) == 1 else None, limit=limit)

        # Apply source/license filters
        filtered = []
        for r in results:
            if include_sources and r.group.source_id not in include_sources:
                continue
            if exclude_sources and r.group.source_id in exclude_sources:
                continue
            # License filtering would need item-level check
            filtered.append(r)

        table = Table(title=f"Search: {query} (mode: {mode})")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="blue")
        table.add_column("Styles", style="yellow")

        for r in filtered[:limit]:
            table.add_row(
                r.group.canonical_name,
                r.group.source_id,
                ", ".join(r.group.styles),
            )

        console.print(table)
        console.print(f"[dim]Found {len(filtered)} results[/dim]")
    else:
        results = vault.search(
            query,
            source_id=list(source)[0] if len(source) == 1 else None,
            styles=[style] if style else None,
            limit=limit * 2,  # Get more to filter
        )

        # Apply source/license filters
        filtered = []
        for r in results:
            if include_sources and r.item.source_id not in include_sources:
                continue
            if exclude_sources and r.item.source_id in exclude_sources:
                continue
            if r.item.license:
                lic = r.item.license.spdx or r.item.license.name
                if include_licenses and lic not in include_licenses:
                    continue
                if exclude_licenses and lic in exclude_licenses:
                    continue
            filtered.append(r)

        table = Table(title=f"Search: {query} (mode: {mode})")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="blue")
        table.add_column("Style", style="yellow")
        table.add_column("Path", style="dim")

        for r in filtered[:limit]:
            table.add_row(
                r.item.name,
                r.item.source_id,
                r.item.style or "-",
                r.item.path,
            )

        console.print(table)
        console.print(f"[dim]Found {len(filtered)} results[/dim]")


def _search_static(
    ctx: click.Context,
    query: str,
    include_sources: set[str] | None,
    exclude_sources: set[str] | None,
    include_licenses: set[str] | None,
    exclude_licenses: set[str] | None,
    limit: int,
    grouped: bool,
) -> None:
    """Search using static JSON files (same as static website)."""
    import json

    vault: StagVault = ctx.obj["vault"]

    # Try to find static index
    static_paths = [
        Path("./static/index"),
        Path("./static_site/index/index"),
        vault.data_dir.parent / "static" / "index",
    ]

    index_dir = None
    for path in static_paths:
        if (path / "search").exists():
            index_dir = path
            break

    if not index_dir:
        console.print("[red]Static index not found. Run 'stagvault static build' first.[/red]")
        return

    # Load sources metadata
    sources_file = index_dir / "sources.json"
    if sources_file.exists():
        sources_data = json.loads(sources_file.read_text())
        if isinstance(sources_data, dict):
            sources = {s["id"]: s for s in sources_data.get("sources", [])}
        else:
            sources = {s["id"]: s for s in sources_data}
    else:
        sources = {}

    # Extract prefix from query
    query_lower = query.lower()
    if len(query_lower) < 2:
        console.print("[yellow]Query must be at least 2 characters[/yellow]")
        return

    prefix = query_lower[:2]
    prefix_file = index_dir / "search" / f"{prefix}.json"

    if not prefix_file.exists():
        console.print(f"[yellow]No results for '{query}'[/yellow]")
        return

    # Load and filter results
    items = json.loads(prefix_file.read_text())

    # Filter by query match
    filtered = []
    for item in items:
        name = item.get("n", "").lower()
        tags = [t.lower() for t in item.get("t", [])]

        # Check if query matches name or tags
        if query_lower in name or any(query_lower in t for t in tags):
            # Apply source filters
            source_id = item.get("s")
            if include_sources and source_id not in include_sources:
                continue
            if exclude_sources and source_id in exclude_sources:
                continue

            # Apply license filters
            item_license = item.get("l") or sources.get(source_id, {}).get("license")
            if include_licenses and item_license not in include_licenses:
                continue
            if exclude_licenses and item_license in exclude_licenses:
                continue

            filtered.append(item)

    # Display results
    table = Table(title=f"Search: {query} (mode: static)")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="blue")
    table.add_column("Style", style="yellow")

    for item in filtered[:limit]:
        table.add_row(
            item.get("n", ""),
            item.get("s", ""),
            item.get("y", "-"),
        )

    console.print(table)
    console.print(f"[dim]Found {len(filtered)} results (static mode)[/dim]")


def _search_rest(
    ctx: click.Context,
    query: str,
    include_sources: set[str] | None,
    exclude_sources: set[str] | None,
    include_licenses: set[str] | None,
    exclude_licenses: set[str] | None,
    style: str | None,
    limit: int,
    grouped: bool,
) -> None:
    """Search using REST API endpoints."""
    import urllib.request
    import urllib.parse
    import json

    # Build URL
    params = {"q": query, "limit": str(limit), "grouped": str(grouped).lower()}
    if include_sources:
        params["sources"] = ",".join(include_sources)
    if style:
        params["style"] = style

    url = f"http://localhost:8000/svault/search?{urllib.parse.urlencode(params)}"

    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        console.print(f"[red]REST API error: {e}[/red]")
        console.print("[dim]Make sure the API server is running: stagvault serve[/dim]")
        return

    # Apply additional filters that REST might not support
    results = data.get("results", data) if isinstance(data, dict) else data

    # Display results
    table = Table(title=f"Search: {query} (mode: rest)")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="blue")
    if grouped:
        table.add_column("Styles", style="yellow")
    else:
        table.add_column("Style", style="yellow")

    for item in results[:limit]:
        if grouped:
            table.add_row(
                item.get("canonical_name", item.get("name", "")),
                item.get("source_id", ""),
                ", ".join(item.get("styles", [])),
            )
        else:
            table.add_row(
                item.get("name", ""),
                item.get("source_id", ""),
                item.get("style", "-"),
            )

    console.print(table)
    console.print(f"[dim]Found {len(results)} results (rest mode)[/dim]")


# Sources command group


@main.group()
def sources() -> None:
    """Manage data sources."""
    pass


@sources.command("list")
@click.option("--installed", is_flag=True, help="Only show installed sources")
@click.option("--available", is_flag=True, help="Only show available (not synced)")
@click.pass_context
def sources_list(ctx: click.Context, installed: bool, available: bool) -> None:
    """List configured sources."""
    vault: StagVault = ctx.obj["vault"]

    status_filter = None
    if installed:
        status_filter = SourceStatus.INSTALLED
    elif available:
        status_filter = SourceStatus.AVAILABLE

    sources_list = vault.list_sources(status=status_filter)

    table = Table(title="Configured Sources")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("Status", justify="center")
    table.add_column("Items", justify="right")
    table.add_column("Thumbnails", justify="right")
    table.add_column("Disk Usage", justify="right")

    for info in sources_list:
        status_style = "green" if info.is_installed else "yellow"
        status_text = f"[{status_style}]{info.status.value}[/{status_style}]"

        items = str(info.item_count) if info.item_count is not None else "-"
        thumbs = str(info.thumbnail_count) if info.thumbnail_count is not None else "-"
        disk = info.disk_usage_formatted

        table.add_row(
            info.id,
            info.name,
            info.source_type,
            status_text,
            items,
            thumbs,
            disk,
        )

    console.print(table)


@sources.command("add")
@click.argument("source_id")
@click.option("--no-sync", is_flag=True, help="Don't sync after adding")
@click.option("--thumbnails", is_flag=True, help="Generate thumbnails (disabled by default)")
@click.pass_context
def sources_add(
    ctx: click.Context, source_id: str, no_sync: bool, thumbnails: bool
) -> None:
    """Add/install a source."""
    vault: StagVault = ctx.obj["vault"]

    async def run() -> None:
        await vault.add_source(
            source_id, sync=not no_sync, thumbnails=thumbnails
        )

    with console.status(f"Adding source {source_id}..."):
        asyncio.run(run())

    info = vault.get_source_info(source_id)
    console.print(f"[green]Added source: {info.name}[/green]")

    if info.item_count:
        console.print(f"  Items: {info.item_count}")
    if info.thumbnail_count:
        console.print(f"  Thumbnails: {info.thumbnail_count}")


@sources.command("remove")
@click.argument("source_id")
@click.option("--purge", is_flag=True, help="Also remove config file")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def sources_remove(
    ctx: click.Context, source_id: str, purge: bool, yes: bool
) -> None:
    """Remove a source's data."""
    vault: StagVault = ctx.obj["vault"]

    info = vault.get_source_info(source_id)

    if not yes:
        msg = f"Remove data for '{info.name}'"
        if purge:
            msg += " (including config)"
        msg += "?"
        if not click.confirm(msg):
            console.print("[yellow]Cancelled[/yellow]")
            return

    async def run() -> None:
        await vault.remove_source(source_id, purge_config=purge)

    asyncio.run(run())
    console.print(f"[green]Removed source: {source_id}[/green]")


@sources.command("info")
@click.argument("source_id")
@click.pass_context
def sources_info(ctx: click.Context, source_id: str) -> None:
    """Show detailed info about a source."""
    vault: StagVault = ctx.obj["vault"]

    info = vault.get_source_info(source_id)

    console.print(f"[bold cyan]{info.name}[/bold cyan] ({info.id})")
    console.print(f"  Type: {info.source_type}")
    console.print(f"  Status: {info.status.value}")

    if info.description:
        console.print(f"  Description: {info.description}")
    if info.homepage:
        console.print(f"  Homepage: {info.homepage}")
    if info.item_count is not None:
        console.print(f"  Items: {info.item_count}")
    if info.thumbnail_count is not None:
        console.print(f"  Thumbnails: {info.thumbnail_count}")
    if info.disk_usage_bytes is not None:
        console.print(f"  Disk usage: {info.disk_usage_formatted}")
    if info.last_synced:
        console.print(f"  Last synced: {info.last_synced.isoformat()}")


# Thumbnails command group


@main.group()
def thumbnails() -> None:
    """Manage thumbnail generation."""
    pass


@thumbnails.command("generate")
@click.option("--source", "-s", default=None, help="Specific source")
@click.option("--size", "-z", multiple=True, type=int, help="Specific sizes only")
@click.option("--force", "-f", is_flag=True, help="Regenerate existing thumbnails")
@click.pass_context
def thumbnails_generate(
    ctx: click.Context, source: str | None, size: tuple[int, ...], force: bool
) -> None:
    """Generate thumbnails for git sources."""
    vault: StagVault = ctx.obj["vault"]

    sizes = list(size) if size else None
    sources_to_process = [source] if source else list(vault.configs.keys())

    total_generated = 0
    total_skipped = 0
    total_failed = 0

    for sid in sources_to_process:
        config = vault.configs.get(sid)
        if config is None or not config.is_git_source:
            continue

        handler = vault.get_handler(sid)
        if not handler.is_synced():
            console.print(f"[yellow]Skipping {sid} (not synced)[/yellow]")
            continue

        async def get_items() -> list:
            return await handler.scan()

        items = asyncio.run(get_items())
        source_dir = vault.data_dir / sid

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Generating thumbnails for {sid}...", total=None)

            result = vault.thumbnail_generator.generate_for_source(
                sid, items, source_dir, sizes=sizes, force=force
            )

        total_generated += result.generated_jpg + result.generated_png
        total_skipped += result.skipped
        total_failed += result.failed

        if result.errors:
            for item_id, error in result.errors[:5]:
                console.print(f"[red]  Error: {item_id}: {error}[/red]")
            if len(result.errors) > 5:
                console.print(f"[red]  ... and {len(result.errors) - 5} more[/red]")

    console.print(f"[green]Generated: {total_generated}[/green]")
    console.print(f"[dim]Skipped: {total_skipped}[/dim]")
    if total_failed:
        console.print(f"[red]Failed: {total_failed}[/red]")


@thumbnails.command("clear")
@click.option("--source", "-s", default=None, help="Specific source only")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def thumbnails_clear(ctx: click.Context, source: str | None, yes: bool) -> None:
    """Clear thumbnail cache."""
    vault: StagVault = ctx.obj["vault"]

    if not yes:
        msg = f"Clear thumbnails for {source}" if source else "Clear all thumbnails"
        if not click.confirm(msg + "?"):
            console.print("[yellow]Cancelled[/yellow]")
            return

    if source:
        count = vault.thumbnail_generator.clear_source(source)
    else:
        count = vault.thumbnail_generator.clear_all()

    console.print(f"[green]Cleared {count} thumbnail entries[/green]")


@thumbnails.command("stats")
@click.pass_context
def thumbnails_stats(ctx: click.Context) -> None:
    """Show thumbnail cache statistics."""
    vault: StagVault = ctx.obj["vault"]

    stats = vault.get_thumbnail_stats()

    console.print("[bold]Thumbnail Statistics[/bold]")
    console.print(f"  Total: {stats['total_count']}")
    console.print(f"  Size: {_format_bytes(stats['total_size_bytes'])}")

    if stats.get("sources"):
        console.print("\n[bold]By Source:[/bold]")
        for source_id, count in sorted(stats["sources"].items()):
            console.print(f"  {source_id}: {count}")

    if stats.get("sizes"):
        console.print("\n[bold]By Size:[/bold]")
        for size, count in sorted(stats["sizes"].items()):
            size_name = ThumbnailSize.from_int(size)
            label = f"{size}px ({size_name.name})" if size_name else f"{size}px"
            console.print(f"  {label}: {count}")


def _format_bytes(size: int) -> str:
    """Format bytes to human readable."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@main.command()
@click.option("--source", "-s", default=None, help="Filter by source")
@click.pass_context
def styles(ctx: click.Context, source: str | None) -> None:
    """List available styles."""
    vault: StagVault = ctx.obj["vault"]

    style_list = vault.list_styles(source)

    if style_list:
        console.print("[bold]Available styles:[/bold]")
        for s in style_list:
            console.print(f"  - {s}")
    else:
        console.print("[yellow]No styles found (index may be empty)[/yellow]")


@main.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show index statistics."""
    vault: StagVault = ctx.obj["vault"]

    stats = vault.get_stats()
    total = stats.pop("total", 0)

    table = Table(title="Index Statistics")
    table.add_column("Source", style="cyan")
    table.add_column("Items", justify="right", style="green")

    for source_id, count in sorted(stats.items()):
        table.add_row(source_id, str(count))

    table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
    console.print(table)

    # Also show thumbnail stats
    thumb_stats = vault.get_thumbnail_stats()
    if thumb_stats.get("total_count", 0) > 0:
        console.print(
            f"\n[dim]Thumbnails: {thumb_stats['total_count']} "
            f"({_format_bytes(thumb_stats['total_size_bytes'])})[/dim]"
        )


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind")
@click.option("--port", "-p", default=8000, help="Port to bind")
@click.option("--prefix", default="/svault", help="API prefix")
@click.pass_context
def serve(ctx: click.Context, host: str, port: int, prefix: str) -> None:
    """Start the API server."""
    import uvicorn
    from fastapi import FastAPI

    from stagvault.api import create_router

    vault: StagVault = ctx.obj["vault"]

    app = FastAPI(title="StagVault API")
    app.include_router(create_router(vault, prefix=prefix))

    console.print(f"[green]Starting server at http://{host}:{port}{prefix}[/green]")
    uvicorn.run(app, host=host, port=port)


# Static site commands


@main.group()
def static() -> None:
    """Build and serve static site."""
    pass


@static.command("build")
@click.option("--output", "-o", default="./static", help="Output directory")
@click.option("--thumbnails", "-t", is_flag=True, help="Include thumbnails (64px JPG)")
@click.pass_context
def static_build(ctx: click.Context, output: str, thumbnails: bool) -> None:
    """Build static index for client-side search."""
    import shutil

    from stagvault.static import StaticIndexBuilder

    vault: StagVault = ctx.obj["vault"]

    # Get all items from index
    items = vault.query.list_all()
    if not items:
        console.print("[yellow]No items in index. Run 'stagvault index' first.[/yellow]")
        return

    # Get source metadata
    sources = {}
    for source_id, config in vault.configs.items():
        license_name = "unknown"
        if hasattr(config, "license") and config.license:
            license_name = config.license.spdx or config.license.name or "unknown"
        sources[source_id] = {
            "name": config.name,
            "type": config.source_type,
            "license": license_name,
            "category": config.category,
            "subcategory": config.subcategory,
        }

    output_path = Path(output)
    output_path.mkdir(parents=True, exist_ok=True)

    # Build search index
    builder = StaticIndexBuilder(
        output_path / "index",
        data_dir=vault.data_dir if thumbnails else None,
    )

    status_msg = "Building static index"
    if thumbnails:
        status_msg += " with thumbnails"
    status_msg += "..."

    with console.status(status_msg):
        stats = builder.build(items, sources, include_thumbnails=thumbnails)

    # Copy web files
    web_src = Path(__file__).parent / "static" / "web"
    if web_src.exists():
        for file in web_src.iterdir():
            if file.is_file():
                shutil.copy(file, output_path / file.name)

    console.print("[green]Static site built successfully![/green]")
    console.print(f"  Items: {stats['total_items']}")
    console.print(f"  Sources: {stats['sources']}")
    console.print(f"  Licenses: {stats['licenses']}")
    console.print(f"  Tags: {stats['tags']}")
    console.print(f"  Search files: {stats['prefix_files']}")
    if thumbnails:
        console.print(f"  Thumbnails: {stats['thumbnails_copied']}")
    console.print(f"\n  Output: {output_path.absolute()}")
    console.print(f"\n  Run: stagvault static serve -d {output}")


@static.command("serve")
@click.option("--dir", "-d", "directory", default="./static", help="Static files directory")
@click.option("--port", "-p", default=8080, help="Port to bind")
@click.pass_context
def static_serve(ctx: click.Context, directory: str, port: int) -> None:
    """Serve static files with basic HTTP server."""
    import http.server
    import os
    import socketserver

    dir_path = Path(directory).resolve()
    if not dir_path.exists():
        console.print(f"[red]Directory not found: {directory}[/red]")
        console.print("Run 'stagvault static build' first.")
        return

    os.chdir(dir_path)

    handler = http.server.SimpleHTTPRequestHandler

    # Add CORS headers
    class CORSHandler(handler):
        def end_headers(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

    with socketserver.TCPServer(("", port), CORSHandler) as httpd:
        console.print(f"[green]Serving static files at http://localhost:{port}[/green]")
        console.print(f"  Directory: {dir_path}")
        console.print("  Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            console.print("\n[yellow]Server stopped[/yellow]")


if __name__ == "__main__":
    main()
