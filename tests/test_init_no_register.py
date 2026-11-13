"""P27-TS01–TS04 — `shelf init --no-register` never writes the user config."""

import subprocess

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core import git as git_core
from shelf.core.config import default_config_path, load_config


def run(args):
    return CliRunner().invoke(cli, args)


@pytest.fixture
def git_commit_env(isolated_git_identity, monkeypatch):
    for key in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{key}_NAME", "t")
        monkeypatch.setenv(f"GIT_{key}_EMAIL", "t@t")


def _registered(tmp_path):
    """A user config that already registers another library."""
    first = tmp_path / "first"
    assert run(["init", "--library", str(first)]).exit_code == 0
    return first, default_config_path().read_bytes()


def test_no_register_creates_a_library_and_leaves_the_config_byte_identical(tmp_path):
    first, before = _registered(tmp_path)
    lib = tmp_path / "unregistered"
    r = run(["init", "--no-register", "--library", str(lib)])
    assert r.exit_code == 0, r.output
    assert (lib / "catalog.json").is_file()
    assert default_config_path().read_bytes() == before
    assert load_config(default_config_path()).library == str(first)
    assert f"shelf --library {lib}" in r.output
    assert f"shelf init --adopt {lib}" in r.output
    audit = run(["--library", str(lib), "audit"])
    assert audit.exit_code == 0, audit.output


def test_no_register_never_creates_a_config_file(tmp_path):
    lib = tmp_path / "unregistered"
    r = run(["init", "--no-register", "--library", str(lib)])
    assert r.exit_code == 0, r.output
    assert (lib / "catalog.json").is_file()
    assert not default_config_path().exists()


def test_no_register_still_refuses_an_existing_library_at_the_target(tmp_path):
    lib = tmp_path / "unregistered"
    assert run(["init", "--no-register", "--library", str(lib)]).exit_code == 0
    r = run(["init", "--no-register", "--library", str(lib)])
    assert r.exit_code == 5, r.output


def test_no_register_with_git_and_github(tmp_path, git_commit_env, monkeypatch):
    _, before = _registered(tmp_path)
    calls = []

    def fake_gh(args):
        calls.append(args)
        if args[:2] == ["repo", "create"]:
            return f"https://github.com/{args[2]}.git"
        raise AssertionError(f"unexpected gh invocation: {args}")

    monkeypatch.setattr(git_core, "_gh", fake_gh)
    lib = tmp_path / "team"
    r = run(
        ["init", "--no-register", "--library", str(lib), "--github", "--owner", "me"]
        + ["--repo-name", "x"]
    )
    assert r.exit_code == 0, r.output
    assert calls == [["repo", "create", "me/x", "--private"]]
    origin = subprocess.run(
        ["git", "-C", str(lib), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert origin == "https://github.com/me/x.git"
    assert default_config_path().read_bytes() == before


def test_no_register_with_scope_project_exits_two_and_writes_nothing(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    monkeypatch.chdir(repo)
    r = CliRunner().invoke(cli, ["init", "--scope", "project", "--no-register"])
    assert r.exit_code == 2
    assert "--scope project never registers in the user config; drop --no-register" in r.output
    assert not (repo / ".shelf").exists()
    assert not default_config_path().exists()


def test_no_register_with_adopt_is_a_usage_error(tmp_path):
    first, before = _registered(tmp_path)
    r = run(["init", "--adopt", str(first), "--no-register"])
    assert r.exit_code == 2
    assert default_config_path().read_bytes() == before


def test_without_the_flag_init_still_registers(tmp_path):
    lib = tmp_path / "lib"
    r = run(["init", "--library", str(lib)])
    assert r.exit_code == 0, r.output
    assert load_config(default_config_path()).library == str(lib)
    assert "--adopt" not in r.output


def test_printed_commands_work_for_a_path_with_spaces(tmp_path):
    import shlex

    _registered(tmp_path)
    lib = tmp_path / "team shelf"
    r = run(["init", "--no-register", "--library", str(lib)])
    assert r.exit_code == 0, r.output
    use = next(line for line in r.output.splitlines() if line.startswith("use it with: "))
    argv = shlex.split(use.removeprefix("use it with: ").replace("<command>", "audit"))
    assert argv[0] == "shelf"
    audit = run(argv[1:])
    assert audit.exit_code == 0, audit.output
    adopt = next(line for line in r.output.splitlines() if "shelf init --adopt" in line)
    argv = shlex.split(adopt.split(": ", 1)[1])
    assert argv[1:] == ["init", "--adopt", str(lib)]


def test_an_empty_adopt_with_no_register_is_a_usage_error(tmp_path):
    lib = tmp_path / "new"
    r = run(["init", "--adopt", "", "--no-register", "--library", str(lib)])
    assert r.exit_code == 2, r.output
    assert not lib.exists()
