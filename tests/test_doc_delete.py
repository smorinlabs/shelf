"""P03-TS04 (delete half) — shelf doc delete."""

import io
import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d", "--slug", SLUG]


class TtyInput(io.BytesIO):
    def isatty(self):
        return True


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seeded(tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def test_delete_requires_yes_when_not_tty(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    r = run(["doc", "delete", SLUG])
    assert r.exit_code == 2
    assert "--yes" in r.output
    assert json.loads((root / "catalog.json").read_text())["documents"]


def test_delete_prompts_on_tty_and_accepts_yes(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    r = CliRunner().invoke(cli, ["doc", "delete", SLUG], input=TtyInput(b"y\n"))
    assert r.exit_code == 0, r.output
    assert json.loads((root / "catalog.json").read_text())["documents"] == []


def test_delete_with_yes_removes_entry_and_folder(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    r = run(["doc", "delete", SLUG, "--yes"])
    assert r.exit_code == 0, r.output
    assert json.loads((root / "catalog.json").read_text())["documents"] == []
    assert not (root / "docs" / "topics" / "dev-tooling" / SLUG).exists()


def test_delete_unknown_id_exits_three(isolated_env, tmp_path):
    _seeded(tmp_path)
    assert run(["doc", "delete", "nope", "--yes"]).exit_code == 3


def test_delete_dry_run_changes_nothing(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "delete", SLUG, "--dry-run"])
    assert r.exit_code == 0
    assert "would delete" in r.output
    assert (root / "catalog.json").read_text() == before
    assert (root / "docs" / "topics" / "dev-tooling" / SLUG).exists()


def test_rm_alias(isolated_env, tmp_path):
    _seeded(tmp_path)
    assert run(["doc", "rm", SLUG, "--yes"]).exit_code == 0
