"""P02-TS03 — doc list filter/query matrix and doc view output shapes."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.atomic import library_lock
from shelf.core.catalog import Document, FileVariant, RepoRef, commit_library, load_catalog
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def _seed():
    assert run(["init"]).exit_code == 0
    root = default_library_path()
    with library_lock(root):
        cat = load_catalog(root, for_write=True)
        cat.topics = ["dev-tooling", "claude-code"]
        cat.documents = [
            Document(
                id="2026-01-01-uv-notes",
                title="UV Notes",
                description="python packaging",
                kind="reference",
                tags=["python", "uv"],
                category="dev-tooling",
                files=[
                    FileVariant(
                        format="md",
                        path="docs/topics/dev-tooling/2026-01-01-uv-notes/2026-01-01-uv-notes.md",
                    )
                ],
                primary="md",
                added="2026-01-01",
            ),
            Document(
                id="2026-02-01-flox-prd",
                title="Flox PRD",
                description="cli extensions",
                kind="spec",
                tags=["rust"],
                repo=RepoRef(
                    name="flox-cli", url="https://github.com/flox/flox", subject="cli-extensions"
                ),
                files=[
                    FileVariant(
                        format="md",
                        path="docs/repos/flox-cli/2026-02-01-flox-prd/2026-02-01-flox-prd.md",
                    )
                ],
                primary="md",
                added="2026-02-01",
            ),
            Document(
                id="2026-03-01-hooks-guide",
                title="Hooks Guide",
                description="claude hooks",
                kind="tutorial",
                tags=["claude-code"],
                category="claude-code",
                files=[
                    FileVariant(
                        format="md",
                        path="docs/topics/claude-code/2026-03-01-hooks-guide/2026-03-01-hooks-guide.md",
                    )
                ],
                primary="md",
                added="2026-03-01",
            ),
        ]
        commit_library(root, cat)
    return root


def _ids(result):
    return [line.split("\t")[0] for line in result.output.splitlines()]


def test_list_default_sorted_added_desc(isolated_env):
    _seed()
    r = run(["doc", "list"])
    assert r.exit_code == 0
    assert _ids(r) == ["2026-03-01-hooks-guide", "2026-02-01-flox-prd", "2026-01-01-uv-notes"]


def test_filters_and_together(isolated_env):
    _seed()
    r = run(["doc", "list", "--kind", "reference", "--tag", "python"])
    assert _ids(r) == ["2026-01-01-uv-notes"]
    r = run(["doc", "list", "--kind", "reference", "--tag", "rust"])
    assert r.exit_code == 0 and r.output == ""  # empty result is success


def test_query_matches_id_title_description_tags_subject(isolated_env):
    _seed()
    for q in ("uv-notes", "Flox", "packaging", "claude-code", "cli-extensions"):
        assert run(["doc", "list", "--query", q]).output != "", q


def test_repo_and_topic_filters(isolated_env):
    _seed()
    assert _ids(run(["doc", "list", "--repo", "flox-cli"])) == ["2026-02-01-flox-prd"]
    assert _ids(run(["doc", "list", "--topic", "dev-tooling"])) == ["2026-01-01-uv-notes"]


def test_limit_and_sort_by_title(isolated_env):
    _seed()
    r = run(["doc", "list", "--sort-by", "title", "--limit", "2"])
    assert _ids(r) == ["2026-02-01-flox-prd", "2026-03-01-hooks-guide"]  # Flox, Hooks


def test_list_json_equals_o_json(isolated_env):
    _seed()
    a = run(["doc", "list", "--json"])
    b = run(["doc", "list", "-o", "json"])
    assert a.output == b.output
    docs = json.loads(a.output)
    assert {d["id"] for d in docs} == {
        "2026-01-01-uv-notes",
        "2026-02-01-flox-prd",
        "2026-03-01-hooks-guide",
    }


def test_view_json_includes_abs_paths(isolated_env):
    root = _seed()
    r = run(["doc", "view", "2026-02-01-flox-prd", "--json"])
    data = json.loads(r.output)
    assert data["repo"]["subject"] == "cli-extensions"
    assert data["files"][0]["abs_path"] == str(
        root / "docs/repos/flox-cli/2026-02-01-flox-prd/2026-02-01-flox-prd.md"
    )


def test_view_unknown_id_exits_three(isolated_env):
    _seed()
    r = run(["doc", "view", "nope"])
    assert r.exit_code == 3
    assert "not found" in r.output


def test_ls_alias(isolated_env):
    _seed()
    assert run(["doc", "ls"]).output == run(["doc", "list"]).output
