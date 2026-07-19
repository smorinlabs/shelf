"""P05-TS02 — regen and fingerprint round-trip (§11.12, §13)."""

import hashlib
import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    return default_library_path()


def _hand_edit_catalog(root):
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    raw["topics"].append("hand-added")
    path.write_text(json.dumps(raw, indent=2) + "\n")
    return path.read_text()


def test_parse_fingerprint_round_trip(isolated_env):
    from shelf.core.index import parse_fingerprint, render_index, template_text

    root = _init()
    catalog_text = (root / "catalog.json").read_text()
    parsed = parse_fingerprint((root / "index.html").read_text())
    assert parsed is not None
    cat_hash, tmpl_hash = parsed
    assert cat_hash == hashlib.sha256(catalog_text.encode()).hexdigest()
    assert tmpl_hash == hashlib.sha256(template_text().encode()).hexdigest()
    assert parse_fingerprint(render_index(catalog_text)) == parsed
    assert parse_fingerprint("<html>no fingerprint</html>") is None


def test_regen_refreshes_after_hand_edit(isolated_env):
    from shelf.core.index import parse_fingerprint

    root = _init()
    catalog_text = _hand_edit_catalog(root)
    import hashlib as h

    expected = h.sha256(catalog_text.encode()).hexdigest()
    stale = parse_fingerprint((root / "index.html").read_text())
    assert stale is not None and stale[0] != expected  # stale before regen
    r = run(["regen"])
    assert r.exit_code == 0, r.output
    fresh = parse_fingerprint((root / "index.html").read_text())
    assert fresh is not None and fresh[0] == expected


def test_regen_renders_on_disk_bytes_verbatim(isolated_env):
    """A v0 catalog stays v0 on disk — regen must not re-serialize it."""
    root = _init()
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    del raw["schema_version"]
    path.write_text(json.dumps(raw))
    before = path.read_text()
    assert run(["regen"]).exit_code == 0
    assert path.read_text() == before  # catalog untouched, byte-for-byte


def test_regen_refuses_newer_schema(isolated_env):
    root = _init()
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    raw["schema_version"] = 99
    path.write_text(json.dumps(raw))
    r = run(["regen"])
    assert r.exit_code == 1
    assert "newer" in r.output


def test_regen_dry_run_writes_nothing(isolated_env):
    root = _init()
    _hand_edit_catalog(root)
    before = (root / "index.html").read_text()
    r = run(["regen", "--dry-run"])
    assert r.exit_code == 0
    assert "would regenerate" in r.output
    assert (root / "index.html").read_text() == before
