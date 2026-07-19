"""P02-TS01 (unit level) — config round-trip and resolution precedence."""

import os
from pathlib import Path

import click
import pytest

from shelf.core.config import ShelfConfig, default_config_path, load_config, save_config
from shelf.core.paths import default_library_path, resolve_library


def test_default_paths_follow_xdg(isolated_env):
    assert default_config_path() == Path(os.environ["XDG_CONFIG_HOME"]) / "shelf" / "shelf_config.toml"
    assert default_library_path() == Path(os.environ["XDG_DATA_HOME"]) / "shelf"


def test_config_round_trip_kebab_keys(tmp_path):
    path = tmp_path / "shelf_config.toml"
    save_config(path, ShelfConfig(library="/tmp/lib", server_port=9000))
    text = path.read_text()
    assert 'server-port = 9000' in text
    assert "server_port" not in text  # kebab keys on disk (R3.8)
    cfg = load_config(path)
    assert cfg.library == "/tmp/lib"
    assert cfg.server_port == 9000
    assert cfg.remove_source is True  # defaults survive partial files
    assert cfg.handoff_agent == "claude"


def test_missing_config_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg == ShelfConfig()


def test_precedence_flag_beats_env_beats_config(monkeypatch):
    cfg = ShelfConfig(library="/from-config")
    monkeypatch.setenv("SHELF_LIBRARY", "/from-env")
    assert resolve_library("/from-flag", cfg) == Path("/from-flag")
    assert resolve_library(None, cfg) == Path("/from-env")
    monkeypatch.delenv("SHELF_LIBRARY")
    assert resolve_library(None, cfg) == Path("/from-config")


def test_unresolvable_library_errors_with_guidance():
    with pytest.raises(click.ClickException, match="shelf init"):
        resolve_library(None, ShelfConfig())
