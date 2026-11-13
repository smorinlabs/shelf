"""Git and GitHub subprocess helpers."""

import os
import re
import subprocess
from pathlib import Path

import click

from shelf.core.paths import discover_project


def toplevel(path: Path) -> Path | None:
    """The work-tree root of the Git repository containing *path*, or None."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return Path(out.stdout.strip()).resolve()


def append_gitignore(repo: Path, entries: list[str]) -> None:
    """Add each missing *entry* to `<repo>/.gitignore`, keeping every existing line."""
    path = repo / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    missing = [e for e in entries if e not in text.splitlines()]
    if not missing:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    path.write_text(text + "".join(f"{e}\n" for e in missing), encoding="utf-8")


def is_git_repo(root: Path) -> bool:
    """Return whether *root* is a Git library: the work-tree root itself, or the project
    library of the repo it sits in. Any other library that merely sits inside a repo
    (a dotfiles home, a personal folder beside a project shelf) is not one."""
    if not root.is_dir():
        return False
    top = toplevel(root)
    if top is None:
        return False
    if top == root.resolve():
        return True
    try:
        project = discover_project(top)
    except click.ClickException:
        return False
    return project is not None and project.library == root.resolve()


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


def _git(root: Path, args: list[str], literal: bool = False) -> str:
    # GIT_LITERAL_PATHSPECS: shelf passes real file paths, which may contain glob
    # characters such as `*`; `--` alone would still expand them as patterns.
    env = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"} if literal else None
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        ).stdout
    except FileNotFoundError as exc:
        raise click.ClickException("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or "git exited with a non-zero status"
        raise click.ClickException(f"git {args[0]} failed: {detail}") from exc


def merge_in_progress(root: Path) -> bool:
    """Return whether *root* has an unfinished merge (Git refuses partial commits then)."""
    # Check Git's merge-state file, not the revision: `rev-parse --verify MERGE_HEAD`
    # also resolves a branch or tag that happens to be named MERGE_HEAD.
    state_file = _git(root, ["rev-parse", "--git-path", "MERGE_HEAD"]).strip()
    return (root / state_file).is_file()


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
    # Tracked, or on disk and not ignored: stage, then commit. An ignored untracked path
    # (index.html in a project library) is left out; `git add` refuses one by name.
    # Only in HEAD (a deletion the user already staged): `git add` rejects the path,
    # but `commit --only` records it.
    staged = [
        p
        for p in paths
        if _git(root, ["ls-files", "--cached", "--", p], literal=True).strip()
        or ((root / p).exists() and not _ignored(root, p))
    ]
    has_head = (
        subprocess.run(
            ["git", "-C", str(root), "rev-parse", "-q", "--verify", "HEAD^{commit}"],
            capture_output=True,
        ).returncode
        == 0
    )
    head_only = [
        p
        for p in paths
        if has_head
        and p not in staged
        and _git(root, ["ls-tree", "-r", "--name-only", "HEAD", "--", p], literal=True).strip()
    ]
    usable = staged + head_only
    if not usable:
        # `--only` with no pathspec records an empty commit and leaves the index,
        # including anything the user staged, out of it.
        _git(root, ["commit", "--only", "--allow-empty", "-m", message])
        return
    if staged:
        _git(root, ["add", "-A", "--", *staged], literal=True)
    _git(root, ["commit", "--only", "--allow-empty", "-m", message, "--", *usable], literal=True)


def _ignored(root: Path, path: str) -> bool:
    # check-ignore takes path names, not pathspecs (it rejects GIT_LITERAL_PATHSPECS).
    out = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--", path])
    return out.returncode == 0


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


DEFAULT_GITHUB_REPO = "shelf-library"
_GITHUB_NAME_RE = re.compile(r"[A-Za-z0-9._-]{1,100}")


def valid_github_repo_name(name: str) -> bool:
    """GitHub repository names: ASCII letters, digits, '.', '_' and '-', at most 100
    characters, and not '.' or '..'."""
    return bool(_GITHUB_NAME_RE.fullmatch(name)) and name not in (".", "..")


def github_create_and_link(root: Path, owner: str, name: str = DEFAULT_GITHUB_REPO) -> str:
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
