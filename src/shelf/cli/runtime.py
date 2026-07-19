"""Per-invocation helpers: active config and resolved library from ctx.obj."""

from pathlib import Path

import click

from shelf.core.config import ShelfConfig, default_config_path, load_config
from shelf.core.paths import resolve_library


def active_config_path(ctx: click.Context) -> Path:
    override = ctx.obj.get("config")
    return Path(override) if override else default_config_path()


def get_config(ctx: click.Context) -> ShelfConfig:
    return load_config(active_config_path(ctx))


def get_library(ctx: click.Context) -> Path:
    return resolve_library(ctx.obj.get("library"), get_config(ctx))
