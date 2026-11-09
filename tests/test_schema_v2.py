"""P21-TS01, TS07 (write half), TS13 — schema v2: `publish`, `shelf_version`, lossless migration."""

import json
from importlib.metadata import version

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.catalog import CURRENT_SCHEMA_VERSION
from shelf.core.paths import default_library_path

BASE = ["--kind", "reference", "--description", "d", "--no-remove-source"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _catalog(root):
    return json.loads((root / "catalog.json").read_text())


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev"]).exit_code == 0
    return default_library_path()


def _add(tmp_path, title, *extra):
    src = tmp_path / f"{title.lower().replace(' ', '-')}.md"
    src.write_text(f"# {title}\n")
    r = run(["doc", "add", str(src), "--topic", "dev", "--title", title, *BASE, *extra])
    assert r.exit_code == 0, r.output
    return [d for d in _catalog(default_library_path())["documents"] if d["title"] == title][0]


# A v1 catalog as shelf 0.10.0 wrote it, with every field populated at least once.
V1_DOCS = [
    {
        "id": "2026-01-02-repo-doc",
        "title": "Repo doc",
        "description": "anchored to a repo",
        "kind": "reference",
        "tags": ["a", "b"],
        "repo": {"name": "widget", "url": "https://github.com/o/widget", "subject": "api"},
        "files": [
            {
                "format": "md",
                "path": "docs/repos/widget/2026-01-02-repo-doc/2026-01-02-repo-doc.md",
            },
            {
                "format": "html",
                "path": "docs/repos/widget/2026-01-02-repo-doc/2026-01-02-repo-doc.html",
                "source": "md",
            },
        ],
        "primary": "html",
        "added": "2026-01-02",
        "doc_date": "2025-12-31",
        "source": "/tmp/repo-doc.md",
    },
    {
        "id": "2026-01-03-topic-doc",
        "title": "Topic doc",
        "description": "anchored to a topic",
        "kind": "reference",
        "tags": [],
        "category": "dev",
        "files": [
            {
                "format": "pdf",
                "path": "docs/topics/dev/2026-01-03-topic-doc/2026-01-03-topic-doc.pdf",
            }
        ],
        "primary": "pdf",
        "added": "2026-01-03",
        "doc_date": None,
        "source": None,
    },
]


def _write_v1(root):
    raw = _catalog(root)
    raw["schema_version"] = 1
    raw.pop("shelf_version", None)
    raw["documents"] = json.loads(json.dumps(V1_DOCS))
    for doc in raw["documents"]:
        for f in doc["files"]:
            (root / f["path"]).parent.mkdir(parents=True, exist_ok=True)
            (root / f["path"]).write_text("x")
    (root / "catalog.json").write_text(json.dumps(raw))
    return raw


def test_migration_from_v1_loses_nothing(isolated_env):
    root = _init()
    before = _write_v1(root)
    r = run(["migrate"])
    assert r.exit_code == 0, r.output
    after = _catalog(root)
    assert after["schema_version"] == 2 == CURRENT_SCHEMA_VERSION
    assert after["shelf_version"] == version("shelf")
    assert after["topics"] == before["topics"]
    assert after["kinds"] == before["kinds"]
    assert len(after["documents"]) == len(V1_DOCS)
    by_id = {d["id"]: d for d in after["documents"]}
    for old in V1_DOCS:
        new = by_id[old["id"]]
        assert set(new) - set(old) == {"publish"}, new
        assert new["publish"] is False
        assert {k: new[k] for k in old} == old


def test_migration_chain_from_v0_reaches_v2(isolated_env):
    root = _init()
    raw = _catalog(root)
    del raw["schema_version"]
    (root / "catalog.json").write_text(json.dumps(raw))
    assert run(["migrate"]).exit_code == 0
    assert _catalog(root)["schema_version"] == 2


def test_v1_catalog_reads_but_refuses_writes_until_migrated(isolated_env):
    root = _init()
    _write_v1(root)
    assert run(["doc", "list"]).exit_code == 0
    r = run(["topic", "add", "x"])
    assert r.exit_code == 5 and "migrate" in r.output


def test_every_library_write_records_the_shelf_version(isolated_env):
    root = _init()
    raw = _catalog(root)
    raw["shelf_version"] = "0.0.1"
    (root / "catalog.json").write_text(json.dumps(raw))
    assert run(["topic", "add", "other"]).exit_code == 0
    assert _catalog(root)["shelf_version"] == version("shelf")


def test_doc_add_publish_flag_sets_the_field(isolated_env, tmp_path):
    _init()
    assert _add(tmp_path, "Shown", "--publish")["publish"] is True
    assert _add(tmp_path, "Hidden")["publish"] is False


def test_doc_update_publish_and_no_publish(isolated_env, tmp_path):
    root = _init()
    doc = _add(tmp_path, "Toggle")
    assert run(["doc", "update", doc["id"], "--publish"]).exit_code == 0
    assert _catalog(root)["documents"][0]["publish"] is True
    assert run(["doc", "update", doc["id"], "--no-publish"]).exit_code == 0
    assert _catalog(root)["documents"][0]["publish"] is False


def test_doc_view_and_list_json_show_publish(isolated_env, tmp_path):
    _init()
    doc = _add(tmp_path, "Seen", "--publish")
    view = json.loads(run(["doc", "view", doc["id"], "--json"]).output)
    assert view["publish"] is True
    rows = json.loads(run(["doc", "list", "--json"]).output)
    assert rows[0]["publish"] is True
