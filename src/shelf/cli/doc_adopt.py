"""shelf doc adopt — register an existing in-library folder (PRD §11.15)."""

from pathlib import Path

import click

from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import Document, FileVariant, RepoRef, commit_library, load_catalog
from shelf.core.errors import ConflictError
from shelf.core.ingest import FORMAT_MAP, pick_primary


@click.command("adopt")
@click.argument("folder")
@click.option("--kind", "kind_", required=True)
@click.option("--title", required=True)
@click.option("--description", required=True)
@click.option("--tag", "tags_", multiple=True)
@click.option("--create-topic", is_flag=True)
@click.option("--repo-url", default=None)
@click.option("--subject", default=None)
@click.option("--primary", "primary_", default=None)
@click.option("--doc-date", default=None)
@click.pass_context
def doc_adopt(
    ctx,
    folder,
    kind_,
    title,
    description,
    tags_,
    create_topic,
    repo_url,
    subject,
    primary_,
    doc_date,
):
    """Register an existing per-document folder without copying."""
    root = get_library(ctx)
    rel = Path(folder)
    if rel.is_absolute():
        if not rel.is_relative_to(root):
            raise click.UsageError(f"'{rel}' is outside the library at {root}")
        rel = rel.relative_to(root)
    parts = rel.parts
    if len(parts) != 4 or parts[0] != "docs" or parts[1] not in ("repos", "topics"):
        raise click.UsageError(
            "folder must be docs/repos/<repo>/<slug> or docs/topics/<topic>/<slug>"
        )
    bucket, group, slug = parts[1], parts[2], parts[3]
    target = root / rel
    if not target.is_dir():
        raise click.ClickException(f"'{rel}' is not a directory inside the library")

    variant_files = sorted(
        p for p in target.iterdir() if p.is_file() and p.suffix.lower() in FORMAT_MAP
    )
    if not variant_files:
        raise click.ClickException(f"'{rel}' contains no known-format files (md/html/pdf)")
    formats = [FORMAT_MAP[p.suffix.lower()] for p in variant_files]
    if primary_ is not None and primary_ not in formats:
        raise click.UsageError(f"--primary '{primary_}' is not among the folder's formats")

    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        if kind_ not in catalog.kinds:
            raise click.ClickException(f"kind '{kind_}' is not in the kind list")
        if any(d.id == slug for d in catalog.documents):
            raise ConflictError(f"slug '{slug}' already exists in the catalog")
        if bucket == "topics":
            if group not in catalog.topics:
                if not create_topic:
                    raise click.ClickException(
                        f"unknown topic '{group}' — pass --create-topic to create it"
                    )
                catalog.topics.append(group)
            repo_ref = None
            category = group
        else:
            repo_ref = RepoRef(name=group, url=repo_url, subject=subject)
            category = None
        added = slug[:10] if len(slug) >= 10 and slug[4] == "-" and slug[7] == "-" else None
        doc = Document(
            id=slug,
            title=title,
            description=description,
            kind=kind_,
            tags=list(tags_),
            category=category,
            repo=repo_ref,
            files=[
                FileVariant(format=f, path=str(rel / p.name))
                for p, f in zip(variant_files, formats, strict=True)
            ],
            primary=primary_ or pick_primary(formats),
            added=added,
            doc_date=doc_date,
            source=str(rel),
        )
        catalog.documents.append(doc)
        commit_library(root, catalog)
    click.echo(f"adopted '{slug}' ({', '.join(formats)})")
