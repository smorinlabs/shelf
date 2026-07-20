"""Git and GitHub subprocess helpers."""

import subprocess
from pathlib import Path

import click


def is_git_repo(root: Path) -> bool:
    """Return whether *root* has Git repository metadata."""
    return (root / ".git").exists()


def git_init(root: Path) -> None:
    """Initialize a quiet Git repository at *root*."""
    try:
        subprocess.run(
            ["git", "-C", str(root), "init", "-q"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git exited with a non-zero status"
        raise click.ClickException(f"git init failed: {detail}") from exc


def git_commit_all(root: Path, message: str) -> None:
    """Stage all changes and create an operation commit, even with no net diff."""
    commands = (["add", "-A"], ["commit", "--allow-empty", "-m", message])
    for args in commands:
        try:
            subprocess.run(
                ["git", "-C", str(root), *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or "git exited with a non-zero status"
            raise click.ClickException(f"git {args[0]} failed: {detail}") from exc


def _gh(args: list[str]) -> str:
    """Run GitHub CLI arguments and return trimmed standard output."""
    try:
        return subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "gh exited with a non-zero status"
        raise click.ClickException(f"gh {' '.join(args)} failed: {detail}") from exc


def github_create_and_link(root: Path, owner: str, name: str = "shelf-library") -> str:
    """Create a private GitHub repository and add it as the local origin."""
    url = _gh(["repo", "create", f"{owner}/{name}", "--private"])
    try:
        subprocess.run(
            ["git", "-C", str(root), "remote", "add", "origin", url],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git exited with a non-zero status"
        raise click.ClickException(f"git remote add origin failed: {detail}") from exc
    return url
