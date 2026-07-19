"""P03 — doc format add (§11.3) and doc format delete (§11.13)."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d",
        "--slug", SLUG]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seeded(tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def _entry(root):
    return json.loads((root / "catalog.json").read_text())["documents"][0]


def test_format_add_appends_variant(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "notes.pdf"
    pdf.write_text("%PDF")
    r = run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"])
    assert r.exit_code == 0, r.output
    entry = _entry(root)
    assert {f["format"] for f in entry["files"]} == {"md", "pdf"}
    assert (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.pdf").is_file()
    assert entry["primary"] == "md"  # unchanged
    assert pdf.exists()


def test_format_add_unknown_id_exits_three(isolated_env, tmp_path):
    _seeded(tmp_path)
    pdf = tmp_path / "x.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", "nope", str(pdf)]).exit_code == 3


def test_format_add_existing_format_needs_replace(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    other = tmp_path / "other.md"
    other.write_text("# new content")
    r = run(["doc", "format", "add", SLUG, str(other), "--no-remove-source"])
    assert r.exit_code == 5
    assert "--replace" in r.output
    r = run(["doc", "format", "add", SLUG, str(other), "--replace", "--no-remove-source"])
    assert r.exit_code == 0
    md = root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.md"
    assert md.read_text() == "# new content"
    assert len([f for f in _entry(root)["files"] if f["format"] == "md"]) == 1


def test_format_add_primary_reassignment_validated(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--primary", "docx"]).exit_code == 2
    r = run(["doc", "format", "add", SLUG, str(pdf), "--primary", "pdf", "--no-remove-source"])
    assert r.exit_code == 0
    assert _entry(root)["primary"] == "pdf"


def test_format_delete_removes_variant_and_file(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    r = run(["doc", "format", "delete", SLUG, "pdf"])
    assert r.exit_code == 0, r.output
    assert {f["format"] for f in _entry(root)["files"]} == {"md"}
    assert not (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.pdf").exists()


def test_format_delete_refuses_last_variant(isolated_env, tmp_path):
    _seeded(tmp_path)
    r = run(["doc", "format", "delete", SLUG, "md"])
    assert r.exit_code == 5
    assert "doc delete" in r.output


def test_format_delete_primary_needs_successor(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    r = run(["doc", "format", "delete", SLUG, "md"])  # md is primary
    assert r.exit_code == 2
    assert "--primary" in r.output
    r = run(["doc", "format", "delete", SLUG, "md", "--primary", "pdf"])
    assert r.exit_code == 0
    assert _entry(root)["primary"] == "pdf"


def test_format_delete_force_drops_dead_entry(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.pdf").unlink()  # dead ref
    r = run(["doc", "format", "delete", SLUG, "pdf"])
    assert r.exit_code == 1  # missing file without --force is an error
    r = run(["doc", "format", "delete", SLUG, "pdf", "--force"])
    assert r.exit_code == 0
    assert {f["format"] for f in _entry(root)["files"]} == {"md"}
