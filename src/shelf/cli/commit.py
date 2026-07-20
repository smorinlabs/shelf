"""Shared CLI options and helpers for optional Git commits."""

from pathlib import Path

import click

from shelf.core.git import is_git_repo


def commit_options(fn):
    """Add the shared commit controls to a Click command."""
    fn = click.option("--commit/--no-commit", "commit", default=False)(fn)
    fn = click.option("--commit-message", "commit_message", default=None)(fn)
    return fn


def require_git_if_commit(root: Path, commit: bool) -> None:
    """Fail before mutation when a requested commit has no Git repository."""
    if commit and not is_git_repo(root):
        raise click.ClickException("not a git repository; initialize one with 'shelf init --git'")


def auto_message(*parts: object) -> str:
    """Build the conventional automatic Shelf commit message."""
    return "shelf: " + " ".join(map(str, parts))
