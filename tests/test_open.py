"""P06-T04 — shelf open: --static, enhanced reuse/host, and process persistence.

PRD §11.7: enhanced `shelf open` must *reuse* an already-running instance rather than
starting a second server, and when it does start one it must *host* it in the
foreground — blocking like `python -m http.server` — so the standalone `shelf` process
stays alive to serve the browser it just opened. A daemon-thread server that returns
control to the CLI dies the instant the process exits, which killed the browser's
connection before it could ever load the page.

`open_cmd`'s corrected model exposes three seams:
  - `_launch(url)` — opens a URL in the browser.
  - `_probe(port) -> bool` — True if a shelf server already answers on that port.
  - `_serve_blocking(server)` — blocks serving until interrupted (Ctrl-C); a no-op
    monkeypatch here so unit tests don't hang.

Unit tests below monkeypatch these seams (and `shelf.cli.open_cmd.serve`, imported via
`from shelf.server.serve import serve`, same style as `test_server.py`) so nothing binds
a real socket or starts a real thread. That is also exactly why the old test suite could
not catch the daemon-thread-dies bug: a mocked `serve` never proves the process survives.
The integration test at the bottom closes that gap by driving a real `shelf open`
subprocess and polling its port from outside the process.
"""

import os
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.config import ShelfConfig, default_config_path, save_config
from shelf.core.paths import default_library_path

REPO_ROOT = Path(__file__).resolve().parent.parent


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


# --- enhanced (default): reuse an already-running instance, else host a new one --


def test_open_enhanced_reuses_running_server(monkeypatch):
    """When `_probe` finds a server already answering, `shelf open` must just point the
    browser at it — never start a second server on top of it."""
    root = _init()
    save_config(default_config_path(), ShelfConfig(library=str(root), server_port=9010))

    launched = []
    monkeypatch.setattr("shelf.cli.open_cmd._launch", launched.append)
    monkeypatch.setattr("shelf.cli.open_cmd._probe", lambda port: True)

    serve_calls = []
    monkeypatch.setattr(
        "shelf.cli.open_cmd.serve",
        lambda root_, port: serve_calls.append((root_, port)) or (_FakeServer(port), port),
    )

    r = run(["open"])

    assert r.exit_code == 0, r.output
    assert serve_calls == []  # an existing server already answers — no new one is started
    assert launched == ["http://127.0.0.1:9010"]


def test_open_enhanced_hosts_new_server_when_none_running(monkeypatch):
    """When `_probe` finds nothing listening, `shelf open` must start a server on the
    resolved (configured) port and hand it to `_serve_blocking` to host in the
    foreground — the seam that keeps the real CLI process (and therefore the server)
    alive for the browser."""
    root = _init()
    save_config(default_config_path(), ShelfConfig(library=str(root), server_port=9020))

    launched = []
    monkeypatch.setattr("shelf.cli.open_cmd._launch", launched.append)
    monkeypatch.setattr("shelf.cli.open_cmd._probe", lambda port: False)
    monkeypatch.setattr("shelf.cli.open_cmd._serve_blocking", lambda server: None)

    serve_calls = []

    def fake_serve(root_, port):
        serve_calls.append((root_, port))
        return _FakeServer(port), port

    monkeypatch.setattr("shelf.cli.open_cmd.serve", fake_serve)

    r = run(["open"])

    assert r.exit_code == 0, r.output
    assert len(serve_calls) == 1
    assert serve_calls[0][1] == 9020  # started on the resolved (configured) port
    assert launched == ["http://127.0.0.1:9020"]


# --- unconfigured library: exit 1 with `shelf init` guidance, before doing anything --


@pytest.mark.parametrize("args", [["open"], ["open", "--static"]])
def test_open_unconfigured_library_errors_with_guidance(isolated_env, args):
    r = run(args)
    assert r.exit_code == 1
    assert "shelf init" in r.output


# --- INTEGRATION: the server must outlive the launching call, for real ------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _poll_for_200(url: str, timeout: float = 6.0, interval: float = 0.2) -> str:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
        time.sleep(interval)
    raise AssertionError(f"{url} never answered 200 within {timeout}s (last error: {last_error})")


def _poll_until_unreachable(url: str, timeout: float = 5.0, interval: float = 0.2) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
        except (urllib.error.URLError, OSError):
            return
        time.sleep(interval)
    raise AssertionError(f"{url} still answering {timeout}s after the server was terminated")


def test_open_enhanced_host_mode_persists_server_for_the_browser():
    """This is the bug the mocked unit tests above cannot see: a `shelf open` that
    starts its server on a daemon thread and returns dies with the CLI process, so the
    browser it just opened gets a dead port. Host mode must instead block the
    foreground process until interrupted.

    This drives a real, isolated `shelf open` subprocess (its own XDG_CONFIG_HOME /
    XDG_DATA_HOME via the autouse `isolated_env` fixture) and polls its port from
    *outside* the process — something no in-process mock of `serve`/`_launch` can prove.
    If the process exits (or the port never answers) the server did not persist.
    """
    if shutil.which("uv") is None:
        pytest.skip("uv not on PATH")

    root = _init()
    try:
        port = _free_port()
    except OSError:
        pytest.skip("could not allocate a free loopback port")
    save_config(default_config_path(), ShelfConfig(library=str(root), server_port=port))

    env = dict(os.environ)
    # Neutralize the real browser launch (`_launch` is unchanged, real `webbrowser.open`
    # runs inside the subprocess) — a GUI browser must not pop up during a test run.
    env["BROWSER"] = "true"

    proc = subprocess.Popen(
        ["uv", "run", "shelf", "open"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        body = _poll_for_200(f"http://127.0.0.1:{port}/")
        assert "shelf:fingerprint" in body or 'id="kopen"' in body
    finally:
        if proc.poll() is None:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait(timeout=5)
        _poll_until_unreachable(f"http://127.0.0.1:{port}/")
