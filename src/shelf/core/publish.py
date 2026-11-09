"""Build the filtered static site that `shelf publish` writes (P21, design Part 2).

The library folder is never served: the site holds only published documents, a
catalog and index built from them alone, and `.nojekyll`.
"""

import dataclasses
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from shelf.core.catalog import CATALOG_FILENAME, Catalog, Document, dumps_catalog
from shelf.core.git import is_git_repo, toplevel
from shelf.core.index import render_index
from shelf.core.preview import build_snippets

MODES = ("marked", "all")


def publish_mode(value: str | None, config_path: Path) -> str:
    mode = value or "marked"
    if mode not in MODES:
        raise click.ClickException(
            f'publish = "{mode}" in {config_path} is not valid — use "marked" or "all"'
        )
    return mode


def select(catalog: Catalog, mode: str) -> list[Document]:
    return list(catalog.documents) if mode == "all" else [d for d in catalog.documents if d.publish]


def site_catalog(catalog: Catalog, docs: list[Document]) -> Catalog:
    """Only `docs`, and only the topics and kinds they use (no labels from unpublished docs).
    `source` is dropped: it is the local path a file was added from."""
    topics = {d.category for d in docs if d.category is not None}
    kinds = {d.kind for d in docs}
    return Catalog(
        schema_version=catalog.schema_version,
        topics=[t for t in catalog.topics if t in topics],
        kinds=[k for k in catalog.kinds if k in kinds],
        documents=[dataclasses.replace(d, source=None) for d in docs],
        shelf_version=catalog.shelf_version,
    )


def check_out_dir(root: Path, out: Path) -> None:
    """Refuse a destination that would replace the library or its documents, or that holds
    files shelf did not build. `_site/` inside the library root is allowed: it is how a
    dedicated library repo builds in CI, and audit never looks outside docs/ and the catalog."""
    lib, dest = root.resolve(), out.resolve()
    if lib.is_relative_to(dest) or dest.is_relative_to(lib / "docs"):
        raise click.UsageError(f"--out {out} overlaps the library at {root} — pick another folder")
    if dest.exists() and (not dest.is_dir() or _foreign(dest)):
        raise click.ClickException(
            f"{out} exists and is not a previous shelf build — remove it or pick another --out"
        )


def _foreign(dest: Path) -> bool:
    if not any(dest.iterdir()):
        return False
    return not ((dest / ".nojekyll").is_file() and (dest / CATALOG_FILENAME).is_file())


def source_base(root: Path, slug: str | None) -> str:
    """GitHub blob URL of the library folder on the deployed branch (J3), or ""."""
    if slug is None or not is_git_repo(root):
        return ""
    server, repo, ref = (
        os.environ.get("GITHUB_SERVER_URL"),
        os.environ.get("GITHUB_REPOSITORY"),
        os.environ.get("GITHUB_REF_NAME"),
    )
    # The Actions variables describe the workflow's repo; use them only for that checkout.
    if not (server and ref and repo and repo.lower() == slug.lower()):
        ref = _branch(root)
        if ref is None:
            return ""
        server, repo = "https://github.com", slug
    base = f"{server.rstrip('/')}/{repo}/blob/{ref}"
    top = toplevel(root)
    if top is not None and root.resolve() != top:
        base += "/" + root.resolve().relative_to(top).as_posix()
    return base


def _branch(root: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return out or None


def build_site(
    root: Path, catalog: Catalog, docs: list[Document], out: Path, *, base_url: str, source: str
) -> None:
    """Write the site into a sibling staging folder, then swap it into place."""
    folders = sorted({str(Path(f.path).parent) for d in docs for f in d.files})
    _check_sources(root, docs, folders)
    filtered = site_catalog(catalog, docs)
    catalog_text = dumps_catalog(filtered)
    snippets = build_snippets(root, [d.to_dict() for d in docs])
    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}.", dir=out.parent))
    try:
        for rel in folders:
            shutil.copytree(root / rel, staging / rel, dirs_exist_ok=True)
        (staging / CATALOG_FILENAME).write_text(catalog_text, encoding="utf-8")
        (staging / "index.html").write_text(
            render_index(catalog_text, snippets, root=base_url, source=source), encoding="utf-8"
        )
        (staging / ".nojekyll").write_text("")
        _make_world_readable(staging)
        if out.exists():
            shutil.rmtree(out)
        staging.rename(out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _check_sources(root: Path, docs: list[Document], folders: list[str]) -> None:
    """Fail before building when a published file is missing, or when a published folder
    holds a symlink (copying it would publish whatever it points to)."""
    missing = [f.path for d in docs for f in d.files if not (root / f.path).is_file()]
    if missing:
        raise click.ClickException(
            "published file(s) missing: " + ", ".join(missing) + " — run 'shelf audit'"
        )
    links = [
        p.relative_to(root).as_posix()
        for rel in folders
        for p in [root / rel, *(root / rel).rglob("*")]
        if p.is_symlink()
    ]
    if links:
        raise click.ClickException(
            "refusing to publish a symlink: " + ", ".join(links) + " — replace it with the file"
        )


def _make_world_readable(site: Path) -> None:
    """A served site must be readable by the web server's account: dirs 755, files 644."""
    site.chmod(0o755)
    for p in site.rglob("*"):
        p.chmod(0o755 if p.is_dir() else 0o644)
