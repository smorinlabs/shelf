"""P04-TS02 — doc move: three relocations, path rewrites, crash discipline (§11.5)."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = [
    "--kind",
    "reference",
    "--title",
    "UV Notes",
    "--description",
    "d",
    "--slug",
    SLUG,
]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seed_topical(tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    assert run(["topic", "add", "claude-code"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def _entry(root):
    return json.loads((root / "catalog.json").read_text())["documents"][0]


def test_topic_to_topic_moves_folder_and_paths(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    r = run(["doc", "move", SLUG, "--topic", "claude-code"])
    assert r.exit_code == 0, r.output
    entry = _entry(root)
    assert entry["category"] == "claude-code"
    assert entry["files"][0]["path"] == f"docs/topics/claude-code/{SLUG}/{SLUG}.md"
    assert (root / "docs" / "topics" / "claude-code" / SLUG / f"{SLUG}.md").is_file()
    assert not (root / "docs" / "topics" / "dev-tooling" / SLUG).exists()


def test_move_warns_about_stale_paths(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    r = run(["doc", "move", SLUG, "--topic", "claude-code"])
    assert "no longer resolve" in r.output


def test_topical_to_repo_switch(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    r = run(["doc", "move", SLUG, "--repo", "flox", "--subject", "cli"])
    assert r.exit_code == 0, r.output
    entry = _entry(root)
    assert "category" not in entry
    assert entry["repo"]["name"] == "flox"
    assert entry["repo"]["subject"] == "cli"
    assert (root / "docs" / "repos" / "flox" / SLUG / f"{SLUG}.md").is_file()


def test_repo_to_topical_switch(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    assert run(["doc", "move", SLUG, "--repo", "flox"]).exit_code == 0
    r = run(["doc", "move", SLUG, "--topic", "dev-tooling"])
    assert r.exit_code == 0, r.output
    entry = _entry(root)
    assert entry["category"] == "dev-tooling"
    assert "repo" not in entry
    assert not (root / "docs" / "repos" / "flox" / SLUG).exists()


def test_unknown_topic_governed(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    r = run(["doc", "move", SLUG, "--topic", "brand-new"])
    assert r.exit_code == 1
    assert "--create-topic" in r.output
    assert run(["doc", "move", SLUG, "--topic", "brand-new", "--create-topic"]).exit_code == 0


def test_exactly_one_anchor_required(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    assert run(["doc", "move", SLUG]).exit_code == 2
    assert run(["doc", "move", SLUG, "--topic", "x", "--repo", "y"]).exit_code == 2


def test_same_anchor_is_error(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    r = run(["doc", "move", SLUG, "--topic", "dev-tooling"])
    assert r.exit_code == 1
    assert "already" in r.output


def test_unknown_id_exits_three(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    assert run(["doc", "move", "nope", "--topic", "claude-code"]).exit_code == 3


def test_dry_run_shows_paths_changes_nothing(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "move", SLUG, "--topic", "claude-code", "--dry-run"])
    assert r.exit_code == 0
    assert "dev-tooling" in r.output and "claude-code" in r.output
    assert (root / "catalog.json").read_text() == before
    assert (root / "docs" / "topics" / "dev-tooling" / SLUG).is_dir()


def test_precommit_failure_rolls_back_staged_copy(isolated_env, tmp_path, monkeypatch):
    root = _seed_topical(tmp_path)
    import shelf.cli.doc_move as mod

    def boom(*a, **k):
        raise OSError("injected")

    monkeypatch.setattr(mod, "commit_library", boom)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "move", SLUG, "--topic", "claude-code"])
    assert r.exit_code != 0
    assert (root / "catalog.json").read_text() == before
    assert (root / "docs" / "topics" / "dev-tooling" / SLUG).is_dir()  # original intact
    assert not (root / "docs" / "topics" / "claude-code" / SLUG).exists()  # staged copy gone


def test_postcommit_failure_leaves_old_folder_as_orphan(isolated_env, tmp_path, monkeypatch):
    root = _seed_topical(tmp_path)
    import shelf.core.catalog as cat_mod

    calls = {"n": 0}
    real = cat_mod.atomic_write_text

    def flaky(path, text):
        calls["n"] += 1
        if calls["n"] == 2:  # index write, after the catalog commit
            raise OSError("injected index failure")
        real(path, text)

    monkeypatch.setattr(cat_mod, "atomic_write_text", flaky)
    r = run(["doc", "move", SLUG, "--topic", "claude-code"])
    assert r.exit_code != 0
    entry = _entry(root)
    assert entry["category"] == "claude-code"  # commit happened
    assert (root / "docs" / "topics" / "claude-code" / SLUG / f"{SLUG}.md").is_file()
    orphans = CliRunner().invoke(cli, ["orphan", "list"]).output
    assert f"docs/topics/dev-tooling/{SLUG}" in orphans  # old folder detectable
