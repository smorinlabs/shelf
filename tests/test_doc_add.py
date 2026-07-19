"""P03-TS02/TS03 + T01 — shelf doc add: validation order, rollback, source handling."""

import datetime
import json
from pathlib import Path

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


def _src(tmp_path, name="uv-notes.md", text="# hi"):
    f = tmp_path / name
    f.write_text(text)
    return f


def _catalog(root):
    return json.loads((root / "catalog.json").read_text())


def test_add_topical_happy_path_removes_source(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    before = datetime.date.today().isoformat()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    after = datetime.date.today().isoformat()
    assert r.exit_code == 0, r.output
    entry = _catalog(root)["documents"][0]
    assert before <= entry["added"] <= after
    slug = entry["id"]
    assert slug == f"{entry['added']}-uv-notes"
    dest = root / "docs" / "topics" / "dev-tooling" / slug / f"{slug}.md"
    assert dest.read_text() == "# hi"
    assert entry["primary"] == "md"
    assert entry["source"] == str(src)
    assert not src.exists()  # remove-source default true


def test_no_remove_source_keeps_original(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source"])
    assert r.exit_code == 0
    assert src.exists()


def test_multi_variant_single_entry(isolated_env, tmp_path):
    root = _init()
    md = _src(tmp_path, "a.md")
    pdf = _src(tmp_path, "a.pdf", "%PDF")
    r = run(["doc", "add", str(md), str(pdf), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert {f["format"] for f in entry["files"]} == {"md", "pdf"}
    assert entry["primary"] == "md"


def test_duplicate_format_usage_error(isolated_env, tmp_path):
    _init()
    a, b = _src(tmp_path, "a.md"), _src(tmp_path, "b.md")
    r = run(["doc", "add", str(a), str(b), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 2


def test_both_or_neither_anchor_usage_error(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    assert run(["doc", "add", str(src), *BASE]).exit_code == 2
    assert run(["doc", "add", str(src), "--topic", "t", "--repo", "r", *BASE]).exit_code == 2


def test_unknown_topic_needs_create_topic(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "fresh", *BASE, "--no-remove-source"])
    assert r.exit_code == 1
    assert "--create-topic" in r.output
    r = run(["doc", "add", str(src), "--topic", "fresh", "--create-topic", *BASE])
    assert r.exit_code == 0
    assert "fresh" in _catalog(root)["topics"]


def test_unknown_kind_never_created(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", "--kind", "novel",
             "--title", "T", "--description", "d"])
    assert r.exit_code == 1
    assert "novel" not in _catalog(root)["kinds"]


def test_slug_collision_conflict(isolated_env, tmp_path):
    _init()
    a = _src(tmp_path, "a.md")
    fixed = ["--slug", "2026-01-01-fixed"]
    assert run(["doc", "add", str(a), "--topic", "dev-tooling", *BASE, *fixed,
                "--no-remove-source"]).exit_code == 0
    b = _src(tmp_path, "b.md")
    r = run(["doc", "add", str(b), "--topic", "dev-tooling", *BASE, *fixed])
    assert r.exit_code == 5
    assert "--slug" in r.output


def test_repo_anchored_layout(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--repo", "flox", "--repo-url", "https://github.com/flox/flox",
             "--subject", "cli", *BASE])
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert entry["repo"]["name"] == "flox"
    assert "category" not in entry
    slug = entry["id"]
    assert (root / "docs" / "repos" / "flox" / slug / f"{slug}.md").is_file()


def test_repo_without_url_or_remote_errors(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--repo", "flox", *BASE])
    assert r.exit_code == 1
    assert "--repo-url" in r.output


def test_tags_and_assets(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    asset = _src(tmp_path, "diagram.pdf", "%PDF")
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE,
             "--tag", "python", "--tag", "uv", "--assets", str(asset)])
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert entry["tags"] == ["python", "uv"]
    slug = entry["id"]
    assert (root / "docs" / "topics" / "dev-tooling" / slug / "diagram.pdf").is_file()


def test_dry_run_changes_nothing(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--dry-run"])
    assert r.exit_code == 0
    assert "would add" in r.output
    assert (root / "catalog.json").read_text() == before
    assert src.exists()


def test_rollback_on_commit_failure(isolated_env, tmp_path, monkeypatch):
    root = _init()
    src = _src(tmp_path)
    import shelf.cli.doc_add as mod

    def boom(*a, **k):
        raise OSError("injected")

    monkeypatch.setattr(mod, "commit_library", boom)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--slug", "2026-01-01-fixed"])
    assert r.exit_code != 0
    assert (root / "catalog.json").read_text() == before
    assert src.exists()  # source never removed on failure
    assert not (root / "docs" / "topics" / "dev-tooling" / "2026-01-01-fixed").exists()  # rolled back
