"""Library location resolution — the PRD §4 precedence chain."""

import os
from dataclasses import dataclass
from pathlib import Path, PurePath

import click

from shelf.core.config import CONFIG_FILENAME, PROJECT_DIR, ShelfConfig, read_config_data

ENV_LIBRARY = "SHELF_LIBRARY"
DEFAULT_PROJECT_LIBRARY = "shelf"


@dataclass(frozen=True)
class ProjectScope:
    """A discovered project scope: `<root>/.shelf/shelf_config.toml` naming `<root>/<library>`."""

    root: Path
    config_path: Path
    library: Path
    data: dict


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


def find_project_config(start: Path) -> Path | None:
    """Nearest `.shelf/shelf_config.toml` from *start* upward, stopping at the first
    directory where `.git` exists (a directory, or a file in a git worktree)."""
    for d in [start, *start.parents]:
        candidate = d / PROJECT_DIR / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if (d / ".git").exists():
            return None
    return None


def discover_project(start: Path | None = None) -> ProjectScope | None:
    config_path = find_project_config((start or Path.cwd()).resolve())
    if config_path is None:
        return None
    root = config_path.parent.parent
    data = read_config_data(config_path)
    value = data.get("library", DEFAULT_PROJECT_LIBRARY)
    library = (root / str(value)).resolve()
    if PurePath(str(value)).is_absolute() or not library.is_relative_to(root):
        raise click.ClickException(
            f"{config_path}: library must be a relative path inside {root} "
            f"(it is committed with the repo), not '{value}'"
        )
    return ProjectScope(root=root, config_path=config_path, library=library, data=data)
