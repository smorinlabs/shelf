"""shelf doc move — relocate a document (PRD §11.5)."""

import shutil

import click

from shelf.cli.doc_variants import find_doc
from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import CATALOG_FILENAME, RepoRef, commit_library, load_catalog
from shelf.core.ingest import doc_rel_dir


@click.command("move")
@click.argument("doc_id")
@click.option("--topic", "topic_", default=None)
@click.option("--create-topic", is_flag=True)
@click.option("--repo", "repo_", default=None)
@click.option("--repo-url", default=None)
@click.option("--subject", default=None)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def doc_move(ctx, doc_id, topic_, create_topic, repo_, repo_url, subject, dry_run):
    """Relocate a document (topic, repo, or anchoring change)."""
    if (topic_ is None) == (repo_ is None):
        raise click.UsageError("exactly one of --topic or --repo is required")

    root = get_library(ctx)
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
        if dry_run:
            click.echo(f"would move {old_rel} -> {new_rel}")
            return
        for variant in doc.files:
            variant.path = variant.path.replace(old_rel, new_rel, 1)

        src_dir = root / old_rel
        dest_dir = root / new_rel
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_dir, dest_dir)
        before_text = (root / CATALOG_FILENAME).read_text(encoding="utf-8")
        try:
            commit_library(root, catalog)
        except BaseException:
            try:
                committed = (root / CATALOG_FILENAME).read_text(encoding="utf-8") != before_text
            except OSError:
                committed = False
            if not committed:
                shutil.rmtree(dest_dir, ignore_errors=True)
            raise
        shutil.rmtree(src_dir, ignore_errors=True)
    click.echo(f"moved '{doc_id}' {old_rel} -> {new_rel}")
    click.echo(
        "warning: absolute paths previously copied for this document no longer resolve",
        err=True,
    )
