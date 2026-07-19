# P05 Audit and Regen Implementation Plan (v0.5.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `shelf audit` — the five §11.6 checks with per-finding remediations, `--json`, `--pre-commit`, and snapshot-under-lock — plus `shelf regen` (§11.12) and full fingerprint verification (catalog + template hashes).

**Architecture:** A pure `core/audit.py` engine returning `Finding` records (check number, stable code, detail, remediation) computed from a lock-snapshot of `catalog.json` + `index.html`; raw-JSON-level entry inspection so malformed catalogs yield findings, never crashes. `regen` writes only `index.html`, rendered from the on-disk catalog bytes verbatim.

**Tech Stack:** As P04; no new dependencies.

**Agent assignments:** red sonnet · green codex (stage or stop; controller commits; cancel collected background jobs) · Task 3 gate fable + haiku (`just all` run unpiped).

## Global Constraints

- Spec of record: SHELF-PRD.md §11.6 (checks + remediation matrix), §11.12 (`regen`), §13 (fingerprint), §5 (conformance: audit-with-findings exits 1 as a documented predicate — report on stdout, no stderr error object).
- The five checks and their remediations, exactly per §11.6:
  1. orphans → `shelf orphan list` / `shelf doc adopt` / `shelf orphan delete`
  2. dead `files[]` references → `shelf doc format delete <id> <fmt> --force`
  3. malformed/uncategorized entries (missing required fields; unknown kind; unknown category; folder↔anchoring mismatch; `added` ≠ slug date prefix; `schema_version` older than current) → `shelf doc update` / `shelf migrate`
  4. missing/unparseable `shelf_config.toml`, `catalog.json`, `index.html`; fingerprint mismatch (either hash) → `shelf init --adopt` / restore / `shelf regen`
  5. dirty git state for `catalog.json`, `index.html`, `docs/` (only when the library is a git repo; **skipped under `--pre-commit`**) → commit the changes
- Fingerprint comparison covers BOTH hashes: catalog bytes and installed template bytes.
- Audit takes the library lock only long enough to snapshot the two files (TS03: a mid-transaction state is never observed; audit blocks until the mutator releases).
- `regen`: writes only `index.html`; renders from the on-disk catalog text verbatim (never re-serializes); refuses a newer `schema_version`; `--dry-run` writes nothing.
- Exit codes: clean audit 0 · findings 1 (predicate; no stderr error record) · usage 2. Implementers never edit `tests/`; Conventional Commits + trailer:
  `Claude-Session: https://claude.ai/code/session_015GDbGv8iA9Zd4iBfY1b2Zx`
- Worktree branch `p05-audit-regen`; never the live checkout.

## Plan-level decisions (recorded for the gate)

1. **Programmatic fixtures over static ones**: each audit check gets a builder helper that breaks a freshly-inited library in exactly one way. Checked-in fixture files can't work — fingerprints are content-derived and would be permanently stale. (Supersedes the orchestration plan's haiku-fixture note.)
2. **`regen --commit` deferred to P07** with the rest of the cross-cutting `--commit` plumbing (consistent with the P03/P04 deferral).
3. **Audit on a newer `schema_version`** reports a check-3 finding (`schema-newer`, remediation "upgrade shelf") rather than refusing — audit is the diagnostic tool and must not be locked out of the state it diagnoses.
4. **Conformance-suite amendment (Codex review find):** `test_stub_leaf_errors_cleanly` pins `audit` as its stub probe; Task 2's red phase re-points it at `open` (the last remaining stub). P06's plan MUST delete that test when `open` becomes real.

## File Structure

```
src/shelf/core/audit.py       # Finding dataclass + run_audit engine
src/shelf/core/index.py       # + template_text(), parse_fingerprint(), hashes helper (refactor render_index onto them)
src/shelf/cli/audit_cmd.py    # audit command
src/shelf/cli/library.py      # + regen_cmd
tests/test_regen.py, tests/test_audit.py
```

---

### Task 1: Fingerprint helpers and `shelf regen`

**Files:**
- Test: `tests/test_regen.py`
- Modify: `src/shelf/core/index.py` (refactor + helpers), `src/shelf/cli/library.py` (add `regen_cmd`), `src/shelf/cli/main.py` (register, drop `regen` stub)

**Interfaces:**
- Produces: `template_text() -> str`; `parse_fingerprint(html: str) -> tuple[str, str] | None` (catalog-hash, template-hash); `render_index(catalog_text)` unchanged in behavior; `regen_cmd` per §11.12. Task 2's staleness check consumes `parse_fingerprint` + `template_text`.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_regen.py`:

```python
"""P05-TS02 — regen and fingerprint round-trip (§11.12, §13)."""

import hashlib
import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    return default_library_path()


def _hand_edit_catalog(root):
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    raw["topics"].append("hand-added")
    path.write_text(json.dumps(raw, indent=2) + "\n")
    return path.read_text()


def test_parse_fingerprint_round_trip(isolated_env):
    from shelf.core.index import parse_fingerprint, render_index, template_text

    root = _init()
    catalog_text = (root / "catalog.json").read_text()
    parsed = parse_fingerprint((root / "index.html").read_text())
    assert parsed is not None
    cat_hash, tmpl_hash = parsed
    assert cat_hash == hashlib.sha256(catalog_text.encode()).hexdigest()
    assert tmpl_hash == hashlib.sha256(template_text().encode()).hexdigest()
    assert parse_fingerprint(render_index(catalog_text)) == parsed
    assert parse_fingerprint("<html>no fingerprint</html>") is None


def test_regen_refreshes_after_hand_edit(isolated_env):
    from shelf.core.index import parse_fingerprint

    root = _init()
    catalog_text = _hand_edit_catalog(root)
    import hashlib as h

    expected = h.sha256(catalog_text.encode()).hexdigest()
    stale = parse_fingerprint((root / "index.html").read_text())
    assert stale is not None and stale[0] != expected  # stale before regen
    r = run(["regen"])
    assert r.exit_code == 0, r.output
    fresh = parse_fingerprint((root / "index.html").read_text())
    assert fresh is not None and fresh[0] == expected


def test_regen_renders_on_disk_bytes_verbatim(isolated_env):
    """A v0 catalog stays v0 on disk — regen must not re-serialize it."""
    root = _init()
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    del raw["schema_version"]
    path.write_text(json.dumps(raw))
    before = path.read_text()
    assert run(["regen"]).exit_code == 0
    assert path.read_text() == before  # catalog untouched, byte-for-byte


def test_regen_refuses_newer_schema(isolated_env):
    root = _init()
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    raw["schema_version"] = 99
    path.write_text(json.dumps(raw))
    r = run(["regen"])
    assert r.exit_code == 1
    assert "newer" in r.output


def test_regen_dry_run_writes_nothing(isolated_env):
    root = _init()
    _hand_edit_catalog(root)
    before = (root / "index.html").read_text()
    r = run(["regen", "--dry-run"])
    assert r.exit_code == 0
    assert "would regenerate" in r.output
    assert (root / "index.html").read_text() == before
```

- [ ] **Step 2: Verify failure; commit red** *(sonnet)* — `test: add regen and fingerprint tests (red)` (+ trailer); ruff format/check the file first. Expected failures: `parse_fingerprint`/`template_text` don't exist; `regen` is a stub.
- [ ] **Step 3: Implement** *(codex)*

`src/shelf/core/index.py` — full replacement:

```python
"""index.html generation and fingerprinting (PRD §13)."""

import hashlib
import json
import re
from importlib.metadata import version
from importlib.resources import files
from string import Template

_FINGERPRINT_RE = re.compile(
    r"shelf:fingerprint catalog=sha256:([0-9a-f]{64}) "
    r"template=sha256:([0-9a-f]{64}) version=\S+"
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def template_text() -> str:
    return files("shelf.templates").joinpath("index.html.tmpl").read_text(encoding="utf-8")


def parse_fingerprint(html: str) -> tuple[str, str] | None:
    match = _FINGERPRINT_RE.search(html)
    return (match.group(1), match.group(2)) if match else None


def render_index(catalog_text: str) -> str:
    tmpl = template_text()
    fingerprint = (
        f"shelf:fingerprint catalog=sha256:{_sha256(catalog_text)} "
        f"template=sha256:{_sha256(tmpl)} version={version('shelf')}"
    )
    doc_count = len(json.loads(catalog_text).get("documents", []))
    return Template(tmpl).substitute(fingerprint=fingerprint, doc_count=doc_count)
```

Add to `src/shelf/cli/library.py`:

```python
from shelf.core.index import render_index


@click.command("regen")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def regen_cmd(ctx: click.Context, dry_run: bool) -> None:
    """Regenerate index.html from the current catalog and installed template."""
    root = get_library(ctx)
    with library_lock(root):
        catalog_text = (root / CATALOG_FILENAME).read_text(encoding="utf-8")
        raw = json.loads(catalog_text)
        if raw.get("schema_version", 0) > CURRENT_SCHEMA_VERSION:
            raise click.ClickException(
                "catalog schema_version is newer than this shelf understands — upgrade shelf"
            )
        if dry_run:
            click.echo("would regenerate index.html")
            return
        from shelf.core.atomic import atomic_write_text

        atomic_write_text(root / "index.html", render_index(catalog_text))
    click.echo("regenerated index.html")
```

(Imports at top per ruff; `CURRENT_SCHEMA_VERSION` from `shelf.core.catalog`.) In `main.py`: drop the `regen` stub; register `regen_cmd`.

- [ ] **Step 4: Verify** — `uv run pytest tests/ -q` fully green (152); ruff clean; `uv run ty check` clean.
- [ ] **Step 5: Stage** — `feat: shelf regen and fingerprint parsing helpers`.

---

### Task 2: The audit engine and command

**Files:**
- Test: `tests/test_audit.py`
- Create: `src/shelf/core/audit.py`, `src/shelf/cli/audit_cmd.py`
- Modify: `src/shelf/cli/main.py` (register, drop `audit` stub)

**Interfaces:**
- Consumes: `scan_orphans`, `doc_rel_dir` (via raw-dict reimplementation below), `parse_fingerprint`, `template_text`, `library_lock`, `output_options`.
- Produces: `Finding(check: int, code: str, detail: str, remediation: str)` dataclass; `run_audit(root: Path, config_path: Path, *, pre_commit: bool = False) -> list[Finding]`; `audit_cmd` (`--pre-commit`, output options; clean → "library is consistent" exit 0; findings → report exit 1). Stable codes: `orphan`, `dead-reference`, `missing-field`, `unknown-kind`, `unknown-category`, `anchor-mismatch`, `added-slug-mismatch`, `schema-old`, `schema-newer`, `config-missing`, `catalog-unparseable`, `index-missing`, `index-stale`, `git-dirty`.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_audit.py`:

```python
"""P05-TS01 + TS03 — the five audit checks, remediations, and snapshot-under-lock."""

import json
import subprocess
import threading

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = [
    "--kind", "reference", "--title", "UV Notes", "--description", "d",
    "--slug", SLUG,
]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seeded(tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def _raw(root):
    return json.loads((root / "catalog.json").read_text())


def _write_raw(root, raw):
    (root / "catalog.json").write_text(json.dumps(raw, indent=2) + "\n")


def _codes(result):
    return {f["code"] for f in json.loads(result.output)}


def test_clean_library_exits_zero(isolated_env, tmp_path):
    _seeded(tmp_path)
    assert run(["regen"]).exit_code == 0  # hand: seeded lib is consistent already
    r = run(["audit"])
    assert r.exit_code == 0, r.output
    assert "consistent" in r.output


def test_orphan_finding(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    stray = root / "docs" / "topics" / "dev-tooling" / "2026-02-02-stray"
    stray.mkdir(parents=True)
    (stray / "x.md").write_text("x")
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "orphan" in _codes(r)
    table = run(["audit"])
    assert "orphan" in table.output and ("doc adopt" in table.output or "orphan delete" in table.output)


def test_dead_reference_finding(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.md").unlink()
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "dead-reference" in _codes(r)
    assert "format delete" in run(["audit"]).output


def test_malformed_entry_findings(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["documents"][0]["kind"] = "made-up"
    raw["documents"][0]["added"] = "1999-01-01"
    del raw["documents"][0]["description"]
    _write_raw(root, raw)
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    codes = _codes(r)
    assert {"unknown-kind", "added-slug-mismatch", "missing-field"} <= codes


def test_schema_findings(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    del raw["schema_version"]
    _write_raw(root, raw)
    r = run(["audit", "--json"])
    assert "schema-old" in _codes(r)
    assert "migrate" in run(["audit"]).output
    raw = _raw(root)
    raw["schema_version"] = 99
    _write_raw(root, raw)
    assert "schema-newer" in _codes(run(["audit", "--json"]))


def test_index_and_config_findings(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    (root / "index.html").unlink()
    r = run(["audit", "--json"])
    assert "index-missing" in _codes(r)
    assert run(["regen"]).exit_code == 0
    raw = _raw(root)
    raw["topics"].append("hand-added")
    _write_raw(root, raw)
    r = run(["audit", "--json"])
    assert "index-stale" in _codes(r)
    assert "regen" in run(["audit"]).output
    from shelf.core.config import default_config_path

    default_config_path().unlink()
    assert "config-missing" in _codes(run(["audit", "--json"]))


def test_template_change_makes_index_stale(isolated_env, tmp_path, monkeypatch):
    _seeded(tmp_path)
    import shelf.core.index as index_mod

    monkeypatch.setattr(index_mod, "template_text", lambda: "<html>$fingerprint v2 $doc_count</html>")
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "index-stale" in _codes(r)
    assert run(["regen"]).exit_code == 0
    assert run(["audit"]).exit_code == 0  # fresh under the new template


def _git(root, *args):
    import os

    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", *args], cwd=root, check=True, env=env)


def test_git_dirty_finding_and_pre_commit_skip(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    assert run(["audit"]).exit_code == 0  # committed clean library
    assert run(["topic", "add", "makes-dirty"]).exit_code == 0
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "git-dirty" in _codes(r)
    r = run(["audit", "--pre-commit", "--json"])
    assert r.exit_code == 0, r.output
    assert "git-dirty" not in _codes(r)


def test_audit_blocks_on_lock_no_false_stale(isolated_env, tmp_path):
    """TS03: audit snapshots under the lock; a mid-transaction state is never observed."""
    root = _seeded(tmp_path)
    from shelf.core.atomic import library_lock
    from shelf.core.catalog import Catalog, commit_library, load_catalog

    results = {}
    attempting = threading.Event()
    import shelf.core.audit as audit_mod

    real_lock = audit_mod.library_lock

    def signaling_lock(*args, **kwargs):
        attempting.set()
        return real_lock(*args, **kwargs)

    def run_audit_thread():
        results["audit"] = CliRunner().invoke(cli, ["audit"])

    import unittest.mock

    with unittest.mock.patch.object(audit_mod, "library_lock", signaling_lock), library_lock(root):
        # simulate mid-transaction: catalog advanced, index not yet rewritten
        catalog = load_catalog(root, for_write=True)
        catalog.topics.append("mid-transaction")
        from shelf.core.atomic import atomic_write_text
        from shelf.core.catalog import dumps_catalog

        atomic_write_text(root / "catalog.json", dumps_catalog(catalog))
        t = threading.Thread(target=run_audit_thread)
        t.start()
        assert attempting.wait(2)  # audit has reached its lock acquisition
        t.join(timeout=0.3)
        assert t.is_alive()  # audit is blocked on the lock, not reading torn state
        # finish the transaction before releasing
        from shelf.core.index import render_index

        atomic_write_text(root / "index.html", render_index(dumps_catalog(catalog)))
    t.join(timeout=5)
    assert not t.is_alive()
    assert results["audit"].exit_code == 0, results["audit"].output
```

- [ ] **Step 2: Conformance-suite amendment** *(sonnet, same red commit)* — in `tests/test_conformance.py`, `test_stub_leaf_errors_cleanly` currently probes `audit`; change its probe to `open` (the last remaining stub) with the comment `# open is the last stub; P06 deletes this test when it becomes real`. Keep `audit`/`regen` in the `--help` matrix unchanged.
- [ ] **Step 3: Verify failure; commit red** *(sonnet)* — `test: add audit five-check and lock-snapshot tests (red)` (+ trailer); ruff the files first.
- [ ] **Step 4: Implement** *(codex)*

`src/shelf/core/audit.py`:

```python
"""The audit engine (PRD §11.6) — raw-level inspection, findings never crashes."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import shelf.core.index as index_mod
from shelf.core.atomic import library_lock
from shelf.core.catalog import CURRENT_SCHEMA_VERSION
from shelf.core.index import _sha256, parse_fingerprint


@dataclass
class Finding:
    check: int
    code: str
    detail: str
    remediation: str


REQUIRED_FIELDS = ("id", "title", "description", "kind")


def _doc_dir(doc: dict) -> str | None:
    if isinstance(doc.get("repo"), dict) and doc["repo"].get("name"):
        return f"docs/repos/{doc['repo']['name']}/{doc.get('id')}"
    if doc.get("category"):
        return f"docs/topics/{doc['category']}/{doc.get('id')}"
    return None


def run_audit(root: Path, config_path: Path, *, pre_commit: bool = False) -> list[Finding]:
    findings: list[Finding] = []

    with library_lock(root):
        try:
            catalog_text = (root / "catalog.json").read_text(encoding="utf-8")
        except OSError:
            return [Finding(4, "catalog-unparseable", "catalog.json is missing or unreadable",
                            "restore it from git history or a backup")]
        try:
            index_text = (root / "index.html").read_text(encoding="utf-8")
        except OSError:
            index_text = None

    if not config_path.is_file():
        findings.append(Finding(4, "config-missing", str(config_path),
                                "register the library with 'shelf init --adopt <path>'"))
    try:
        raw = json.loads(catalog_text)
    except json.JSONDecodeError as exc:
        findings.append(Finding(4, "catalog-unparseable", str(exc),
                                "restore catalog.json from git history or a backup"))
        return findings

    schema = raw.get("schema_version", 0)
    if schema > CURRENT_SCHEMA_VERSION:
        findings.append(Finding(3, "schema-newer", f"schema_version {schema}",
                                "upgrade shelf"))
    elif schema < CURRENT_SCHEMA_VERSION:
        findings.append(Finding(3, "schema-old", f"schema_version {schema}",
                                "run 'shelf migrate'"))

    topics = set(raw.get("topics", []))
    kinds = set(raw.get("kinds", []))
    cataloged_dirs: set[str] = set()
    for doc in raw.get("documents", []):
        doc_id = doc.get("id", "<missing id>")
        for field in REQUIRED_FIELDS:
            if not doc.get(field):
                findings.append(Finding(3, "missing-field", f"{doc_id}: {field}",
                                        f"repair with 'shelf doc update {doc_id}'"))
        if doc.get("kind") and doc["kind"] not in kinds:
            findings.append(Finding(3, "unknown-kind", f"{doc_id}: {doc['kind']}",
                                    f"fix with 'shelf doc update {doc_id} --kind <kind>'"))
        has_repo = isinstance(doc.get("repo"), dict)
        if not has_repo and doc.get("category") and doc["category"] not in topics:
            findings.append(Finding(3, "unknown-category", f"{doc_id}: {doc['category']}",
                                    "add the topic or move the document"))
        added = doc.get("added")
        if added and isinstance(doc_id, str) and len(doc_id) >= 10 and doc_id[:10] != added:
            findings.append(Finding(3, "added-slug-mismatch", f"{doc_id}: added={added}",
                                    f"repair with 'shelf doc update {doc_id} --added {doc_id[:10]} --force'"))
        expected_dir = _doc_dir(doc)
        if expected_dir:
            cataloged_dirs.add(expected_dir)
            for variant in doc.get("files", []):
                path = variant.get("path", "")
                if not path.startswith(expected_dir + "/"):
                    findings.append(Finding(3, "anchor-mismatch", f"{doc_id}: {path}",
                                            f"relocate with 'shelf doc move {doc_id}'"))
                if path and not (root / path).is_file():
                    findings.append(Finding(
                        2, "dead-reference", f"{doc_id}: {path}",
                        f"drop with 'shelf doc format delete {doc_id} {variant.get('format', '?')} --force'"))

    docs_dir = root / "docs"
    if docs_dir.is_dir():
        for bucket in ("repos", "topics"):
            base = docs_dir / bucket
            if not base.is_dir():
                continue
            for group in sorted(base.iterdir()):
                if group.is_file():
                    findings.append(Finding(1, "orphan", str(group.relative_to(root)),
                                            "inspect with 'shelf orphan list'; adopt with 'shelf doc adopt' or delete with 'shelf orphan delete'"))
                    continue
                for entry in sorted(group.iterdir()):
                    rel = str(entry.relative_to(root))
                    if rel not in cataloged_dirs:
                        findings.append(Finding(1, "orphan", rel,
                                                "inspect with 'shelf orphan list'; adopt with 'shelf doc adopt' or delete with 'shelf orphan delete'"))

    if index_text is None:
        findings.append(Finding(4, "index-missing", "index.html",
                                "regenerate with 'shelf regen'"))
    else:
        parsed = parse_fingerprint(index_text)
        if parsed is None or parsed != (_sha256(catalog_text), _sha256(index_mod.template_text())):
            findings.append(Finding(4, "index-stale", "fingerprint mismatch",
                                    "regenerate with 'shelf regen'"))

    if not pre_commit and (root / ".git").exists():
        out = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--",
             "catalog.json", "index.html", "docs"],
            capture_output=True, text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            findings.append(Finding(5, "git-dirty", out.stdout.strip().splitlines()[0] + " ...",
                                    "commit the library changes (git add / git commit)"))

    return findings
```

(Codex: ensure ruff/ty clean over the new modules.)

`src/shelf/cli/audit_cmd.py`:

```python
"""shelf audit (PRD §11.6)."""

import json
from dataclasses import asdict

import click

from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import active_config_path, get_library
from shelf.core.audit import run_audit


@click.command("audit")
@click.option("--pre-commit", "pre_commit", is_flag=True,
              help="Skip the dirty-git check (for use as a pre-commit hook).")
@output_options
@click.pass_context
def audit_cmd(ctx, pre_commit, output, json_):
    """Run the library consistency check."""
    root = get_library(ctx)
    findings = run_audit(root, active_config_path(ctx), pre_commit=pre_commit)
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            click.echo("library is consistent")
        for f in findings:
            click.echo(f"check {f.check} [{f.code}]: {f.detail}")
            click.echo(f"  fix: {f.remediation}")
    if findings:
        ctx.exit(1)
```

In `main.py`: drop the `audit` stub; register `audit_cmd`.

- [ ] **Step 5: Verify** — `uv run pytest tests/ -q` fully green (161); ruff + ty clean; `just all` (unpiped) green.
- [ ] **Step 6: Stage** — `feat: shelf audit with five checks, remediations, and lock snapshot`.

---

### Task 3: Phase gate (fable + haiku)

- [ ] **Step 1: Verification** — full suite; `make check`; `just all` run UNPIPED; live smoke: seed → break one thing per check → `audit` table + `--json` → apply two remediations live (`regen`, `orphan delete`) → audit clean; `audit --pre-commit` in a git-inited library.
- [ ] **Step 2: Whole-branch review** *(fable)* — triage carried Minors; verify stable finding codes documented in the command help or report.
- [ ] **Step 3: Version bump** — `0.5.0`, `uv sync`, commit.
- [ ] **Step 4: Status flips** *(haiku)* — P05 `[x]` + Regression line.
- [ ] **Step 5: Merge + tag + push** — `v0.5.0`, push per standing order, remove worktree, zombie sweep.
