"""shelf doc move — relocate a document (PRD §11.5)."""

import shutil
from contextlib import ExitStack

import click

from shelf.cli.commit import (
    auto_message,
    commit_options,
    library_paths,
    require_git_if_commit,
)
from shelf.cli.doc_variants import find_doc
from shelf.cli.runtime import (
    get_library,
    resolve_target,
    same_library,
    scope_option,
    scope_target,
)
from shelf.core.atomic import library_lock
from shelf.core.catalog import CATALOG_FILENAME, RepoRef, commit_library, load_catalog
from shelf.core.errors import ConflictError
from shelf.core.git import git_commit_all
from shelf.core.ingest import (
    check_free_folder,
    claim_folder,
    doc_rel_dir,
    overlaps,
    prune_nested_group,
    validate_repo_name,
)


@click.command("move")
@click.argument("doc_id")
@click.option("--topic", "topic_", default=None)
@click.option("--create-topic", is_flag=True)
@click.option("--repo", "repo_", default=None, help="<repo> or <owner>/<repo>.")
@click.option("--repo-url", default=None)
@click.option("--subject", default=None)
@click.option(
    "--to-scope",
    type=click.Choice(["user", "project"]),
    default=None,
    help="Move the document to the other scope's library, keeping its anchor.",
)
@click.option("--dry-run", is_flag=True)
@commit_options
@scope_option()
@click.pass_context
def doc_move(
    ctx,
    doc_id,
    topic_,
    create_topic,
    repo_,
    repo_url,
    subject,
    to_scope,
    dry_run,
    commit,
    commit_message,
):
    """Relocate a document (topic, repo, or anchoring change), or move it between scopes."""
    if to_scope is not None:
        if topic_ or repo_ or repo_url or subject:
            raise click.UsageError(
                "--to-scope keeps the anchor; it cannot be combined with --topic or --repo"
            )
        _move_to_scope(ctx, doc_id, to_scope, create_topic, dry_run, commit, commit_message)
        return
    if (topic_ is None) == (repo_ is None):
        raise click.UsageError("exactly one of --topic or --repo is required")
    if repo_ is not None:
        validate_repo_name(repo_)

    root = get_library(ctx)
    require_git_if_commit(root, commit)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        old_rel = doc_rel_dir(doc)

        if topic_ is not None:
            if doc.repo is None and doc.category == topic_:
                raise click.ClickException(f"'{doc_id}' is already in topic '{topic_}'")
            if topic_ not in catalog.topics:
                if not create_topic:
                    raise click.ClickException(
                        f"unknown topic '{topic_}' — pass --create-topic to create it"
                    )
                catalog.topics.append(topic_)
            doc.repo = None
            doc.category = topic_
        else:
            if doc.repo is not None and doc.repo.name == repo_:
                raise click.ClickException(f"'{doc_id}' is already anchored to repo '{repo_}'")
            doc.category = None
            doc.repo = RepoRef(name=repo_, url=repo_url, subject=subject)

        new_rel = doc_rel_dir(doc)
        if overlaps(new_rel, old_rel):
            raise ConflictError(
                f"folder '{new_rel}' overlaps the document's own folder '{old_rel}'"
            )
        if (root / new_rel).exists():
            raise ConflictError(f"folder '{new_rel}' already exists")
        check_free_folder(catalog, new_rel, exclude=doc)
        if dry_run:
            click.echo(f"would move {old_rel} -> {new_rel}")
            return
        for variant in doc.files:
            variant.path = variant.path.replace(old_rel, new_rel, 1)

        src_dir = root / old_rel
        dest_dir = root / new_rel
        claim_folder(dest_dir, new_rel)
        before_text = (root / CATALOG_FILENAME).read_text(encoding="utf-8")
        try:
            shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)
            commit_library(root, catalog)
        except BaseException:
            try:
                committed = (root / CATALOG_FILENAME).read_text(encoding="utf-8") != before_text
            except OSError:
                # unreadable witness: keep data — residue is orphan-detectable.
                committed = True
            if not committed:
                shutil.rmtree(dest_dir, ignore_errors=True)
                prune_nested_group(root, new_rel)
            raise
        shutil.rmtree(src_dir, ignore_errors=True)
        prune_nested_group(root, old_rel)
    if commit:
        git_commit_all(
            root,
            commit_message or auto_message("doc", "move", doc_id),
            library_paths(old_rel, new_rel),
        )
    click.echo(f"moved '{doc_id}' {old_rel} -> {new_rel}")
    click.echo(
        "warning: absolute paths previously copied for this document no longer resolve",
        err=True,
    )


def _move_to_scope(ctx, doc_id, to_scope, create_topic, dry_run, commit, commit_message):
    """Add to the target library, then delete from the source, holding both locks.

    Holding the source lock across the copy keeps a concurrent edit of the source
    from being deleted unseen. The locks are taken in path order, so two opposite
    moves cannot deadlock. A failure between the two steps leaves the document in
    both libraries, which `shelf audit` reports as a cross-scope duplicate (check 6).
    """
    source = resolve_target(ctx)
    if source.scope == to_scope:
        raise click.UsageError(f"'{doc_id}' is already in the {to_scope} library")
    target = scope_target(ctx, to_scope)
    if same_library(source, target):
        raise click.UsageError(
            f"the {source.scope} and {to_scope} scopes are the same library ({source.root})"
        )
    require_git_if_commit(source.root, commit)
    require_git_if_commit(target.root, commit)
    rel = None
    leftover = None
    with ExitStack() as locks:
        for root in sorted((source.root, target.root), key=lambda p: str(p.resolve())):
            locks.enter_context(library_lock(root))
        doc = find_doc(load_catalog(source.root), doc_id)
        rel = doc_rel_dir(doc)
        catalog = load_catalog(target.root, for_write=True)
        if any(d.id == doc_id for d in catalog.documents):
            raise ConflictError(f"'{doc_id}' is already in the {to_scope} library")
        if doc.kind not in catalog.kinds:
            raise click.ClickException(
                f"kind '{doc.kind}' is not in the {to_scope} library — "
                f"add it with 'shelf kind add {doc.kind} --scope {to_scope}'"
            )
        if doc.category is not None and doc.category not in catalog.topics:
            if not create_topic:
                raise click.ClickException(
                    f"unknown topic '{doc.category}' in the {to_scope} library "
                    "— pass --create-topic to create it"
                )
            catalog.topics.append(doc.category)
        check_free_folder(catalog, rel)
        if dry_run:
            click.echo(f"would move '{doc_id}' {source.scope} -> {to_scope} ({rel})")
            return
        dest = target.root / rel
        if dest.exists():
            raise ConflictError(f"folder '{rel}' already exists in the {to_scope} library")
        claim_folder(dest, rel)
        before_text = (target.root / CATALOG_FILENAME).read_text(encoding="utf-8")
        try:
            shutil.copytree(source.root / rel, dest, dirs_exist_ok=True)
            catalog.documents.append(doc)
            commit_library(target.root, catalog)
        except BaseException:
            try:
                committed = (target.root / CATALOG_FILENAME).read_text(
                    encoding="utf-8"
                ) != before_text
            except OSError:
                committed = True  # unreadable witness: keep data — residue is audit-detectable
            if not committed:
                shutil.rmtree(dest, ignore_errors=True)
                prune_nested_group(target.root, rel)
            raise
        try:
            _delete_from_source(source.root, doc_id, rel)
        except OSError as exc:
            leftover = exc
    if commit:
        git_commit_all(
            target.root,
            commit_message or auto_message("doc", "move", doc_id, "from", source.scope),
            library_paths(rel),
        )
    if leftover is not None:
        raise click.ClickException(
            f"'{doc_id}' was added to the {to_scope} library but not removed from the "
            f"{source.scope} library ({leftover}) — remove the leftover with "
            f"'shelf doc delete {doc_id} --scope {source.scope}'"
        ) from leftover
    if commit:
        git_commit_all(
            source.root,
            commit_message or auto_message("doc", "move", doc_id, "to", to_scope),
            library_paths(rel),
        )
    click.echo(f"moved '{doc_id}' {source.scope} -> {to_scope} ({rel})")


def _delete_from_source(root, doc_id, rel):
    """Caller holds the source library lock."""
    catalog = load_catalog(root, for_write=True)
    catalog.documents = [d for d in catalog.documents if d.id != doc_id]
    commit_library(root, catalog)
    shutil.rmtree(root / rel, ignore_errors=True)
    prune_nested_group(root, rel)
