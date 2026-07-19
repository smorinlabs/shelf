"""Library-level commands: path (this task); init/adopt and migrate follow."""

import click

from shelf.cli.runtime import active_config_path, get_library


@click.command("path")
@click.argument("which", required=False, type=click.Choice(["config", "index"]))
@click.pass_context
def path_cmd(ctx: click.Context, which: str | None) -> None:
    """Print resolved locations."""
    if which == "config":
        click.echo(active_config_path(ctx))
        return
    root = get_library(ctx)
    click.echo(root / "index.html" if which == "index" else root)
