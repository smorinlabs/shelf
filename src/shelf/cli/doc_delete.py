"""shelf doc delete (PRD §11.10) and orphan commands (§11.15 — Task 5)."""

import json
import shutil
import sys
from pathlib import Path

import click

from shelf.cli.doc_variants import find_doc
from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import commit_library, load_catalog
from shelf.core.errors import ConflictError, NotFoundError
from shelf.core.ingest import doc_rel_dir, scan_orphans


def _confirm_or_fail(prompt: str, yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise click.UsageError("refusing to delete without confirmation — pass --yes")
    click.confirm(prompt, abort=True, err=True)


@click.command("delete")
@click.argument("doc_id")
@click.option("-y", "--yes", is_flag=True, help="Assume yes (non-interactive consent).")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def doc_delete(ctx, doc_id, yes, dry_run):
    """Delete a document — its entry and its folder."""
    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        rel_dir = doc_rel_dir(doc)
        if dry_run:
            click.echo(
                f"would delete '{doc_id}' and folder {rel_dir}/ ({len(doc.files)} variant(s))"
            )
            return
        _confirm_or_fail(f"delete '{doc_id}' and {rel_dir}/ permanently?", yes)
        catalog.documents = [d for d in catalog.documents if d.id != doc_id]
        commit_library(root, catalog)
        shutil.rmtree(root / rel_dir, ignore_errors=True)
    click.echo(f"deleted '{doc_id}'")


@click.command("list")
@output_options
@click.pass_context
def orphan_list(ctx, output, json_):
    """List uncataloged files under docs/."""
    root = get_library(ctx)
    orphans = scan_orphans(root, load_catalog(root))
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps(orphans, indent=2))
    else:
        for o in orphans:
            click.echo(o)


@click.command("delete")
@click.argument("path")
@click.option("-y", "--yes", is_flag=True)
@click.pass_context
def orphan_delete(ctx, path, yes):
    """Delete an uncataloged file or folder under docs/."""
    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root)
        rel = Path(path)
        if rel.is_absolute():
            if not rel.is_relative_to(root):
                raise click.UsageError(f"'{rel}' is outside the library at {root}")
            rel = rel.relative_to(root)
        target = root / rel
        if not str(rel).startswith("docs/"):
            raise click.UsageError("orphan paths live under docs/")
        if not target.exists():
            raise NotFoundError(f"'{rel}' does not exist")
        cataloged = {doc_rel_dir(d) for d in catalog.documents}
        rel_s = str(rel)
        if rel_s in cataloged or any(rel_s.startswith(c + "/") for c in cataloged):
            raise ConflictError(f"'{rel}' belongs to a cataloged document — not an orphan")
        _confirm_or_fail(f"delete orphan '{rel}' permanently?", yes)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    click.echo(f"deleted orphan '{rel}'")
