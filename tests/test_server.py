"""P06-T03 — hardened local server: PAGE.root injection, traversal defense, port fallback (red)."""

import json
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

TOPIC = "guides"

_PAGE_RE = re.compile(r"const PAGE = (.*?);", re.DOTALL)


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", TOPIC]).exit_code == 0
    return default_library_path()


def _add_doc(tmp_path, *, title, body, name):
    src = tmp_path / name
    src.write_text(body, encoding="utf-8")
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            TOPIC,
            "--kind",
            "reference",
            "--title",
            title,
            "--description",
            f"About {title}",
        ]
    )
    assert r.exit_code == 0, r.output


def _extract_page(html_text: str) -> dict:
    match = _PAGE_RE.search(html_text)
    assert match is not None, "no `const PAGE = ...;` data site found in response body"
    return json.loads(match.group(1))


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _get(url):
    """GET url, returning (status, body) whether or not the server errors."""
    try:
        with urllib.request.urlopen(url) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture
def library_root(isolated_env, tmp_path):
    """A real library, seeded with one doc via the CLI, then regenerated."""
    root = _init()
    _add_doc(
        tmp_path, title="Hello Doc", body="# Hello Doc\n\nHello doc body text.", name="hello.md"
    )
    assert run(["regen"]).exit_code == 0
    return root


@pytest.fixture
def running_server(library_root):
    """A real serve() instance on a background thread, always torn down."""
    from shelf.server.serve import serve

    server, port = serve(library_root, _free_port())
    base_url = f"http://127.0.0.1:{port}"
    try:
        yield server, port, base_url
    finally:
        server.shutdown()
        server.server_close()


# --- find_free_port -----------------------------------------------------------


def test_find_free_port_returns_preferred_when_free():
    from shelf.server.serve import find_free_port

    port = _free_port()
    assert find_free_port(port) == port


def test_find_free_port_returns_different_free_port_when_occupied():
    from shelf.server.serve import find_free_port

    occupied = _free_port()
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", occupied))
    blocker.listen(1)
    try:
        fallback = find_free_port(occupied)
        assert fallback != occupied

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(("127.0.0.1", fallback))  # must actually be bindable
        finally:
            probe.close()
    finally:
        blocker.close()


# --- make_server / serve: binding ----------------------------------------------


def test_make_server_binds_127_0_0_1_only(library_root):
    from http.server import ThreadingHTTPServer

    from shelf.server.serve import make_server

    port = _free_port()
    server = make_server(library_root, port)
    try:
        assert isinstance(server, ThreadingHTTPServer)
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[0] != "0.0.0.0"
        assert server.server_address[1] == port
    finally:
        server.server_close()


def test_serve_binds_127_0_0_1_only(running_server):
    server, port, base_url = running_server
    assert server.server_address[0] == "127.0.0.1"
    assert server.server_address[0] != "0.0.0.0"


# --- GET / : root injection, no on-disk mutation, no caching -------------------


def test_get_root_injects_absolute_root_and_disk_stays_unchanged(running_server, library_root):
    server, port, base_url = running_server
    index_path = library_root / "index.html"
    before = index_path.read_bytes()

    status, body = _get(f"{base_url}/")
    assert status == 200

    page = _extract_page(body.decode("utf-8"))
    assert page["root"] == str(library_root)

    after = index_path.read_bytes()
    assert after == before  # response-only injection — never rewritten on disk


def test_regen_between_two_requests_is_reflected_without_caching(
    running_server, library_root, tmp_path
):
    server, port, base_url = running_server

    status, first_body = _get(f"{base_url}/")
    assert status == 200
    first_titles = {d["title"] for d in _extract_page(first_body.decode("utf-8"))["docs"]}
    assert first_titles == {"Hello Doc"}

    _add_doc(tmp_path, title="Second Doc", body="# Second Doc\n\nMore body text.", name="second.md")
    assert run(["regen"]).exit_code == 0

    status, second_body = _get(f"{base_url}/")
    assert status == 200
    second_titles = {d["title"] for d in _extract_page(second_body.decode("utf-8"))["docs"]}
    assert second_titles == {"Hello Doc", "Second Doc"}


# --- GET /docs/... --------------------------------------------------------------


def test_get_docs_file_returns_real_on_disk_contents(running_server, library_root):
    server, port, base_url = running_server
    doc_files = list(library_root.glob("docs/**/*.md"))
    assert doc_files, "expected at least one seeded doc file on disk"
    doc_path = doc_files[0]
    rel = doc_path.relative_to(library_root).as_posix()
    on_disk = doc_path.read_bytes()

    status, body = _get(f"{base_url}/{rel}")
    assert status == 200
    assert body == on_disk


# --- path traversal --------------------------------------------------------------


def test_dotdot_traversal_never_escapes_root(running_server):
    server, port, base_url = running_server
    status, body = _get(f"{base_url}/../../etc/passwd")
    assert status in (403, 404)
    assert body != Path("/etc/passwd").read_bytes()
    assert b"root:" not in body


def test_encoded_dotdot_traversal_never_escapes_root(running_server):
    server, port, base_url = running_server
    status, body = _get(f"{base_url}/%2e%2e/%2e%2e/etc/passwd")
    assert status in (403, 404)
    assert body != Path("/etc/passwd").read_bytes()
    assert b"root:" not in body


def test_absolute_path_traversal_never_escapes_root(running_server, tmp_path):
    server, port, base_url = running_server
    outside = tmp_path / "outside-secret.txt"
    sentinel = "TOP_SECRET_OUTSIDE_ROOT_CONTENT"
    outside.write_text(sentinel, encoding="utf-8")

    status, body = _get(f"{base_url}{outside}")
    assert status in (403, 404)
    assert sentinel.encode() not in body


# --- symlink escape --------------------------------------------------------------


def test_symlink_escape_never_escapes_root(running_server, library_root, tmp_path):
    server, port, base_url = running_server

    outside_file = tmp_path / "outside-secret-symlink-target.txt"
    file_sentinel = "TOP_SECRET_SYMLINK_FILE_CONTENT"
    outside_file.write_text(file_sentinel, encoding="utf-8")

    outside_dir = tmp_path / "outside-secret-symlink-dir"
    outside_dir.mkdir()
    dir_sentinel = "TOP_SECRET_SYMLINK_DIR_CONTENT"
    (outside_dir / "inside.txt").write_text(dir_sentinel, encoding="utf-8")

    file_symlink = library_root / "docs" / "escape-file-symlink.txt"
    file_symlink.symlink_to(outside_file)

    dir_symlink = library_root / "docs" / "escape-dir-symlink"
    dir_symlink.symlink_to(outside_dir, target_is_directory=True)

    file_rel = file_symlink.relative_to(library_root).as_posix()
    status, body = _get(f"{base_url}/{file_rel}")
    assert status in (403, 404)
    assert file_sentinel.encode() not in body

    dir_rel = dir_symlink.relative_to(library_root).as_posix()
    status, body = _get(f"{base_url}/{dir_rel}/inside.txt")
    assert status in (403, 404)
    assert dir_sentinel.encode() not in body
