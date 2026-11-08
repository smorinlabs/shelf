"""Per-invocation helpers: the target library, its scope, and its settings (PRD §4).

Single-target precedence: `--scope project` → the project library; otherwise
`--library` > `SHELF_LIBRARY` > project scope > user config > error. `--scope user`
skips the project scope. Settings follow the target: a project target layers the
project file over the user file; a user target reads the user file only.
"""

import os
from dataclasses import dataclass
from pathlib import Path

import click

from shelf.core.config import ShelfConfig, config_from, default_config_path, read_config_data
from shelf.core.paths import ENV_LIBRARY, ProjectScope, discover_project, resolve_library

_UNSET = object()


@dataclass(frozen=True)
class Target:
    scope: str  # "project" or "user"
    root: Path
    config: ShelfConfig
    config_path: Path


def scope_option(*, allow_all: bool = False):
    """`--scope` on a library command; stored in ctx.obj for the resolvers below."""
    choices = ["user", "project", "all"] if allow_all else ["user", "project"]

    def store(ctx: click.Context, _param: click.Parameter, value: str | None) -> None:
        ctx.ensure_object(dict)["scope"] = value

    return click.option(
        "--scope",
        type=click.Choice(choices),
        default=None,
        expose_value=False,
        callback=store,
        help="Which library: user or project"
        + (", or all" if allow_all else "")
        + " (default: the project library when one is found).",
    )


def active_config_path(ctx: click.Context) -> Path:
    """The user config file: `--config PATH`, else `$XDG_CONFIG_HOME/shelf/shelf_config.toml`."""
    override = ctx.obj.get("config")
    return Path(override) if override else default_config_path()


def user_config(ctx: click.Context) -> ShelfConfig:
    return config_from(read_config_data(active_config_path(ctx)))


def project_scope(ctx: click.Context) -> ProjectScope | None:
    """The discovered project scope; `--config` replaces discovery (R5.2), so then none."""
    cached = ctx.obj.get("_project", _UNSET)
    if cached is _UNSET:
        cached = None if ctx.obj.get("config") else discover_project()
        ctx.obj["_project"] = cached
    return cached  # type: ignore[return-value]


def _require_project(ctx: click.Context) -> ProjectScope:
    proj = project_scope(ctx)
    if proj is None:
        raise click.UsageError(
            "no project scope here (no .shelf/shelf_config.toml between this directory "
            "and the repo root) — create one with 'shelf init --scope project'"
        )
    if ctx.obj.get("library"):
        raise click.UsageError("--scope project cannot be combined with --library")
    return proj


def _target_scope(ctx: click.Context) -> str:
    requested = ctx.obj.get("scope")
    if requested in ("user", "project"):
        return requested
    if ctx.obj.get("library") or os.environ.get(ENV_LIBRARY):
        return "user"
    return "project" if project_scope(ctx) is not None else "user"


def _project_target(ctx: click.Context, proj: ProjectScope) -> Target:
    layered = {k: v for k, v in proj.data.items() if k != "library"}
    cfg = config_from(read_config_data(active_config_path(ctx)), layered)
    return Target("project", proj.library, cfg, proj.config_path)


def _user_target(ctx: click.Context) -> Target:
    cfg = user_config(ctx)
    root = resolve_library(ctx.obj.get("library"), cfg)
    return Target("user", root, cfg, active_config_path(ctx))


def resolve_target(ctx: click.Context) -> Target:
    if _target_scope(ctx) == "project":
        return _project_target(ctx, _require_project(ctx))
    return _user_target(ctx)


def scope_target(ctx: click.Context, scope: str) -> Target:
    """The library of one named scope, regardless of `--scope`."""
    if scope == "project":
        proj = project_scope(ctx)
        if proj is None:
            raise click.UsageError(
                "no project scope here — create one with 'shelf init --scope project'"
            )
        return _project_target(ctx, proj)
    return _user_target(ctx)


def resolve_targets(ctx: click.Context) -> list[Target]:
    """Every library a read covers: project then user, narrowed by `--scope`."""
    requested = ctx.obj.get("scope")
    if requested in ("user", "project"):
        return [resolve_target(ctx)]
    if requested is None and (ctx.obj.get("library") or os.environ.get(ENV_LIBRARY)):
        return [_user_target(ctx)]
    proj = project_scope(ctx)
    targets = [_project_target(ctx, proj)] if proj is not None else []
    try:
        targets.append(_user_target(ctx))
    except click.ClickException:
        if not targets:
            raise
    return targets


def target_config(ctx: click.Context) -> ShelfConfig:
    """Settings of the target library, without requiring that a library exists."""
    if _target_scope(ctx) == "project":
        return _project_target(ctx, _require_project(ctx)).config
    return user_config(ctx)


def target_config_path(ctx: click.Context) -> Path:
    """The config file of the target library: the project file or the user file."""
    if _target_scope(ctx) == "project":
        return _require_project(ctx).config_path
    return active_config_path(ctx)


def get_config(ctx: click.Context) -> ShelfConfig:
    return target_config(ctx)


def get_library(ctx: click.Context) -> Path:
    return resolve_target(ctx).root
