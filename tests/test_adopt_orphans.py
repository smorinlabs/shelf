"""P03-T06 — doc adopt and orphan list/delete (§11.15)."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


def _orphan_folder(root, slug="2026-01-01-strays"):
    d = root / "docs" / "topics" / "dev-tooling" / slug
    d.mkdir(parents=True)
    (d / f"{slug}.md").write_text("# stray")
    return d


def test_orphan_list_detects_uncataloged_folder(isolated_env):
    root = _init()
    d = _orphan_folder(root)
    r = run(["orphan", "list"])
    assert r.exit_code == 0
    assert "2026-01-01-strays" in r.output
    j = run(["orphan", "list", "--json"])
    assert str(d.relative_to(root)) in json.loads(j.output)


def test_orphan_list_empty_after_adopt(isolated_env):
    root = _init()
    _orphan_folder(root)
    r = run(
        [
            "doc",
            "adopt",
            "docs/topics/dev-tooling/2026-01-01-strays",
            "--kind",
            "reference",
            "--title",
            "Strays",
            "--description",
            "d",
        ]
    )
    assert r.exit_code == 0, r.output
    entry = json.loads((root / "catalog.json").read_text())["documents"][0]
    assert entry["id"] == "2026-01-01-strays"
    assert entry["category"] == "dev-tooling"
    assert (
        entry["files"][0]["path"]
        == "docs/topics/dev-tooling/2026-01-01-strays/2026-01-01-strays.md"
    )
    assert run(["orphan", "list"]).output == ""


def test_adopt_slug_collision_conflicts(isolated_env):
    root = _init()
    _orphan_folder(root)
    assert (
        run(
            [
                "doc",
                "adopt",
                "docs/topics/dev-tooling/2026-01-01-strays",
                "--kind",
                "reference",
                "--title",
                "S",
                "--description",
                "d",
            ]
        ).exit_code
        == 0
    )
    assert (
        run(
            [
                "doc",
                "adopt",
                "docs/topics/dev-tooling/2026-01-01-strays",
                "--kind",
                "reference",
                "--title",
                "S",
                "--description",
                "d",
            ]
        ).exit_code
        == 5
    )


def test_adopt_unknown_topic_governed(isolated_env):
    root = _init()
    d = root / "docs" / "topics" / "brand-new" / "2026-01-01-x"
    d.mkdir(parents=True)
    (d / "2026-01-01-x.md").write_text("x")
    r = run(
        [
            "doc",
            "adopt",
            "docs/topics/brand-new/2026-01-01-x",
            "--kind",
            "reference",
            "--title",
            "X",
            "--description",
            "d",
        ]
    )
    assert r.exit_code == 1
    assert "--create-topic" in r.output
    r = run(
        [
            "doc",
            "adopt",
            "docs/topics/brand-new/2026-01-01-x",
            "--create-topic",
            "--kind",
            "reference",
            "--title",
            "X",
            "--description",
            "d",
        ]
    )
    assert r.exit_code == 0


def test_adopt_requires_known_format_file(isolated_env):
    root = _init()
    d = root / "docs" / "topics" / "dev-tooling" / "2026-01-01-empty"
    d.mkdir(parents=True)
    (d / "notes.docx").write_text("x")
    r = run(
        [
            "doc",
            "adopt",
            "docs/topics/dev-tooling/2026-01-01-empty",
            "--kind",
            "reference",
            "--title",
            "E",
            "--description",
            "d",
        ]
    )
    assert r.exit_code == 1


def test_orphan_delete_refuses_cataloged_path(isolated_env, tmp_path):
    root = _init()
    src = tmp_path / "real.md"
    src.write_text("# real")
    assert (
        run(
            [
                "doc",
                "add",
                str(src),
                "--topic",
                "dev-tooling",
                "--kind",
                "reference",
                "--title",
                "Real",
                "--description",
                "d",
            ]
        ).exit_code
        == 0
    )
    entry = json.loads((root / "catalog.json").read_text())["documents"][0]
    folder = "/".join(entry["files"][0]["path"].split("/")[:-1])
    r = run(["orphan", "delete", folder, "--yes"])
    assert r.exit_code == 5


def test_orphan_delete_removes_stray(isolated_env):
    root = _init()
    d = _orphan_folder(root)
    r = run(["orphan", "delete", str(d.relative_to(root)), "--yes"])
    assert r.exit_code == 0
    assert not d.exists()
    r = run(["orphan", "delete", "docs/topics/nope", "--yes"])
    assert r.exit_code == 3
