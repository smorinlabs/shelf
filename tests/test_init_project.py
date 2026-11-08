"""P20-TS04 — `shelf init --scope project`, the .gitignore append, the agent offer, and
rebuilding a missing index.html (a gitignored file a fresh clone lacks)."""

import subprocess
import tomllib

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.config import default_config_path


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


@pytest.fixture
def repo(tmp_path, monkeypatch, isolated_git_identity):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))  # agent installs never see the real ~
    (tmp_path / "home").mkdir()
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    (root / ".gitignore").write_text("node_modules/\n*.pyc")  # no trailing newline
    monkeypatch.chdir(root / "src")
    return root.resolve()


def test_creates_marker_config_and_library_at_the_repo_top(repo):
    r = run(["init", "--scope", "project"])
    assert r.exit_code == 0, r.output
    cfg = tomllib.loads((repo / ".shelf" / "shelf_config.toml").read_text())
    assert cfg == {"library": "shelf", "remove-source": False}
    assert (repo / "shelf" / "catalog.json").is_file()
    assert (repo / "shelf" / "docs" / "topics").is_dir()
    assert not (repo / "shelf" / ".git").exists()
    assert not default_config_path().exists()  # the user config is untouched
    assert f"initialized project library at {repo / 'shelf'}" in r.output


def test_appends_to_gitignore_without_losing_lines(repo):
    assert run(["init", "--scope", "project"]).exit_code == 0
    lines = (repo / ".gitignore").read_text().splitlines()
    assert lines[:2] == ["node_modules/", "*.pyc"]
    assert ".shelf.lock" in lines
    assert "/shelf/index.html" in lines
    assert run(["init", "--scope", "project", "--force"]).exit_code == 0
    again = (repo / ".gitignore").read_text().splitlines()
    assert again.count(".shelf.lock") == 1  # never duplicated


def test_index_is_gitignored_and_the_catalog_is_not(repo):
    assert run(["init", "--scope", "project"]).exit_code == 0
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "shelf/catalog.json" in status
    assert "index.html" not in status
    assert ".shelf.lock" not in status


def test_the_new_project_scope_is_discovered(repo):
    assert run(["init", "--scope", "project"]).exit_code == 0
    r = run(["path"])
    assert r.output.strip() == str(repo / "shelf")


def test_relative_library_option_and_readme(repo):
    r = run(["init", "--scope", "project", "--library", "docs/shelf"])
    assert r.exit_code == 0, r.output
    assert (repo / "docs" / "shelf" / "README.md").is_file()
    assert "/docs/shelf/index.html" in (repo / ".gitignore").read_text()


def test_library_at_the_repo_root_writes_no_readme(repo):
    (repo / "README.md").write_text("# my project\n")
    r = run(["init", "--scope", "project", "--library", "."])
    assert r.exit_code == 0, r.output
    assert (repo / "README.md").read_text() == "# my project\n"
    assert "/index.html" in (repo / ".gitignore").read_text().splitlines()


@pytest.mark.parametrize("value", ["/abs/lib", "../outside"])
def test_library_must_be_relative_inside_the_repo(repo, value):
    assert run(["init", "--scope", "project", "--library", value]).exit_code == 2


@pytest.mark.parametrize("flag", [["--git"], ["--github"], ["--adopt", "x"]])
def test_repo_creating_flags_are_rejected(repo, flag):
    assert run(["init", "--scope", "project", *flag]).exit_code == 2


def test_outside_a_git_repo_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = run(["init", "--scope", "project"])
    assert r.exit_code == 1
    assert "Git repository" in r.output


def test_an_existing_project_scope_needs_force(repo):
    assert run(["init", "--scope", "project"]).exit_code == 0
    assert run(["init", "--scope", "project"]).exit_code == 5


def test_offers_the_project_scope_agent_install(repo):
    r = run(["init", "--scope", "project"])
    assert "shelf agent install --scope project" in r.output
    assert not (repo / ".claude").exists()


def test_yes_accepts_the_agent_install_offer(repo):
    r = run(["init", "--scope", "project", "--yes"])
    assert r.exit_code == 0, r.output
    assert (repo / ".claude" / "skills" / "shelf" / "SKILL.md").is_file()
    assert (repo / ".agents" / "skills" / "shelf" / "SKILL.md").is_file()


def test_plain_init_git_appends_to_an_existing_gitignore(tmp_path, isolated_git_identity):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / ".gitignore").write_text("scratch/\n")
    r = run(["init", "--library", str(lib), "--git"])
    assert r.exit_code == 0, r.output
    assert (lib / ".gitignore").read_text().splitlines() == ["scratch/", ".shelf.lock"]


def test_open_rebuilds_a_missing_index(repo, monkeypatch):
    assert run(["init", "--scope", "project"]).exit_code == 0
    index = repo / "shelf" / "index.html"
    index.unlink()  # a fresh clone: index.html is gitignored
    launched = []
    monkeypatch.setattr("shelf.cli.open_cmd._launch", lambda url, browser: launched.append(url))
    r = run(["open", "--static"])
    assert r.exit_code == 0, r.output
    assert index.is_file()
    assert launched == [index.resolve().as_uri()]


def test_audit_reports_a_missing_index_as_a_regen_finding(repo):
    import json

    assert run(["init", "--scope", "project"]).exit_code == 0
    (repo / "shelf" / "index.html").unlink()
    r = run(["audit", "--pre-commit", "--json"])
    assert r.exit_code == 1
    findings = json.loads(r.output)
    assert {(f["check"], f["code"]) for f in findings} == {(4, "index-missing")}
    assert "shelf regen" in findings[0]["remediation"]
