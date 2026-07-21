"""shelf doc add handoff (PRD §11.2) — launch the configured AI agent when
classification flags are missing, unless already inside an AI session."""

import os
from pathlib import Path
from typing import NoReturn

import click

_VALID_AGENTS = ("claude", "codex")


def in_ai_session() -> str | None:
    """Return the AI session label if running inside one, else None.

    Claude Code sets CLAUDECODE; Codex sets CODEX_THREAD_ID (Codex CLI 0.144.6).
    """
    if os.environ.get("CLAUDECODE"):
        return "Claude Code"
    if os.environ.get("CODEX_THREAD_ID"):
        return "Codex"
    return None


def resolve_agent(flag: str | None, cfg_agent: str) -> str:
    """Resolve the handoff agent: flag > config > (config default 'claude')."""
    agent = flag or cfg_agent
    if agent not in _VALID_AGENTS:
        raise click.ClickException(
            f"unknown handoff agent '{agent}' — use one of {', '.join(_VALID_AGENTS)}"
        )
    return agent


def build_handoff_prompt(paths: list[Path]) -> str:
    """Build the primed introductory prompt referencing the shelf-add skill."""
    listed = ", ".join(f"`{p}`" for p in paths)
    return f"Use the shelf-add skill to add {listed} to shelf. Walk me through classification."


def _launch_handoff(agent: str, prompt: str) -> NoReturn:
    """Replace this process with the agent, seeded with the primed prompt.

    Isolated seam (like core.git._gh) so tests mock os.execvp. On success the
    process image is replaced and nothing after this returns.
    """
    try:
        os.execvp(agent, [agent, prompt])
    except OSError as exc:
        raise click.ClickException(
            f"handoff agent '{agent}' could not be launched: {exc} "
            "(not installed or not on PATH, or not executable)"
        ) from exc


def run_handoff(agent: str, paths: list[Path]) -> NoReturn:
    """Build the primed prompt and hand off to the agent (execs; never returns)."""
    _launch_handoff(agent, build_handoff_prompt(paths))
