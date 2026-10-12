"""doc format add / delete (PRD §11.3, §11.13)."""

import shutil
from pathlib import Path

import click

from shelf.cli.commit import auto_message, commit_options, require_git_if_commit
from shelf.cli.runtime import get_config, get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import (
    CATALOG_FILENAME,
    Catalog,
    Document,
    FileVariant,
    commit_library,
    load_catalog,
)
from shelf.core.errors import ConflictError, NotFoundError
from shelf.core.git import git_commit_all
from shelf.core.ingest import doc_rel_dir, infer_format
from shelf.core.reference import check_reference, read_record
from shelf.core.reference_transaction import (
    begin_transaction,
    clear_transaction,
    write_reference_file,
)


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
@click.option("--reference-record", type=click.Path(exists=True, dir_okay=False))
@click.option("--assets", "assets_", multiple=True, type=click.Path(exists=True))
@click.option("--format", "format_", default=None)
@click.option("--replace", is_flag=True, help="Overwrite an existing same-format variant.")
@click.option("--primary", "primary_", default=None)
@click.option("--source", "source_", default=None)
@click.option("--remove-source/--no-remove-source", "remove_source_", default=None)
@commit_options
@click.pass_context
def format_add(
    ctx,
    doc_id,
    files,
    assets_,
    format_,
    replace,
    primary_,
    source_,
    remove_source_,
    commit,
    commit_message,
    reference_record,
):
    """Add a format variant to an existing document."""
    paths = [Path(f).resolve() for f in files]
    record = read_record(reference_record) if reference_record else None
    if record is not None and (format_ is not None or assets_):
        raise click.UsageError("reference ingestion does not accept --format or --assets")
    new_formats = [infer_format(p, format_) for p in paths]
    if len(set(new_formats)) != len(new_formats):
        raise click.UsageError("two files of the same format")

    root = get_library(ctx)
    if record and any(
        p.is_relative_to(root.resolve()) for p in [*paths, Path(reference_record).resolve()]
    ):
        raise click.UsageError("stage reference inputs outside the library to preserve originals")
    require_git_if_commit(root, commit)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        if doc.reference and assets_:
            raise click.UsageError("managed references do not accept --assets")
        if (
            doc.reference
            and record is None
            and {"html", "json"} & {f.casefold() for f in new_formats}
        ):
            raise click.UsageError("managed references require --reference-record")
        if record is not None:
            check_reference(record, paths, catalog, old=doc, root=root)
            paths.append(Path(reference_record).resolve())
            new_formats.append("json")
            doc.reference = record
            doc.title = record["name"]
            doc.description = record.get("description") or "Unknown"
            doc.source = record["entity_url"]
            doc.tags = list(
                dict.fromkeys(
                    [
                        *doc.tags,
                        *record.get("tags", []),
                        *record.get("categories", []),
                        *record.get("projects", []),
                    ]
                )
            )
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
        backups: dict[Path, bytes] = {}
        before_text: str | None = None
        try:
            if record:
                # Transaction describes the new pair, including initial adoption.
                old_files = doc.files
                doc.files = [f for f in doc.files if f.format not in new_formats] + [
                    FileVariant(format=fmt, path=f"{rel_dir}/{doc.id}.{fmt}") for fmt in new_formats
                ]
                staged = begin_transaction(root, doc, paths, new_formats)
                doc.files = old_files
            for p, fmt in zip(paths, new_formats, strict=True):
                target = dest / f"{doc.id}.{fmt}"
                if not target.exists():
                    created.append(target)
                elif target.is_file():
                    backups.setdefault(target, target.read_bytes())
                if record:
                    write_reference_file(target, staged[str(target.relative_to(root))]["after"])
                else:
                    shutil.copy2(p, target)
            for a in assets_:
                ap = Path(a)
                target = dest / ap.name
                if not target.exists():
                    created.append(target)
                elif target.is_file() and target not in created:
                    backups.setdefault(target, target.read_bytes())
                if ap.is_dir():
                    shutil.copytree(ap, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(ap, target)
            for fmt in new_formats:
                variant = FileVariant(format=fmt, path=f"{rel_dir}/{doc.id}.{fmt}", source=source_)
                doc.files = [f for f in doc.files if f.format != fmt] + [variant]
            if primary_ is not None:
                doc.primary = primary_
            before_text = (root / CATALOG_FILENAME).read_text()
            commit_library(root, catalog)
            if record:
                clear_transaction(root)
        except BaseException:
            try:
                committed = (
                    before_text is not None and (root / CATALOG_FILENAME).read_text() != before_text
                )
            except OSError:
                # unreadable witness: keep data — residue is orphan-detectable.
                committed = True
            if not committed:
                for target in reversed(created):
                    if target.is_dir():
                        shutil.rmtree(target, ignore_errors=True)
                    else:
                        target.unlink(missing_ok=True)
                for target, data in backups.items():
                    if record:
                        write_reference_file(target, data.decode("utf-8"))
                    else:
                        target.write_bytes(data)
                if record:
                    clear_transaction(root)
            raise

    if commit:
        git_commit_all(
            root,
            commit_message or auto_message("doc", "format", "add", doc_id, ",".join(new_formats)),
        )
    effective_remove = get_config(ctx).remove_source if remove_source_ is None else remove_source_
    if effective_remove:
        for p in paths:
            p.unlink(missing_ok=True)
    click.echo(f"added format(s) {', '.join(new_formats)} to '{doc_id}'")


@click.command("delete")
@click.argument("doc_id")
@click.argument("fmt")
@click.option(
    "--primary", "primary_", default=None, help="New primary when deleting the current one."
)
@click.option("--force", "-f", is_flag=True, help="Drop the entry even if its file is missing.")
@commit_options
@click.pass_context
def format_delete(ctx, doc_id, fmt, primary_, force, commit, commit_message):
    """Remove one format variant."""
    root = get_library(ctx)
    require_git_if_commit(root, commit)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        if doc.reference and fmt in {"html", "json"}:
            raise click.UsageError(
                "cannot remove managed reference formats; delete the document instead"
            )
        variant = next((f for f in doc.files if f.format == fmt), None)
        if variant is None:
            raise NotFoundError(f"document '{doc_id}' has no '{fmt}' variant")
        if len(doc.files) == 1:
            raise ConflictError("cannot remove the last variant — use 'shelf doc delete'")
        remaining = {f.format for f in doc.files if f.format != fmt}
        if doc.primary == fmt and primary_ is None:
            raise click.UsageError("deleting the primary variant — pass --primary <successor>")
        if primary_ is not None and primary_ not in remaining:
            raise click.UsageError(f"--primary '{primary_}' is not a remaining format")
        target = root / variant.path
        if not target.exists() and not force:
            raise click.ClickException(
                f"file '{variant.path}' is already missing — pass --force to drop the entry"
            )
        doc.files = [f for f in doc.files if f.format != fmt]
        if primary_ is not None:
            doc.primary = primary_
        commit_library(root, catalog)
        target.unlink(missing_ok=True)
    if commit:
        git_commit_all(
            root,
            commit_message or auto_message("doc", "format", "delete", doc_id, fmt),
        )
    click.echo(f"removed '{fmt}' from '{doc_id}'")
