"""P02-T04 — topic/kind add and list, with index regeneration on mutation."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def _init():
    assert run(["init"]).exit_code == 0
    return default_library_path()


def test_topic_add_and_list(isolated_env):
    _init()
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    assert run(["topic", "add", "agentic-infra"]).exit_code == 0
    r = run(["topic", "list"])
    assert r.exit_code == 0
    assert r.output.splitlines() == ["agentic-infra", "dev-tooling"]  # sorted


def test_topic_add_duplicate_conflicts(isolated_env):
    _init()
    run(["topic", "add", "x"])
    r = run(["topic", "add", "x"])
    assert r.exit_code == 5
    assert "already exists" in r.output


def test_kind_list_seeded_and_json(isolated_env):
    _init()
    r = run(["kind", "list", "--json"])
    assert r.exit_code == 0
    assert "spec" in json.loads(r.output)
    r2 = run(["kind", "list", "-o", "json"])
    assert r2.output == r.output  # --json ≡ -o json, byte-identical


def test_mutation_regenerates_index(isolated_env):
    root = _init()
    before = (root / "index.html").read_text()
    run(["topic", "add", "fresh-topic"])
    after = (root / "index.html").read_text()
    assert before != after  # fingerprint changed with the catalog


def test_empty_topic_list_exits_zero(isolated_env):
    _init()
    r = run(["topic", "list"])
    assert r.exit_code == 0
    assert r.output == ""
