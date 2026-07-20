"""Open the generated Shelf UI."""

import webbrowser

import click

from shelf.cli.runtime import get_config, get_library
from shelf.server.serve import serve


def _launch(url: str) -> None:
    """Open a URL in the default browser."""
    webbrowser.open(url)


@click.command("open")
@click.option("--static", "static_", is_flag=True, help="Open the on-disk static index.")
@click.pass_context
def open_cmd(ctx: click.Context, static_: bool) -> None:
    """Open the library UI."""
    root = get_library(ctx)
    if static_:
        _launch((root / "index.html").resolve().as_uri())
        return

    config = get_config(ctx)
    _, port = serve(root, config.server_port)
    _launch(f"http://127.0.0.1:{port}")
