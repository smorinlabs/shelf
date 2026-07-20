"""Open the generated Shelf UI."""

import urllib.request
import webbrowser
from socketserver import BaseServer

import click

from shelf.cli.runtime import get_config, get_library
from shelf.server.serve import serve


def _launch(url: str) -> None:
    """Open a URL in the default browser."""
    webbrowser.open(url)


def _probe(port: int) -> bool:
    """Return whether a Shelf server is already answering on the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.5) as response:
            return response.status == 200 and b"shelf:fingerprint" in response.read()
    except Exception:
        return False


def _serve_blocking(server: BaseServer) -> None:
    """Serve in the foreground until interrupted, then shut down cleanly."""
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


@click.command("open")
@click.option("--static", "static_", is_flag=True, help="Open the on-disk static index.")
@click.pass_context
def open_cmd(ctx: click.Context, static_: bool) -> None:
    """Open the library UI."""
    root = get_library(ctx)
    if static_:
        _launch((root / "index.html").resolve().as_uri())
        return

    port = get_config(ctx).server_port
    if _probe(port):
        _launch(f"http://127.0.0.1:{port}")
        return

    server, actual = serve(root, port)
    _launch(f"http://127.0.0.1:{actual}")
    _serve_blocking(server)
