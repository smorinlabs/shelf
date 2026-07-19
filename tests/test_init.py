"""P02-T03/T06 + TS04 (adopt half) — shelf init and init --adopt."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.catalog import SEED_KINDS
from shelf.core.config import default_config_path, load_config
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def test_init_scaffolds_default_library(isolated_env):
    r = run(["init"])
    assert r.exit_code == 0, r.output
    root = default_library_path()
    catalog = json.loads((root / "catalog.json").read_text())
    assert catalog["schema_version"] == 1
    assert catalog["topics"] == []
    assert catalog["kinds"] == SEED_KINDS
    assert catalog["documents"] == []
    assert (root / "docs" / "repos").is_dir()
    assert (root / "docs" / "topics").is_dir()
    assert "shelf:fingerprint" in (root / "index.html").read_text()
    assert (root / "README.md").is_file()
    assert load_config(default_config_path()).library == str(root)


def test_init_explicit_library_flag(tmp_path):
    target = tmp_path / "mylib"
    r = run(["init", "--library", str(target)])
    assert r.exit_code == 0
    assert (target / "catalog.json").is_file()
    assert load_config(default_config_path()).library == str(target)


def test_init_refuses_reinit_without_force(isolated_env):
    assert run(["init"]).exit_code == 0
    r = run(["init"])
    assert r.exit_code == 5  # conflict
    assert "--force" in r.output
    assert run(["init", "--force"]).exit_code == 0


def test_adopt_registers_existing_library(tmp_path, isolated_env):
    clone = tmp_path / "clone"
    assert run(["init", "--library", str(clone)]).exit_code == 0
    # simulate a fresh machine: wipe the config, keep the library
    default_config_path().unlink()
    r = run(["init", "--adopt", str(clone)])
    assert r.exit_code == 0, r.output
    assert load_config(default_config_path()).library == str(clone)


def test_adopt_validates_library_shape(tmp_path):
    bogus = tmp_path / "bogus"
    bogus.mkdir()
    r = run(["init", "--adopt", str(bogus)])
    assert r.exit_code == 1
    assert "catalog.json" in r.output


def test_adopt_and_force_are_mutually_exclusive(tmp_path):
    clone = tmp_path / "x"
    clone.mkdir()
    r = run(["init", "--adopt", str(clone), "--force"])
    assert r.exit_code == 2  # usage error
