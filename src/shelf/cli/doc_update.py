"""shelf doc update — pure catalog metadata rewrites (PRD §11.4)."""

import click

from shelf.cli.doc_variants import find_doc
from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import commit_library, load_catalog


def _reject_anchor(ctx, param, value):
    if value is not None:
        raise click.UsageError("anchoring changes relocate the document — use 'shelf doc move'")


@click.command("update")
@click.argument("doc_id")
@click.option("--title", default=None)
@click.option("--description", default=None)
@click.option("--kind", "kind_", default=None)
@click.option("--add-tag", "add_tags", multiple=True)
@click.option("--remove-tag", "remove_tags", multiple=True)
@click.option("--set-tags", default=None, help="Comma-separated replacement tag list.")
@click.option("--primary", "primary_", default=None)
@click.option("--doc-date", default=None)
@click.option("--clear-doc-date", is_flag=True)
@click.option("--source", "source_", default=None)
@click.option("--repo-url", default=None)
@click.option("--subject", default=None)
@click.option("--clear-subject", is_flag=True)
@click.option("--added", default=None, help="Dangerous: desyncs the slug (requires --force).")
@click.option("--force", "-f", is_flag=True)
@click.option("--topic", "topic_", callback=_reject_anchor, expose_value=False, default=None)
@click.option("--repo", "repo_", callback=_reject_anchor, expose_value=False, default=None)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def doc_update(
    ctx,
    doc_id,
    title,
    description,
    kind_,
    add_tags,
    remove_tags,
    set_tags,
    primary_,
    doc_date,
    clear_doc_date,
    source_,
    repo_url,
    subject,
    clear_subject,
    added,
    force,
    dry_run,
):
    """Change a document's metadata."""
    fields_given = any(
        [
            title is not None,
            description is not None,
            kind_ is not None,
            add_tags,
            remove_tags,
            set_tags is not None,
            primary_ is not None,
            doc_date is not None,
            clear_doc_date,
            source_ is not None,
            repo_url is not None,
            subject is not None,
            clear_subject,
            added is not None,
        ]
    )
    if not fields_given:
        raise click.UsageError("at least one field option is required")

    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        before = doc.to_dict()

        if kind_ is not None and kind_ not in catalog.kinds:
            raise click.ClickException(f"kind '{kind_}' is not in the kind list")
        if primary_ is not None and primary_ not in {f.format for f in doc.files}:
            raise click.UsageError(f"--primary '{primary_}' is not a format this document has")
        if repo_url is not None or subject is not None or clear_subject:
            repo_ref = doc.repo
            if repo_ref is None:
                raise click.ClickException("repo fields only apply to repo-anchored documents")
            if repo_url is not None:
                repo_ref.url = repo_url
            if subject is not None:
                repo_ref.subject = subject
            if clear_subject:
                repo_ref.subject = None
        if added is not None and not force:
            raise click.ClickException(
                "--added desyncs the slug's date prefix — pass --force to proceed"
            )

        if title is not None:
            doc.title = title
        if description is not None:
            doc.description = description
        if kind_ is not None:
            doc.kind = kind_
        if set_tags is not None:
            doc.tags = [t for t in (s.strip() for s in set_tags.split(",")) if t]
        for tag in add_tags:
            if tag not in doc.tags:
                doc.tags.append(tag)
        for tag in remove_tags:
            if tag in doc.tags:
                doc.tags.remove(tag)
        if primary_ is not None:
            doc.primary = primary_
        if doc_date is not None:
            doc.doc_date = doc_date
        if clear_doc_date:
            doc.doc_date = None
        if source_ is not None:
            doc.source = source_
        if added is not None:
            doc.added = added
            click.echo(
                "warning: --added desyncs the slug's date prefix (audit will flag it)", err=True
            )

        after = doc.to_dict()
        changes = [
            f"{key}: {before.get(key)} -> {after.get(key)}"
            for key in sorted(set(before) | set(after))
            if before.get(key) != after.get(key)
        ]
        if dry_run:
            for line in changes:
                click.echo(line)
            return
        commit_library(root, catalog)
    for line in changes:
        click.echo(line)
