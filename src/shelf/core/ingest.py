"""Document ingestion helpers (PRD §6, §11.2)."""

import subprocess
from collections.abc import Iterable
from pathlib import Path

import click

from shelf.core.catalog import Catalog, Document

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


def validate_repo_name(name: str) -> str:
    """A repo group is `<repo>` or `<owner>/<repo>`: one level of nesting at most."""
    segments = name.split("/")
    if "\\" in name or len(segments) > 2 or any(s in ("", ".", "..") for s in segments):
        raise click.UsageError(
            f"--repo '{name}' must be <repo> or <owner>/<repo> "
            "(at most one '/', no '\\', and no empty, '.' or '..' segments)"
        )
    return name


def group_entries(docs_dir: Path, repo_names: Iterable[str]) -> tuple[list[Path], list[Path]]:
    """Walk docs/repos and docs/topics. Return (strays, entries): files sitting directly in
    a bucket, and every candidate document folder (or file) inside a group. A folder under
    docs/repos/<owner>/ is a nested group, not a document, when `<owner>/<name>` is one of
    *repo_names*."""
    nested = {n for n in repo_names if "/" in n}
    strays: list[Path] = []
    entries: list[Path] = []

    def children(folder: Path) -> list[Path]:
        return [p for p in sorted(folder.iterdir()) if not (p.is_file() and p.name == ".gitkeep")]

    for bucket in ("repos", "topics"):
        base = docs_dir / bucket
        if not base.is_dir():
            continue
        for group in sorted(base.iterdir()):
            if group.is_file():
                if group.name != ".gitkeep":
                    strays.append(group)
                continue
            for entry in children(group):
                if bucket == "repos" and entry.is_dir() and f"{group.name}/{entry.name}" in nested:
                    entries.extend(children(entry))
                else:
                    entries.append(entry)
    return strays, entries


def prune_nested_group(root: Path, rel_dir: str) -> None:
    """Remove the `<owner>/<repo>` folders a removed nested document left empty."""
    parts = Path(rel_dir).parts
    if len(parts) != 5:
        return
    for folder in (root.joinpath(*parts[:4]), root.joinpath(*parts[:3])):
        try:
            folder.rmdir()
        except OSError:
            return


def infer_repo_url(source: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(source.parent), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    url = out.stdout.strip()
    return url if out.returncode == 0 and url else None


def scan_orphans(root: Path, catalog: Catalog) -> list[str]:
    cataloged = {doc_rel_dir(d): d for d in catalog.documents}
    orphans: list[str] = []
    docs_dir = root / "docs"
    strays, entries = group_entries(docs_dir, (d.repo.name for d in catalog.documents if d.repo))
    orphans.extend(str(p.relative_to(root)) for p in strays)
    for entry in entries:
        rel = str(entry.relative_to(root))
        if rel not in cataloged:
            orphans.append(rel)
            continue
        doc = cataloged[rel]
        expected_files = {f.path for f in doc.files}
        for child in sorted(entry.iterdir()):
            child_rel = str(child.relative_to(root))
            # Variants are canonically named <id>.<format>; other files
            # in the document folder are supporting assets.
            if child.is_file() and child.stem == doc.id and child_rel not in expected_files:
                orphans.append(child_rel)
    for entry in sorted(docs_dir.iterdir()):
        if entry.is_file():
            if entry.name == ".gitkeep":
                continue
            orphans.append(str(entry.relative_to(root)))
    return sorted(orphans)
