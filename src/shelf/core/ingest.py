"""Document ingestion helpers (PRD §6, §11.2)."""

import subprocess
from pathlib import Path

import click

from shelf.core.catalog import Document

FORMAT_MAP = {".md": "md", ".html": "html", ".htm": "html", ".pdf": "pdf"}
PRIMARY_ORDER = ["md", "html", "pdf"]


def infer_format(path: str | Path, override: str | None = None) -> str:
    if override:
        return override
    suffix = Path(path).suffix.lower()
    if suffix not in FORMAT_MAP:
        raise click.UsageError(f"cannot infer format of '{path}' — pass --format")
    return FORMAT_MAP[suffix]


def pick_primary(formats: list[str]) -> str:
    for fmt in PRIMARY_ORDER:
        if fmt in formats:
            return fmt
    return formats[0]


def doc_rel_dir(doc: Document) -> str:
    if doc.repo is not None:
        return f"docs/repos/{doc.repo.name}/{doc.id}"
    return f"docs/topics/{doc.category}/{doc.id}"


def infer_repo_url(source: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(source.parent), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except OSError:
        return None
    url = out.stdout.strip()
    return url if out.returncode == 0 and url else None
