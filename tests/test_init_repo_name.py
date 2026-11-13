"""P26-TS01–TS04 — `shelf init --github --repo-name`, and its folder-name default."""

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core import git as git_core


def run(args):
    return CliRunner().invoke(cli, args)


@pytest.fixture
def git_commit_env(isolated_git_identity, monkeypatch):
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "t")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "t@t")


@pytest.fixture
def gh_calls(monkeypatch):
    calls: list[list[str]] = []

    def fake_gh(args):
        calls.append(args)
        if args[:2] == ["repo", "create"]:
            return f"https://github.com/{args[2]}.git"
        raise AssertionError(f"unexpected gh invocation: {args}")

    monkeypatch.setattr(git_core, "_gh", fake_gh)
    return calls


def test_repo_name_is_passed_to_gh_repo_create(tmp_path, git_commit_env, gh_calls):
    r = run(
        ["init", "--library", str(tmp_path / "lib"), "--github", "--owner", "me"]
        + ["--repo-name", "foo"]
    )
    assert r.exit_code == 0, r.output
    assert gh_calls == [["repo", "create", "me/foo", "--private"]]


def test_repo_name_without_github_is_a_usage_error(tmp_path):
    root = tmp_path / "lib"
    r = run(["init", "--library", str(root), "--repo-name", "foo"])
    assert r.exit_code == 2
    assert "--repo-name requires --github" in r.output
    assert not root.exists()


def test_repo_name_with_scope_project_is_a_usage_error(tmp_path):
    r = run(["init", "--scope", "project", "--repo-name", "foo"])
    assert r.exit_code == 2


def test_default_name_is_the_library_folder_name(tmp_path, git_commit_env, gh_calls):
    r = run(
        ["init", "--library", str(tmp_path / "x" / "agent-tooling-shelf"), "--github"]
        + ["--owner", "me"]
    )
    assert r.exit_code == 0, r.output
    assert gh_calls == [["repo", "create", "me/agent-tooling-shelf", "--private"]]


def test_default_user_library_keeps_shelf_library(tmp_path, git_commit_env, gh_calls):
    default = Path(os.environ["XDG_DATA_HOME"]) / "shelf"
    r = run(["init", "--github", "--owner", "me"])
    assert r.exit_code == 0, r.output
    assert (default / "catalog.json").is_file()
    assert gh_calls == [["repo", "create", "me/shelf-library", "--private"]]


def test_default_user_library_given_explicitly_keeps_shelf_library(
    tmp_path, git_commit_env, gh_calls
):
    default = Path(os.environ["XDG_DATA_HOME"]) / "shelf"
    r = run(["init", "--library", str(default), "--github", "--owner", "me"])
    assert r.exit_code == 0, r.output
    assert gh_calls == [["repo", "create", "me/shelf-library", "--private"]]


@pytest.mark.parametrize("name", ["bad name", "a/b", ".", "..", "x" * 101, "", "nö"])
def test_invalid_repo_name_is_rejected_before_gh_or_any_write(tmp_path, gh_calls, name):
    root = tmp_path / "lib"
    r = run(["init", "--library", str(root), "--github", "--repo-name", name])
    assert r.exit_code == 2, r.output
    assert gh_calls == []
    assert not root.exists()


def test_an_invalid_default_name_asks_for_repo_name(tmp_path, gh_calls):
    root = tmp_path / "my shelf"
    r = run(["init", "--library", str(root), "--github", "--owner", "me"])
    assert r.exit_code == 2, r.output
    assert "--repo-name" in r.output
    assert gh_calls == []
    assert not root.exists()


@pytest.mark.parametrize("name", ["a", "My.Repo_name-2", "x" * 100, ".hidden"])
def test_valid_repo_names_are_accepted(tmp_path, git_commit_env, gh_calls, name):
    r = run(
        ["init", "--library", str(tmp_path / "lib"), "--github", "--owner", "me"]
        + ["--repo-name", name]
    )
    assert r.exit_code == 0, r.output
    assert gh_calls == [["repo", "create", f"me/{name}", "--private"]]
