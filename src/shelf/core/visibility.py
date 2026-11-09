"""Which GitHub repo holds a library, and whether it is public (P21 private-repo guard).

Detection order: inside GitHub Actions, the event file at `$GITHUB_EVENT_PATH`;
otherwise `gh api repos/<owner>/<repo>` for the `origin` remote. Any failure is
"unknown", which the guard treats as private.
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shelf.core.git import is_git_repo

_SLUG_RE = re.compile(
    r"^(?:git@github\.com:|ssh://git@github\.com/|https://github\.com/)"
    r"([^/]+)/([^/]+?)(?:\.git)?/?$"
)
KNOWN = ("public", "private", "internal")


@dataclass(frozen=True)
class Repo:
    slug: str | None  # "owner/name", when known
    visibility: str  # public | private | internal | unknown


def _gh(args: list[str]) -> str | None:
    """Output of one `gh` call, or None on any failure."""
    try:
        out = subprocess.run(["gh", *args], capture_output=True, text=True, check=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout


def github_slug(root: Path) -> str | None:
    """`owner/name` of the `origin` remote of the repo containing `root`, if it is GitHub."""
    try:
        url = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    match = _SLUG_RE.match(url)
    return f"{match.group(1)}/{match.group(2)}" if match else None


def _from_event(path: str) -> Repo:
    try:
        repo = json.loads(Path(path).read_text(encoding="utf-8"))["repository"]
        slug = repo.get("full_name")
        vis = repo.get("visibility")
        if vis not in KNOWN:
            private = repo["private"]
            if not isinstance(private, bool):
                return Repo(slug, "unknown")
            vis = "private" if private else "public"
        return Repo(slug, vis)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return Repo(None, "unknown")


def detect(root: Path) -> Repo:
    event = os.environ.get("GITHUB_EVENT_PATH")
    if event:
        return _from_event(event)
    # The P20 rule: a library nested in an unrelated repo (e.g. dotfiles) is not in it.
    slug = github_slug(root) if is_git_repo(root) else None
    if slug is None:
        return Repo(None, "unknown")
    out = _gh(["api", f"repos/{slug}", "--jq", ".visibility"])
    vis = (out or "").strip()
    return Repo(slug, vis if vis in KNOWN else "unknown")


def pages_url(slug: str | None) -> str | None:
    """The repo's GitHub Pages URL (custom domain included), when Pages is on."""
    if slug is None:
        return None
    out = (_gh(["api", f"repos/{slug}/pages", "--jq", ".html_url"]) or "").strip()
    return out if out.startswith(("https://", "http://")) else None
