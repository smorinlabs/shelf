"""P23 — `scripts/sync_agent_skills.py`: plugins/shelf/skills is the master copy."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sync_agent_skills.py"
MASTER = "plugins/shelf/skills"
COPY = "src/shelf/agent_skills"


@pytest.fixture(autouse=True)
def no_inherited_git_repo(monkeypatch):
    """Run from inside a git hook, GIT_DIR and friends would point git at the real repo."""
    out = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True)
    for name in out.stdout.split():
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    root = tmp_path / "repo"
    (root / MASTER / "shelf").mkdir(parents=True)
    (root / MASTER / "shelf" / "SKILL.md").write_text("name: shelf\nv1\n")
    git(root, "init", "-q")
    git(root, "config", "user.email", "t@t")
    git(root, "config", "user.name", "t")
    sync(root)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "baseline")
    return root


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


def sync(root, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=root, capture_output=True, text=True
    )


def staged(root):
    return set(git(root, "diff", "--cached", "--name-only").split())


# --- TS01 -----------------------------------------------------------------


def test_sync_rebuilds_the_copy_and_marks_it_generated(repo):
    (repo / MASTER / "shelf" / "SKILL.md").write_text("name: shelf\nv2\n")
    (repo / COPY / "stale.md").write_text("left over")
    r = sync(repo)
    assert r.returncode == 0, r.stderr
    assert (repo / COPY / "shelf" / "SKILL.md").read_text() == "name: shelf\nv2\n"
    assert not (repo / COPY / "stale.md").exists()
    marker = (repo / COPY / "GENERATED.md").read_text()
    assert MASTER in marker


def test_check_reports_drift_and_names_the_master(repo):
    assert sync(repo, "--check").returncode == 0
    (repo / MASTER / "shelf" / "SKILL.md").write_text("name: shelf\nv2\n")
    r = sync(repo, "--check")
    assert r.returncode == 1
    assert MASTER in r.stderr
    assert (repo / COPY / "shelf" / "SKILL.md").read_text() == "name: shelf\nv1\n"


# --- TS02 -----------------------------------------------------------------


def test_staged_master_edit_is_copied_and_staged(repo):
    (repo / MASTER / "shelf" / "SKILL.md").write_text("name: shelf\nv2\n")
    git(repo, "add", MASTER)
    r = sync(repo, "--staged")
    assert r.returncode == 0, r.stderr
    assert f"{COPY}/shelf/SKILL.md" in staged(repo)
    assert git(repo, "show", f":{COPY}/shelf/SKILL.md") == "name: shelf\nv2\n"


def test_unstaged_master_edits_are_not_copied(repo):
    master_md = repo / MASTER / "shelf" / "SKILL.md"
    master_md.write_text("name: shelf\nv2\n")
    git(repo, "add", MASTER)
    master_md.write_text("name: shelf\nv3 unstaged\n")
    r = sync(repo, "--staged")
    assert r.returncode == 0, r.stderr
    assert git(repo, "show", f":{COPY}/shelf/SKILL.md") == "name: shelf\nv2\n"


# --- TS03 -----------------------------------------------------------------


def test_an_edit_to_the_copy_alone_fails_and_is_kept(repo):
    copy_md = repo / COPY / "shelf" / "SKILL.md"
    copy_md.write_text("name: shelf\nedited the wrong copy\n")
    git(repo, "add", COPY)
    r = sync(repo, "--staged")
    assert r.returncode == 1
    assert MASTER in r.stderr
    assert f"git restore --staged -- {COPY}/" in r.stderr
    assert copy_md.read_text() == "name: shelf\nedited the wrong copy\n"


def test_non_ascii_master_paths_are_synced(repo):
    (repo / MASTER / "shelf" / "café.md").write_text("accent")
    git(repo, "add", MASTER)
    r = sync(repo, "--staged")
    assert r.returncode == 0, r.stderr
    assert git(repo, "show", f":{COPY}/shelf/café.md") == "accent"


def test_non_ascii_copy_only_edit_is_refused(repo):
    (repo / COPY / "shelf" / "café.md").write_text("wrong copy")
    git(repo, "add", COPY)
    assert sync(repo, "--staged").returncode == 1


def test_deleting_every_master_file_leaves_a_marker_only_copy(repo):
    git(repo, "rm", "-rq", MASTER)
    r = sync(repo, "--staged")
    assert r.returncode == 0, r.stderr
    assert git(repo, "ls-files", "--", COPY).split() == [f"{COPY}/GENERATED.md"]


def test_nothing_staged_in_either_folder_is_a_no_op(repo):
    (repo / "other.txt").write_text("x")
    git(repo, "add", "other.txt")
    r = sync(repo, "--staged")
    assert r.returncode == 0, r.stderr
    assert staged(repo) == {"other.txt"}


# --- TS04 -----------------------------------------------------------------


def test_lefthook_runs_the_staged_sync_before_commit():
    config = (REPO / "lefthook.yml").read_text()
    assert "pre-commit:" in config
    assert "scripts/sync_agent_skills.py --staged" in config


def test_the_real_copy_is_in_sync_with_the_master(tmp_path):
    work = tmp_path / "work"
    shutil.copytree(REPO / MASTER, work / MASTER)
    shutil.copytree(REPO / COPY, work / COPY)
    r = sync(work, "--check")
    assert r.returncode == 0, r.stderr
