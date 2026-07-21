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


def test_adopt_absolute_path_outside_library_is_usage_error(isolated_env, tmp_path):
    _init()
    outside = tmp_path / "elsewhere" / "docs" / "topics" / "dev-tooling" / "2026-01-01-x"
    outside.mkdir(parents=True)
    r = run(
        ["doc", "adopt", str(outside), "--kind", "reference", "--title", "X", "--description", "d"]
    )
    assert r.exit_code == 2, r.output
    assert not isinstance(r.exception, ValueError)


def test_orphan_delete_absolute_path_outside_library_is_usage_error(isolated_env, tmp_path):
    _init()
    stray = tmp_path / "elsewhere.md"
    stray.write_text("x")
    r = run(["orphan", "delete", str(stray), "--yes"])
    assert r.exit_code == 2, r.output
    assert not isinstance(r.exception, ValueError)


def test_orphan_delete_dotdot_traversal_to_catalog_json_rejected(isolated_env):
    """Data-safety regression: 'docs/../catalog.json' passes the naive
    str(rel).startswith('docs/') check even though it resolves to catalog.json
    once joined onto root — a relative ../-traversal must be rejected, not deleted.
    """
    root = _init()
    before = (root / "catalog.json").read_text()
    r = run(["orphan", "delete", "docs/../catalog.json", "--yes"])
    assert r.exit_code != 0
    assert (root / "catalog.json").exists()
    assert (root / "catalog.json").read_text() == before


def test_orphan_delete_dotdot_traversal_escaping_library_rejected(isolated_env):
    """A relative ../../ path can escape the library root entirely — the victim
    file living beside the library must survive."""
    root = _init()
    victim = root.parent / "victim.txt"
    victim.write_text("precious")
    r = run(["orphan", "delete", "docs/../../victim.txt", "--yes"])
    assert r.exit_code != 0
    assert victim.exists()
    assert victim.read_text() == "precious"


def test_scan_orphans_ignores_gitkeep_at_bucket_root(isolated_env):
    """P07 regression: `init --git` writes `.gitkeep` directly under docs/repos/ and
    docs/topics/ so git tracks the empty buckets — that's housekeeping, not an orphan.
    """
    from shelf.core.catalog import load_catalog
    from shelf.core.ingest import scan_orphans

    root = _init()
    (root / "docs" / "repos" / ".gitkeep").write_text("", encoding="utf-8")
    (root / "docs" / "topics" / ".gitkeep").write_text("", encoding="utf-8")
    assert scan_orphans(root, load_catalog(root)) == []


def test_scan_orphans_ignores_gitkeep_under_doc_folder(isolated_env):
    """Same housekeeping exemption one level down, sibling to real per-document folders."""
    from shelf.core.catalog import load_catalog
    from shelf.core.ingest import scan_orphans

    root = _init()
    group_dir = root / "docs" / "topics" / "dev-tooling"
    group_dir.mkdir(parents=True, exist_ok=True)
    (group_dir / ".gitkeep").write_text("", encoding="utf-8")
    assert scan_orphans(root, load_catalog(root)) == []


def test_orphan_list_ignores_gitkeep_on_git_library(
    isolated_env, isolated_git_identity, monkeypatch
):
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    assert run(["init", "--git"]).exit_code == 0
    r = run(["orphan", "list"])
    assert r.exit_code == 0
    assert ".gitkeep" not in r.output


def test_adopt_validates_primary_against_found_formats(isolated_env):
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
            "S",
            "--description",
            "d",
            "--primary",
            "pdf",
        ]
    )
    assert r.exit_code == 2, r.output
    assert json.loads((root / "catalog.json").read_text())["documents"] == []


def _add_cataloged_doc(root, tmp_path):
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
    return json.loads((root / "catalog.json").read_text())["documents"][0]


def test_orphan_delete_docs_root_rejected(isolated_env, tmp_path):
    """Regression: the A1 fix opened this — 'orphan delete docs' must NOT wipe docs/."""
    root = _init()
    entry = _add_cataloged_doc(root, tmp_path)
    r = run(["orphan", "delete", "docs", "--yes"])
    assert r.exit_code != 0
    assert (root / "docs").is_dir()
    assert (root / entry["files"][0]["path"]).is_file()


def test_orphan_delete_ancestor_of_cataloged_doc_rejected(isolated_env, tmp_path):
    """Deleting a group dir that CONTAINS a cataloged doc must be refused (ancestor)."""
    root = _init()
    entry = _add_cataloged_doc(root, tmp_path)
    r = run(["orphan", "delete", "docs/topics/dev-tooling", "--yes"])
    assert r.exit_code != 0
    assert (root / "docs" / "topics" / "dev-tooling").is_dir()
    assert (root / entry["files"][0]["path"]).is_file()


def test_orphan_delete_bucket_roots_rejected(isolated_env):
    """Structural bucket roots (docs, docs/topics, docs/repos) are not orphans."""
    root = _init()
    assert run(["orphan", "delete", "docs/topics", "--yes"]).exit_code != 0
    assert (root / "docs" / "topics").is_dir()
    assert run(["orphan", "delete", "docs/repos", "--yes"]).exit_code != 0
    assert (root / "docs" / "repos").is_dir()
