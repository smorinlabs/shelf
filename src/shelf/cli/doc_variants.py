"""doc format add / delete (PRD §11.3, §11.13)."""

import shutil
from pathlib import Path

import click

from shelf.cli.runtime import get_config, get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import Catalog, Document, FileVariant, commit_library, load_catalog
from shelf.core.errors import ConflictError, NotFoundError
from shelf.core.ingest import doc_rel_dir, infer_format


def find_doc(catalog: Catalog, doc_id: str) -> Document:
    doc = next((d for d in catalog.documents if d.id == doc_id), None)
    if doc is None:
        raise NotFoundError(
            f"document '{doc_id}' not found — try 'shelf doc list --query {doc_id}'"
        )
    return doc


@click.command("add")
@click.argument("doc_id")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--assets", "assets_", multiple=True, type=click.Path(exists=True))
@click.option("--format", "format_", default=None)
@click.option("--replace", is_flag=True, help="Overwrite an existing same-format variant.")
@click.option("--primary", "primary_", default=None)
@click.option("--source", "source_", default=None)
@click.option("--remove-source/--no-remove-source", "remove_source_", default=None)
@click.pass_context
def format_add(ctx, doc_id, files, assets_, format_, replace, primary_, source_, remove_source_):
    """Add a format variant to an existing document."""
    paths = [Path(f).resolve() for f in files]
    new_formats = [infer_format(p, format_) for p in paths]
    if len(set(new_formats)) != len(new_formats):
        raise click.UsageError("two files of the same format")

    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        existing = {f.format for f in doc.files}
        clashes = [f for f in new_formats if f in existing]
        if clashes and not replace:
            raise ConflictError(f"format '{clashes[0]}' already exists — pass --replace")
        final_formats = existing | set(new_formats)
        if primary_ is not None and primary_ not in final_formats:
            raise click.UsageError(f"--primary '{primary_}' is not a format the document will have")
        rel_dir = doc_rel_dir(doc)
        dest = root / rel_dir
        created: list[Path] = []
        try:
            for p, fmt in zip(paths, new_formats, strict=True):
                target = dest / f"{doc.id}.{fmt}"
                if not target.exists():
                    created.append(target)
                shutil.copy2(p, target)
            for a in assets_:
                ap = Path(a)
                target = dest / ap.name
                if ap.is_dir():
                    shutil.copytree(ap, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(ap, target)
            for fmt in new_formats:
                variant = FileVariant(format=fmt, path=f"{rel_dir}/{doc.id}.{fmt}", source=source_)
                doc.files = [f for f in doc.files if f.format != fmt] + [variant]
            if primary_ is not None:
                doc.primary = primary_
            commit_library(root, catalog)
        except BaseException:
            for target in created:
                target.unlink(missing_ok=True)
            raise

    effective_remove = get_config(ctx).remove_source if remove_source_ is None else remove_source_
    if effective_remove:
        for p in paths:
            p.unlink(missing_ok=True)
    click.echo(f"added format(s) {', '.join(new_formats)} to '{doc_id}'")
