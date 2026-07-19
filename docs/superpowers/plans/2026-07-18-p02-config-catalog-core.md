# P02 Config and Catalog Core Implementation Plan (v0.2.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The library's foundation — config resolution, the catalog model with atomic commits and locking, `shelf init`/`--adopt`, `migrate`, taxonomy add/list, `path`, and the read surface (`doc list`/`doc view`) with the standard option tiers.

**Architecture:** A `core/` layer (errors, atomic IO + lock, config, paths, catalog, index, migrations) with no click dependencies except exit-code exceptions, and a `cli/` layer of thin command modules registered onto the P01 group tree. Every mutation goes through one helper (`commit_library`) that enforces the PRD §5 commit-point ordering.

**Tech Stack:** Python ≥3.12 (tomllib), click, tomli-w (TOML writing), pytest; uv/ruff/ty/just from P01.

**Agent assignments (per the SDD orchestration plan):** red steps sonnet · green steps codex (stage, controller commits; report files inside the worktree) · Task 9 gate fable + haiku. Escalation: two failed verify rounds → opus.

## Global Constraints

- Spec of record: SHELF-PRD.md §4 (config/resolution), §5 (single-writer, atomicity, conformance note), §10 (catalog schema), §11.1 (init/adopt), §11.8 (path), §11.9 (topic/kind), §11.11 (doc list/view), §11.14 (migrate), §13 (fingerprint).
- Config file: `${XDG_CONFIG_HOME:-~/.config}/shelf/shelf_config.toml`, kebab-case keys (`library`, `remove-source`, `server-port`, `browser`, `handoff-agent`).
- Resolution precedence, exact: `--library` flag > `SHELF_LIBRARY` env > `library` key in the active config (`--config <path>` replaces discovery) > error with guidance to run `shelf init`.
- Default library location: `${XDG_DATA_HOME:-~/.local/share}/shelf`. Seed kinds, exact list: `reference`, `explainer`, `tutorial`, `playbook`, `spec`, `cheatsheet`.
- `catalog.json`: `schema_version` = 1 current. Newer → every command refuses (exit 1). Older → read commands work; mutating commands refuse with exit 5 pointing at `shelf migrate`.
- Exit codes (§6 by reference): 0 ok · 1 error · 2 usage · 3 not found (`doc view` unknown id) · 5 conflict/precondition (already-configured init without `--force`, duplicate topic/kind, lock timeout, old-schema mutation).
- Atomicity (§5): prepare in temp → `os.replace` of `catalog.json` is the commit point → `index.html` second. Every command that writes library files takes the exclusive advisory lock `.shelf.lock` at the library root.
- Fingerprint (§13), exact format inside the generated index.html:
  `<!-- shelf:fingerprint catalog=sha256:<hex> template=sha256:<hex> version=<semver> -->`
- Option tiers (§11 conventions): global core `-h/--help`, `-V/--version`, `-v/--verbose` (repeatable count), `-q/--quiet`, `--config`, `--debug`, `--no-input`; result output `-o/--output table|json` with `--json` ≡ `-o json` byte-identically; `table` is the human default.
- Implementers never edit files under `tests/` (red suites are the contract). Conventional Commits; every commit ends with the trailer line:
  `Claude-Session: https://claude.ai/code/session_015GDbGv8iA9Zd4iBfY1b2Zx`
- Work happens in the P02 worktree on branch `p02-config-catalog`; never in the live checkout.

## Plan-level decision (recorded for the gate)

The placeholder `index.html.tmpl` moves from P03-T04 into this phase (Task 3): `shelf init` must scaffold `index.html` (§11.1) and `commit_library` must regenerate it on every mutation (§5), so the template cannot wait for P03. At the gate, PROJECTS.md P03-T04 is reworded to "regen already wired via commit_library (P02); extend template only as needed."

## Design: atomicity and locking (reviewed design — implementers follow it verbatim)

- `atomic_write_text(path, text)`: temp file created in `path.parent` (same filesystem), write + flush + fsync, `os.replace(tmp, path)`. On any failure the temp file is deleted and the original is untouched.
- `commit_library(root, catalog)`: validate → serialize catalog → render index → `atomic_write_text(catalog.json)` (**the commit point**) → `atomic_write_text(index.html)`. A crash between the two writes leaves a valid catalog and a stale index — audit-detectable (P05), `regen`-repairable, per §5.
- `library_lock(root, timeout=None)`: `fcntl.flock` exclusive on `<root>/.shelf.lock`; `timeout=None` blocks; a numeric timeout polls `LOCK_NB` every 50 ms and raises `ConflictError` (exit 5) on expiry. Callers: every mutating command wraps load→mutate→commit in one lock hold. Read commands do not lock in P02 (audit's snapshot-under-lock lands in P05).

## File Structure

```
src/shelf/core/errors.py       # exit-code-bearing exceptions (3, 5; schema errors)
src/shelf/core/atomic.py       # atomic_write_text, library_lock
src/shelf/core/config.py       # ShelfConfig, load/save, default path, kebab keys
src/shelf/core/paths.py        # default_library_path, resolve_library (precedence)
src/shelf/core/catalog.py      # Catalog/Document models, load/validate/commit_library
src/shelf/core/index.py        # render_index + fingerprint
src/shelf/core/migrations.py   # MIGRATIONS registry (v0 → v1)
src/shelf/templates/__init__.py, src/shelf/templates/index.html.tmpl
src/shelf/cli/output.py        # output_options decorator, resolve_format
src/shelf/cli/runtime.py       # active_config_path, get_config, get_library (ctx helpers)
src/shelf/cli/library.py       # init (+ --adopt), path, migrate commands
src/shelf/cli/taxonomy.py      # topic/kind add + list
src/shelf/cli/docs.py          # doc list, doc view
src/shelf/cli/main.py          # root options + registration (stubs replaced as commands land)
tests/conftest.py, tests/test_atomic.py, tests/test_config.py, tests/test_catalog.py,
tests/test_option_tiers.py, tests/test_init.py, tests/test_taxonomy.py,
tests/test_doc_read.py, tests/test_migrate.py
```

---

### Task 1: Errors, atomic writes, and the library lock

**Files:**
- Test: `tests/test_atomic.py`
- Create: `src/shelf/core/__init__.py`, `src/shelf/core/errors.py`, `src/shelf/core/atomic.py`

**Interfaces:**
- Produces: `NotFoundError` (exit 3), `ConflictError` (exit 5), `SchemaTooOldError(ConflictError)` — all `click.ClickException` subclasses; `atomic_write_text(path: Path, text: str) -> None`; `library_lock(root: Path, timeout: float | None = None)` context manager; `LOCK_FILENAME = ".shelf.lock"`. Every later task's mutation path consumes these.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_atomic.py`:

```python
"""P02-TS02 — atomic writes and the library lock."""

import os
import threading

import click
import pytest

from shelf.core.atomic import atomic_write_text, library_lock
from shelf.core.errors import ConflictError, NotFoundError


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "catalog.json"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
    assert list(tmp_path.iterdir()) == [target]  # no temp residue


def test_atomic_write_failure_leaves_original(tmp_path, monkeypatch):
    target = tmp_path / "catalog.json"
    target.write_text("original")

    def boom(src, dst):
        raise OSError("injected")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="injected"):
        atomic_write_text(target, "new")
    assert target.read_text() == "original"
    assert list(tmp_path.iterdir()) == [target]  # temp cleaned up


def test_lock_serializes(tmp_path):
    attempted = threading.Event()
    acquired = threading.Event()
    failures: list[BaseException] = []

    def worker():
        try:
            attempted.set()
            with library_lock(tmp_path):
                acquired.set()
        except BaseException as exc:
            failures.append(exc)

    with library_lock(tmp_path):
        t = threading.Thread(target=worker)
        t.start()
        assert attempted.wait(2)
        assert not acquired.wait(0.3)  # still blocked while we hold the lock
    t.join(timeout=2)
    assert not t.is_alive()
    assert acquired.is_set()
    assert not failures


def test_lock_timeout_raises_conflict(tmp_path):
    with library_lock(tmp_path):
        with pytest.raises(ConflictError):
            with library_lock(tmp_path, timeout=0.2):
                pass


def test_exit_codes():
    assert NotFoundError("x").exit_code == 3
    assert ConflictError("x").exit_code == 5
    assert issubclass(NotFoundError, click.ClickException)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_atomic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shelf.core'`.

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_atomic.py
git commit -m "test: add P02-TS02 atomic write and lock tests (red)"
```

- [ ] **Step 4: Implement** *(codex)*

`src/shelf/core/__init__.py`: empty file.

`src/shelf/core/errors.py`:

```python
"""Exit-code-bearing exceptions (cli-design-standard §6, PRD §5 conformance note)."""

import click


class NotFoundError(click.ClickException):
    """The requested resource does not exist — exit 3."""

    exit_code = 3


class ConflictError(click.ClickException):
    """Conflict / precondition failed — exit 5."""

    exit_code = 5


class SchemaTooOldError(ConflictError):
    """Catalog schema older than current; mutation refused until `shelf migrate`."""
```

`src/shelf/core/atomic.py`:

```python
"""Atomic file writes and the library advisory lock (PRD §5)."""

import fcntl
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from shelf.core.errors import ConflictError

LOCK_FILENAME = ".shelf.lock"


def atomic_write_text(path: Path, text: str) -> None:
    """Write via temp file + os.replace; the replace is the commit point."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


@contextmanager
def library_lock(root: Path, timeout: float | None = None) -> Iterator[None]:
    """Exclusive advisory lock at <root>/.shelf.lock; ConflictError on timeout."""
    fh = open(root / LOCK_FILENAME, "a+")
    try:
        if timeout is None:
            fcntl.flock(fh, fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ConflictError(
                            "library is locked by another shelf process"
                        ) from None
                    time.sleep(0.05)
        yield
    finally:
        fh.close()
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_atomic.py -v` — Expected: 5 passed.

- [ ] **Step 6: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/core/
# controller: git commit -m "feat: core errors, atomic writes, library lock"
```

---

### Task 2: Config module and library resolution

**Files:**
- Test: `tests/conftest.py`, `tests/test_config.py`
- Create: `src/shelf/core/config.py`, `src/shelf/core/paths.py`
- Modify: `pyproject.toml` (add `tomli-w`)

**Interfaces:**
- Consumes: `atomic_write_text` from Task 1.
- Produces: `ShelfConfig` dataclass (`library: str | None`, `remove_source: bool = True`, `server_port: int = 8765`, `browser: str = "Google Chrome"`, `handoff_agent: str = "claude"`); `CONFIG_FILENAME = "shelf_config.toml"`; `default_config_path() -> Path`; `load_config(path) -> ShelfConfig`; `save_config(path, cfg) -> None`; `default_library_path() -> Path`; `resolve_library(cli_library: str | None, config: ShelfConfig) -> Path` (raises `click.ClickException` with "run 'shelf init'" guidance when unresolvable); `ENV_LIBRARY = "SHELF_LIBRARY"`.

- [ ] **Step 1: Add the dependency**

Run: `uv add tomli-w` — Expected: resolves, lockfile updated.

- [ ] **Step 2: Write the failing tests** *(sonnet)*

`tests/conftest.py`:

```python
"""Shared fixtures — isolate every test from the real home directory."""

import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.delenv("SHELF_LIBRARY", raising=False)
    return tmp_path
```

`tests/test_config.py`:

```python
"""P02-TS01 (unit level) — config round-trip and resolution precedence."""

import os
from pathlib import Path

import click
import pytest

from shelf.core.config import ShelfConfig, default_config_path, load_config, save_config
from shelf.core.paths import default_library_path, resolve_library


def test_default_paths_follow_xdg(isolated_env):
    assert default_config_path() == Path(os.environ["XDG_CONFIG_HOME"]) / "shelf" / "shelf_config.toml"
    assert default_library_path() == Path(os.environ["XDG_DATA_HOME"]) / "shelf"


def test_config_round_trip_kebab_keys(tmp_path):
    path = tmp_path / "shelf_config.toml"
    save_config(path, ShelfConfig(library="/tmp/lib", server_port=9000))
    text = path.read_text()
    assert 'server-port = 9000' in text
    assert "server_port" not in text  # kebab keys on disk (R3.8)
    cfg = load_config(path)
    assert cfg.library == "/tmp/lib"
    assert cfg.server_port == 9000
    assert cfg.remove_source is True  # defaults survive partial files
    assert cfg.handoff_agent == "claude"


def test_missing_config_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "absent.toml")
    assert cfg == ShelfConfig()


def test_precedence_flag_beats_env_beats_config(monkeypatch):
    cfg = ShelfConfig(library="/from-config")
    monkeypatch.setenv("SHELF_LIBRARY", "/from-env")
    assert resolve_library("/from-flag", cfg) == Path("/from-flag")
    assert resolve_library(None, cfg) == Path("/from-env")
    monkeypatch.delenv("SHELF_LIBRARY")
    assert resolve_library(None, cfg) == Path("/from-config")


def test_unresolvable_library_errors_with_guidance():
    with pytest.raises(click.ClickException, match="shelf init"):
        resolve_library(None, ShelfConfig())
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shelf.core.config'`.

- [ ] **Step 4: Commit the red tests** *(sonnet)*

```bash
git add tests/conftest.py tests/test_config.py pyproject.toml uv.lock
git commit -m "test: add P02-TS01 config and resolution tests (red)"
```

- [ ] **Step 5: Implement** *(codex)*

`src/shelf/core/config.py`:

```python
"""shelf_config.toml read/write (PRD §4) — kebab keys on disk, R3.8 parity."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from shelf.core.atomic import atomic_write_text

CONFIG_FILENAME = "shelf_config.toml"

_KEY_MAP = {
    "library": "library",
    "remove-source": "remove_source",
    "server-port": "server_port",
    "browser": "browser",
    "handoff-agent": "handoff_agent",
}


@dataclass
class ShelfConfig:
    library: str | None = None
    remove_source: bool = True
    server_port: int = 8765
    browser: str = "Google Chrome"
    handoff_agent: str = "claude"


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "shelf" / CONFIG_FILENAME


def load_config(path: Path) -> ShelfConfig:
    if not path.is_file():
        return ShelfConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = ShelfConfig()
    for key, attr in _KEY_MAP.items():
        if key in data:
            setattr(cfg, attr, data[key])
    return cfg


def save_config(path: Path, cfg: ShelfConfig) -> None:
    data = {
        key: getattr(cfg, attr)
        for key, attr in _KEY_MAP.items()
        if getattr(cfg, attr) is not None
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, tomli_w.dumps(data))
```

`src/shelf/core/paths.py`:

```python
"""Library location resolution — the PRD §4 precedence chain."""

import os
from pathlib import Path

import click

from shelf.core.config import ShelfConfig

ENV_LIBRARY = "SHELF_LIBRARY"


def default_library_path() -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "shelf"


def resolve_library(cli_library: str | None, config: ShelfConfig) -> Path:
    if cli_library:
        return Path(cli_library)
    env = os.environ.get(ENV_LIBRARY)
    if env:
        return Path(env)
    if config.library:
        return Path(config.library)
    raise click.ClickException("no library configured — run 'shelf init' to create one")
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run pytest tests/test_config.py tests/test_atomic.py -v` — Expected: all pass.

- [ ] **Step 7: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/core/config.py src/shelf/core/paths.py
# controller: git commit -m "feat: config module and library resolution chain"
```

---

### Task 3: Catalog model, index rendering, commit_library

**Files:**
- Test: `tests/test_catalog.py`
- Create: `src/shelf/core/catalog.py`, `src/shelf/core/index.py`, `src/shelf/templates/__init__.py`, `src/shelf/templates/index.html.tmpl`

**Interfaces:**
- Consumes: `atomic_write_text`, `library_lock`, errors from Task 1.
- Produces: `CURRENT_SCHEMA_VERSION = 1`, `CATALOG_FILENAME = "catalog.json"`, `SEED_KINDS` (the six); dataclasses `FileVariant(format, path, source=None)`, `RepoRef(name, url=None, subject=None)`, `Document(id, title, description, kind, tags, category=None, repo=None, files, primary=None, added=None, doc_date=None, source=None)`, `Catalog(schema_version=1, topics, kinds, documents)` with `Catalog.from_dict(raw)`, `catalog.to_dict()`, `catalog.validate()`; `dumps_catalog(catalog) -> str`; `load_catalog(root, *, for_write=False) -> Catalog`; `commit_library(root, catalog) -> None` (validate → catalog write = commit point → index write); `render_index(catalog_text: str) -> str` embedding the fingerprint. Tasks 5–8 mutate only through `commit_library`.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_catalog.py`:

```python
"""Catalog model: round-trip, validation, schema gates, atomic commit, fingerprint."""

import json
import re
from pathlib import Path

import click
import pytest

from shelf.core.catalog import (
    CATALOG_FILENAME,
    SEED_KINDS,
    Catalog,
    Document,
    FileVariant,
    RepoRef,
    commit_library,
    dumps_catalog,
    load_catalog,
)
from shelf.core.errors import SchemaTooOldError


def _doc(**over):
    base = dict(
        id="2026-01-01-a", title="A", description="d", kind="spec",
        tags=["t"], category="dev-tooling",
        files=[FileVariant(format="md", path="docs/topics/dev-tooling/2026-01-01-a/2026-01-01-a.md")],
        primary="md", added="2026-01-01",
    )
    base.update(over)
    return Document(**base)


def _catalog(**over):
    base = dict(topics=["dev-tooling"], kinds=list(SEED_KINDS), documents=[_doc()])
    base.update(over)
    return Catalog(**base)


def test_round_trip(tmp_path):
    cat = _catalog()
    commit_library(tmp_path, cat)
    loaded = load_catalog(tmp_path)
    assert loaded.schema_version == 1
    assert loaded.topics == ["dev-tooling"]
    assert loaded.documents[0].id == "2026-01-01-a"
    assert loaded.documents[0].files[0].format == "md"


def test_serialized_shape(tmp_path):
    commit_library(tmp_path, _catalog())
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    assert list(raw)[0] == "schema_version"
    doc = raw["documents"][0]
    assert "repo" not in doc  # topical entry omits repo (§10)
    assert doc["category"] == "dev-tooling"


def test_repo_anchored_omits_category(tmp_path):
    doc = _doc(category=None, repo=RepoRef(name="flox", url="https://x", subject="cli"))
    commit_library(tmp_path, _catalog(documents=[doc]))
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    entry = raw["documents"][0]
    assert "category" not in entry
    assert entry["repo"]["name"] == "flox"


def test_validate_rejects_unknown_kind(tmp_path):
    with pytest.raises(click.ClickException, match="kind"):
        commit_library(tmp_path, _catalog(documents=[_doc(kind="nope")]))


def test_validate_rejects_unknown_category(tmp_path):
    with pytest.raises(click.ClickException, match="topic"):
        commit_library(tmp_path, _catalog(documents=[_doc(category="nope")]))


def test_validate_requires_exactly_one_anchor(tmp_path):
    both = _doc(repo=RepoRef(name="x"))
    with pytest.raises(click.ClickException, match="anchor"):
        commit_library(tmp_path, _catalog(documents=[both]))


def test_newer_schema_refused(tmp_path):
    commit_library(tmp_path, _catalog())
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    raw["schema_version"] = 99
    (tmp_path / CATALOG_FILENAME).write_text(json.dumps(raw))
    with pytest.raises(click.ClickException, match="newer"):
        load_catalog(tmp_path)


def test_older_schema_read_ok_write_refused(tmp_path):
    commit_library(tmp_path, _catalog())
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    del raw["schema_version"]  # pre-versioned catalog == v0
    (tmp_path / CATALOG_FILENAME).write_text(json.dumps(raw))
    assert load_catalog(tmp_path).documents  # read path works
    with pytest.raises(SchemaTooOldError, match="migrate"):
        load_catalog(tmp_path, for_write=True)


def test_commit_writes_index_with_fingerprint(tmp_path):
    commit_library(tmp_path, _catalog())
    html = (tmp_path / "index.html").read_text()
    m = re.search(
        r"<!-- shelf:fingerprint catalog=sha256:([0-9a-f]{64}) "
        r"template=sha256:([0-9a-f]{64}) version=(\d+\.\d+\.\d+) -->",
        html,
    )
    assert m, html


def test_commit_point_ordering(tmp_path, monkeypatch):
    """A failure writing the index leaves a valid, current catalog (stale index)."""
    commit_library(tmp_path, _catalog())
    import shelf.core.catalog as cat_mod

    real = cat_mod.atomic_write_text
    def fail_on_index(path, text):
        if path.name == "index.html":
            raise OSError("injected index failure")
        real(path, text)

    monkeypatch.setattr(cat_mod, "atomic_write_text", fail_on_index)
    newer = _catalog(topics=["dev-tooling", "extra"])
    with pytest.raises(OSError):
        commit_library(tmp_path, newer)
    assert "extra" in load_catalog(tmp_path).topics  # catalog committed first
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_catalog.py -v` — Expected: FAIL, `No module named 'shelf.core.catalog'`.

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_catalog.py
git commit -m "test: add catalog model, schema-gate, and fingerprint tests (red)"
```

- [ ] **Step 4: Implement** *(codex)*

`src/shelf/templates/__init__.py`: empty file.

`src/shelf/templates/index.html.tmpl`:

```html
<!doctype html>
<!-- $fingerprint -->
<meta charset="utf-8">
<title>shelf</title>
<p>shelf library — the full UI arrives in P06. Documents cataloged: $doc_count.</p>
```

`src/shelf/core/index.py`:

```python
"""index.html generation from the packaged template, with fingerprint (PRD §13)."""

import hashlib
import json
from importlib.metadata import version
from importlib.resources import files
from string import Template


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_index(catalog_text: str) -> str:
    template_text = (
        files("shelf.templates").joinpath("index.html.tmpl").read_text(encoding="utf-8")
    )
    fingerprint = (
        f"shelf:fingerprint catalog=sha256:{_sha256(catalog_text)} "
        f"template=sha256:{_sha256(template_text)} version={version('shelf')}"
    )
    doc_count = len(json.loads(catalog_text).get("documents", []))
    return Template(template_text).substitute(fingerprint=fingerprint, doc_count=doc_count)
```

`src/shelf/core/catalog.py`:

```python
"""catalog.json model — the single source of truth (PRD §10), mutated only via commit_library (§5)."""

import json
from dataclasses import dataclass, field
from pathlib import Path

import click

from shelf.core.atomic import atomic_write_text
from shelf.core.errors import SchemaTooOldError
from shelf.core.index import render_index

CURRENT_SCHEMA_VERSION = 1
CATALOG_FILENAME = "catalog.json"
SEED_KINDS = ["reference", "explainer", "tutorial", "playbook", "spec", "cheatsheet"]


@dataclass
class FileVariant:
    format: str
    path: str
    source: str | None = None


@dataclass
class RepoRef:
    name: str
    url: str | None = None
    subject: str | None = None


@dataclass
class Document:
    id: str
    title: str
    description: str
    kind: str
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    repo: RepoRef | None = None
    files: list[FileVariant] = field(default_factory=list)
    primary: str | None = None
    added: str | None = None
    doc_date: str | None = None
    source: str | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "id": self.id, "title": self.title, "description": self.description,
            "kind": self.kind, "tags": self.tags,
        }
        if self.repo is not None:
            out["repo"] = {k: v for k, v in vars(self.repo).items() if v is not None}
        else:
            out["category"] = self.category
        out["files"] = [
            {k: v for k, v in vars(f).items() if v is not None} for f in self.files
        ]
        out.update(primary=self.primary, added=self.added,
                   doc_date=self.doc_date, source=self.source)
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> "Document":
        repo = RepoRef(**raw["repo"]) if raw.get("repo") else None
        return cls(
            id=raw["id"], title=raw["title"], description=raw["description"],
            kind=raw["kind"], tags=list(raw.get("tags", [])),
            category=raw.get("category"), repo=repo,
            files=[FileVariant(**f) for f in raw.get("files", [])],
            primary=raw.get("primary"), added=raw.get("added"),
            doc_date=raw.get("doc_date"), source=raw.get("source"),
        )


@dataclass
class Catalog:
    schema_version: int = CURRENT_SCHEMA_VERSION
    topics: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "topics": self.topics,
            "kinds": self.kinds,
            "documents": [d.to_dict() for d in self.documents],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Catalog":
        return cls(
            schema_version=raw.get("schema_version", 0),
            topics=list(raw.get("topics", [])),
            kinds=list(raw.get("kinds", [])),
            documents=[Document.from_dict(d) for d in raw.get("documents", [])],
        )

    def validate(self) -> None:
        for doc in self.documents:
            if (doc.repo is None) == (doc.category is None):
                raise click.ClickException(
                    f"document '{doc.id}' must have exactly one anchor (repo or category)"
                )
            if doc.kind not in self.kinds:
                raise click.ClickException(
                    f"document '{doc.id}' has kind '{doc.kind}' not in the kind list"
                )
            if doc.category is not None and doc.category not in self.topics:
                raise click.ClickException(
                    f"document '{doc.id}' has category '{doc.category}' not in the topic list"
                )


def dumps_catalog(catalog: Catalog) -> str:
    return json.dumps(catalog.to_dict(), indent=2, ensure_ascii=False) + "\n"


def load_catalog(root: Path, *, for_write: bool = False) -> Catalog:
    raw = json.loads((root / CATALOG_FILENAME).read_text(encoding="utf-8"))
    found = raw.get("schema_version", 0)
    if found > CURRENT_SCHEMA_VERSION:
        raise click.ClickException(
            f"catalog schema_version {found} is newer than this shelf understands — upgrade shelf"
        )
    if for_write and found < CURRENT_SCHEMA_VERSION:
        raise SchemaTooOldError(
            f"catalog schema_version {found} is older than current — run 'shelf migrate' first"
        )
    return Catalog.from_dict(raw)


def commit_library(root: Path, catalog: Catalog) -> None:
    """Validate, then write catalog.json (the commit point), then index.html (§5)."""
    catalog.validate()
    catalog.schema_version = CURRENT_SCHEMA_VERSION
    catalog_text = dumps_catalog(catalog)
    index_text = render_index(catalog_text)
    atomic_write_text(root / CATALOG_FILENAME, catalog_text)
    atomic_write_text(root / "index.html", index_text)
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_catalog.py -v` — Expected: 10 passed.

- [ ] **Step 6: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/core/catalog.py src/shelf/core/index.py src/shelf/templates/
# controller: git commit -m "feat: catalog model with commit-point ordering and fingerprinted index"
```

---

### Task 4: Standard option tiers, runtime helpers, `shelf path`

**Files:**
- Test: `tests/test_option_tiers.py`
- Create: `src/shelf/cli/output.py`, `src/shelf/cli/runtime.py`, `src/shelf/cli/library.py` (path command only in this task)
- Modify: `src/shelf/cli/main.py` (root options, `-h` alias, register `path`, drop its stub)

**Interfaces:**
- Consumes: config/paths from Task 2.
- Produces: `output_options(fn)` decorator adding `-o/--output table|json` (default table) and `--json` (param name `json_`); `resolve_format(output: str, json_: bool) -> str`; `active_config_path(ctx) -> Path` (`--config` value or `default_config_path()`); `get_config(ctx) -> ShelfConfig`; `get_library(ctx) -> Path` (resolution chain, using the root `--library` value); root group options stored in `ctx.obj` dict under keys `library`, `config`, `verbose`, `quiet`, `debug`, `no_input`. Tasks 5–8 build commands on these helpers only.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_option_tiers.py`:

```python
"""P02-T08 + TS01 (CLI level) — global core options and shelf path."""

from pathlib import Path

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.config import ShelfConfig, default_config_path, save_config


def run(args, env=None):
    return CliRunner().invoke(cli, args, env=env or {})


def test_dash_h_is_help():
    r = run(["-h"])
    assert r.exit_code == 0
    assert "Usage: shelf" in r.output


def test_global_core_flags_accepted():
    r = run(["-vv", "-q", "--debug", "--no-input", "path", "config"])
    assert r.exit_code == 0


def test_path_config_prints_active_config(isolated_env):
    r = run(["path", "config"])
    assert r.exit_code == 0
    assert r.output.strip() == str(default_config_path())


def test_path_config_honors_config_flag(tmp_path):
    custom = tmp_path / "custom.toml"
    r = run(["--config", str(custom), "path", "config"])
    assert r.exit_code == 0
    assert r.output.strip() == str(custom)


def test_path_precedence_flag_env_config(tmp_path):
    lib_flag, lib_env, lib_cfg = tmp_path / "a", tmp_path / "b", tmp_path / "c"
    save_config(default_config_path(), ShelfConfig(library=str(lib_cfg)))
    r = run(["--library", str(lib_flag), "path"], env={"SHELF_LIBRARY": str(lib_env)})
    assert r.output.strip() == str(lib_flag)
    r = run(["path"], env={"SHELF_LIBRARY": str(lib_env)})
    assert r.output.strip() == str(lib_env)
    r = run(["path"])
    assert r.output.strip() == str(lib_cfg)


def test_path_unconfigured_errors_with_guidance(isolated_env):
    r = run(["path"])
    assert r.exit_code == 1
    assert "shelf init" in r.output


def test_path_index(tmp_path):
    save_config(default_config_path(), ShelfConfig(library=str(tmp_path / "lib")))
    r = run(["path", "index"])
    assert r.output.strip() == str(tmp_path / "lib" / "index.html")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_option_tiers.py -v`
Expected: FAIL — `-h` unknown option; `path` is a stub raising "not implemented".

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_option_tiers.py
git commit -m "test: add option-tier and shelf path tests (red)"
```

- [ ] **Step 4: Implement** *(codex)*

`src/shelf/cli/output.py`:

```python
"""Result-output option tier: -o/--output with --json shorthand (R4.1/R4.2)."""

import click


def output_options(fn):
    fn = click.option("--json", "json_", is_flag=True, help="Shorthand for -o json.")(fn)
    fn = click.option(
        "-o", "--output",
        type=click.Choice(["table", "json"]), default="table", show_default=True,
        help="Output format.",
    )(fn)
    return fn


def resolve_format(output: str, json_: bool) -> str:
    return "json" if json_ else output
```

`src/shelf/cli/runtime.py`:

```python
"""Per-invocation helpers: active config and resolved library from ctx.obj."""

from pathlib import Path

import click

from shelf.core.config import ShelfConfig, default_config_path, load_config
from shelf.core.paths import resolve_library


def active_config_path(ctx: click.Context) -> Path:
    override = ctx.obj.get("config")
    return Path(override) if override else default_config_path()


def get_config(ctx: click.Context) -> ShelfConfig:
    return load_config(active_config_path(ctx))


def get_library(ctx: click.Context) -> Path:
    return resolve_library(ctx.obj.get("library"), get_config(ctx))
```

`src/shelf/cli/library.py`:

```python
"""Library-level commands: path (this task); init/adopt and migrate follow."""

import click

from shelf.cli.runtime import active_config_path, get_library


@click.command("path")
@click.argument("which", required=False, type=click.Choice(["config", "index"]))
@click.pass_context
def path_cmd(ctx: click.Context, which: str | None) -> None:
    """Print resolved locations."""
    if which == "config":
        click.echo(active_config_path(ctx))
        return
    root = get_library(ctx)
    click.echo(root / "index.html" if which == "index" else root)
```

`src/shelf/cli/main.py` — modify the root group (replacing the current decorator block and callback):

```python
@click.group(
    "shelf",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(_VERSION, "-V", "--version", prog_name="shelf", message="shelf %(version)s")
@click.option("--library", "library_", type=click.Path(), default=None, help="Library path override.")
@click.option("--config", "config_", type=click.Path(), default=None, help="Config file overriding discovery.")
@click.option("-v", "--verbose", count=True, help="Increase diagnostic detail (repeatable).")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-essential output.")
@click.option("--debug", is_flag=True, help="Maximum diagnostics.")
@click.option("--no-input", is_flag=True, help="Never prompt; fail if input would be required.")
@click.pass_context
def cli(ctx, library_, config_, verbose, quiet, debug, no_input):
    """Shelf — a private documentation library."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        library=library_, config=config_, verbose=verbose,
        quiet=quiet, debug=debug, no_input=no_input,
    )
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)
```

Then, at the bottom of `main.py`: remove `("path", "Print resolved locations.")` from the top-level stub list and register the real command:

```python
from shelf.cli.library import path_cmd

cli.add_command(path_cmd)
```

(Import at top of file per ruff isort rules; the registration line stays at the bottom.)

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_option_tiers.py tests/ -q` — Expected: all pass (including P01 suites).

- [ ] **Step 6: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/cli/
# controller: git commit -m "feat: standard option tiers, runtime helpers, real shelf path"
```

---

### Task 5: `shelf init` and `shelf init --adopt`

**Files:**
- Test: `tests/test_init.py`
- Modify: `src/shelf/cli/library.py` (add `init_cmd`), `src/shelf/cli/main.py` (register, drop `init` stub)

**Interfaces:**
- Consumes: everything above; `commit_library`, `SEED_KINDS`, `library_lock`.
- Produces: `init_cmd` — `shelf init [--library <path>] [--adopt <path>] [--force]`; a scaffolded library (catalog.json seeded, docs/repos, docs/topics, fingerprinted index.html, README.md) and a written `shelf_config.toml`. `validate_library(root) -> None` helper (raises `click.ClickException` naming what's missing) — reused by later phases.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_init.py`:

```python
"""P02-T03/T06 + TS04 (adopt half) — shelf init and init --adopt."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.catalog import SEED_KINDS
from shelf.core.config import default_config_path, load_config
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def test_init_scaffolds_default_library(isolated_env):
    r = run(["init"])
    assert r.exit_code == 0, r.output
    root = default_library_path()
    catalog = json.loads((root / "catalog.json").read_text())
    assert catalog["schema_version"] == 1
    assert catalog["topics"] == []
    assert catalog["kinds"] == SEED_KINDS
    assert catalog["documents"] == []
    assert (root / "docs" / "repos").is_dir()
    assert (root / "docs" / "topics").is_dir()
    assert "shelf:fingerprint" in (root / "index.html").read_text()
    assert (root / "README.md").is_file()
    assert load_config(default_config_path()).library == str(root)


def test_init_explicit_library_flag(tmp_path):
    target = tmp_path / "mylib"
    r = run(["init", "--library", str(target)])
    assert r.exit_code == 0
    assert (target / "catalog.json").is_file()
    assert load_config(default_config_path()).library == str(target)


def test_init_refuses_reinit_without_force(isolated_env):
    assert run(["init"]).exit_code == 0
    r = run(["init"])
    assert r.exit_code == 5  # conflict
    assert "--force" in r.output
    assert run(["init", "--force"]).exit_code == 0


def test_adopt_registers_existing_library(tmp_path, isolated_env):
    clone = tmp_path / "clone"
    assert run(["init", "--library", str(clone)]).exit_code == 0
    # simulate a fresh machine: wipe the config, keep the library
    default_config_path().unlink()
    r = run(["init", "--adopt", str(clone)])
    assert r.exit_code == 0, r.output
    assert load_config(default_config_path()).library == str(clone)


def test_adopt_validates_library_shape(tmp_path):
    bogus = tmp_path / "bogus"
    bogus.mkdir()
    r = run(["init", "--adopt", str(bogus)])
    assert r.exit_code == 1
    assert "catalog.json" in r.output


def test_adopt_and_force_are_mutually_exclusive(tmp_path):
    clone = tmp_path / "x"
    clone.mkdir()
    r = run(["init", "--adopt", str(clone), "--force"])
    assert r.exit_code == 2  # usage error
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_init.py -v` — Expected: FAIL — `init` stub raises "not implemented" (exit 1).

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_init.py
git commit -m "test: add shelf init and adopt tests (red)"
```

- [ ] **Step 4: Implement** *(codex)*

Add to `src/shelf/cli/library.py`:

```python
from pathlib import Path

from shelf.cli.runtime import get_config
from shelf.core.atomic import library_lock
from shelf.core.catalog import CATALOG_FILENAME, SEED_KINDS, Catalog, commit_library, load_catalog
from shelf.core.config import save_config
from shelf.core.errors import ConflictError
from shelf.core.paths import default_library_path

README_TEXT = "# shelf library\n\nManaged by the `shelf` CLI — do not edit catalog.json by hand.\n"


def validate_library(root: Path) -> None:
    if not (root / CATALOG_FILENAME).is_file():
        raise click.ClickException(f"'{root}' has no catalog.json — not a shelf library")
    load_catalog(root)  # parses; refuses a newer schema
    for sub in ("docs/repos", "docs/topics"):
        if not (root / sub).is_dir():
            raise click.ClickException(f"'{root}' is missing {sub}/ — not a shelf library")


@click.command("init")
@click.option("--library", "library_", type=click.Path(), default=None, help="Where to create the library.")
@click.option("--adopt", "adopt_", type=click.Path(), default=None, help="Register an existing library instead of scaffolding.")
@click.option("--force", is_flag=True, help="Re-initialize over an existing configured library.")
@click.pass_context
def init_cmd(ctx: click.Context, library_: str | None, adopt_: str | None, force: bool) -> None:
    """Create, adopt, and register a library."""
    if adopt_ and force:
        raise click.UsageError("--adopt and --force are mutually exclusive")
    cfg_path = active_config_path(ctx)
    cfg = get_config(ctx)

    if adopt_:
        root = Path(adopt_)
        validate_library(root)
        cfg.library = str(root)
        save_config(cfg_path, cfg)
        click.echo(f"adopted library at {root}")
        return

    root = Path(library_ or ctx.obj.get("library") or default_library_path())
    if cfg.library and Path(cfg.library, CATALOG_FILENAME).is_file() and not force:
        raise ConflictError(
            f"a library is already configured at {cfg.library} — pass --force to re-initialize"
        )
    (root / "docs" / "repos").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "topics").mkdir(parents=True, exist_ok=True)
    with library_lock(root):
        commit_library(root, Catalog(kinds=list(SEED_KINDS)))
    if not (root / "README.md").is_file():
        (root / "README.md").write_text(README_TEXT, encoding="utf-8")
    cfg.library = str(root)
    save_config(cfg_path, cfg)
    click.echo(f"initialized library at {root}")
```

In `src/shelf/cli/main.py`: remove `("init", "Create, adopt, and register a library.")` from the top-level stub list; add `from shelf.cli.library import init_cmd, path_cmd` and `cli.add_command(init_cmd)`.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_init.py tests/ -q` — Expected: all pass.

- [ ] **Step 6: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/cli/
# controller: git commit -m "feat: shelf init with scaffold, --force, and --adopt"
```

---

### Task 6: Taxonomy commands — `topic add|list`, `kind add|list`

**Files:**
- Test: `tests/test_taxonomy.py`
- Create: `src/shelf/cli/taxonomy.py`
- Modify: `src/shelf/cli/main.py` (register real commands on the `topic`/`kind` groups, drop those stubs)

**Interfaces:**
- Consumes: `get_library`, `library_lock`, `load_catalog(for_write=True)`, `commit_library`, `ConflictError`, `output_options`/`resolve_format`.
- Produces: `topic_add`, `topic_list`, `kind_add`, `kind_list` commands. Mutation pattern for every later phase: `with library_lock(root): catalog = load_catalog(root, for_write=True); mutate; commit_library(root, catalog)`.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_taxonomy.py`:

```python
"""P02-T04 — topic/kind add and list, with index regeneration on mutation."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def _init():
    assert run(["init"]).exit_code == 0
    return default_library_path()


def test_topic_add_and_list(isolated_env):
    _init()
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    assert run(["topic", "add", "agentic-infra"]).exit_code == 0
    r = run(["topic", "list"])
    assert r.exit_code == 0
    assert r.output.splitlines() == ["agentic-infra", "dev-tooling"]  # sorted


def test_topic_add_duplicate_conflicts(isolated_env):
    _init()
    run(["topic", "add", "x"])
    r = run(["topic", "add", "x"])
    assert r.exit_code == 5
    assert "already exists" in r.output


def test_kind_list_seeded_and_json(isolated_env):
    _init()
    r = run(["kind", "list", "--json"])
    assert r.exit_code == 0
    assert "spec" in json.loads(r.output)
    r2 = run(["kind", "list", "-o", "json"])
    assert r2.output == r.output  # --json ≡ -o json, byte-identical


def test_mutation_regenerates_index(isolated_env):
    root = _init()
    before = (root / "index.html").read_text()
    run(["topic", "add", "fresh-topic"])
    after = (root / "index.html").read_text()
    assert before != after  # fingerprint changed with the catalog


def test_empty_topic_list_exits_zero(isolated_env):
    _init()
    r = run(["topic", "list"])
    assert r.exit_code == 0
    assert r.output == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_taxonomy.py -v` — Expected: FAIL — stubs raise "not implemented".

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_taxonomy.py
git commit -m "test: add taxonomy add/list tests (red)"
```

- [ ] **Step 4: Implement** *(codex)*

`src/shelf/cli/taxonomy.py`:

```python
"""topic/kind add and list (PRD §11.9) — governed growth's explicit steps."""

import json

import click

from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import commit_library, load_catalog
from shelf.core.errors import ConflictError


def _add(ctx: click.Context, list_name: str, name: str) -> None:
    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        items = getattr(catalog, list_name)
        label = list_name[:-1]  # "topics" -> "topic"
        if name in items:
            raise ConflictError(f"{label} '{name}' already exists")
        items.append(name)
        commit_library(root, catalog)
    click.echo(f"added {list_name[:-1]} '{name}'")


def _list(ctx: click.Context, list_name: str, output: str, json_: bool) -> None:
    catalog = load_catalog(get_library(ctx))
    items = sorted(getattr(catalog, list_name))
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps(items, indent=2))
    else:
        for item in items:
            click.echo(item)


@click.command("add")
@click.argument("name")
@click.pass_context
def topic_add(ctx, name):
    """Add a topic bucket."""
    _add(ctx, "topics", name)


@click.command("list")
@output_options
@click.pass_context
def topic_list(ctx, output, json_):
    """List topic buckets."""
    _list(ctx, "topics", output, json_)


@click.command("add")
@click.argument("name")
@click.pass_context
def kind_add(ctx, name):
    """Add a kind."""
    _add(ctx, "kinds", name)


@click.command("list")
@output_options
@click.pass_context
def kind_list(ctx, output, json_):
    """List kinds."""
    _list(ctx, "kinds", output, json_)
```

In `src/shelf/cli/main.py`: delete the `topic`/`kind` stub loops; register instead:

```python
from shelf.cli import taxonomy

topic.add_command(taxonomy.topic_add)
topic.add_command(taxonomy.topic_list)
kind.add_command(taxonomy.kind_add)
kind.add_command(taxonomy.kind_list)
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_taxonomy.py tests/ -q` — Expected: all pass.

- [ ] **Step 6: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/cli/
# controller: git commit -m "feat: topic and kind add/list with locked atomic mutations"
```

---

### Task 7: The read surface — `doc list` and `doc view`

**Files:**
- Test: `tests/test_doc_read.py`
- Create: `src/shelf/cli/docs.py`
- Modify: `src/shelf/cli/main.py` (register on `doc` group, drop `list`/`view` stubs, add `ls` alias)

**Interfaces:**
- Consumes: catalog model, `get_library`, `output_options`, `NotFoundError`.
- Produces: `doc_list` (`--repo --topic --kind --tag* --query --limit --sort-by added|title`, output options; alias `ls` registered via `doc.add_command(doc_list, "ls")` hidden-from-docs is acceptable), `doc_view <id>` (output options; JSON adds `abs_path` per file). Table row format: `id<TAB>title<TAB>kind<TAB>anchor` where anchor is `repo:<name>` or `topic:<category>`.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_doc_read.py`:

```python
"""P02-TS03 — doc list filter/query matrix and doc view output shapes."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.atomic import library_lock
from shelf.core.catalog import Document, FileVariant, RepoRef, commit_library, load_catalog
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def _seed():
    assert run(["init"]).exit_code == 0
    root = default_library_path()
    with library_lock(root):
        cat = load_catalog(root, for_write=True)
        cat.topics = ["dev-tooling", "claude-code"]
        cat.documents = [
            Document(id="2026-01-01-uv-notes", title="UV Notes", description="python packaging",
                     kind="reference", tags=["python", "uv"], category="dev-tooling",
                     files=[FileVariant(format="md", path="docs/topics/dev-tooling/2026-01-01-uv-notes/2026-01-01-uv-notes.md")],
                     primary="md", added="2026-01-01"),
            Document(id="2026-02-01-flox-prd", title="Flox PRD", description="cli extensions",
                     kind="spec", tags=["rust"],
                     repo=RepoRef(name="flox-cli", url="https://github.com/flox/flox", subject="cli-extensions"),
                     files=[FileVariant(format="md", path="docs/repos/flox-cli/2026-02-01-flox-prd/2026-02-01-flox-prd.md")],
                     primary="md", added="2026-02-01"),
            Document(id="2026-03-01-hooks-guide", title="Hooks Guide", description="claude hooks",
                     kind="tutorial", tags=["claude-code"], category="claude-code",
                     files=[FileVariant(format="md", path="docs/topics/claude-code/2026-03-01-hooks-guide/2026-03-01-hooks-guide.md")],
                     primary="md", added="2026-03-01"),
        ]
        commit_library(root, cat)
    return root


def _ids(result):
    return [line.split("\t")[0] for line in result.output.splitlines()]


def test_list_default_sorted_added_desc(isolated_env):
    _seed()
    r = run(["doc", "list"])
    assert r.exit_code == 0
    assert _ids(r) == ["2026-03-01-hooks-guide", "2026-02-01-flox-prd", "2026-01-01-uv-notes"]


def test_filters_and_together(isolated_env):
    _seed()
    r = run(["doc", "list", "--kind", "reference", "--tag", "python"])
    assert _ids(r) == ["2026-01-01-uv-notes"]
    r = run(["doc", "list", "--kind", "reference", "--tag", "rust"])
    assert r.exit_code == 0 and r.output == ""  # empty result is success


def test_query_matches_id_title_description_tags_subject(isolated_env):
    _seed()
    for q in ("uv-notes", "Flox", "packaging", "claude-code", "cli-extensions"):
        assert run(["doc", "list", "--query", q]).output != "", q


def test_repo_and_topic_filters(isolated_env):
    _seed()
    assert _ids(run(["doc", "list", "--repo", "flox-cli"])) == ["2026-02-01-flox-prd"]
    assert _ids(run(["doc", "list", "--topic", "dev-tooling"])) == ["2026-01-01-uv-notes"]


def test_limit_and_sort_by_title(isolated_env):
    _seed()
    r = run(["doc", "list", "--sort-by", "title", "--limit", "2"])
    assert _ids(r) == ["2026-02-01-flox-prd", "2026-03-01-hooks-guide"]  # Flox, Hooks


def test_list_json_equals_o_json(isolated_env):
    _seed()
    a = run(["doc", "list", "--json"])
    b = run(["doc", "list", "-o", "json"])
    assert a.output == b.output
    docs = json.loads(a.output)
    assert {d["id"] for d in docs} == {
        "2026-01-01-uv-notes", "2026-02-01-flox-prd", "2026-03-01-hooks-guide"
    }


def test_view_json_includes_abs_paths(isolated_env):
    root = _seed()
    r = run(["doc", "view", "2026-02-01-flox-prd", "--json"])
    data = json.loads(r.output)
    assert data["repo"]["subject"] == "cli-extensions"
    assert data["files"][0]["abs_path"] == str(
        root / "docs/repos/flox-cli/2026-02-01-flox-prd/2026-02-01-flox-prd.md"
    )


def test_view_unknown_id_exits_three(isolated_env):
    _seed()
    r = run(["doc", "view", "nope"])
    assert r.exit_code == 3
    assert "not found" in r.output


def test_ls_alias(isolated_env):
    _seed()
    assert run(["doc", "ls"]).output == run(["doc", "list"]).output
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_doc_read.py -v` — Expected: FAIL — stubs.

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_doc_read.py
git commit -m "test: add doc list/view read-surface tests (red)"
```

- [ ] **Step 4: Implement** *(codex)*

`src/shelf/cli/docs.py`:

```python
"""The read surface: doc list and doc view (PRD §11.11)."""

import json

import click

from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import get_library
from shelf.core.catalog import Document, load_catalog
from shelf.core.errors import NotFoundError


def _anchor(doc: Document) -> str:
    return f"repo:{doc.repo.name}" if doc.repo else f"topic:{doc.category}"


def _matches(doc: Document, query: str) -> bool:
    q = query.lower()
    hay = [doc.id, doc.title, doc.description, *doc.tags]
    if doc.repo and doc.repo.subject:
        hay.append(doc.repo.subject)
    return any(q in h.lower() for h in hay)


@click.command("list")
@click.option("--repo", "repo_", default=None, help="Only documents anchored to this repo.")
@click.option("--topic", "topic_", default=None, help="Only documents in this topic.")
@click.option("--kind", "kind_", default=None, help="Only documents of this kind.")
@click.option("--tag", "tags_", multiple=True, help="Require this tag (repeatable, AND).")
@click.option("--query", default=None, help="Substring match over id/title/description/tags/subject.")
@click.option("--limit", type=int, default=None, help="Cap the number of results.")
@click.option("--sort-by", type=click.Choice(["added", "title"]), default="added", show_default=True)
@output_options
@click.pass_context
def doc_list(ctx, repo_, topic_, kind_, tags_, query, limit, sort_by, output, json_):
    """Filter and query documents."""
    docs = load_catalog(get_library(ctx)).documents
    if repo_:
        docs = [d for d in docs if d.repo and d.repo.name == repo_]
    if topic_:
        docs = [d for d in docs if d.category == topic_]
    if kind_:
        docs = [d for d in docs if d.kind == kind_]
    for tag in tags_:
        docs = [d for d in docs if tag in d.tags]
    if query:
        docs = [d for d in docs if _matches(d, query)]
    if sort_by == "title":
        docs = sorted(docs, key=lambda d: d.title.lower())
    else:
        docs = sorted(docs, key=lambda d: d.added or "", reverse=True)
    if limit is not None:
        docs = docs[:limit]
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps([d.to_dict() for d in docs], indent=2, ensure_ascii=False))
    else:
        for d in docs:
            click.echo(f"{d.id}\t{d.title}\t{d.kind}\t{_anchor(d)}")


@click.command("view")
@click.argument("doc_id")
@output_options
@click.pass_context
def doc_view(ctx, doc_id, output, json_):
    """Print one document in full."""
    root = get_library(ctx)
    catalog = load_catalog(root)
    doc = next((d for d in catalog.documents if d.id == doc_id), None)
    if doc is None:
        raise NotFoundError(
            f"document '{doc_id}' not found — try 'shelf doc list --query {doc_id}'"
        )
    data = doc.to_dict()
    for entry in data["files"]:
        entry["abs_path"] = str(root / entry["path"])
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        for key, value in data.items():
            click.echo(f"{key}: {json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value}")


```

In `src/shelf/cli/main.py`: remove `("list", …)` and `("view", …)` from the `doc` stub loop; register:

```python
from shelf.cli import docs as doc_cmds

doc.add_command(doc_cmds.doc_list)
doc.add_command(doc_cmds.doc_list, "ls")
doc.add_command(doc_cmds.doc_view)
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/test_doc_read.py tests/ -q` — Expected: all pass.
Note: `tests/test_conformance.py` asserts `doc list --help` and `doc view --help` still exit 0 — they do, as real commands.

- [ ] **Step 6: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/cli/
# controller: git commit -m "feat: doc list and doc view read surface with output tiers"
```

---

### Task 8: `shelf migrate` and old-schema refusal

**Files:**
- Test: `tests/test_migrate.py`
- Create: `src/shelf/core/migrations.py`
- Modify: `src/shelf/cli/library.py` (add `migrate_cmd`), `src/shelf/cli/main.py` (register, drop stub)

**Interfaces:**
- Consumes: catalog load/commit, lock.
- Produces: `MIGRATIONS: dict[int, Callable[[dict], dict]]` (`{0: _v0_add_schema_version}`); `migrate_cmd` — `shelf migrate [--dry-run] [--json]`. The refusal wiring already exists (`load_catalog(for_write=True)` raises `SchemaTooOldError`); this task proves it end-to-end.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_migrate.py`:

```python
"""P02-T07 + TS04 (migrate half) — schema migration and refusal rules."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args):
    return CliRunner().invoke(cli, args)


def _downgrade_to_v0():
    root = default_library_path()
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    del raw["schema_version"]
    path.write_text(json.dumps(raw))
    return root


def test_migrate_noop_when_current(isolated_env):
    run(["init"])
    r = run(["migrate"])
    assert r.exit_code == 0
    assert "already" in r.output


def test_old_schema_blocks_mutation_until_migrate(isolated_env):
    run(["init"])
    _downgrade_to_v0()
    r = run(["topic", "add", "x"])
    assert r.exit_code == 5
    assert "migrate" in r.output
    assert run(["doc", "list"]).exit_code == 0  # read path stays compatible
    assert run(["migrate"]).exit_code == 0
    assert run(["topic", "add", "x"]).exit_code == 0


def test_migrate_sets_current_version_and_regenerates_index(isolated_env):
    run(["init"])
    root = _downgrade_to_v0()
    before = (root / "index.html").read_text()
    r = run(["migrate"])
    assert r.exit_code == 0
    raw = json.loads((root / "catalog.json").read_text())
    assert raw["schema_version"] == 1
    assert (root / "index.html").read_text() != before


def test_migrate_dry_run_changes_nothing(isolated_env):
    run(["init"])
    root = _downgrade_to_v0()
    r = run(["migrate", "--dry-run"])
    assert r.exit_code == 0
    assert "0" in r.output and "1" in r.output  # reports from -> to
    assert "schema_version" not in json.loads((root / "catalog.json").read_text())
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_migrate.py -v` — Expected: FAIL — `migrate` stub.

- [ ] **Step 3: Commit the red tests** *(sonnet)*

```bash
git add tests/test_migrate.py
git commit -m "test: add migrate and schema-refusal tests (red)"
```

- [ ] **Step 4: Implement** *(codex)*

`src/shelf/core/migrations.py`:

```python
"""Catalog schema migrations — one forward step per source version."""

from collections.abc import Callable


def _v0_add_schema_version(raw: dict) -> dict:
    raw["schema_version"] = 1
    return raw


MIGRATIONS: dict[int, Callable[[dict], dict]] = {0: _v0_add_schema_version}
```

Add to `src/shelf/cli/library.py`:

```python
import json

from shelf.core.catalog import CURRENT_SCHEMA_VERSION, Catalog, dumps_catalog
from shelf.core.migrations import MIGRATIONS


@click.command("migrate")
@click.option("--dry-run", is_flag=True, help="Report the migration without applying it.")
@click.option("--json", "json_", is_flag=True, help="Machine-readable report.")
@click.pass_context
def migrate_cmd(ctx: click.Context, dry_run: bool, json_: bool) -> None:
    """Migrate the catalog to the current schema version."""
    root = get_library(ctx)
    with library_lock(root):
        raw = json.loads((root / CATALOG_FILENAME).read_text(encoding="utf-8"))
        found = raw.get("schema_version", 0)
        if found > CURRENT_SCHEMA_VERSION:
            raise click.ClickException(
                f"catalog schema_version {found} is newer than this shelf understands — upgrade shelf"
            )
        report = {"from": found, "to": CURRENT_SCHEMA_VERSION}
        if found == CURRENT_SCHEMA_VERSION:
            click.echo(json.dumps(report) if json_ else "catalog is already at the current schema version")
            return
        if dry_run:
            click.echo(json.dumps(report) if json_
                       else f"would migrate schema_version {found} -> {CURRENT_SCHEMA_VERSION}")
            return
        for step in range(found, CURRENT_SCHEMA_VERSION):
            raw = MIGRATIONS[step](raw)
        commit_library(root, Catalog.from_dict(raw))
    click.echo(json.dumps(report) if json_
               else f"migrated schema_version {found} -> {CURRENT_SCHEMA_VERSION}")
```

In `src/shelf/cli/main.py`: remove the `migrate` stub entry; add `migrate_cmd` to the `library` import and `cli.add_command(migrate_cmd)`.

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest tests/ -q` — Expected: full suite passes.

- [ ] **Step 6: Stage** *(codex stages; controller commits)*

```bash
git add src/shelf/cli/ src/shelf/core/migrations.py
# controller: git commit -m "feat: shelf migrate with forward migrations and refusal wiring"
```

---

### Task 9: Phase gate (fable + haiku)

**Files:**
- Modify: `PROJECTS.md` (P02 statuses + the P03-T04 rewording from the plan-level decision), `pyproject.toml` (version → `0.2.0`)

- [ ] **Step 1: Verification pass** *(sonnet)* — full `uv run pytest -q`, `make check`, `just all`; also `uv run shelf -V` → `shelf 0.2.0` after the version bump.
- [ ] **Step 2: Whole-branch review** *(fable)* — review package over the branch; spot-check §4/§5/§10/§11 bindings; triage deferred Minors from the ledger.
- [ ] **Step 3: Version bump** — set `version = "0.2.0"` in `pyproject.toml`, `uv sync`, commit `chore: bump version to 0.2.0`.
- [ ] **Step 4: Status flips** *(haiku)* — P02 items `[x]` + Regression Test Status; reword P03-T04 per the plan-level decision; commit `docs(projects): mark P02 complete at v0.2.0`.
- [ ] **Step 5: Merge + tag** *(fable)* — merge `p02-config-catalog` into `main` via `git -C` (no branch switch in the live checkout); tag `v0.2.0`.
- [ ] **Step 6: Push** — `main` + tag to `smorinlabs/shelf`, **only with Steve's confirmation**; remove the worktree.
