"""P02-T07 + TS04 (migrate half) — schema migration and refusal rules."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def _downgrade_to_v0():
    root = default_library_path()
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    del raw["schema_version"]
    path.write_text(json.dumps(raw))
    return root


def test_migrate_noop_when_current(isolated_env):
    run(["init"])
    r = run(["migrate"])
    assert r.exit_code == 0
    assert "already" in r.output


def test_old_schema_blocks_mutation_until_migrate(isolated_env):
    run(["init"])
    _downgrade_to_v0()
    r = run(["topic", "add", "x"])
    assert r.exit_code == 5
    assert "migrate" in r.output
    assert run(["doc", "list"]).exit_code == 0  # read path stays compatible
    assert run(["migrate"]).exit_code == 0
    assert run(["topic", "add", "x"]).exit_code == 0


def test_migrate_sets_current_version_and_regenerates_index(isolated_env):
    run(["init"])
    root = _downgrade_to_v0()
    before = (root / "index.html").read_text()
    r = run(["migrate"])
    assert r.exit_code == 0
    raw = json.loads((root / "catalog.json").read_text())
    assert raw["schema_version"] == 1
    assert (root / "index.html").read_text() != before


def test_migrate_dry_run_changes_nothing(isolated_env):
    run(["init"])
    root = _downgrade_to_v0()
    r = run(["migrate", "--dry-run"])
    assert r.exit_code == 0
    assert "0" in r.output and "1" in r.output  # reports from -> to
    assert "schema_version" not in json.loads((root / "catalog.json").read_text())
