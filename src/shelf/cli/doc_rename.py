"""shelf doc rename — change a document's ID and folder together (P25, Q4)."""

import datetime
import shutil
from pathlib import Path

import click

from shelf.cli.commit import (
    auto_message,
    commit_options,
    library_paths,
    require_git_if_commit,
)
from shelf.cli.doc_variants import find_doc
from shelf.cli.runtime import get_library, scope_option
from shelf.core.atomic import library_lock
from shelf.core.catalog import CATALOG_FILENAME, commit_library, load_catalog
from shelf.core.errors import ConflictError
from shelf.core.git import git_commit_all
from shelf.core.ingest import check_free_folder, claim_folder, doc_rel_dir
from shelf.core.slugs import apply_date_rule, is_iso_date, undated_warning, validate_slug


@click.command(
    "rename",
    epilog=(
        "Example:\n\n\b\n"
        "  shelf doc rename 2026-11-12-superpowers 2026-11-12-skills-notes --dry-run"
    ),
)
@click.argument("doc_id")
@click.argument("new_slug")
@click.option("--dry-run", is_flag=True)
@commit_options
@scope_option()
@click.pass_context
def doc_rename(ctx, doc_id, new_slug, dry_run, commit, commit_message):
    """Rename a document's ID and folder (the added date is prefixed when NEW_SLUG has none)."""
    validate_slug(new_slug)
    root = get_library(ctx)
    require_git_if_commit(root, commit)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        base = doc.added if is_iso_date(doc.added) else datetime.date.today().isoformat()
        new_id, added, dated = apply_date_rule(new_slug, base)
        if new_id == doc_id:
            raise ConflictError(f"'{doc_id}' already has that ID")
        if any(d.id == new_id for d in catalog.documents):
            raise ConflictError(f"slug '{new_id}' already exists — pick another name")
        old_rel = doc_rel_dir(doc)
        doc.id = new_id
        doc.added = added
        new_rel = doc_rel_dir(doc)
        if (root / new_rel).exists():
            raise ConflictError(f"folder '{new_rel}' already exists — pick another name")
        check_free_folder(catalog, new_rel, exclude=doc)

        # Variant files named <id>.<format> follow the ID; other names (adopted files,
        # supporting assets) are kept.
        src_dir = root / old_rel
        dest_dir = root / new_rel
        renames: list[tuple[str, str]] = []
        new_paths: list[str] = []
        for variant in doc.files:
            name = Path(variant.path).name
            if Path(name).stem == doc_id:
                new_name = new_id + Path(name).suffix
                renames.append((name, new_name))
                name = new_name
            new_paths.append(f"{new_rel}/{name}")
        moved_away = {old for old, _ in renames}
        for _, new_name in renames:
            if (src_dir / new_name).exists() and new_name not in moved_away:
                raise ConflictError(
                    f"'{old_rel}/{new_name}' already exists and would be overwritten "
                    "— rename or remove it first"
                )
        if dated:
            click.echo(undated_warning(new_slug, new_id), err=True)
        if dry_run:
            click.echo(f"would rename '{doc_id}' -> '{new_id}' ({old_rel} -> {new_rel})")
            return
        for variant, path in zip(doc.files, new_paths, strict=True):
            variant.path = path

        claim_folder(dest_dir, new_rel)
        before_text = (root / CATALOG_FILENAME).read_text(encoding="utf-8")
        try:
            shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
            for old_name, new_name in renames:
                (dest_dir / old_name).rename(dest_dir / new_name)
            commit_library(root, catalog)
        except BaseException:
            try:
                committed = (root / CATALOG_FILENAME).read_text(encoding="utf-8") != before_text
            except OSError:
                # unreadable witness: keep data — residue is orphan-detectable.
                committed = True
            if not committed:
                shutil.rmtree(dest_dir, ignore_errors=True)
            raise
        shutil.rmtree(src_dir, ignore_errors=True)
    if commit:
        git_commit_all(
            root,
            commit_message or auto_message("doc", "rename", doc_id, "to", new_id),
            library_paths(old_rel, new_rel),
        )
    click.echo(f"renamed '{doc_id}' -> '{new_id}' ({old_rel} -> {new_rel})")
    click.echo(
        "warning: absolute paths previously copied for this document no longer resolve",
        err=True,
    )
