"""Library-level commands: path (this task); init/adopt and migrate follow."""

import json
from pathlib import Path

import click

from shelf.cli.runtime import active_config_path, get_config, get_library
from shelf.core.atomic import atomic_write_text, library_lock
from shelf.core.catalog import (
    CATALOG_FILENAME,
    CURRENT_SCHEMA_VERSION,
    SEED_KINDS,
    Catalog,
    commit_library,
    load_catalog,
)
from shelf.core.config import save_config
from shelf.core.errors import ConflictError
from shelf.core.index import render_index
from shelf.core.migrations import MIGRATIONS
from shelf.core.paths import default_library_path
from shelf.core.preview import build_snippets

README_TEXT = "# shelf library\n\nManaged by the `shelf` CLI — do not edit catalog.json by hand.\n"


def validate_library(root: Path) -> None:
    if not (root / CATALOG_FILENAME).is_file():
        raise click.ClickException(f"'{root}' has no catalog.json — not a shelf library")
    load_catalog(root)  # parses; refuses a newer schema
    for sub in ("docs/repos", "docs/topics"):
        if not (root / sub).is_dir():
            raise click.ClickException(f"'{root}' is missing {sub}/ — not a shelf library")


@click.command("init")
@click.option(
    "--library", "library_", type=click.Path(), default=None, help="Where to create the library."
)
@click.option(
    "--adopt",
    "adopt_",
    type=click.Path(),
    default=None,
    help="Register an existing library instead of scaffolding.",
)
@click.option("--force", is_flag=True, help="Re-initialize over an existing configured library.")
@click.pass_context
def init_cmd(ctx: click.Context, library_: str | None, adopt_: str | None, force: bool) -> None:
    """Create, adopt, and register a library."""
    if adopt_ and force:
        raise click.UsageError("--adopt and --force are mutually exclusive")
    cfg_path = active_config_path(ctx)
    cfg = get_config(ctx)

    if adopt_:
        root = Path(adopt_)
        validate_library(root)
        cfg.library = str(root)
        save_config(cfg_path, cfg)
        click.echo(f"adopted library at {root}")
        return

    root = Path(library_ or ctx.obj.get("library") or default_library_path())
    target_exists = (root / CATALOG_FILENAME).is_file()
    configured_root = Path(cfg.library) if cfg.library else None
    configured_exists = (
        configured_root is not None and (configured_root / CATALOG_FILENAME).is_file()
    )
    if (target_exists or configured_exists) and not force:
        existing_root = root if target_exists else configured_root
        raise ConflictError(
            f"a library already exists at {existing_root} — pass --force to re-initialize "
            f"or 'shelf init --adopt {existing_root}' to register it"
        )
    (root / "docs" / "repos").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "topics").mkdir(parents=True, exist_ok=True)
    with library_lock(root):
        commit_library(root, Catalog(kinds=list(SEED_KINDS)))
    if not (root / "README.md").is_file():
        (root / "README.md").write_text(README_TEXT, encoding="utf-8")
    cfg.library = str(root)
    save_config(cfg_path, cfg)
    click.echo(f"initialized library at {root}")


@click.command("path")
@click.argument("which", required=False, type=click.Choice(["config", "index"]))
@click.pass_context
def path_cmd(ctx: click.Context, which: str | None) -> None:
    """Print resolved locations."""
    if which == "config":
        click.echo(active_config_path(ctx))
        return
    root = get_library(ctx)
    click.echo(root / "index.html" if which == "index" else root)


@click.command("regen")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def regen_cmd(ctx: click.Context, dry_run: bool) -> None:
    """Regenerate index.html from the current catalog and installed template."""
    root = get_library(ctx)
    with library_lock(root):
        catalog_text = (root / CATALOG_FILENAME).read_text(encoding="utf-8")
        raw = json.loads(catalog_text)
        if raw.get("schema_version", 0) > CURRENT_SCHEMA_VERSION:
            raise click.ClickException(
                "catalog schema_version is newer than this shelf understands — upgrade shelf"
            )
        if dry_run:
            click.echo("would regenerate index.html")
            return
        snips = build_snippets(root, raw.get("documents", []))
        atomic_write_text(root / "index.html", render_index(catalog_text, snips))
    click.echo("regenerated index.html")


@click.command("migrate")
@click.option("--dry-run", is_flag=True, help="Report the migration without applying it.")
@click.option("--json", "json_", is_flag=True, help="Machine-readable report.")
@click.pass_context
def migrate_cmd(ctx: click.Context, dry_run: bool, json_: bool) -> None:
    """Migrate the catalog to the current schema version."""
    root = get_library(ctx)
    with library_lock(root):
        raw = json.loads((root / CATALOG_FILENAME).read_text(encoding="utf-8"))
        found = raw.get("schema_version", 0)
        if found > CURRENT_SCHEMA_VERSION:
            raise click.ClickException(
                f"catalog schema_version {found} is newer than this shelf understands "
                "— upgrade shelf"
            )
        report = {"from": found, "to": CURRENT_SCHEMA_VERSION}
        if found == CURRENT_SCHEMA_VERSION:
            click.echo(
                json.dumps(report) if json_ else "catalog is already at the current schema version"
            )
            return
        if dry_run:
            click.echo(
                json.dumps(report)
                if json_
                else f"would migrate schema_version {found} -> {CURRENT_SCHEMA_VERSION}"
            )
            return
        for step in range(found, CURRENT_SCHEMA_VERSION):
            raw = MIGRATIONS[step](raw)
        commit_library(root, Catalog.from_dict(raw))
    click.echo(
        json.dumps(report)
        if json_
        else f"migrated schema_version {found} -> {CURRENT_SCHEMA_VERSION}"
    )
