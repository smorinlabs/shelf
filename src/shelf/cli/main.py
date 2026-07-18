"""shelf CLI entry point."""
from importlib.metadata import version

import click

_VERSION = version("shelf")


@click.group("shelf", invoke_without_command=True)
@click.version_option(_VERSION, "-V", "--version", prog_name="shelf", message="shelf %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Shelf — a private documentation library."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)
