"""P07-T01 + TS01 — git core + commit plumbing helper tests (red)."""

import os
import pathlib
import subprocess

import click
import pytest
from click.testing import CliRunner
from shelf.cli.commit import auto_message, commit_options, require_git_if_commit
from shelf.core.git import (
    git_commit_all,
    git_init,
    github_create_and_link,
    is_git_repo,
)

from shelf.core import git as git_core


@pytest.fixture(autouse=True)
def isolated_git_identity(monkeypatch):
    """Keep test commits from touching the real developer's global/system git config."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def init_repo_with_identity(root):
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)


# --- is_git_repo -------------------------------------------------------


def test_is_git_repo_false_on_plain_dir(tmp_path):
    assert is_git_repo(tmp_path) is False


def test_is_git_repo_true_after_git_init(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    assert is_git_repo(tmp_path) is True


# --- git_init ------------------------------------------------------------


def test_git_init_creates_dot_git(tmp_path):
    git_init(tmp_path)
    assert (tmp_path / ".git").exists()


# --- git_commit_all --------------------------------------------------------


def test_git_commit_all_creates_commit_with_message_and_files(tmp_path):
    init_repo_with_identity(tmp_path)
    (tmp_path / "a.txt").write_text("hello\n")
    (tmp_path / "b.txt").write_text("world\n")

    git_commit_all(tmp_path, "shelf: doc add a")

    subject = subprocess.run(
        ["git", "-C", str(tmp_path), "log", "-1", "--pretty=%s"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert subject == "shelf: doc add a"

    names = subprocess.run(
        ["git", "-C", str(tmp_path), "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert set(names) == {"a.txt", "b.txt"}


def test_git_commit_all_on_non_repo_raises_click_exception(tmp_path):
    (tmp_path / "a.txt").write_text("hello\n")

    with pytest.raises(click.ClickException):
        git_commit_all(tmp_path, "shelf: doc add a")


# --- github_create_and_link -----------------------------------------------


def test_github_create_and_link_adds_origin_and_returns_url(tmp_path, monkeypatch):
    root = tmp_path / "lib"
    root.mkdir()
    init_repo_with_identity(root)

    calls = []

    def fake_gh(args):
        calls.append(args)
        return "https://github.com/acme/shelf-library.git"

    monkeypatch.setattr(git_core, "_gh", fake_gh)

    url = github_create_and_link(root, "acme", "shelf-library")

    assert url == "https://github.com/acme/shelf-library.git"
    assert calls == [["repo", "create", "acme/shelf-library", "--private"]]

    remote = subprocess.run(
        ["git", "-C", str(root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert remote == url


# --- require_git_if_commit --------------------------------------------------


def test_require_git_if_commit_raises_naming_init_git_when_not_a_repo(tmp_path):
    with pytest.raises(click.ClickException, match="shelf init --git"):
        require_git_if_commit(tmp_path, True)


def test_require_git_if_commit_noop_when_commit_false(tmp_path):
    require_git_if_commit(tmp_path, False)  # must not raise


def test_require_git_if_commit_noop_when_root_is_a_repo(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    require_git_if_commit(tmp_path, True)  # must not raise


# --- auto_message ------------------------------------------------------------


def test_auto_message_multiple_parts():
    assert auto_message("doc", "add", "x") == "shelf: doc add x"


def test_auto_message_single_part():
    assert auto_message("migrate") == "shelf: migrate"


def test_auto_message_path_argument():
    assert auto_message("orphan", "delete", pathlib.Path("docs/x")) == "shelf: orphan delete docs/x"


# --- commit_options -----------------------------------------------------------


def test_commit_options_defaults_off_and_no_message():
    @click.command()
    @commit_options
    def cmd(commit, commit_message):
        click.echo(f"commit={commit} message={commit_message}")

    result = CliRunner().invoke(cmd, [])
    assert result.exit_code == 0, result.output
    assert "commit=False message=None" in result.output


def test_commit_options_accepts_commit_and_message_flags():
    @click.command()
    @commit_options
    def cmd(commit, commit_message):
        click.echo(f"commit={commit} message={commit_message}")

    result = CliRunner().invoke(cmd, ["--commit", "--commit-message", "hi"])
    assert result.exit_code == 0, result.output
    assert "commit=True message=hi" in result.output


def test_commit_options_accepts_no_commit_flag():
    @click.command()
    @commit_options
    def cmd(commit, commit_message):
        click.echo(f"commit={commit} message={commit_message}")

    result = CliRunner().invoke(cmd, ["--no-commit"])
    assert result.exit_code == 0, result.output
    assert "commit=False" in result.output
