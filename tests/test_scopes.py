"""P20 — project-scoped libraries: discovery, precedence, settings per target."""

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.cli.runtime import target_config
from shelf.core.catalog import SEED_KINDS, Catalog, commit_library
from shelf.core.config import default_config_path, load_config, save_config
from shelf.core.paths import default_library_path, discover_project

BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def scaffold(root: Path) -> Path:
    (root / "docs" / "repos").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "topics").mkdir(parents=True, exist_ok=True)
    commit_library(root, Catalog(kinds=list(SEED_KINDS), topics=["dev-tooling"]))
    return root


def project(repo: Path, text: str = 'library = "shelf"\nremove-source = false\n') -> Path:
    """A repo with a `.git` marker and a project config; returns the repo."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    (repo / ".shelf").mkdir(exist_ok=True)
    (repo / ".shelf" / "shelf_config.toml").write_text(text)
    return repo


def user_library() -> Path:
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


# --- TS01: discovery ----------------------------------------------------------


def test_marker_beside_git_at_the_repo_top_is_found(tmp_path):
    repo = project(tmp_path / "repo")
    deep = repo / "a" / "b"
    deep.mkdir(parents=True)
    found = discover_project(deep)
    assert found is not None
    assert found.root == repo.resolve()
    assert found.library == (repo / "shelf").resolve()


def test_nearest_marker_wins(tmp_path):
    repo = project(tmp_path / "repo")
    sub = repo / "sub"
    (sub / ".shelf").mkdir(parents=True)
    (sub / ".shelf" / "shelf_config.toml").write_text('library = "lib"\n')
    (sub / "x").mkdir()
    found = discover_project(sub / "x")
    assert found.library == (sub / "lib").resolve()


def test_search_stops_at_the_git_boundary(tmp_path):
    outer = tmp_path / "outer"
    (outer / ".shelf").mkdir(parents=True)
    (outer / ".shelf" / "shelf_config.toml").write_text('library = "shelf"\n')
    inner = outer / "repo"
    (inner / ".git").mkdir(parents=True)
    assert discover_project(inner) is None


def test_a_worktree_git_file_is_a_boundary_too(tmp_path):
    outer = tmp_path / "outer"
    (outer / ".shelf").mkdir(parents=True)
    (outer / ".shelf" / "shelf_config.toml").write_text('library = "shelf"\n')
    wt = outer / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
    assert discover_project(wt) is None


def test_library_defaults_to_shelf(tmp_path):
    repo = project(tmp_path / "repo", text="remove-source = false\n")
    assert discover_project(repo).library == (repo / "shelf").resolve()


@pytest.mark.parametrize("value", ["/abs/lib", "../outside"])
def test_project_library_must_be_relative_and_inside_the_repo(tmp_path, value):
    repo = project(tmp_path / "repo", text=f'library = "{value}"\n')
    with pytest.raises(click.ClickException, match="relative"):
        discover_project(repo)


def test_config_flag_replaces_discovery(tmp_path, monkeypatch):
    repo = project(tmp_path / "repo")
    scaffold(repo / "shelf")
    other = scaffold(tmp_path / "other")
    cfg = tmp_path / "custom.toml"
    cfg.write_text(f'library = "{other}"\n')
    monkeypatch.chdir(repo)
    r = run(["--config", str(cfg), "path"])
    assert r.exit_code == 0, r.output
    assert r.output.strip() == str(other)


# --- TS02: precedence ---------------------------------------------------------


@pytest.fixture
def both(tmp_path, monkeypatch):
    """A configured user library and a repo with a project library; cwd inside the repo."""
    user = user_library()
    repo = project(tmp_path / "repo")
    proj = scaffold(repo / "shelf")
    monkeypatch.chdir(repo)
    return user, proj.resolve()


def _path(args=()):
    r = run([*args])
    return r.exit_code, r.output.strip()


def test_project_beats_user_config(both):
    _, proj = both
    assert _path(["path"]) == (0, str(proj))


def test_env_beats_project_and_flag_beats_env(both, tmp_path, monkeypatch):
    monkeypatch.setenv("SHELF_LIBRARY", str(tmp_path / "from-env"))
    assert _path(["path"]) == (0, str(tmp_path / "from-env"))
    assert _path(["--library", str(tmp_path / "flag"), "path"]) == (0, str(tmp_path / "flag"))


def test_scope_user_skips_the_project(both):
    user, _ = both
    assert _path(["path", "--scope", "user"]) == (0, str(user))


def test_scope_project_without_a_project_exits_2(isolated_env):
    user_library()
    r = run(["path", "--scope", "project"])
    assert r.exit_code == 2
    assert "no project scope" in r.output


def test_scope_project_with_library_flag_exits_2(both, tmp_path):
    r = run(["--library", str(tmp_path / "x"), "path", "--scope", "project"])
    assert r.exit_code == 2


def test_scope_project_beats_env(both, tmp_path, monkeypatch):
    _, proj = both
    monkeypatch.setenv("SHELF_LIBRARY", str(tmp_path / "from-env"))
    assert _path(["path", "--scope", "project"]) == (0, str(proj))


def test_unconfigured_without_project_errors_with_guidance(isolated_env):
    r = run(["path"])
    assert r.exit_code == 1
    assert "shelf init" in r.output


def test_path_scope_all_prints_each_scope(both):
    user, proj = both
    r = run(["path", "--scope", "all"])
    assert r.exit_code == 0, r.output
    assert r.output.splitlines() == [f"project\t{proj}", f"user\t{user}"]


def test_mutations_target_the_project_library(both, tmp_path):
    user, proj = both
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 0, r.output
    assert "uv-notes" in (proj / "catalog.json").read_text()
    assert "uv-notes" not in (user / "catalog.json").read_text()


def test_settings_follow_the_target_library(both, tmp_path):
    """The project's remove-source = false applies to project writes, not user writes."""
    user, proj = both
    kept = tmp_path / "kept.md"
    kept.write_text("# a")
    r = run(["doc", "add", str(kept), "--topic", "dev-tooling", *BASE, "--slug", "kept"])
    assert r.exit_code == 0, r.output
    assert kept.exists()
    gone = tmp_path / "gone.md"
    gone.write_text("# b")
    r = run(
        ["doc", "add", str(gone), "--scope", "user", "--topic", "dev-tooling", *BASE]
        + ["--slug", "gone"]
    )
    assert r.exit_code == 0, r.output
    assert not gone.exists()
    assert "gone" in (user / "catalog.json").read_text()


def test_project_settings_layer_over_user_settings(both):
    """A key the project file does not set comes from the user file."""
    path = default_config_path()
    cfg = load_config(path)
    cfg.server_port = 9100
    save_config(path, cfg)
    ctx = click.Context(cli, obj={"library": None, "config": None})
    assert target_config(ctx).server_port == 9100
    assert target_config(ctx).remove_source is False


# --- TS03: combined reads -----------------------------------------------------


def _add(src_dir: Path, slug: str, *scope: str) -> None:
    f = src_dir / f"{slug}.md"
    f.write_text(f"# {slug}")
    r = run(["doc", "add", str(f), *scope, "--topic", "dev-tooling", *BASE, "--slug", slug])
    assert r.exit_code == 0, r.output


@pytest.fixture
def seeded(both, tmp_path):
    _add(tmp_path, "2026-01-01-in-project")
    _add(tmp_path, "2026-02-01-in-user", "--scope", "user")
    return both


def test_list_spans_both_scopes_and_labels_each(seeded):
    r = run(["doc", "list"])
    assert r.exit_code == 0, r.output
    rows = [line.split("\t") for line in r.output.splitlines()]
    assert [(row[0], row[-1]) for row in rows] == [
        ("2026-02-01-in-user", "user"),
        ("2026-01-01-in-project", "project"),
    ]


def test_list_json_carries_scope(seeded):
    r = run(["doc", "list", "--json"])
    assert {(d["id"], d["scope"]) for d in json.loads(r.output)} == {
        ("2026-02-01-in-user", "user"),
        ("2026-01-01-in-project", "project"),
    }


@pytest.mark.parametrize(
    ("scope", "only"), [("user", "2026-02-01-in-user"), ("project", "2026-01-01-in-project")]
)
def test_list_scope_narrows(seeded, scope, only):
    r = run(["doc", "list", "--scope", scope])
    assert [line.split("\t")[0] for line in r.output.splitlines()] == [only]


def test_view_finds_a_user_document_from_inside_the_project(seeded):
    r = run(["doc", "view", "2026-02-01-in-user", "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert data["scope"] == "user"


def test_view_of_an_id_in_both_scopes_is_a_conflict(seeded, tmp_path):
    _add(tmp_path, "2026-02-01-in-user")  # same id, now also in the project
    r = run(["doc", "view", "2026-02-01-in-user"])
    assert r.exit_code == 5
    assert "--scope" in r.output
    r = run(["doc", "view", "2026-02-01-in-user", "--scope", "project", "--json"])
    assert json.loads(r.output)["scope"] == "project"


def test_list_outside_a_project_labels_user(isolated_env, tmp_path):
    user_library()
    _add(tmp_path, "2026-01-01-solo")
    r = run(["doc", "list"])
    assert r.output.strip().split("\t")[-1] == "user"
