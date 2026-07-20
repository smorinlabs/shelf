"""Shared fixtures — isolate every test from the real home directory."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("SHELF_LIBRARY", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    return tmp_path


@pytest.fixture
def isolated_git_identity(monkeypatch):
    """Keep test commits from touching the real developer's global/system git config."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def git_init_library(root: Path) -> None:
    """Turn an already-scaffolded shelf library into a git repo: local isolated
    identity, a `.gitignore` covering `.shelf.lock` (in place of the not-yet-landed
    'shelf init --git'), and one baseline commit to diff future commits against.

    Requires `isolated_git_identity` (or equivalent env vars) to already be active.
    """
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / ".gitignore").write_text(".shelf.lock\n")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(root), "commit", "-q", "-m", "chore: test baseline"], check=True
    )
