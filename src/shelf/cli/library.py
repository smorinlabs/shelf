"""Library-level commands: path (this task); init/adopt and migrate follow."""

from pathlib import Path

import click

from shelf.cli.runtime import active_config_path, get_config, get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import CATALOG_FILENAME, SEED_KINDS, Catalog, commit_library, load_catalog
from shelf.core.config import save_config
from shelf.core.errors import ConflictError
from shelf.core.paths import default_library_path

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
    if cfg.library and Path(cfg.library, CATALOG_FILENAME).is_file() and not force:
        raise ConflictError(
            f"a library is already configured at {cfg.library} — pass --force to re-initialize"
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
