"""The read surface: doc list and doc view (PRD §11.11)."""

import json

import click

from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import resolve_targets, scope_option
from shelf.core.catalog import Document, load_catalog
from shelf.core.errors import ConflictError, NotFoundError


def _anchor(doc: Document) -> str:
    return f"repo:{doc.repo.name}" if doc.repo else f"topic:{doc.category}"


def _matches(doc: Document, query: str) -> bool:
    q = query.lower()
    hay = [doc.id, doc.title, doc.description, *doc.tags]
    if doc.repo and doc.repo.subject:
        hay.append(doc.repo.subject)
    return any(q in h.lower() for h in hay)


@click.command("list")
@click.option("--repo", "repo_", default=None, help="Only documents anchored to this repo.")
@click.option("--topic", "topic_", default=None, help="Only documents in this topic.")
@click.option("--kind", "kind_", default=None, help="Only documents of this kind.")
@click.option("--tag", "tags_", multiple=True, help="Require this tag (repeatable, AND).")
@click.option(
    "--query", default=None, help="Substring match over id/title/description/tags/subject."
)
@click.option("--limit", type=int, default=None, help="Cap the number of results.")
@click.option(
    "--sort-by", type=click.Choice(["added", "title"]), default="added", show_default=True
)
@output_options
@scope_option(allow_all=True)
@click.pass_context
def doc_list(ctx, repo_, topic_, kind_, tags_, query, limit, sort_by, output, json_):
    """Filter and query documents across the project and user libraries."""
    scoped = [(t.scope, d) for t in resolve_targets(ctx) for d in load_catalog(t.root).documents]
    scope_of = {id(d): scope for scope, d in scoped}
    docs = [d for _, d in scoped]
    if repo_:
        docs = [d for d in docs if d.repo and d.repo.name == repo_]
    if topic_:
        docs = [d for d in docs if d.category == topic_]
    if kind_:
        docs = [d for d in docs if d.kind == kind_]
    for tag in tags_:
        docs = [d for d in docs if tag in d.tags]
    if query:
        docs = [d for d in docs if _matches(d, query)]
    if sort_by == "title":
        docs = sorted(docs, key=lambda d: d.title.lower())
    else:
        docs = sorted(docs, key=lambda d: d.added or "", reverse=True)
    if limit is not None:
        docs = docs[:limit]
    if resolve_format(output, json_) == "json":
        rows = [{**d.to_dict(), "scope": scope_of[id(d)]} for d in docs]
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        for d in docs:
            click.echo(f"{d.id}\t{d.title}\t{d.kind}\t{_anchor(d)}\t{scope_of[id(d)]}")


@click.command("view")
@click.argument("doc_id")
@output_options
@scope_option(allow_all=True)
@click.pass_context
def doc_view(ctx, doc_id, output, json_):
    """Print one document in full (searches the project and user libraries)."""
    hits = [
        (t, d)
        for t in resolve_targets(ctx)
        for d in load_catalog(t.root).documents
        if d.id == doc_id
    ]
    if not hits:
        raise NotFoundError(
            f"document '{doc_id}' not found — try 'shelf doc list --query {doc_id}'"
        )
    if len(hits) > 1:
        raise ConflictError(
            f"document '{doc_id}' is in both the project and user libraries "
            "— pick one with --scope project or --scope user"
        )
    target, doc = hits[0]
    root = target.root
    data = {**doc.to_dict(), "scope": target.scope}
    for entry in data["files"]:
        entry["abs_path"] = str(root / entry["path"])
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for key, value in data.items():
            rendered_value = (
                json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
            )
            click.echo(f"{key}: {rendered_value}")
