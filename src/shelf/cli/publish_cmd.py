"""`shelf publish` — build the filtered static site (P21; PRD §11)."""

from pathlib import Path

import click

from shelf.cli.runtime import resolve_target, scope_option
from shelf.core import publish as pub
from shelf.core import visibility
from shelf.core.atomic import library_lock
from shelf.core.catalog import load_catalog
from shelf.core.errors import GuardError

_EPILOG = """\b
Examples:
  shelf publish --dry-run            # what would be published, and from which repo
  shelf publish                      # build _site/ with documents marked --publish
  shelf publish --force              # the repo is private: publish anyway
\b
Publishing everything: set publish = "all" in the library's config file
(every document and every variant). A private, internal, or undetectable repo
always needs --force, in both modes; no config key turns that guard off.
"""


def _plural(n: int) -> str:
    return f"{n} document" + ("" if n == 1 else "s")


@click.command("publish", epilog=_EPILOG)
@click.option(
    "--out",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("_site"),
    show_default=True,
    help="Folder to build the site into.",
)
@click.option("--dry-run", is_flag=True, help="List what would be published; build nothing.")
@click.option("--force", is_flag=True, help="Publish from a private, internal, or unknown repo.")
@click.option("--base-url", default=None, help="Site URL for this build (overrides config).")
@click.option(
    "--detected-base-url",
    default=None,
    help="Pages URL found by the workflow (actions/configure-pages); used when no override.",
)
@scope_option()
@click.pass_context
def publish_cmd(ctx, out, dry_run, force, base_url, detected_base_url):
    """Build a static site of the library's published documents."""
    target = resolve_target(ctx)
    root = target.root
    mode = pub.publish_mode(target.config.publish, target.config_path)
    pub.check_out_dir(root, out)
    repo = visibility.detect(root)
    where = f"{repo.slug or root} ({repo.visibility})"
    with library_lock(root):
        catalog = load_catalog(root)
        docs = pub.select(catalog, mode)
        held = len(catalog.documents) - len(docs)
        if dry_run:
            click.echo(
                f"would publish {len(docs)} of {len(catalog.documents)} documents "
                f"(mode: {mode}) from {where}"
            )
            for d in docs:
                click.echo(f"  {d.id}\t{d.title}")
            if held:
                click.echo(
                    f"{_plural(held)} not published. To publish everything, "
                    f'set publish = "all" in {target.config_path}.'
                )
            if repo.visibility != "public":
                click.echo(_guard_note(repo.visibility))
            return
        if repo.visibility != "public" and not force:
            raise GuardError(
                f"{_subject(repo, root)}; publishing {_plural(len(docs))} requires --force: "
                f"shelf publish --out {out} --force"
            )
        url = (
            base_url
            or target.config.base_url
            or detected_base_url
            or visibility.pages_url(repo.slug)
            or ""
        ).rstrip("/")
        pub.build_site(
            root, catalog, docs, out, base_url=url, source=pub.source_base(root, repo.slug)
        )
    click.echo(f"built {out}: {_plural(len(docs))} (mode: {mode}) from {where}")


def _subject(repo: visibility.Repo, root: Path) -> str:
    if repo.visibility != "unknown":
        return f"{repo.slug} is {repo.visibility}"
    if repo.slug is None:
        return (
            f"the library at {root} is in no GitHub repo shelf can check "
            "(visibility unknown, treated as private)"
        )
    return f"{repo.slug} visibility could not be checked (unknown, treated as private)"


def _guard_note(vis: str) -> str:
    if vis == "unknown":
        return "Repo visibility is unknown (treated as private): publishing requires --force."
    return f"This repo is {vis}: publishing requires --force."
