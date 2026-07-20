"""Git and GitHub subprocess helpers."""

import subprocess
from pathlib import Path

import click


def is_git_repo(root: Path) -> bool:
    """Return whether *root* has Git repository metadata."""
    return (root / ".git").exists()


def git_init(root: Path) -> None:
    """Initialize a quiet Git repository at *root*."""
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)


def git_commit_all(root: Path, message: str) -> None:
    """Stage all changes and commit them, translating Git failures for Click."""
    commands = (["add", "-A"], ["commit", "-m", message])
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
    return subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def github_create_and_link(root: Path, owner: str, name: str = "shelf-library") -> str:
    """Create a private GitHub repository and add it as the local origin."""
    url = _gh(["repo", "create", f"{owner}/{name}", "--private"])
    subprocess.run(
        ["git", "-C", str(root), "remote", "add", "origin", url],
        check=True,
    )
    return url
