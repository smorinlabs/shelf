"""P04-TS01 — doc update field matrix (§11.4)."""

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
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def _seed_repo(tmp_path):
    assert run(["init"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert (
        run(
            [
                "doc",
                "add",
                str(src),
                "--repo",
                "flox",
                "--repo-url",
                "https://github.com/flox/flox",
                *BASE,
            ]
        ).exit_code
        == 0
    )
    return default_library_path()


def _entry(root):
    return json.loads((root / "catalog.json").read_text())["documents"][0]


def test_title_edit_never_reslugs_or_moves(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    r = run(["doc", "update", SLUG, "--title", "Totally New Title"])
    assert r.exit_code == 0, r.output
    entry = _entry(root)
    assert entry["title"] == "Totally New Title"
    assert entry["id"] == SLUG
    assert (root / "docs" / "topics" / "dev-tooling" / SLUG).is_dir()


def test_kind_validated(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    assert run(["doc", "update", SLUG, "--kind", "nope"]).exit_code == 1
    assert run(["doc", "update", SLUG, "--kind", "spec"]).exit_code == 0


def test_tag_operations(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    assert run(["doc", "update", SLUG, "--add-tag", "python", "--add-tag", "uv"]).exit_code == 0
    assert _entry(root)["tags"] == ["python", "uv"]
    assert run(["doc", "update", SLUG, "--remove-tag", "python"]).exit_code == 0
    assert _entry(root)["tags"] == ["uv"]
    assert run(["doc", "update", SLUG, "--set-tags", "a,b,c"]).exit_code == 0
    assert _entry(root)["tags"] == ["a", "b", "c"]
    r = run(["doc", "update", SLUG, "--set-tags", "a,b", "--add-tag", "c", "--remove-tag", "a"])
    assert r.exit_code == 0
    assert _entry(root)["tags"] == [
        "b",
        "c",
    ]  # same-invocation precedence: set, then add, then remove


def test_primary_must_be_existing_format(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    assert run(["doc", "update", SLUG, "--primary", "pdf"]).exit_code == 2
    assert run(["doc", "update", SLUG, "--primary", "md"]).exit_code == 0


def test_doc_date_set_and_clear(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    assert run(["doc", "update", SLUG, "--doc-date", "2025-12-01"]).exit_code == 0
    assert _entry(root)["doc_date"] == "2025-12-01"
    assert run(["doc", "update", SLUG, "--clear-doc-date"]).exit_code == 0
    assert _entry(root)["doc_date"] is None


def test_repo_fields_only_on_repo_anchored(isolated_env, tmp_path):
    root = _seed_repo(tmp_path)
    assert run(["doc", "update", SLUG, "--subject", "cli"]).exit_code == 0
    assert _entry(root)["repo"]["subject"] == "cli"
    assert run(["doc", "update", SLUG, "--clear-subject"]).exit_code == 0
    assert "subject" not in _entry(root)["repo"]


def test_repo_fields_rejected_on_topical(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    r = run(["doc", "update", SLUG, "--subject", "cli"])
    assert r.exit_code == 1
    assert "repo-anchored" in r.output


def test_anchoring_options_point_at_move(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    r = run(["doc", "update", SLUG, "--topic", "elsewhere"])
    assert r.exit_code == 2
    assert "doc move" in r.output
    r = run(["doc", "update", SLUG, "--repo", "somewhere"])
    assert r.exit_code == 2
    assert "doc move" in r.output


def test_added_requires_force_and_warns(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    r = run(["doc", "update", SLUG, "--added", "2020-01-01"])
    assert r.exit_code == 1
    assert "--force" in r.output
    r = run(["doc", "update", SLUG, "--added", "2020-01-01", "--force"])
    assert r.exit_code == 0
    assert "desync" in r.output
    assert _entry(root)["added"] == "2020-01-01"


def test_no_field_options_is_usage_error(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    assert run(["doc", "update", SLUG]).exit_code == 2


def test_unknown_id_exits_three(isolated_env, tmp_path):
    _seed_topical(tmp_path)
    assert run(["doc", "update", "nope", "--title", "X"]).exit_code == 3


def test_dry_run_shows_diff_changes_nothing(isolated_env, tmp_path):
    root = _seed_topical(tmp_path)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "update", SLUG, "--title", "Changed", "--dry-run"])
    assert r.exit_code == 0
    assert "title: UV Notes -> Changed" in r.output
    assert (root / "catalog.json").read_text() == before
