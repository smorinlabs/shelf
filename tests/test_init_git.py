"""P07-T03 — `shelf init --git` / `--github` / `--owner` tests (red).

`init` currently only knows `--library`/`--adopt`/`--force`; `--git`, `--github`,
and `--owner` don't exist yet, so every test here fails against today's CLI
(Click exit 2, unrecognized option) until Task 3 implements them.

Identity note: `shelf init --git` makes its initial commit *inside* the CLI
call, before a test gets a chance to configure a repo-local git identity (the
repo doesn't exist yet). So on top of `isolated_git_identity` (which blocks
the real global/system git config), `git_commit_env` below supplies identity
via `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env vars, which git honors regardless of
config files and regardless of when/where the repo is created.
"""

import subprocess

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core import git as git_core


def run(args):
    return CliRunner().invoke(cli, args)


@pytest.fixture
def git_commit_env(isolated_git_identity, monkeypatch):
    """Isolated git identity available to any repo `shelf init --git` creates."""
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")


def _log_subjects(root):
    out = subprocess.run(
        ["git", "-C", str(root), "log", "--pretty=%s"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return out.splitlines() if out else []


def _tree_files(root):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split())


def _origin_url(root):
    return subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


# --- init --git --------------------------------------------------------


def test_init_git_creates_repo_with_single_initial_commit(tmp_path, git_commit_env):
    root = tmp_path / "lib"
    r = run(["init", "--library", str(root), "--git"])
    assert r.exit_code == 0, r.output
    assert (root / ".git").is_dir()
    assert _log_subjects(root) == ["shelf: init"]


def test_init_git_initial_commit_tree_and_gitignore(tmp_path, git_commit_env):
    root = tmp_path / "lib"
    r = run(["init", "--library", str(root), "--git"])
    assert r.exit_code == 0, r.output

    tree = _tree_files(root)
    assert {"catalog.json", "index.html", "README.md", ".gitignore"} <= tree
    assert any(f.startswith("docs/repos/") for f in tree)
    assert any(f.startswith("docs/topics/") for f in tree)
    assert ".shelf.lock" not in tree

    gitignore = (root / ".gitignore").read_text()
    assert ".shelf.lock" in gitignore


def test_init_without_git_leaves_no_repo(tmp_path):
    root = tmp_path / "lib"
    r = run(["init", "--library", str(root)])
    assert r.exit_code == 0, r.output
    assert not (root / ".git").exists()


# --- init --github -------------------------------------------------------


def test_init_github_implies_git_and_sets_origin(tmp_path, git_commit_env, monkeypatch):
    root = tmp_path / "lib"
    calls = []

    def fake_gh(args):
        calls.append(args)
        if args[:2] == ["api", "user"]:
            return "octocat"
        if args[:2] == ["repo", "create"]:
            return "https://github.com/octocat/shelf-library.git"
        raise AssertionError(f"unexpected gh invocation: {args}")

    monkeypatch.setattr(git_core, "_gh", fake_gh)

    r = run(["init", "--library", str(root), "--github"])
    assert r.exit_code == 0, r.output
    assert (root / ".git").is_dir()
    assert _log_subjects(root) == ["shelf: init"]
    assert _origin_url(root) == "https://github.com/octocat/shelf-library.git"

    assert ["api", "user", "--jq", ".login"] in calls
    create_calls = [c for c in calls if c[:2] == ["repo", "create"]]
    assert len(create_calls) == 1
    assert create_calls[0][2].startswith("octocat/")
    assert len(calls) == 2  # owner resolution + repo create, no extras


def test_init_github_explicit_owner_skips_resolution(tmp_path, git_commit_env, monkeypatch):
    root = tmp_path / "lib"
    calls = []

    def fake_gh(args):
        calls.append(args)
        if args[:2] == ["repo", "create"]:
            return "https://github.com/someorg/shelf-library.git"
        raise AssertionError(f"unexpected gh invocation: {args}")

    monkeypatch.setattr(git_core, "_gh", fake_gh)

    r = run(["init", "--library", str(root), "--github", "--owner", "someorg"])
    assert r.exit_code == 0, r.output
    assert all(c[:2] != ["api", "user"] for c in calls)
    assert len(calls) == 1
    assert calls[0][:2] == ["repo", "create"]
    assert calls[0][2].startswith("someorg/")
    assert _origin_url(root) == "https://github.com/someorg/shelf-library.git"


# --- mutual exclusion -----------------------------------------------------


def test_init_adopt_and_git_are_mutually_exclusive(tmp_path):
    target = tmp_path / "x"
    target.mkdir()
    r = run(["init", "--adopt", str(target), "--git"])
    assert r.exit_code == 2  # usage error


# --- B8: --owner requires --github -----------------------------------------


def test_init_owner_without_github_is_usage_error(tmp_path):
    """B8: `--owner` only means anything alongside `--github`; without it,
    it's silently accepted today. Must be a usage error (exit 2)."""
    root = tmp_path / "lib"
    r = run(["init", "--library", str(root), "--owner", "acme"])
    assert r.exit_code == 2
