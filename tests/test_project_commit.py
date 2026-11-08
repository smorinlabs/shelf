"""P20-TS06 — project-scope --commit stages only shelf paths in the host repo."""

import subprocess

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli

BASE = ["--kind", "reference", "--title", "API Guide", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture
def host(tmp_path, monkeypatch, isolated_git_identity):
    repo = (tmp_path / "repo").resolve()
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    (repo / "app.py").write_text("print('v1')\n")
    monkeypatch.chdir(repo)
    assert run(["init", "--scope", "project"]).exit_code == 0
    assert run(["topic", "add", "api"]).exit_code == 0
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "baseline")
    (repo / "app.py").write_text("print('v2, not shelf work')\n")
    (repo / "notes.txt").write_text("untracked, not shelf work\n")
    return repo


def test_doc_add_commit_touches_only_shelf_paths(host):
    src = host / "guide.md"
    src.write_text("# API guide\n")
    r = run(["doc", "add", str(src), "--topic", "api", *BASE, "--commit"])
    assert r.exit_code == 0, r.output
    committed = git(host, "show", "--name-only", "--format=", "HEAD").split()
    assert "shelf/catalog.json" in committed
    assert any(p.startswith("shelf/docs/topics/api/") for p in committed)
    assert "app.py" not in committed
    assert "notes.txt" not in committed
    assert not any(p.endswith("index.html") for p in committed)  # gitignored in project scope
    status = git(host, "status", "--porcelain")
    assert " M app.py" in status
    assert "?? notes.txt" in status
    assert src.exists()  # project default: remove-source = false


def test_regen_commit_with_an_ignored_index_makes_no_index_commit(host):
    before = git(host, "rev-parse", "HEAD")
    r = run(["regen", "--commit"])
    assert r.exit_code == 0, r.output
    assert git(host, "show", "--name-only", "--format=", "HEAD").split() == []
    assert git(host, "rev-parse", "HEAD^") == before


def test_merge_in_progress_is_detected_from_the_library_subfolder(host):
    (host / ".git" / "MERGE_HEAD").write_text(git(host, "rev-parse", "HEAD"))
    r = run(["topic", "add", "more", "--commit"])
    assert r.exit_code == 1
    assert "merge is in progress" in r.output
