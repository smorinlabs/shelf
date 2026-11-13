"""P25-TS03–TS06 — nested `owner/repo` groups, repo-name validation, add-then-audit property."""

import itertools
import json
import re
import shutil
import subprocess

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core import visibility
from shelf.core.paths import default_library_path

URL = ["--repo-url", "https://github.com/obra/superpowers"]
META = ["--kind", "reference", "--title", "Superpowers Notes", "--description", "d"]
SLUG = "2026-01-01-sp-notes"
_PAGE_RE = re.compile(r"const PAGE = (.*?);\n", re.DOTALL)
_FUZZY_RE = re.compile(r"/\* fuzzy:start \*/(.*?)/\* fuzzy:end \*/", re.DOTALL)


def _match(pattern, text):
    match = pattern.search(text)
    assert match is not None
    return match.group(1)


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


def _src(tmp_path, name="notes.md"):
    f = tmp_path / name
    f.write_text("# Superpowers\n\nbody text\n")
    return f


def _add_nested(tmp_path, repo="obra/superpowers", slug=SLUG):
    r = run(["doc", "add", str(_src(tmp_path)), "--repo", repo, *URL, *META, "--slug", slug])
    assert r.exit_code == 0, r.output
    return r


def _findings(root):
    r = run(["audit", "--json"])
    return json.loads(r.output) if r.output.strip() else []


def _assert_clean(root):
    r = run(["audit"])
    assert r.exit_code == 0, r.output


def _snapshot(root):
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


# --- P25-TS03 -------------------------------------------------------------------------------


def test_nested_repo_writes_two_level_folder_and_audits_clean(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    assert (root / "docs/repos/obra/superpowers" / SLUG / f"{SLUG}.md").is_file()
    doc = json.loads((root / "catalog.json").read_text())["documents"][0]
    assert doc["repo"]["name"] == "obra/superpowers"
    _assert_clean(root)
    assert not [f for f in _findings(root) if f["code"] == "orphan"]
    r = run(["orphan", "list", "--json"])
    assert r.exit_code == 0 and json.loads(r.output) == []


def test_nested_and_flat_groups_coexist_under_one_owner(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    _add_nested(tmp_path, repo="obra", slug="2026-01-02-flat")
    assert (root / "docs/repos/obra/2026-01-02-flat").is_dir()
    _assert_clean(root)


def test_orphans_inside_nested_groups_are_found(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    stray_doc = root / "docs/repos/obra/superpowers/2026-02-02-stray"
    stray_doc.mkdir()
    (stray_doc / "2026-02-02-stray.md").write_text("x")
    stray_variant = root / "docs/repos/obra/superpowers" / SLUG / f"{SLUG}.pdf"
    stray_variant.write_text("%PDF")
    unknown_group = root / "docs/repos/obra/unknown/2026-03-03-x"
    unknown_group.mkdir(parents=True)
    expected = {
        "docs/repos/obra/superpowers/2026-02-02-stray",
        f"docs/repos/obra/superpowers/{SLUG}/{SLUG}.pdf",
        "docs/repos/obra/unknown",
    }
    assert {f["detail"] for f in _findings(root) if f["code"] == "orphan"} == expected
    assert set(json.loads(run(["orphan", "list", "--json"]).output)) == expected
    r = run(["orphan", "delete", "docs/repos/obra/superpowers/2026-02-02-stray", "--yes"])
    assert r.exit_code == 0, r.output
    for protected in ("docs/repos/obra", "docs/repos/obra/superpowers"):
        assert run(["orphan", "delete", protected, "--yes"]).exit_code != 0


def test_index_sidebar_and_palette_see_the_nested_group(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    html_text = (root / "index.html").read_text()
    page = json.loads(_match(_PAGE_RE, html_text))
    doc = next(d for d in page["docs"] if d["id"] == SLUG)
    assert doc["anchor"] == {"type": "repo", "group": "obra/superpowers", "subject": ""}
    assert doc["formats"][0]["path"] == f"docs/repos/obra/superpowers/{SLUG}/{SLUG}.md"
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    script = tmp_path / "palette.js"
    script.write_text(
        _match(_FUZZY_RE, html_text)
        + f"const DOCS = {json.dumps(page['docs'])};\n"
        + 'const hits = rankDocs(DOCS, "superpowers");\n'
        + f'if (hits.length !== 1 || hits[0].id !== "{SLUG}") {{ process.exit(1); }}\n'
        + 'console.log("ok");\n'
    )
    result = subprocess.run([node, str(script)], capture_output=True, text=True)
    assert result.stdout.strip() == "ok", result.stderr


# --- P25-TS04 -------------------------------------------------------------------------------

BAD_REPOS = ["a/b/c", "a\\b", "a//b", "../x", "a/./b", "/a", "a/", ".", "..", ""]


@pytest.mark.parametrize("repo", BAD_REPOS)
@pytest.mark.parametrize("dry_run", [False, True])
def test_bad_repo_names_exit_two_and_write_nothing(isolated_env, tmp_path, repo, dry_run):
    root = _init()
    before = _snapshot(root)
    extra = ["--dry-run"] if dry_run else []
    r = run(["doc", "add", str(_src(tmp_path)), "--repo", repo, *URL, *META, *extra])
    assert r.exit_code == 2, r.output
    assert _snapshot(root) == before


@pytest.mark.parametrize("repo", BAD_REPOS)
def test_doc_move_rejects_bad_repo_names(isolated_env, tmp_path, repo):
    root = _init()
    _add_nested(tmp_path)
    before = _snapshot(root)
    r = run(["doc", "move", SLUG, "--repo", repo])
    assert r.exit_code == 2, r.output
    assert _snapshot(root) == before


# --- P25-TS05 -------------------------------------------------------------------------------


def test_move_between_flat_and_nested_groups(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    r = run(["doc", "move", SLUG, "--repo", "flox"])
    assert r.exit_code == 0, r.output
    assert (root / "docs/repos/flox" / SLUG / f"{SLUG}.md").is_file()
    assert not (root / "docs/repos/obra").exists()  # emptied nested folders are pruned
    _assert_clean(root)
    r = run(["doc", "move", SLUG, "--repo", "obra/superpowers"])
    assert r.exit_code == 0, r.output
    assert (root / "docs/repos/obra/superpowers" / SLUG / f"{SLUG}.md").is_file()
    _assert_clean(root)
    r = run(["doc", "move", SLUG, "--topic", "dev-tooling"])
    assert r.exit_code == 0, r.output
    _assert_clean(root)


def test_delete_prunes_emptied_nested_folders(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    assert run(["doc", "delete", SLUG, "--yes"]).exit_code == 0
    assert not (root / "docs/repos/obra").exists()
    _assert_clean(root)


def test_update_repo_fields_on_a_nested_document(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    r = run(["doc", "update", SLUG, "--subject", "skills", "--repo-url", "https://x/y"])
    assert r.exit_code == 0, r.output
    repo = json.loads((root / "catalog.json").read_text())["documents"][0]["repo"]
    assert repo == {"name": "obra/superpowers", "url": "https://x/y", "subject": "skills"}
    _assert_clean(root)


def test_adopt_a_nested_folder(isolated_env, tmp_path):
    root = _init()
    folder = root / "docs/repos/obra/superpowers/2026-04-04-found"
    folder.mkdir(parents=True)
    (folder / "2026-04-04-found.md").write_text("# found")
    r = run(["doc", "adopt", "docs/repos/obra/superpowers/2026-04-04-found", *META])
    assert r.exit_code == 0, r.output
    doc = json.loads((root / "catalog.json").read_text())["documents"][0]
    assert doc["repo"]["name"] == "obra/superpowers"
    _assert_clean(root)
    assert json.loads(run(["orphan", "list", "--json"]).output) == []


@pytest.mark.parametrize(
    "folder",
    ["docs/topics/a/b/2026-01-01-x", "docs/repos/a/b/c/2026-01-01-x", "docs/repos/a/../x"],
)
def test_adopt_rejects_other_shapes(isolated_env, tmp_path, folder):
    _init()
    assert run(["doc", "adopt", folder, *META]).exit_code == 2


def test_publish_with_nested_groups(isolated_env, tmp_path, monkeypatch):
    root = _init()
    r = run(
        ["doc", "add", str(_src(tmp_path)), "--repo", "obra/superpowers", *URL, *META]
        + ["--slug", SLUG, "--publish"]
    )
    assert r.exit_code == 0, r.output
    monkeypatch.setattr(visibility, "detect", lambda root: visibility.Repo("o/lib", "public"))
    monkeypatch.setattr(visibility, "pages_url", lambda slug: None)
    site = tmp_path / "_site"
    r = run(["publish", "--out", str(site)])
    assert r.exit_code == 0, r.output
    assert (site / "docs/repos/obra/superpowers" / SLUG / f"{SLUG}.md").is_file()
    published = json.loads((site / "catalog.json").read_text())["documents"]
    assert [d["repo"]["name"] for d in published] == ["obra/superpowers"]
    _assert_clean(root)


# --- P25-TS06 -------------------------------------------------------------------------------

ANCHORS = {
    "topic": ["--topic", "dev-tooling"],
    "new-topic": ["--topic", "brand-new", "--create-topic"],
    "flat-repo": ["--repo", "flox", *URL],
    "nested-repo": ["--repo", "obra/superpowers", *URL],
}
SLUGS = {"derived": [], "dated": ["--slug", "1999-01-01-x"], "undated": ["--slug", "plain"]}
EXTRAS = {
    "none": [],
    "tags": ["--tag", "a", "--tag", "b", "--subject", "s"],
    "publish": ["--publish", "--doc-date", "2025-05-05", "--primary", "md"],
}


@pytest.mark.parametrize(
    ("anchor", "slug", "extra"), list(itertools.product(ANCHORS, SLUGS, EXTRAS))
)
def test_every_successful_add_audits_clean(isolated_env, tmp_path, anchor, slug, extra):
    root = _init()
    extra_args = EXTRAS[extra]
    if anchor.endswith("topic") and "--subject" in extra_args:
        extra_args = ["--tag", "a", "--tag", "b"]  # --subject only applies to repos
    r = run(["doc", "add", str(_src(tmp_path)), *ANCHORS[anchor], *META, *SLUGS[slug], *extra_args])
    assert r.exit_code == 0, r.output
    _assert_clean(root)


# --- rollback, variants, and the server for nested groups ----------------------------------


def test_failed_add_into_a_new_nested_group_leaves_nothing(isolated_env, tmp_path, monkeypatch):
    import shelf.cli.doc_add as mod

    root = _init()

    def boom(*a, **k):
        raise RuntimeError("injected")

    with monkeypatch.context() as m:
        m.setattr(mod, "commit_library", boom)
        r = run(["doc", "add", str(_src(tmp_path)), "--repo", "obra/superpowers", *URL, *META])
    assert r.exit_code != 0
    assert not (root / "docs/repos/obra").exists()
    _assert_clean(root)


def test_failed_move_into_a_new_nested_group_leaves_nothing(isolated_env, tmp_path, monkeypatch):
    import shelf.cli.doc_move as mod

    root = _init()
    _add_nested(tmp_path, repo="flox")

    def boom(*a, **k):
        raise RuntimeError("injected")

    with monkeypatch.context() as m:
        m.setattr(mod, "commit_library", boom)
        assert run(["doc", "move", SLUG, "--repo", "obra/superpowers"]).exit_code != 0
    assert not (root / "docs/repos/obra").exists()
    _assert_clean(root)


def test_format_add_and_delete_on_a_nested_document(isolated_env, tmp_path):
    root = _init()
    _add_nested(tmp_path)
    pdf = tmp_path / "notes.pdf"
    pdf.write_text("%PDF")
    r = run(["doc", "format", "add", SLUG, str(pdf)])
    assert r.exit_code == 0, r.output
    assert (root / "docs/repos/obra/superpowers" / SLUG / f"{SLUG}.pdf").is_file()
    _assert_clean(root)
    r = run(["doc", "format", "delete", SLUG, "pdf"])
    assert r.exit_code == 0, r.output
    _assert_clean(root)


def test_server_serves_a_nested_document(isolated_env, tmp_path):
    import socket
    import urllib.request

    from shelf.server.serve import serve

    root = _init()
    _add_nested(tmp_path)
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    server, port = serve(root, port)
    try:
        url = f"http://127.0.0.1:{port}/docs/repos/obra/superpowers/{SLUG}/{SLUG}.md"
        with urllib.request.urlopen(url) as resp:
            assert resp.status == 200
            assert b"Superpowers" in resp.read()
    finally:
        server.shutdown()
        server.server_close()
