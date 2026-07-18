"""P01-TS02 — cli-design-standard conformance smoke (R9.14 seed)."""

import re
import subprocess

STUB_HELP_PATHS = [
    ["doc", "add"],
    ["doc", "list"],
    ["doc", "view"],
    ["doc", "update"],
    ["doc", "move"],
    ["doc", "delete"],
    ["doc", "adopt"],
    ["doc", "format", "add"],
    ["doc", "format", "delete"],
    ["orphan", "list"],
    ["orphan", "delete"],
    ["topic", "add"],
    ["topic", "list"],
    ["kind", "add"],
    ["kind", "list"],
    ["init"],
    ["audit"],
    ["open"],
    ["path"],
    ["regen"],
    ["migrate"],
]


def run_shelf(*args):
    return subprocess.run(["uv", "run", "shelf", *args], capture_output=True, text=True)


def test_bare_invocation_help_on_stdout_exit_zero():
    r = run_shelf()
    assert r.returncode == 0
    assert "Usage: shelf" in r.stdout


def test_unknown_command_exits_two():
    r = run_shelf("frobnicate")
    assert r.returncode == 2


def test_bare_group_usage_error_on_stderr_exit_two():
    r = run_shelf("doc")
    assert r.returncode == 2
    assert "Usage: shelf doc" in r.stderr


def test_version_format_gnu_style():
    r = run_shelf("-V")
    assert r.returncode == 0
    assert re.fullmatch(r"shelf \d+\.\d+\.\d+", r.stdout.strip())


def test_every_command_has_help():
    for path in STUB_HELP_PATHS:
        r = run_shelf(*path, "--help")
        assert r.returncode == 0, f"--help failed for {path}: {r.stderr}"
        assert "Usage:" in r.stdout, f"no usage text for {path}"


def test_stub_leaf_errors_cleanly():
    r = run_shelf("audit")
    assert r.returncode == 1
    assert "not implemented" in r.stderr.lower()
