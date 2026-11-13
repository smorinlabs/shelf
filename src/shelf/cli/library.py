"""Library-level commands: path (this task); init/adopt and migrate follow."""

import json
import re
from pathlib import Path, PurePath

import click
import tomli_w

from shelf.cli.commit import (
    auto_message,
    commit_options,
    library_paths,
    require_git_if_commit,
)
from shelf.cli.runtime import (
    active_config_path,
    get_library,
    interactive,
    resolve_target,
    resolve_targets,
    scope_option,
    target_config_path,
    user_config,
)
from shelf.core import git as git_core
from shelf.core.atomic import atomic_write_text, library_lock
from shelf.core.catalog import (
    CATALOG_FILENAME,
    CURRENT_SCHEMA_VERSION,
    SEED_KINDS,
    Catalog,
    commit_library,
    load_catalog,
)
from shelf.core.config import CONFIG_FILENAME, PROJECT_DIR, save_config
from shelf.core.errors import ConflictError
from shelf.core.git import git_commit_all
from shelf.core.index import render_index
from shelf.core.migrations import MIGRATIONS
from shelf.core.paths import DEFAULT_PROJECT_LIBRARY, default_library_path
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
@click.option("--git", "git_", is_flag=True, help="Initialize the library as a Git repository.")
@click.option(
    "--github", is_flag=True, help="Create and link a private GitHub repository (implies --git)."
)
@click.option("--owner", metavar="<gh-owner>", help="GitHub owner for --github.")
@click.option(
    "--repo-name",
    metavar="<name>",
    help="GitHub repository name for --github (default: the library folder's name; "
    f"'{git_core.DEFAULT_GITHUB_REPO}' for the default user library).",
)
@click.option(
    "--no-register",
    "no_register",
    is_flag=True,
    help="Create the library without registering it in the user config.",
)
@click.option(
    "--scope",
    type=click.Choice(["user", "project"]),
    default="user",
    show_default=True,
    help="user: your personal library. project: a library committed in this Git repo.",
)
@click.option("-y", "--yes", is_flag=True, help="Accept offers (installing the agent skills).")
@click.pass_context
def init_cmd(
    ctx: click.Context,
    library_: str | None,
    adopt_: str | None,
    force: bool,
    git_: bool,
    github: bool,
    owner: str | None,
    repo_name: str | None,
    no_register: bool,
    scope: str,
    yes: bool,
) -> None:
    """Create, adopt, and register a library.

    \b
    Examples:
      shelf init                    # your personal (user) library
      shelf init --scope project    # a library committed in the current Git repo
      shelf init --library ~/team-shelf --github --repo-name team-shelf
      shelf init --library ~/scratch-shelf --no-register
    """
    if scope == "project":
        if no_register:
            raise click.UsageError(
                "--scope project never registers in the user config; drop --no-register"
            )
        if adopt_ or git_ or github or owner or repo_name is not None:
            raise click.UsageError(
                "--scope project uses the Git repo you are in; "
                "it does not take --adopt, --git, --github, --owner, or --repo-name"
            )
        _init_project(ctx, library_, force, yes)
        return
    if owner and not github:
        raise click.UsageError("--owner requires --github")
    if repo_name is not None and not github:
        raise click.UsageError("--repo-name requires --github")
    if adopt_ and no_register:
        raise click.UsageError("--adopt only registers a library; it cannot take --no-register")
    if adopt_ and (force or git_ or github):
        raise click.UsageError("--adopt is mutually exclusive with --force, --git, and --github")
    cfg_path = active_config_path(ctx)
    cfg = user_config(ctx)

    if adopt_:
        root = Path(adopt_)
        validate_library(root)
        cfg.library = str(root)
        save_config(cfg_path, cfg)
        click.echo(f"adopted library at {root}")
        return

    root = Path(library_ or ctx.obj.get("library") or default_library_path())
    github_repo = _github_repo_name(root, repo_name) if github else None
    target_exists = (root / CATALOG_FILENAME).is_file()
    configured_root = Path(cfg.library) if cfg.library else None
    # An unregistered library never replaces the configured one, so only the target counts.
    configured_exists = (
        not no_register
        and configured_root is not None
        and (configured_root / CATALOG_FILENAME).is_file()
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
    if git_ or github:
        (root / "docs" / "repos" / ".gitkeep").write_text("", encoding="utf-8")
        (root / "docs" / "topics" / ".gitkeep").write_text("", encoding="utf-8")
        git_core.append_gitignore(root, [".shelf.lock"])
        git_core.git_init(root)
        git_core.git_commit_all(root, "shelf: init")
    if github_repo is not None:
        github_owner = owner or git_core._gh(["api", "user", "--jq", ".login"])
        git_core.github_create_and_link(root, github_owner, github_repo)
    if no_register:
        click.echo(f"initialized library at {root} (not registered)")
        click.echo(f"use it with: shelf --library {root} <command>")
        click.echo(f"or register it later with: shelf init --adopt {root}")
        return
    cfg.library = str(root)
    save_config(cfg_path, cfg)
    click.echo(f"initialized library at {root}")


def _github_repo_name(root: Path, repo_name: str | None) -> str:
    """The --github repository name, validated before anything is written or `gh` runs."""
    if repo_name is not None:
        if not git_core.valid_github_repo_name(repo_name):
            raise click.UsageError(
                f"--repo-name '{repo_name}' is not a valid GitHub repository name "
                "(letters, digits, '.', '_' and '-'; at most 100 characters; not ending in '.wiki')"
            )
        return repo_name
    if root.resolve() == default_library_path().resolve():
        return git_core.DEFAULT_GITHUB_REPO
    name = root.resolve().name
    if not git_core.valid_github_repo_name(name):
        raise click.UsageError(
            f"the library folder name '{name}' is not a valid GitHub repository name "
            "— pass --repo-name <name>"
        )
    return name


AGENT_INSTALL_PROJECT = "shelf agent install --scope project"


def _init_project(ctx: click.Context, library_: str | None, force: bool, yes: bool) -> None:
    """Scaffold `<repo>/.shelf/shelf_config.toml` and the library folder it names."""
    top = git_core.toplevel(Path.cwd())
    if top is None:
        raise click.ClickException(
            "--scope project needs a Git repository — run it inside one, or 'git init' first"
        )
    rel = library_ or DEFAULT_PROJECT_LIBRARY
    root = (top / rel).resolve()
    if PurePath(rel).is_absolute() or not root.is_relative_to(top):
        raise click.UsageError(f"--library must be a relative path inside {top}, not '{rel}'")
    cfg_path = top / PROJECT_DIR / CONFIG_FILENAME
    for existing in (cfg_path, root / CATALOG_FILENAME):
        if existing.exists() and not force:
            raise ConflictError(f"{existing} already exists — pass --force to re-initialize")
    for bucket in ("repos", "topics"):  # .gitkeep: a fresh clone still has both buckets
        (root / "docs" / bucket).mkdir(parents=True, exist_ok=True)
        (root / "docs" / bucket / ".gitkeep").touch()
    with library_lock(root):
        commit_library(root, Catalog(kinds=list(SEED_KINDS)))
    if root != top and not (root / "README.md").is_file():
        (root / "README.md").write_text(README_TEXT, encoding="utf-8")
    rel_posix = root.relative_to(top).as_posix()
    literal = re.sub(r"([\\*?\[\]])", r"\\\1", rel_posix)  # gitignore treats these as globs
    index_entry = "/index.html" if rel_posix == "." else f"/{literal}/index.html"
    git_core.append_gitignore(top, [".shelf.lock", index_entry])
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(cfg_path, tomli_w.dumps({"library": rel_posix, "remove-source": False}))
    click.echo(f"initialized project library at {root}")
    _offer_agent_install(ctx, yes)


def _offer_agent_install(ctx: click.Context, yes: bool) -> None:
    from shelf.cli.agent_cmd import install_cmd

    question = "Install shelf's agent skills at project scope, committed for everyone?"
    if yes or (interactive(ctx) and click.confirm(question, default=False)):
        ctx.invoke(install_cmd, scope="project")
        return
    click.echo(f"to give everyone in this repo the shelf skills: {AGENT_INSTALL_PROJECT}")


@click.command("path")
@click.argument("which", required=False, type=click.Choice(["config", "index"]))
@scope_option(allow_all=True)
@click.pass_context
def path_cmd(ctx: click.Context, which: str | None) -> None:
    """Print resolved locations (`--scope all`: one `<scope>\t<path>` line per scope)."""

    def location(target):
        if which == "config":
            return target.config_path
        return target.root / "index.html" if which == "index" else target.root

    if ctx.obj.get("scope") == "all":
        for target in resolve_targets(ctx):
            click.echo(f"{target.scope}\t{location(target)}")
        return
    if which == "config":  # needs no library: printable before 'shelf init'
        click.echo(target_config_path(ctx))
        return
    click.echo(location(resolve_target(ctx)))


@click.command("regen")
@click.option("--dry-run", is_flag=True)
@click.option("--json", "json_", is_flag=True, help="Machine-readable report.")
@commit_options
@scope_option()
@click.pass_context
def regen_cmd(
    ctx: click.Context,
    dry_run: bool,
    json_: bool,
    commit: bool,
    commit_message: str | None,
) -> None:
    """Regenerate index.html from the current catalog and installed template."""
    root = get_library(ctx)
    require_git_if_commit(root, commit)
    with library_lock(root):
        catalog_text = (root / CATALOG_FILENAME).read_text(encoding="utf-8")
        raw = json.loads(catalog_text)
        if raw.get("schema_version", 0) > CURRENT_SCHEMA_VERSION:
            raise click.ClickException(
                "catalog schema_version is newer than this shelf understands — upgrade shelf"
            )
        report = {"index": str((root / "index.html").resolve()), "dry_run": dry_run}
        if dry_run:
            click.echo(json.dumps(report) if json_ else "would regenerate index.html")
            return
        snips = build_snippets(root, raw.get("documents", []))
        atomic_write_text(root / "index.html", render_index(catalog_text, snips))
    if commit:
        git_commit_all(root, commit_message or auto_message("regen"), ["index.html"])
    click.echo(json.dumps(report) if json_ else "regenerated index.html")


@click.command("migrate")
@click.option("--dry-run", is_flag=True, help="Report the migration without applying it.")
@click.option("--json", "json_", is_flag=True, help="Machine-readable report.")
@commit_options
@scope_option()
@click.pass_context
def migrate_cmd(
    ctx: click.Context,
    dry_run: bool,
    json_: bool,
    commit: bool,
    commit_message: str | None,
) -> None:
    """Migrate the catalog to the current schema version."""
    root = get_library(ctx)
    require_git_if_commit(root, commit)
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
    if commit:
        git_commit_all(root, commit_message or auto_message("migrate"), library_paths())
    click.echo(
        json.dumps(report)
        if json_
        else f"migrated schema_version {found} -> {CURRENT_SCHEMA_VERSION}"
    )
