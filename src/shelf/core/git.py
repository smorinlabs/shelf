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
    except FileNotFoundError as exc:
        raise click.ClickException("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git exited with a non-zero status"
        raise click.ClickException(f"git init failed: {detail}") from exc


def _git(root: Path, args: list[str]) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError as exc:
        raise click.ClickException("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git exited with a non-zero status"
        raise click.ClickException(f"git {args[0]} failed: {detail}") from exc


def git_commit_all(root: Path, message: str, paths: list[str] | None = None) -> None:
    """Create an operation commit, even with no net diff.

    With *paths* (library-relative), stage and commit only those paths: unrelated
    working-tree changes and anything the user already staged stay out of the commit
    and keep their state. Paths that are neither on disk nor tracked are skipped.
    Without *paths*, stage and commit everything (used by `init`).
    """
    # P07 hook safety requires committing outside the library lock. Path scoping keeps
    # the user's own work out of shelf commits (P13-T02). A second shelf process that
    # mutates the same paths between lock release and this commit can still have its
    # change recorded here; the Git-serialization lock for that is P13-T01 (deferred).
    if paths is None:
        _git(root, ["add", "-A"])
        _git(root, ["commit", "--allow-empty", "-m", message])
        return
    usable = [
        p
        for p in paths
        if (root / p).exists() or _git(root, ["ls-files", "--cached", "--", p]).strip()
    ]
    # An empty pathspec would commit the whole index, user-staged changes included;
    # catalog.json is always present, so it anchors an otherwise-empty commit.
    scope = usable or ["catalog.json"]
    _git(root, ["add", "-A", "--", *scope])
    _git(root, ["commit", "--only", "--allow-empty", "-m", message, "--", *scope])


def _gh(args: list[str]) -> str:
    """Run GitHub CLI arguments and return trimmed standard output."""
    try:
        return subprocess.run(
            ["gh", *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except FileNotFoundError as exc:
        raise click.ClickException("gh is not installed or not on PATH") from exc
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
    except FileNotFoundError as exc:
        raise click.ClickException("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git exited with a non-zero status"
        raise click.ClickException(f"git remote add origin failed: {detail}") from exc
    return url
