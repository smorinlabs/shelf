"""Library location resolution — the PRD §4 precedence chain."""

import os
from pathlib import Path

import click

from shelf.core.config import ShelfConfig

ENV_LIBRARY = "SHELF_LIBRARY"


def default_library_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "shelf"


def resolve_library(cli_library: str | None, config: ShelfConfig) -> Path:
    if cli_library:
        return Path(cli_library)
    env = os.environ.get(ENV_LIBRARY)
    if env:
        return Path(env)
    if config.library:
        return Path(config.library)
    raise click.ClickException("no library configured — run 'shelf init' to create one")
