"""P03 — doc format add (§11.3) and doc format delete (§11.13)."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d", "--slug", SLUG]


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


def test_format_add_replace_commit_failure_loses_original_content(
    isolated_env, tmp_path, monkeypatch
):
    """Data-safety regression: --replace overwrites the on-disk variant via
    shutil.copy2 BEFORE commit_library is even attempted. When the subsequent
    commit fails, the original content is already gone — there is nothing left
    to roll back to. The original must survive a failed commit.
    """
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("ORIGINAL")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    root = default_library_path()

    new_md = tmp_path / "new.md"
    new_md.write_text("REPLACEMENT")

    import shelf.cli.doc_variants as mod

    def boom(*a, **k):
        raise OSError("injected")

    monkeypatch.setattr(mod, "commit_library", boom)
    r = run(["doc", "format", "add", SLUG, str(new_md), "--replace", "--no-remove-source"])
    assert r.exit_code != 0

    variant = root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.md"
    assert variant.read_text() == "ORIGINAL"  # must not be lost on a failed commit


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


def test_format_delete_validates_primary_even_for_non_primary_deletion(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    r = run(["doc", "format", "delete", SLUG, "pdf", "--primary", "bogus"])
    assert r.exit_code == 2, r.output
    entry = _entry(root)
    assert entry["primary"] == "md"  # untouched
    assert {f["format"] for f in entry["files"]} == {"md", "pdf"}  # nothing deleted


def test_format_delete_success_clean_then_postcommit_index_failure_leaves_undetectable_residue(
    isolated_env, tmp_path, monkeypatch
):
    """Success-path invariant: deleting one variant removes exactly that file and
    leaves the others intact, audit-clean.

    Data-safety regression (post-commit): format_delete calls commit_library()
    with NO try/except at all, then unlink()s the target file. commit_library()
    writes catalog.json (the commit point) and THEN index.html; if the index
    write fails, the exception propagates straight out of format_delete and the
    target.unlink() line never runs — even though the catalog was already
    committed without that variant. The leftover file sits inside a cataloged
    document folder, which orphan-scanning never descends into, so it is
    invisible to both `shelf orphan list` and `shelf audit` (§5c violation).
    """
    root = _seeded(tmp_path)  # SLUG has 'md'
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    html = tmp_path / "n.html"
    html.write_text("<html></html>")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    assert run(["doc", "format", "add", SLUG, str(html), "--no-remove-source"]).exit_code == 0

    folder = root / "docs" / "topics" / "dev-tooling" / SLUG

    # --- success path: deleting 'pdf' cleanly removes exactly that file ---
    r = run(["doc", "format", "delete", SLUG, "pdf"])
    assert r.exit_code == 0, r.output
    assert not (folder / f"{SLUG}.pdf").exists()
    assert (folder / f"{SLUG}.html").exists()  # other variant intact
    assert run(["audit"]).exit_code == 0  # audit stays clean

    # --- inject a post-commit index-write failure on the next delete ---
    import shelf.core.catalog as cat_mod

    real = cat_mod.atomic_write_text
    calls = {"n": 0}

    def flaky(path, text):
        calls["n"] += 1
        if calls["n"] == 2:  # index.html write, after the catalog.json commit
            raise OSError("injected index failure")
        real(path, text)

    monkeypatch.setattr(cat_mod, "atomic_write_text", flaky)
    r = run(["doc", "format", "delete", SLUG, "html"])
    assert r.exit_code != 0

    entry = _entry(root)
    assert {f["format"] for f in entry["files"]} == {"md"}  # catalog committed without html

    leftover = folder / f"{SLUG}.html"
    rel = f"docs/topics/dev-tooling/{SLUG}/{SLUG}.html"
    orphan_out = run(["orphan", "list"]).output
    assert (not leftover.exists()) or (rel in orphan_out), (
        "format delete left a residue file invisible to orphan list after a "
        "post-commit index-write failure (§5c violation)"
    )
