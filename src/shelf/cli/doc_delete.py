"""shelf doc delete (PRD §11.10) and orphan commands (§11.15 — Task 5)."""

import shutil
import sys

import click

from shelf.cli.doc_variants import find_doc
from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import commit_library, load_catalog
from shelf.core.ingest import doc_rel_dir


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
