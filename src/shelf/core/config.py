"""shelf_config.toml read/write (PRD §4) — kebab keys on disk, R3.8 parity."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from shelf.core.atomic import atomic_write_text

CONFIG_FILENAME = "shelf_config.toml"

_KEY_MAP = {
    "library": "library",
    "remove-source": "remove_source",
    "server-port": "server_port",
    "browser": "browser",
    "handoff-agent": "handoff_agent",
}


@dataclass
class ShelfConfig:
    library: str | None = None
    remove_source: bool = True
    server_port: int = 8765
    browser: str = "Google Chrome"
    handoff_agent: str = "claude"


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "shelf" / CONFIG_FILENAME


def load_config(path: Path) -> ShelfConfig:
    if not path.is_file():
        return ShelfConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = ShelfConfig()
    for key, attr in _KEY_MAP.items():
        if key in data:
            setattr(cfg, attr, data[key])
    return cfg


def save_config(path: Path, cfg: ShelfConfig) -> None:
    data = {
        key: getattr(cfg, attr) for key, attr in _KEY_MAP.items() if getattr(cfg, attr) is not None
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, tomli_w.dumps(data))
