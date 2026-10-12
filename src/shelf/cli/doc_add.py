"""shelf doc add — ingest a new document (PRD §11.2)."""

import datetime
import shutil
from pathlib import Path

import click

from shelf.cli.commit import auto_message, commit_options, require_git_if_commit
from shelf.cli.runtime import get_config, get_library
from shelf.core import handoff
from shelf.core.atomic import library_lock
from shelf.core.catalog import (
    CATALOG_FILENAME,
    Document,
    FileVariant,
    RepoRef,
    commit_library,
    load_catalog,
)
from shelf.core.errors import ConflictError
from shelf.core.git import git_commit_all
from shelf.core.ingest import doc_rel_dir, infer_format, infer_repo_url, pick_primary
from shelf.core.reference import check_reference, read_record
from shelf.core.reference_transaction import (
    begin_transaction,
    clear_transaction,
    write_reference_file,
)
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
@click.option("--kind", "kind_", default=None, help="Document kind (must exist).")
@click.option("--tag", "tags_", multiple=True, help="Free-form tag (repeatable).")
@click.option("--title", default=None)
@click.option("--description", default=None)
@click.option(
    "--handoff-agent",
    "handoff_agent",
    default=None,
    type=click.Choice(["claude", "codex"]),
    help="Agent to hand off to when classification flags are missing (overrides config).",
)
@click.option(
    "--no-handoff",
    "no_handoff",
    is_flag=True,
    help="Suppress the handoff; missing flags become an error.",
)
@click.option("--slug", "slug_", default=None, help="Override the derived slug.")
@click.option("--primary", "primary_", default=None, help="Primary format (default heuristic).")
@click.option("--reference-record", type=click.Path(exists=True, dir_okay=False))
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
@commit_options
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
    handoff_agent,
    no_handoff,
    commit,
    commit_message,
    reference_record,
):
    """Add a new document."""
    paths = [Path(f).resolve() for f in files]
    record = read_record(reference_record) if reference_record else None
    if record is not None and (format_ is not None or assets_):
        raise click.UsageError("reference ingestion does not accept --format or --assets")
    if repo_ is not None and topic_ is not None:
        raise click.UsageError("--repo and --topic are mutually exclusive")

    def _blank(value):
        return value is None or not str(value).strip()

    anchor_present = repo_ is not None or topic_ is not None
    if not anchor_present or _blank(kind_) or _blank(title) or _blank(description):
        # Suppression first: --no-input always exits 2 even inside a session (PRD §5).
        if no_handoff or ctx.obj.get("no_input", False):
            raise click.UsageError(
                "missing required classification flags "
                "(--kind, --title, --description, and one of --repo/--topic)"
            )
        session = handoff.in_ai_session()
        if session is not None:
            raise click.ClickException(
                f"already inside a {session} session — invoke the shelf skill "
                "directly instead of nesting a handoff"
            )
        agent = handoff.resolve_agent(handoff_agent, get_config(ctx).handoff_agent)
        handoff.run_handoff(agent, paths)
        return  # unreachable: run_handoff execs
    formats = [infer_format(p, format_) for p in paths]
    if len(set(formats)) != len(formats):
        raise click.UsageError(
            "two files of the same format — run 'shelf doc add' once per document"
        )
    if primary_ is not None and primary_ not in formats:
        raise click.UsageError(f"--primary '{primary_}' is not among the added formats")

    root = get_library(ctx)
    if record and any(
        p.is_relative_to(root.resolve()) for p in [*paths, Path(reference_record).resolve()]
    ):
        raise click.UsageError("stage reference inputs outside the library to preserve originals")
    require_git_if_commit(root, commit)
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

        if record is not None:
            check_reference(record, paths, catalog)
            if title != record["name"] or description != (record.get("description") or "Unknown"):
                raise click.UsageError("title and description must match the reference record")
            tags_ = tuple(
                dict.fromkeys(
                    [
                        *tags_,
                        *record.get("tags", []),
                        *record.get("categories", []),
                        *record.get("projects", []),
                    ]
                )
            )
            paths.append(Path(reference_record).resolve())
            formats.append("json")
        added = datetime.date.today().isoformat()
        slug = derive_slug(title, added, slug_)
        if slug_ and len(slug) >= 10 and slug[4] == "-" and slug[7] == "-":
            added = slug[:10]
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
            source=record["entity_url"] if record else source_ or str(paths[0]),
            reference=record,
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
        before_text: str | None = None
        try:
            staged = begin_transaction(root, doc, paths, formats) if record else {}
            for p, fmt in zip(paths, formats, strict=True):
                target = dest / f"{slug}.{fmt}"
                if record:
                    write_reference_file(target, staged[str(target.relative_to(root))]["after"])
                else:
                    shutil.copy2(p, target)
            for a in assets_:
                ap = Path(a)
                if ap.is_dir():
                    shutil.copytree(ap, dest / ap.name)
                else:
                    shutil.copy2(ap, dest / ap.name)
            catalog.documents.append(doc)
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
                shutil.rmtree(dest, ignore_errors=True)
                if record:
                    clear_transaction(root)
            raise

    if commit:
        git_commit_all(root, commit_message or auto_message("doc", "add", slug))
    effective_remove = get_config(ctx).remove_source if remove_source_ is None else remove_source_
    if effective_remove:
        for p in paths:
            p.unlink(missing_ok=True)
    click.echo(f"added '{slug}' ({', '.join(formats)}) -> {rel_dir}")
