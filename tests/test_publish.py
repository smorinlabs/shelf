"""P21-TS02–TS05 — `shelf publish`: filtering, guard, dry-run, `_site`, base URL."""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from conftest import git_init_library

from shelf.cli.main import cli
from shelf.core import publish as publish_core
from shelf.core import visibility
from shelf.core.paths import default_library_path

_PAGE_RE = re.compile(r"const PAGE = (.*?);\n", re.DOTALL)


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _config(text):
    path = Path(os.environ["XDG_CONFIG_HOME"]) / "shelf" / "shelf_config.toml"
    path.write_text(path.read_text() + text)


@pytest.fixture
def lib(isolated_env, tmp_path, monkeypatch):
    """A user library with one published and one unpublished document, each with unique labels."""
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "open-topic"]).exit_code == 0
    assert run(["topic", "add", "secret-topic"]).exit_code == 0
    assert run(["kind", "add", "secret-kind"]).exit_code == 0
    pub = tmp_path / "pub.md"
    pub.write_text("# Public Page\n\nPUBLICBODY text.\n")
    sec = tmp_path / "sec.md"
    sec.write_text("# Secret\n\nSECRETSNIPPET text.\n")
    r = run(
        [
            "doc",
            "add",
            str(pub),
            "--topic",
            "open-topic",
            "--kind",
            "reference",
            "--title",
            "Public Page",
            "--description",
            "shown",
            "--tag",
            "open-tag",
            "--publish",
        ]
    )
    assert r.exit_code == 0, r.output
    r = run(
        [
            "doc",
            "add",
            str(sec),
            "--topic",
            "secret-topic",
            "--kind",
            "secret-kind",
            "--title",
            "Secret Title",
            "--description",
            "SECRETDESC",
            "--tag",
            "secret-tag",
        ]
    )
    assert r.exit_code == 0, r.output
    monkeypatch.setattr(visibility, "detect", lambda root: visibility.Repo("o/lib", "public"))
    monkeypatch.setattr(visibility, "pages_url", lambda slug: None)
    return default_library_path()


def _page(site):
    match = _PAGE_RE.search((site / "index.html").read_text())
    assert match is not None
    return json.loads(match.group(1))


SECRETS = [
    "Secret Title",
    "SECRETDESC",
    "SECRETSNIPPET",
    "secret-topic",
    "secret-kind",
    "secret-tag",
]


def test_marked_mode_publishes_only_marked_documents_and_leaks_nothing(lib, tmp_path):
    site = tmp_path / "_site"
    r = run(["publish", "--out", str(site)])
    assert r.exit_code == 0, r.output
    catalog = json.loads((site / "catalog.json").read_text())
    assert [d["title"] for d in catalog["documents"]] == ["Public Page"]
    assert catalog["topics"] == ["open-topic"]
    assert catalog["kinds"] == ["reference"]
    for name in ("index.html", "catalog.json"):
        text = (site / name).read_text()
        for secret in SECRETS:
            assert secret not in text, (name, secret)
    assert "PUBLICBODY" in (site / "index.html").read_text()
    assert not list(site.rglob("*sec*"))
    assert (site / ".nojekyll").is_file()
    assert len(list((site / "docs").rglob("*.md"))) == 1
    # `source` records where a file was added from: a local path, never published.
    assert str(tmp_path) not in (site / "catalog.json").read_text()
    assert catalog["documents"][0]["source"] is None
    assert json.loads((lib / "catalog.json").read_text())["documents"][0]["source"]


def test_all_mode_publishes_every_document_and_variant(lib, tmp_path):
    _config('publish = "all"\n')
    sec_id = [
        d
        for d in json.loads((lib / "catalog.json").read_text())["documents"]
        if d["title"] == "Secret Title"
    ][0]["id"]
    html = tmp_path / "sec.html"
    html.write_text("<p>v</p>")
    assert run(["doc", "format", "add", sec_id, str(html)]).exit_code == 0
    site = tmp_path / "_site"
    r = run(["publish", "--out", str(site)])
    assert r.exit_code == 0, r.output
    assert len(json.loads((site / "catalog.json").read_text())["documents"]) == 2
    assert len(list((site / "docs").rglob("*.html"))) == 1
    assert len(list((site / "docs").rglob("*.md"))) == 2


def test_an_invalid_publish_mode_is_an_error(lib, tmp_path):
    _config('publish = "everything"\n')
    r = run(["publish", "--out", str(tmp_path / "_site")])
    assert r.exit_code != 0
    assert "marked" in r.output and "all" in r.output


@pytest.mark.parametrize("vis", ["private", "internal", "unknown"])
@pytest.mark.parametrize("mode", ["marked", "all"])
def test_guard_refuses_non_public_without_force(lib, tmp_path, monkeypatch, vis, mode):
    if mode == "all":
        _config('publish = "all"\n')
    monkeypatch.setattr(visibility, "detect", lambda root: visibility.Repo("o/lib", vis))
    site = tmp_path / "_site"
    r = run(["publish", "--out", str(site)])
    assert r.exit_code == 2, r.output
    assert "o/lib" in r.output and vis in r.output and "--force" in r.output
    assert not site.exists()
    r = run(["publish", "--out", str(site), "--force"])
    assert r.exit_code == 0, r.output
    assert (site / "index.html").is_file()


def test_dry_run_never_requires_force_and_reports(lib, tmp_path, monkeypatch):
    monkeypatch.setattr(visibility, "detect", lambda root: visibility.Repo("o/lib", "private"))
    site = tmp_path / "_site"
    r = run(["publish", "--out", str(site), "--dry-run"])
    assert r.exit_code == 0, r.output
    assert not site.exists()
    assert "would publish 1 of 2 documents (mode: marked) from o/lib (private)" in r.output
    assert "Public Page" in r.output
    assert "1 document not published" in r.output
    assert 'publish = "all"' in r.output and "shelf_config.toml" in r.output
    assert "requires --force" in r.output


def test_dry_run_on_public_repo_has_no_force_note(lib, tmp_path):
    r = run(["publish", "--out", str(tmp_path / "_site"), "--dry-run"])
    assert r.exit_code == 0
    assert "--force" not in r.output


def test_out_refuses_the_library_and_foreign_folders(lib, tmp_path):
    assert run(["publish", "--out", str(lib)]).exit_code == 2
    assert run(["publish", "--out", str(lib / "docs" / "x")]).exit_code == 2
    assert run(["publish", "--out", str(lib.parent)]).exit_code == 2
    foreign = tmp_path / "mine"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("k")
    r = run(["publish", "--out", str(foreign)])
    assert r.exit_code != 0
    assert (foreign / "keep.txt").read_text() == "k"


def test_out_may_sit_inside_the_library_root_and_audit_ignores_it(lib, isolated_git_identity):
    git_init_library(lib)
    r = run(["publish", "--out", str(lib / "_site")])
    assert r.exit_code == 0, r.output
    assert (lib / "_site" / "index.html").is_file()
    assert run(["audit"]).exit_code == 0, run(["audit"]).output


def test_out_replaces_a_previous_build(lib, tmp_path):
    site = tmp_path / "_site"
    assert run(["publish", "--out", str(site)]).exit_code == 0
    (site / "stale.txt").write_text("old")
    assert run(["publish", "--out", str(site)]).exit_code == 0
    assert not (site / "stale.txt").exists()


def test_publish_never_changes_the_library(lib, tmp_path):
    before = {p: p.read_bytes() for p in lib.rglob("*") if p.is_file()}
    assert run(["publish", "--out", str(tmp_path / "_site")]).exit_code == 0
    after = {p: p.read_bytes() for p in lib.rglob("*") if p.is_file()}
    assert before == after


# --- base URL (TS05) ---------------------------------------------------------------


def test_no_base_url_keeps_relative_paths(lib, tmp_path):
    site = tmp_path / "_site"
    assert run(["publish", "--out", str(site)]).exit_code == 0
    assert _page(site)["root"] == ""


def test_base_url_precedence(lib, tmp_path, monkeypatch):
    site = tmp_path / "_site"
    monkeypatch.setattr(visibility, "pages_url", lambda slug: "https://gh.example/lib/")
    assert run(["publish", "--out", str(site)]).exit_code == 0
    assert _page(site)["root"] == "https://gh.example/lib"
    r = run(["publish", "--out", str(site), "--detected-base-url", "https://ci.example/lib/"])
    assert r.exit_code == 0
    assert _page(site)["root"] == "https://ci.example/lib"
    _config('base-url = "https://docs.example.com"\n')
    r = run(["publish", "--out", str(site), "--detected-base-url", "https://ci.example/lib/"])
    assert _page(site)["root"] == "https://docs.example.com"
    r = run(["publish", "--out", str(site), "--base-url", "https://one.off/"])
    assert r.exit_code == 0
    assert _page(site)["root"] == "https://one.off"


def test_source_links_follow_the_ci_branch(lib, tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/lib")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    site = tmp_path / "_site"
    assert run(["publish", "--out", str(site)]).exit_code == 0
    assert _page(site)["source"] == "https://github.com/o/lib/blob/main"


def test_library_index_has_no_base_url_or_source(lib):
    page = _page(lib)
    assert page["root"] == "" and page["source"] == ""


# --- visibility detection (TS03) -----------------------------------------------------


def _repo_with_origin(path, url):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(path), "remote", "add", "origin", url], check=True)
    return path


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:Own/Repo.git",
        "https://github.com/Own/Repo.git",
        "https://github.com/Own/Repo",
        "ssh://git@github.com/Own/Repo.git",
    ],
)
def test_github_slug_from_origin(tmp_path, url):
    root = _repo_with_origin(tmp_path / "r", url)
    assert visibility.github_slug(root) == "Own/Repo"


def test_non_github_or_missing_remote_has_no_slug(tmp_path):
    assert (
        visibility.github_slug(_repo_with_origin(tmp_path / "a", "https://gitlab.com/o/r")) is None
    )
    plain = tmp_path / "b"
    plain.mkdir()
    assert visibility.github_slug(plain) is None


def test_event_file_is_read_first(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"repository": {"full_name": "o/r", "private": False}}))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setattr(visibility, "_gh", lambda args: pytest.fail("gh must not run"))
    assert visibility.detect(tmp_path) == visibility.Repo("o/r", "public")
    event.write_text(json.dumps({"repository": {"full_name": "o/r", "private": True}}))
    assert visibility.detect(tmp_path).visibility == "private"
    event.write_text(json.dumps({"repository": {"full_name": "o/r", "visibility": "internal"}}))
    assert visibility.detect(tmp_path).visibility == "internal"


def test_gh_is_used_outside_ci(tmp_path, monkeypatch):
    root = _repo_with_origin(tmp_path / "r", "https://github.com/o/r")
    monkeypatch.setattr(visibility, "_gh", lambda args: "public\n")
    assert visibility.detect(root) == visibility.Repo("o/r", "public")


@pytest.mark.parametrize("gh_out", [None, "", "weird"])
def test_any_gh_failure_is_unknown(tmp_path, monkeypatch, gh_out):
    root = _repo_with_origin(tmp_path / "r", "https://github.com/o/r")
    monkeypatch.setattr(visibility, "_gh", lambda args: gh_out)
    assert visibility.detect(root) == visibility.Repo("o/r", "unknown")


def test_unreadable_event_file_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "missing.json"))
    assert visibility.detect(tmp_path).visibility == "unknown"


def test_a_library_inside_an_unrelated_repo_is_unknown(tmp_path, monkeypatch):
    home = _repo_with_origin(tmp_path / "home", "https://github.com/me/dotfiles")  # e.g. dotfiles
    lib = home / ".local" / "share" / "shelf"
    lib.mkdir(parents=True)
    monkeypatch.setattr(visibility, "_gh", lambda args: pytest.fail("gh must not run"))
    assert visibility.detect(lib) == visibility.Repo(None, "unknown")
    assert publish_core.source_base(lib, None) == ""


def test_no_repo_is_unknown(tmp_path):
    assert visibility.detect(tmp_path) == visibility.Repo(None, "unknown")
