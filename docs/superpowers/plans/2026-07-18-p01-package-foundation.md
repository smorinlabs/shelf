# P01 Package Foundation Implementation Plan (v0.1.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A src-layout uv package where `shelf --version` works, every PRD command exists as a stub with correct help/exit-code behavior, and `make check` + `just all` run green.

**Architecture:** One click group (`cli`) with sub-groups `doc`, `doc format`, `orphan`, `topic`, `kind` and top-level tool commands; all leaves are stubs that error `not implemented yet` (exit 1) while help works everywhere. Tooling is the py-launch-blueprint core only: uv, ruff, ty, pytest, just, make.

**Tech Stack:** Python ≥3.12, uv (src layout, `uv init --package`), click ≥8.1, pytest, ruff, ty, just, make.

**Agent assignments (per the SDD orchestration plan):** Task 1 sonnet · Tasks 2–4 red steps sonnet, green steps codex · Task 5 fable + haiku.

## Global Constraints

- Grammar and behavior per SHELF-PRD.md §5 (standards conformance) and §11: bare `shelf` → help on stdout, exit `0`; bare group (`shelf doc`) → help on **stderr**, exit `2`; unknown command → exit `2`; `-V`/`--version` → `shelf <semver>` on stdout, exit `0`.
- `-v` is reserved for verbose (later phase) — never bind it to version.
- Version string lives in `pyproject.toml` only (`0.1.0` this phase); code reads it via `importlib.metadata`.
- Conventional Commits, each ending with the session trailer line used in this repo.
- Work happens in the P01 worktree on branch `p01-foundation`; never in the live checkout.

---

### Task 1: Scaffold the package

**Files:**
- Create: `pyproject.toml`, `src/shelf/__init__.py`, `src/shelf/cli/__init__.py`, `uv.lock`, `.python-version`
- Modify: `.gitignore` (append uv/python entries if missing)

**Interfaces:**
- Produces: importable package `shelf`; console script `shelf = "shelf.cli.main:cli"` (Task 2 creates `main.py`); dev dependency group with pytest/ruff/ty.

- [ ] **Step 1: Initialize the package in the worktree root**

Run:
```bash
uv init --package --name shelf .
```
Expected: creates `pyproject.toml` and `src/shelf/__init__.py` (README.md already exists and is kept).

- [ ] **Step 2: Add dependencies**

Run:
```bash
uv add "click>=8.1"
uv add --dev pytest pytest-cov ruff ty
```
Expected: both commands resolve and write `uv.lock`.

- [ ] **Step 3: Edit `pyproject.toml`**

Ensure these entries exist (merge into what `uv init` generated — do not delete generated build-system settings):

```toml
[project]
name = "shelf"
version = "0.1.0"
description = "A private documentation library and management CLI"
requires-python = ">=3.12"

[project.scripts]
shelf = "shelf.cli.main:cli"
```

- [ ] **Step 4: Create the cli subpackage**

```bash
mkdir -p src/shelf/cli && touch src/shelf/cli/__init__.py
```

- [ ] **Step 5: Sync and verify import**

Run:
```bash
uv sync --all-groups
uv run python -c "import shelf; print('ok')"
```
Expected: `ok`.

- [ ] **Step 6: Append to `.gitignore` if missing**

```
.venv/
__pycache__/
*.egg-info/
.pytest_cache/
.ruff_cache/
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold shelf package (uv src layout, click, dev tooling)"
```

---

### Task 2: Version and smoke tests (P01-TS01)

**Files:**
- Test: `tests/test_cli_smoke.py`
- Create: `src/shelf/cli/main.py`

**Interfaces:**
- Consumes: package from Task 1.
- Produces: `cli` — the root `click.Group`, importable as `from shelf.cli.main import cli`. Root behavior: bare invocation prints help to stdout and exits 0. All later tasks attach to this group.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

```python
"""P01-TS01 — CLI smoke tests."""
from click.testing import CliRunner

from shelf.cli.main import cli


def test_version_exits_zero():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == "shelf 0.1.0"


def test_dash_v_capital_alias():
    result = CliRunner().invoke(cli, ["-V"])
    assert result.exit_code == 0
    assert result.output.strip() == "shelf 0.1.0"


def test_help_exits_zero():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage: shelf" in result.output
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shelf.cli.main'`.

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_cli_smoke.py
git commit -m "test: add P01-TS01 CLI smoke tests (red)"
```

- [ ] **Step 4: Minimal implementation** *(codex)*

`src/shelf/cli/main.py`:

```python
"""shelf CLI entry point."""
from importlib.metadata import version

import click

_VERSION = version("shelf")


@click.group(invoke_without_command=True)
@click.version_option(_VERSION, "-V", "--version", prog_name="shelf", message="shelf %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Shelf — a private documentation library."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_cli_smoke.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add src/shelf/cli/main.py
git commit -m "feat: root cli group with -V/--version and bare-invocation help"
```

---

### Task 3: Full command tree stubs + conformance tests (P01-TS02)

**Files:**
- Test: `tests/test_conformance.py`
- Modify: `src/shelf/cli/main.py`

**Interfaces:**
- Consumes: `cli` from Task 2.
- Produces: groups `doc`, `doc format` (nested under `doc`), `orphan`, `topic`, `kind`; stub leaf commands exactly matching PRD §5's subcommand list. Every group follows the bare-group contract (help→stderr, exit 2). Stubs raise `click.ClickException` (exit 1). Later phases replace stub bodies without renaming commands.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

```python
"""P01-TS02 — cli-design-standard conformance smoke (R9.14 seed)."""
import re
import subprocess

STUB_HELP_PATHS = [
    ["doc", "add"], ["doc", "list"], ["doc", "view"], ["doc", "update"],
    ["doc", "move"], ["doc", "delete"], ["doc", "adopt"],
    ["doc", "format", "add"], ["doc", "format", "delete"],
    ["orphan", "list"], ["orphan", "delete"],
    ["topic", "add"], ["topic", "list"], ["kind", "add"], ["kind", "list"],
    ["init"], ["audit"], ["open"], ["path"], ["regen"], ["migrate"],
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
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_conformance.py -v`
Expected: FAIL — unknown commands (`doc`, `audit`, …) exit 2 where 0/1 expected, missing groups.

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_conformance.py
git commit -m "test: add P01-TS02 conformance smoke tests (red)"
```

- [ ] **Step 4: Implement the command tree** *(codex)*

Extend `src/shelf/cli/main.py`. The pattern — a group factory enforcing the bare-group contract, and a stub decorator:

```python
def _group(parent: click.Group, name: str, help_text: str) -> click.Group:
    @parent.group(name, invoke_without_command=True, help=help_text)
    @click.pass_context
    def grp(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help(), err=True)
            ctx.exit(2)
    return grp


def _stub(parent: click.Group, name: str, help_text: str) -> None:
    @parent.command(name, help=help_text)
    def _cmd() -> None:
        raise click.ClickException(f"'{name}' is not implemented yet")
```

Build the tree exactly (names from PRD §5):

```python
doc = _group(cli, "doc", "Manage documents.")
doc_format = _group(doc, "format", "Manage a document's format variants.")
orphan = _group(cli, "orphan", "Manage uncataloged files.")
topic = _group(cli, "topic", "Manage topic buckets.")
kind = _group(cli, "kind", "Manage kinds.")

for _name, _help in [
    ("add", "Add a new document."), ("list", "Filter and query documents."),
    ("view", "Print one document in full."), ("update", "Change a document's metadata."),
    ("move", "Relocate a document."), ("delete", "Delete a document."),
    ("adopt", "Register an existing in-library folder."),
]:
    _stub(doc, _name, _help)
for _name, _help in [("add", "Add a format variant."), ("delete", "Remove a format variant.")]:
    _stub(doc_format, _name, _help)
for _name, _help in [("list", "List uncataloged files."), ("delete", "Delete an uncataloged file.")]:
    _stub(orphan, _name, _help)
for _name, _help in [("add", "Add a topic."), ("list", "List topics.")]:
    _stub(topic, _name, _help)
for _name, _help in [("add", "Add a kind."), ("list", "List kinds.")]:
    _stub(kind, _name, _help)
for _name, _help in [
    ("init", "Create, adopt, and register a library."),
    ("audit", "Run the library consistency check."),
    ("open", "Open the UI."), ("path", "Print resolved locations."),
    ("regen", "Regenerate index.html from the catalog."),
    ("migrate", "Migrate the catalog to the current schema version."),
]:
    _stub(cli, _name, _help)
```

Note: if any test still fails on click's default behavior (e.g. suggestion text or stream routing differing by click version), adjust the implementation — never the test; the tests encode the standard.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/ -v`
Expected: all pass (smoke + conformance).

- [ ] **Step 6: Commit**

```bash
git add src/shelf/cli/main.py
git commit -m "feat: full noun-verb command tree with conformant stubs"
```

---

### Task 4: Tooling — Justfile, Makefile, lint/typecheck config

**Files:**
- Create: `Justfile`, `Makefile`
- Modify: `pyproject.toml` (ruff config)

**Interfaces:**
- Produces: `just all` (format → lint → typecheck → test) and `make check` (environment preflight) — the phase-gate contract for every later phase.

- [ ] **Step 1: Write the Justfile**

```just
default: all

all: format lint typecheck test

format:
    uv run ruff format .

lint:
    uv run ruff check .

typecheck:
    uv run ty check

test:
    uv run pytest -q
```

- [ ] **Step 2: Write the Makefile**

```make
.PHONY: check
check:
	@command -v uv >/dev/null || { echo "missing: uv"; exit 1; }
	@command -v just >/dev/null || { echo "missing: just"; exit 1; }
	@command -v git >/dev/null || { echo "missing: git"; exit 1; }
	@uv run python -c 'import sys; assert sys.version_info >= (3, 12), "need python >= 3.12"'
	@echo "check: ok"
```

- [ ] **Step 3: Add ruff config to `pyproject.toml`**

```toml
[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 4: Run and fix until green**

Run: `make check` — expected: `check: ok`.
Run: `just all` — expected: format clean, lint clean, ty clean, tests pass. Fix any ruff/ty findings in `src/` (not by loosening config).

- [ ] **Step 5: Commit**

```bash
git add Justfile Makefile pyproject.toml
git commit -m "chore: add just all pipeline and make check preflight"
```

---

### Task 5: Phase gate (fable + haiku)

**Files:**
- Modify: `PROJECTS.md` (P01 statuses)

- [ ] **Step 1: Verification pass** *(sonnet)* — `uv run pytest -q`, `make check`, `just all`, all green in the worktree.
- [ ] **Step 2: Code review** *(fable)* — `/code-review` on the `p01-foundation` diff; PRD §5/§11 spot-check of command names.
- [ ] **Step 3: Flip statuses** *(haiku)* — mark P01 tasks/tests `[x]` in PROJECTS.md, project header `[~]` → `[x]`, note Regression Test Status.
- [ ] **Step 4: Merge + tag** *(fable)* — merge `p01-foundation` into `main` (via `git -C`, no branch switch in the live checkout); tag `v0.1.0`.
- [ ] **Step 5: Push** — branch, `main`, and tag, **only with Steve's confirmation**; remove the worktree.
