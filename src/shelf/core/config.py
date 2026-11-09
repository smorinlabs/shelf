"""shelf_config.toml read/write (PRD §4) — kebab keys on disk, R3.8 parity."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import click
import tomli_w

from shelf.core.atomic import atomic_write_text

CONFIG_FILENAME = "shelf_config.toml"
PROJECT_DIR = ".shelf"  # project scope marker: <repo>/.shelf/shelf_config.toml (R5.2)

# Written by every `shelf init` up to 0.8.0 while nothing read it, so it records no choice.
LEGACY_INIT_BROWSER = "Google Chrome"

_KEY_MAP = {
    "library": "library",
    "remove-source": "remove_source",
    "server-port": "server_port",
    "browser": "browser",
    "handoff-agent": "handoff_agent",
    "publish": "publish",
    "base-url": "base_url",
}


@dataclass
class ShelfConfig:
    library: str | None = None
    remove_source: bool = True
    server_port: int = 8765
    browser: str | None = None
    handoff_agent: str = "claude"
    publish: str | None = None  # "marked" (the default when unset) or "all" (P21)
    base_url: str | None = None


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "shelf" / CONFIG_FILENAME


def read_config_data(path: Path) -> dict:
    """The raw kebab-key table of one config file; empty when the file is absent."""
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise click.ClickException(f"{path} is malformed: {exc}") from exc


def config_from(*layers: dict) -> ShelfConfig:
    """Built-in defaults, then each layer in order; a later layer wins per key (R5.1)."""
    cfg = ShelfConfig()
    for data in layers:
        for key, attr in _KEY_MAP.items():
            if key in data:
                setattr(cfg, attr, data[key])
    if cfg.browser == LEGACY_INIT_BROWSER:
        cfg.browser = None
    return cfg


def load_config(path: Path) -> ShelfConfig:
    return config_from(read_config_data(path))


def save_config(path: Path, cfg: ShelfConfig) -> None:
    data = {
        key: getattr(cfg, attr) for key, attr in _KEY_MAP.items() if getattr(cfg, attr) is not None
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, tomli_w.dumps(data))
