"""P02-T08 + TS01 (CLI level) — global core options and shelf path."""

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.config import ShelfConfig, default_config_path, save_config


def run(args, env=None):
    return CliRunner().invoke(cli, args, env=env or {})


def test_dash_h_is_help():
    r = run(["-h"])
    assert r.exit_code == 0
    assert "Usage: shelf" in r.output


def test_global_core_flags_accepted():
    r = run(["-vv", "-q", "--debug", "--no-input", "path", "config"])
    assert r.exit_code == 0


def test_path_config_prints_active_config(isolated_env):
    r = run(["path", "config"])
    assert r.exit_code == 0
    assert r.output.strip() == str(default_config_path())


def test_path_config_honors_config_flag(tmp_path):
    custom = tmp_path / "custom.toml"
    r = run(["--config", str(custom), "path", "config"])
    assert r.exit_code == 0
    assert r.output.strip() == str(custom)


def test_path_precedence_flag_env_config(tmp_path):
    lib_flag, lib_env, lib_cfg = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    save_config(default_config_path(), ShelfConfig(library=str(lib_cfg)))
    r = run(["--library", str(lib_flag), "path"], env={"SHELF_LIBRARY": str(lib_env)})
    assert r.output.strip() == str(lib_flag)
    r = run(["path"], env={"SHELF_LIBRARY": str(lib_env)})
    assert r.output.strip() == str(lib_env)
    r = run(["path"])
    assert r.output.strip() == str(lib_cfg)


def test_path_unconfigured_errors_with_guidance(isolated_env):
    r = run(["path"])
    assert r.exit_code == 1
    assert "shelf init" in r.output


def test_path_index(tmp_path):
    save_config(default_config_path(), ShelfConfig(library=str(tmp_path / "lib")))
    r = run(["path", "index"])
    assert r.output.strip() == str(tmp_path / "lib" / "index.html")
