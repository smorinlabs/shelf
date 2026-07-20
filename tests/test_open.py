"""P06-T04 — shelf open: --static and enhanced server modes (red).

`open_cmd`'s browser launch goes through an injectable seam, `shelf.cli.open_cmd._launch`,
so these tests capture the URL instead of spawning a real browser.

For the enhanced (server) mode, `shelf.cli.open_cmd.serve` is monkeypatched to a fake that
returns a stand-in server object and a fixed port — this avoids binding a real socket or
starting a real daemon thread inside the test, so there is nothing left to tear down. This
assumes the implementation calls `serve` via the name imported into `shelf.cli.open_cmd`
(`from shelf.server.serve import serve`), the same import style `test_server.py` uses.
"""

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.config import ShelfConfig, default_config_path, save_config
from shelf.core.paths import default_library_path


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    return default_library_path()


class _FakeServer:
    def __init__(self, port):
        self.server_address = ("127.0.0.1", port)

    def shutdown(self):
        pass

    def server_close(self):
        pass


# --- --static: opens the on-disk index.html as a file:// URL -------------------


def test_open_static_opens_index_html_as_file_url(monkeypatch):
    root = _init()
    launched = []
    monkeypatch.setattr("shelf.cli.open_cmd._launch", launched.append)

    r = run(["open", "--static"])

    assert r.exit_code == 0, r.output
    assert len(launched) == 1
    index_path = (root / "index.html").resolve()
    assert launched[0] == index_path.as_uri()
    assert launched[0].startswith("file://")
    assert launched[0].endswith("index.html")


# --- open (enhanced, default): starts the server, opens http://127.0.0.1:<port> --


def test_open_enhanced_starts_server_and_opens_its_port(monkeypatch):
    _init()
    launched = []
    monkeypatch.setattr("shelf.cli.open_cmd._launch", launched.append)

    fake_port = 55123
    calls = []

    def fake_serve(root, port):
        calls.append((root, port))
        return _FakeServer(fake_port), fake_port

    monkeypatch.setattr("shelf.cli.open_cmd.serve", fake_serve)

    r = run(["open"])

    assert r.exit_code == 0, r.output
    assert len(calls) == 1  # the real server was never started — no socket, no thread
    assert len(launched) == 1
    assert launched[0] == f"http://127.0.0.1:{fake_port}"


def test_open_enhanced_uses_configured_server_port(monkeypatch):
    root = _init()
    save_config(default_config_path(), ShelfConfig(library=str(root), server_port=9001))
    monkeypatch.setattr("shelf.cli.open_cmd._launch", lambda url: None)

    requested_ports = []

    def fake_serve(root_, port):
        requested_ports.append(port)
        return _FakeServer(port), port

    monkeypatch.setattr("shelf.cli.open_cmd.serve", fake_serve)

    r = run(["open"])

    assert r.exit_code == 0, r.output
    assert requested_ports == [9001]


# --- unconfigured library: exit 1 with `shelf init` guidance, before doing anything --


@pytest.mark.parametrize("args", [["open"], ["open", "--static"]])
def test_open_unconfigured_library_errors_with_guidance(isolated_env, args):
    r = run(args)
    assert r.exit_code == 1
    assert "shelf init" in r.output
