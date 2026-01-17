"""CLI commands for StagVault."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

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
@click.pass_context
def sync(ctx: click.Context, source: str | None) -> None:
    """Sync (download/update) media sources."""
    vault: StagVault = ctx.obj["vault"]

    async def run() -> dict[str, int]:
        return await vault.sync(source)

    with console.status("Syncing sources..."):
        results = asyncio.run(run())

    table = Table(title="Sync Results")
    table.add_column("Source", style="cyan")
    table.add_column("Items", justify="right", style="green")

    for source_id, count in results.items():
        table.add_row(source_id, str(count))

    console.print(table)


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
    console.print(f"[green]Exported {count} {'groups' if grouped else 'items'} to {output}[/green]")


@main.command()
@click.argument("query")
@click.option("--source", "-s", default=None, help="Filter by source")
@click.option("--style", default=None, help="Filter by style")
@click.option("--limit", "-n", default=20, help="Max results")
@click.option("--grouped/--no-grouped", default=True, help="Group variants")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    source: str | None,
    style: str | None,
    limit: int,
    grouped: bool,
) -> None:
    """Search for media items."""
    vault: StagVault = ctx.obj["vault"]

    if grouped:
        results = vault.search_grouped(query, source_id=source, limit=limit)

        table = Table(title=f"Search: {query}")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="blue")
        table.add_column("Styles", style="yellow")

        for r in results:
            table.add_row(
                r.group.canonical_name,
                r.group.source_id,
                ", ".join(r.group.styles),
            )

        console.print(table)
        console.print(f"[dim]Found {len(results)} results[/dim]")
    else:
        results = vault.search(
            query,
            source_id=source,
            styles=[style] if style else None,
            limit=limit,
        )

        table = Table(title=f"Search: {query}")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="blue")
        table.add_column("Style", style="yellow")
        table.add_column("Path", style="dim")

        for r in results:
            table.add_row(
                r.item.name,
                r.item.source_id,
                r.item.style or "-",
                r.item.path,
            )

        console.print(table)
        console.print(f"[dim]Found {len(results)} results[/dim]")


@main.command()
@click.pass_context
def sources(ctx: click.Context) -> None:
    """List configured sources."""
    vault: StagVault = ctx.obj["vault"]

    table = Table(title="Configured Sources")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("License", style="blue")
    table.add_column("Synced", justify="center")

    for source in vault.list_sources():
        handler = vault.get_handler(source.id)
        synced = "[green]Yes[/green]" if handler.is_synced() else "[red]No[/red]"
        table.add_row(
            source.id,
            source.name,
            source.source_type,
            source.license.spdx,
            synced,
        )

    console.print(table)


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


if __name__ == "__main__":
    main()
