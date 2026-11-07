"""P22 — `shelf agent install | status | uninstall` (alias `shelf skill`)."""

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core import agent

REPO = Path(__file__).resolve().parents[1]
PLUGIN_SKILLS = REPO / "plugins" / "shelf" / "skills"
NAMES = ("shelf", "shelf-reference")
TARGETS = (".claude/skills", ".agents/skills")


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.chdir(h)
    for var in ("GIT_DIR", "GIT_WORK_TREE"):
        monkeypatch.delenv(var, raising=False)
    return h


@pytest.fixture
def checkout(tmp_path):
    """A shelf checkout with the real plugin skills, outside any test repo."""
    root = tmp_path / "shelf-checkout"
    shutil.copytree(PLUGIN_SKILLS, root / "plugins" / "shelf" / "skills")
    return root


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    return path


def dests(root: Path, name: str = "shelf"):
    return [root / t / name for t in TARGETS]


def tree(path: Path) -> dict:
    return {
        str(p.relative_to(path)): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file() and p.name != agent.STAMP
    }


# --- TS07 packaging ---------------------------------------------------------


def test_bundled_skills_match_the_plugin_skills_byte_for_byte():
    for name in NAMES:
        assert tree(agent.bundled_dir() / name) == tree(PLUGIN_SKILLS / name), (
            f"{name}: src/shelf/agent_skills is out of date — run `just sync-agent-skills`"
        )


def test_wheel_contains_the_bundled_skills(tmp_path):
    out = tmp_path / "dist"
    subprocess.run(
        ["uv", "build", "--wheel", "-q", "-o", str(out), str(REPO)],
        check=True,
        capture_output=True,
    )
    (wheel,) = out.glob("*.whl")
    names = zipfile.ZipFile(wheel).namelist()
    assert "shelf/agent_skills/shelf/SKILL.md" in names
    assert "shelf/agent_skills/shelf-reference/SKILL.md" in names


# --- TS01 scope roots -------------------------------------------------------


def test_user_scope_installs_into_both_home_skill_folders(home):
    r = run(["agent", "install"])
    assert r.exit_code == 0, r.output
    for name in NAMES:
        for d in dests(home, name):
            assert (d / "SKILL.md").is_file()


def test_project_scope_installs_at_the_repo_root(home, tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "work" / "repo")
    (repo / "sub").mkdir()
    monkeypatch.chdir(repo / "sub")
    r = run(["agent", "install", "--scope", "project"])
    assert r.exit_code == 0, r.output
    for d in dests(repo):
        assert (d / "SKILL.md").is_file()
    assert not (home / ".claude").exists()


def test_project_scope_outside_a_repo_is_refused(home, tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)
    r = run(["agent", "install", "--scope", "project"])
    assert r.exit_code == 2
    assert "Git repository" in r.output


def test_project_scope_refuses_a_repo_rooted_at_home(home, monkeypatch):
    git_repo(home)
    (home / "x").mkdir()
    monkeypatch.chdir(home / "x")
    r = run(["agent", "install", "--scope", "project"])
    assert r.exit_code == 2
    assert "home directory" in r.output


def test_project_scope_refuses_a_repo_root_that_is_not_an_ancestor(home, tmp_path, monkeypatch):
    other = git_repo(tmp_path / "dotfiles")
    here = tmp_path / "elsewhere"
    here.mkdir()
    monkeypatch.chdir(here)
    monkeypatch.setenv("GIT_DIR", str(other / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(other))
    r = run(["agent", "install", "--scope", "project"])
    assert r.exit_code == 2


# --- TS02 copy mode ---------------------------------------------------------


def test_copy_mode_writes_the_bundled_skill_and_a_stamp(home):
    assert run(["agent", "install"]).exit_code == 0
    for d in dests(home):
        assert tree(d) == tree(agent.bundled_dir() / "shelf")
        stamp = json.loads((d / agent.STAMP).read_text())
        assert stamp["mode"] == "copy"
        assert stamp["version"] == agent.cli_version()


def test_rerun_reports_unchanged_and_a_newer_cli_reports_updated(home):
    assert run(["agent", "install"]).exit_code == 0
    r = run(["agent", "install"])
    assert r.exit_code == 0
    assert "unchanged" in r.output and "created" not in r.output
    stamp_path = home / ".claude/skills/shelf" / agent.STAMP
    stamp_path.write_text(json.dumps({"mode": "copy", "version": "0.0.1"}))
    r = run(["agent", "install"])
    assert r.exit_code == 0
    assert "updated" in r.output


def test_install_leaves_unrelated_skills_alone(home):
    other = home / ".claude/skills/other"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text("other")
    assert run(["agent", "install"]).exit_code == 0
    assert (other / "SKILL.md").read_text() == "other"


# --- TS03 dev mode ----------------------------------------------------------


def test_dev_mode_links_into_the_checkout(home, checkout):
    r = run(["agent", "install", "--dev", "--source", str(checkout)])
    assert r.exit_code == 0, r.output
    for name in NAMES:
        for d in dests(home, name):
            assert d.is_symlink()
            assert Path(os.readlink(d)).is_absolute()
            assert d.resolve() == (checkout / "plugins/shelf/skills" / name).resolve()
    assert not (checkout / "plugins/shelf/skills/shelf" / agent.STAMP).exists()


def test_dev_mode_without_source_uses_the_running_checkout(home):
    r = run(["agent", "install", "--dev"])
    assert r.exit_code == 0, r.output
    assert (home / ".claude/skills/shelf").resolve() == (PLUGIN_SKILLS / "shelf").resolve()


def test_dev_mode_rejects_a_source_without_the_skills(home, tmp_path):
    r = run(["agent", "install", "--dev", "--source", str(tmp_path)])
    assert r.exit_code == 2
    assert "plugins/shelf/skills" in r.output


def test_project_dev_mode_needs_a_source_inside_the_repo(home, checkout, tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "repo")
    monkeypatch.chdir(repo)
    r = run(["agent", "install", "--scope", "project", "--dev", "--source", str(checkout)])
    assert r.exit_code == 2
    assert "inside" in r.output


def test_project_dev_mode_with_an_in_repo_source_writes_relative_links(home, tmp_path, monkeypatch):
    repo = git_repo(tmp_path / "repo")
    shutil.copytree(PLUGIN_SKILLS, repo / "plugins" / "shelf" / "skills")
    monkeypatch.chdir(repo)
    r = run(["agent", "install", "--scope", "project", "--dev", "--source", str(repo)])
    assert r.exit_code == 0, r.output
    for d in dests(repo):
        assert d.is_symlink()
        assert not Path(os.readlink(d)).is_absolute()
        assert (d / "SKILL.md").is_file()


# --- TS04 classification: never replace what shelf did not install ----------


def test_a_foreign_copy_is_skipped_without_force(home):
    foreign = home / ".claude/skills/shelf"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("hand made")
    r = run(["agent", "install"])
    assert r.exit_code == 1
    assert "skipped" in r.output and "--force" in r.output
    assert (foreign / "SKILL.md").read_text() == "hand made"


def test_force_replaces_a_foreign_copy_and_backs_it_up(home):
    foreign = home / ".claude/skills/shelf"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("hand made")
    r = run(["agent", "install", "--force"])
    assert r.exit_code == 0, r.output
    assert tree(foreign) == tree(agent.bundled_dir() / "shelf")
    backup = home / ".claude/skills" / agent.BACKUP_DIR / "shelf" / "SKILL.md"
    assert backup.read_text() == "hand made"


def test_a_link_to_another_target_is_skipped_without_force(home, checkout, tmp_path):
    elsewhere = tmp_path / "elsewhere-skill"
    elsewhere.mkdir()
    (elsewhere / "SKILL.md").write_text("elsewhere")
    link = home / ".claude/skills/shelf"
    link.parent.mkdir(parents=True)
    link.symlink_to(elsewhere)
    r = run(["agent", "install", "--dev", "--source", str(checkout)])
    assert r.exit_code == 1
    assert link.resolve() == elsewhere.resolve()
    r = run(["agent", "install", "--dev", "--source", str(checkout), "--force"])
    assert r.exit_code == 0, r.output
    assert link.resolve() == (checkout / "plugins/shelf/skills/shelf").resolve()


def test_switching_modes_needs_force(home, checkout):
    assert run(["agent", "install"]).exit_code == 0
    r = run(["agent", "install", "--dev", "--source", str(checkout)])
    assert r.exit_code == 1
    assert "--force" in r.output
    assert not (home / ".claude/skills/shelf").is_symlink()
    r = run(["agent", "install", "--dev", "--source", str(checkout), "--force"])
    assert r.exit_code == 0
    assert (home / ".claude/skills/shelf").is_symlink()


def test_an_enabled_shelf_plugin_skips_the_claude_folder(home):
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"enabledPlugins": {"shelf@shelf": True}}))
    r = run(["agent", "install"])
    assert r.exit_code == 1
    assert "plugin" in r.output
    assert not (home / ".claude/skills/shelf").exists()
    assert (home / ".agents/skills/shelf/SKILL.md").is_file()


# --- TS05 safety ------------------------------------------------------------


def test_replacing_a_symlink_never_touches_its_target(home, checkout):
    assert run(["agent", "install", "--dev", "--source", str(checkout)]).exit_code == 0
    before = tree(checkout / "plugins/shelf/skills/shelf")
    assert run(["agent", "install", "--force"]).exit_code == 0
    assert not (home / ".claude/skills/shelf").is_symlink()
    assert tree(checkout / "plugins/shelf/skills/shelf") == before


def test_uninstalling_a_dev_link_unlinks_only(home, checkout):
    assert run(["agent", "install", "--dev", "--source", str(checkout)]).exit_code == 0
    r = run(["agent", "uninstall"])
    assert r.exit_code == 0, r.output
    for d in dests(home):
        assert not d.exists() and not d.is_symlink()
    assert (checkout / "plugins/shelf/skills/shelf/SKILL.md").is_file()


def test_the_backup_slot_holds_only_the_previous_placement(home):
    foreign = home / ".claude/skills/shelf"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("v1")
    assert run(["agent", "install", "--force"]).exit_code == 0
    stamp = foreign / agent.STAMP
    stamp.write_text(json.dumps({"mode": "copy", "version": "0.0.1"}))
    assert run(["agent", "install"]).exit_code == 0
    slot = home / ".claude/skills" / agent.BACKUP_DIR / "shelf"
    assert json.loads((slot / agent.STAMP).read_text())["version"] == "0.0.1"
    assert not (home / ".claude/skills" / agent.BACKUP_DIR / "shelf-v1").exists()


def test_a_failure_mid_swap_restores_the_previous_placement(home, monkeypatch):
    foreign = home / ".claude/skills/shelf"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("keep me")

    def boom(src, dest):
        raise OSError("disk full")

    monkeypatch.setattr(agent, "_move_into_place", boom)
    r = run(["agent", "install", "--force"])
    assert r.exit_code != 0
    assert (foreign / "SKILL.md").read_text() == "keep me"


# --- TS06 dry run and status ------------------------------------------------


def test_dry_run_writes_nothing(home):
    r = run(["agent", "install", "--dry-run"])
    assert r.exit_code == 0, r.output
    assert "would create" in r.output
    assert not (home / ".claude").exists() and not (home / ".agents").exists()


def test_status_json_reports_kind_version_and_staleness(home, checkout):
    assert run(["agent", "install"]).exit_code == 0
    (home / ".agents/skills/shelf").rename(home / "moved")
    (home / ".agents/skills/shelf").symlink_to(checkout / "plugins/shelf/skills/shelf")
    stamp = home / ".claude/skills/shelf-reference" / agent.STAMP
    stamp.write_text(json.dumps({"mode": "copy", "version": "0.0.1"}))
    r = run(["agent", "status", "--json"])
    assert r.exit_code == 0, r.output
    rows = {(row["folder"], row["skill"]): row for row in json.loads(r.output)}
    claude_shelf = rows[(".claude/skills", "shelf")]
    assert claude_shelf["kind"] == "copy" and claude_shelf["stale"] is False
    assert claude_shelf["version"] == agent.cli_version()
    assert rows[(".agents/skills", "shelf")]["kind"] == "dev-link"
    assert rows[(".claude/skills", "shelf-reference")]["stale"] is True


# --- uninstall --------------------------------------------------------------


def test_uninstall_removes_owned_copies_and_skips_foreign_ones(home):
    assert run(["agent", "install"]).exit_code == 0
    foreign = home / ".agents/skills/shelf-reference"
    shutil.rmtree(foreign)
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("hand made")
    r = run(["agent", "uninstall"])
    assert r.exit_code == 1
    assert not (home / ".claude/skills/shelf").exists()
    assert (foreign / "SKILL.md").read_text() == "hand made"
    r = run(["agent", "uninstall", "--force"])
    assert r.exit_code == 0
    assert not foreign.exists()
    backup = home / ".agents/skills" / agent.BACKUP_DIR / "shelf-reference" / "SKILL.md"
    assert backup.read_text() == "hand made"


# --- TS08 adoption of an existing dev setup ---------------------------------


def test_existing_links_to_the_same_checkout_are_left_unchanged(home, checkout):
    for name in NAMES:
        for d in dests(home, name):
            d.parent.mkdir(parents=True, exist_ok=True)
            d.symlink_to(checkout / "plugins/shelf/skills" / name)
    r = run(["agent", "install", "--dev", "--source", str(checkout)])
    assert r.exit_code == 0, r.output
    assert r.output.count("unchanged") == 4
    assert "created" not in r.output and "updated" not in r.output


# --- TS09 alias -------------------------------------------------------------


def test_skill_is_an_alias_for_agent(home):
    assert "skill" in run(["--help"]).output
    r = run(["skill", "install"])
    assert r.exit_code == 0, r.output
    assert (home / ".claude/skills/shelf/SKILL.md").is_file()


# --- stale-copy note in audit -----------------------------------------------


def test_audit_notes_a_stale_user_copy(home):
    assert run(["init"]).exit_code == 0
    assert run(["agent", "install"]).exit_code == 0
    stamp = home / ".claude/skills/shelf" / agent.STAMP
    stamp.write_text(json.dumps({"mode": "copy", "version": "0.0.1"}))
    r = run(["audit"])
    assert r.exit_code == 0, r.output
    assert "shelf agent install" in r.output
    assert "shelf agent install" not in run(["-q", "audit"]).output
