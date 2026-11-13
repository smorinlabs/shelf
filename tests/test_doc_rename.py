"""P25-TS02 — shelf doc rename: ID, folder, variant files, catalog and index move together."""

import json
import subprocess

from click.testing import CliRunner
from conftest import git_init_library

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

OLD = "2026-01-01-uv-notes"
BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seed(tmp_path, slug=OLD, *anchor):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    anchor = anchor or ("--topic", "dev-tooling")
    r = run(["doc", "add", str(src), *anchor, *BASE, "--slug", slug])
    assert r.exit_code == 0, r.output
    root = default_library_path()
    asset = root / "docs" / "topics" / "dev-tooling" / slug / "diagram.png"
    if asset.parent.is_dir():
        asset.write_bytes(b"png")
    return root


def _catalog(root):
    return json.loads((root / "catalog.json").read_text())


def _snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(root).parts
    }


def test_rename_moves_id_folder_variants_and_index(isolated_env, tmp_path):
    root = _seed(tmp_path)
    new = "2026-01-01-uv-guide"
    r = run(["doc", "rename", OLD, new])
    assert r.exit_code == 0, r.output
    doc = _catalog(root)["documents"][0]
    assert doc["id"] == new
    assert doc["added"] == "2026-01-01"
    assert doc["files"][0]["path"] == f"docs/topics/dev-tooling/{new}/{new}.md"
    folder = root / "docs" / "topics" / "dev-tooling"
    assert not (folder / OLD).exists()
    assert (folder / new / f"{new}.md").read_text() == "# hi"
    assert (folder / new / "diagram.png").read_bytes() == b"png"  # assets keep their names
    assert new in (root / "index.html").read_text()
    assert OLD not in (root / "index.html").read_text()
    a = run(["audit"])
    assert a.exit_code == 0, a.output


def test_rename_dates_an_undated_slug_with_the_warning(isolated_env, tmp_path):
    root = _seed(tmp_path)
    r = run(["doc", "rename", OLD, "uv-guide"])
    assert r.exit_code == 0, r.output
    assert _catalog(root)["documents"][0]["id"] == "2026-01-01-uv-guide"
    assert (
        "warning: slug 'uv-guide' had no date; stored as '2026-01-01-uv-guide'. "
        "Rename with: shelf doc rename 2026-01-01-uv-guide <new-slug>"
    ) in r.stderr
    assert run(["audit"]).exit_code == 0


def test_rename_to_another_date_moves_added(isolated_env, tmp_path):
    root = _seed(tmp_path)
    r = run(["doc", "rename", OLD, "1999-09-09-uv-notes"])
    assert r.exit_code == 0, r.output
    assert _catalog(root)["documents"][0]["added"] == "1999-09-09"
    assert run(["audit"]).exit_code == 0


def test_rename_collision_exits_nonzero_and_writes_nothing(isolated_env, tmp_path):
    root = _seed(tmp_path)
    other = tmp_path / "other.md"
    other.write_text("# other")
    taken = "2026-01-01-taken"
    r = run(["doc", "add", str(other), "--topic", "dev-tooling", *BASE, "--slug", taken])
    assert r.exit_code == 0, r.output
    before = _snapshot(root)
    r = run(["doc", "rename", OLD, taken])
    assert r.exit_code != 0
    assert "already exists" in r.output
    assert _snapshot(root) == before


def test_rename_refuses_an_existing_folder(isolated_env, tmp_path):
    root = _seed(tmp_path)
    (root / "docs" / "topics" / "dev-tooling" / "2026-01-01-squat").mkdir()
    before = _snapshot(root)
    r = run(["doc", "rename", OLD, "2026-01-01-squat"])
    assert r.exit_code != 0
    assert _snapshot(root) == before


def test_rename_dry_run_writes_nothing(isolated_env, tmp_path):
    root = _seed(tmp_path)
    before = _snapshot(root)
    r = run(["doc", "rename", OLD, "uv-guide", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "would rename" in r.stdout and "2026-01-01-uv-guide" in r.stdout
    assert "had no date" in r.stderr
    assert _snapshot(root) == before


def test_rename_to_the_same_id_is_an_error(isolated_env, tmp_path):
    _seed(tmp_path)
    assert run(["doc", "rename", OLD, OLD]).exit_code == 5


def test_rename_unknown_id_exits_three(isolated_env, tmp_path):
    _seed(tmp_path)
    assert run(["doc", "rename", "2026-01-01-nope", "x"]).exit_code == 3


def test_rename_in_a_nested_repo_group(isolated_env, tmp_path):
    root = _seed(tmp_path, OLD, "--repo", "obra/superpowers", "--repo-url", "https://x/y")
    r = run(["doc", "rename", OLD, "2026-01-01-sp"])
    assert r.exit_code == 0, r.output
    assert (root / "docs/repos/obra/superpowers/2026-01-01-sp/2026-01-01-sp.md").is_file()
    assert run(["audit"]).exit_code == 0


def test_rename_commit(isolated_env, tmp_path, isolated_git_identity):
    root = _seed(tmp_path)
    git_init_library(root)
    r = run(["doc", "rename", OLD, "2026-01-01-uv-guide", "--commit"])
    assert r.exit_code == 0, r.output
    log = subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--pretty=%s"], capture_output=True, text=True
    ).stdout
    assert "rename" in log
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    assert status.strip() == ""


BAD_SLUGS = ["2026-01-01-a/b", "2026-01-01-a/../../../../docs", "a\\b", ".", "..", ""]


def test_rename_rejects_path_like_slugs_and_writes_nothing(isolated_env, tmp_path):
    root = _seed(tmp_path)
    before = _snapshot(root)
    for bad in BAD_SLUGS:
        for extra in ([], ["--dry-run"]):
            r = run(["doc", "rename", OLD, bad, *extra])
            assert r.exit_code == 2, (bad, r.output)
    assert _snapshot(root) == before


def test_add_rejects_path_like_slugs_and_writes_nothing(isolated_env, tmp_path):
    root = _seed(tmp_path)
    before = _snapshot(root)
    src = tmp_path / "again.md"
    src.write_text("# again")
    for bad in [s for s in BAD_SLUGS if s]:  # an empty --slug means "derive it"
        for extra in ([], ["--dry-run"]):
            r = run(
                ["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--slug", bad, *extra]
            )
            assert r.exit_code == 2, (bad, r.output)
    assert _snapshot(root) == before
