from pathlib import Path

import click
import pytest

from shelf.core import handoff


def test_in_ai_session_none_when_unset(monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    assert handoff.in_ai_session() is None


def test_in_ai_session_detects_claude(monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDECODE", "1")
    assert handoff.in_ai_session() == "Claude Code"


def test_in_ai_session_detects_codex(monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "019f8055-7101-77e3-8d7c-aa002ee55cb1")
    assert handoff.in_ai_session() == "Codex"


def test_in_ai_session_ignores_empty_value(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "")
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    assert handoff.in_ai_session() is None


def test_resolve_agent_flag_wins():
    assert handoff.resolve_agent("codex", "claude") == "codex"


def test_resolve_agent_falls_back_to_config():
    assert handoff.resolve_agent(None, "codex") == "codex"


def test_resolve_agent_rejects_unknown():
    with pytest.raises(click.ClickException, match="unknown handoff agent"):
        handoff.resolve_agent(None, "emacs")


def test_build_handoff_prompt_single_path():
    prompt = handoff.build_handoff_prompt([Path("/tmp/a.md")])
    assert (
        prompt
        == "Use the shelf-add skill to add `/tmp/a.md` to shelf. Walk me through classification."
    )


def test_build_handoff_prompt_multiple_paths():
    prompt = handoff.build_handoff_prompt([Path("/tmp/a.md"), Path("/tmp/b.pdf")])
    assert "`/tmp/a.md`, `/tmp/b.pdf`" in prompt


def test_run_handoff_execs_with_agent_and_prompt(monkeypatch):
    calls = {}

    def fake_execvp(file, args):
        calls["file"] = file
        calls["args"] = args

    monkeypatch.setattr(handoff.os, "execvp", fake_execvp)
    handoff.run_handoff("claude", [Path("/tmp/a.md")])
    assert calls["file"] == "claude"
    assert calls["args"][0] == "claude"
    assert "shelf-add skill" in calls["args"][1]


def test_run_handoff_missing_binary_raises_clickexception(monkeypatch):
    def boom(file, args):
        raise FileNotFoundError(file)

    monkeypatch.setattr(handoff.os, "execvp", boom)
    with pytest.raises(click.ClickException, match="not installed or not on PATH"):
        handoff.run_handoff("codex", [Path("/tmp/a.md")])
