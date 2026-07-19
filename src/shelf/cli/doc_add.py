"""shelf doc add — ingest a new document (PRD §11.2)."""

import datetime
import shutil
from pathlib import Path

import click

from shelf.cli.runtime import get_config, get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import Document, FileVariant, RepoRef, commit_library, load_catalog
from shelf.core.errors import ConflictError
from shelf.core.ingest import doc_rel_dir, infer_format, infer_repo_url, pick_primary
from shelf.core.slugs import derive_slug


@click.command("add")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", "repo_", default=None, help="Anchor to this repo.")
@click.option(
    "--repo-url",
    default=None,
    help="Repo URL (inferred from the source's git remote when possible).",
)
@click.option("--subject", default=None, help="Within-repo subject label.")
@click.option("--topic", "topic_", default=None, help="Anchor to this topic.")
@click.option("--create-topic", is_flag=True, help="Authorize creating an unknown topic.")
@click.option("--kind", "kind_", required=True, help="Document kind (must exist).")
@click.option("--tag", "tags_", multiple=True, help="Free-form tag (repeatable).")
@click.option("--title", required=True)
@click.option("--description", required=True)
@click.option("--slug", "slug_", default=None, help="Override the derived slug.")
@click.option("--primary", "primary_", default=None, help="Primary format (default heuristic).")
@click.option("--doc-date", default=None)
@click.option("--source", "source_", default=None)
@click.option(
    "--assets",
    "assets_",
    multiple=True,
    type=click.Path(exists=True),
    help="Files or directories copied into the document folder.",
)
@click.option("--format", "format_", default=None, help="Override format inference (long-only).")
@click.option("--remove-source/--no-remove-source", "remove_source_", default=None)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def doc_add(
    ctx,
    files,
    repo_,
    repo_url,
    subject,
    topic_,
    create_topic,
    kind_,
    tags_,
    title,
    description,
    slug_,
    primary_,
    doc_date,
    source_,
    assets_,
    format_,
    remove_source_,
    dry_run,
):
    """Add a new document."""
    if (repo_ is None) == (topic_ is None):
        raise click.UsageError("exactly one of --repo or --topic is required")
    paths = [Path(f).resolve() for f in files]
    formats = [infer_format(p, format_) for p in paths]
    if len(set(formats)) != len(formats):
        raise click.UsageError(
            "two files of the same format — run 'shelf doc add' once per document"
        )
    if primary_ is not None and primary_ not in formats:
        raise click.UsageError(f"--primary '{primary_}' is not among the added formats")

    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        if kind_ not in catalog.kinds:
            raise click.ClickException(
                f"kind '{kind_}' is not in the kind list — 'shelf doc add' never creates kinds"
            )
        repo_ref = None
        if repo_ is not None:
            url = repo_url or infer_repo_url(paths[0])
            if url is None:
                raise click.ClickException("cannot infer the repo url — pass --repo-url")
            repo_ref = RepoRef(name=repo_, url=url, subject=subject)
        elif topic_ not in catalog.topics:
            if not create_topic:
                raise click.ClickException(
                    f"unknown topic '{topic_}' — pass --create-topic to create it"
                )
            catalog.topics.append(topic_)

        added = datetime.date.today().isoformat()
        slug = derive_slug(title, added, slug_)
        if any(d.id == slug for d in catalog.documents):
            raise ConflictError(
                f"slug '{slug}' already exists — use --slug or 'shelf doc format add'"
            )
        doc = Document(
            id=slug,
            title=title,
            description=description,
            kind=kind_,
            tags=list(tags_),
            category=None if repo_ref else topic_,
            repo=repo_ref,
            files=[],
            primary=primary_ or pick_primary(formats),
            added=added,
            doc_date=doc_date,
            source=source_ or str(paths[0]),
        )
        rel_dir = doc_rel_dir(doc)
        dest = root / rel_dir
        if dest.exists():
            raise ConflictError(f"folder '{rel_dir}' already exists — use --slug")
        doc.files = [FileVariant(format=f, path=f"{rel_dir}/{slug}.{f}") for f in formats]

        if dry_run:
            click.echo(f"would add '{slug}' -> {rel_dir} ({', '.join(formats)})")
            return

        dest.mkdir(parents=True)
        try:
            for p, fmt in zip(paths, formats, strict=True):
                shutil.copy2(p, dest / f"{slug}.{fmt}")
            for a in assets_:
                ap = Path(a)
                if ap.is_dir():
                    shutil.copytree(ap, dest / ap.name)
                else:
                    shutil.copy2(ap, dest / ap.name)
            catalog.documents.append(doc)
            commit_library(root, catalog)
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True)
            raise

    effective_remove = get_config(ctx).remove_source if remove_source_ is None else remove_source_
    if effective_remove:
        for p in paths:
            p.unlink(missing_ok=True)
    click.echo(f"added '{slug}' ({', '.join(formats)}) -> {rel_dir}")
