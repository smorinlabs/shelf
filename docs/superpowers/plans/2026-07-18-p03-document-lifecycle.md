# P03 Document Lifecycle Implementation Plan (v0.3.0)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Documents enter, change shape, and leave the library: `doc add` (slug derivation, validation order, copy+rename, rollback, source handling), `doc format add/delete`, `doc delete`, `doc adopt`, and `orphan list/delete`.

**Architecture:** Pure helpers in `core/slugs.py` and `core/ingest.py`; three thin command modules (`doc_add.py`, `doc_variants.py`, `doc_delete.py`) that all mutate through the P02 canonical pattern — `library_lock` wrapping load→mutate→`commit_library`. File staging happens before the catalog commit point; staged folders are rolled back on pre-commit failure; post-commit residue degrades to audit-detectable orphans per PRD §5.

**Tech Stack:** As P02 (click, uv, pytest, ruff, ty); no new dependencies.

**Agent assignments:** red sonnet · green codex (stage or stop; controller commits; reports inside worktree; collect long runs via companion `status --wait`) · Task 6 opus (crash-injection) · Task 7 gate fable + haiku.

## Global Constraints

- Spec of record: SHELF-PRD.md §6 (folders), §7 (slugs), §11.2 (`doc add`), §11.3 (`doc format add`), §11.13 (`doc format delete`), §11.10 (`doc delete`), §11.15 (`doc adopt`, `orphan`), §5 (atomicity/lock/conformance).
- Slug: `YYYY-MM-DD-<kebab-title>`, kebab max ~60 chars truncated at a hyphen boundary, `--slug` overrides whole slug, immutable. `added` = the date of the add (today).
- Formats: `.md`→md, `.html`/`.htm`→html, `.pdf`→pdf; unknown → usage error pointing at `--format` (long-only flag). Primary heuristic: md, else html, else pdf, else first.
- `doc add` validation order (§11.2): exactly one anchor → kind exists (never created) → topic exists or `--create-topic` → no duplicate format → slug/folder free. Duplicate slug → ConflictError (5) pointing at `--slug` or `doc format add`.
- Files are **copied, never moved**, renamed `<slug>.<ext>`; source removal (`remove-source` config default; `--remove-source/--no-remove-source` override) runs only after copy, catalog write, index regeneration all succeed.
- Exit codes: usage 2 · not-found 3 · conflict/precondition 5 (duplicate slug/format, last-variant refusal, cataloged-path orphan delete) · generic 1. Non-TTY destructive commands without `--yes` → exit 2 (R8.2).
- Mutations: the canonical locked pattern only; folder deletion (`doc delete`) happens **after** the catalog commit point — post-commit failure leaves an audit-detectable orphan folder, never a broken catalog.
- Implementers never edit `tests/`; Conventional Commits with the session trailer:
  `Claude-Session: https://claude.ai/code/session_015GDbGv8iA9Zd4iBfY1b2Zx`
- Worktree branch `p03-doc-lifecycle`; never the live checkout.

## Plan-level decisions (recorded for the gate)

1. **Handoff deferral:** until P08, `doc add` with missing required flags is a plain click usage error (exit 2). The §11.2 interactive handoff replaces that behavior in P08; `--no-input`'s never-prompt guarantee is trivially satisfied meanwhile.
2. **`--replace` in-place content edge (accepted):** replacing an existing variant overwrites the file before the catalog commit point; a failure between overwrite and commit leaves updated *content* at an unchanged, still-referenced path — consistent state, no rollback needed. Documented, not defended against.
3. **`orphan delete` writes nothing to the catalog/index** (nothing changed); it holds the lock during deletion. Documented deviation from §5's letter, consistent with its intent.
4. **`doc adopt` registers file paths as-is** (no rename) per §11.15's "without copying"; `--repo-url` is optional for adopt (schema allows a URL-less RepoRef).

## File Structure

```
src/shelf/core/slugs.py       # kebab, derive_slug
src/shelf/core/ingest.py      # infer_format, pick_primary, doc_rel_dir, infer_repo_url, scan_orphans
src/shelf/cli/doc_add.py      # doc add
src/shelf/cli/doc_variants.py # doc format add, doc format delete
src/shelf/cli/doc_delete.py   # doc delete, orphan list, orphan delete
src/shelf/cli/doc_adopt.py    # doc adopt
tests/test_slugs.py, tests/test_doc_add.py, tests/test_doc_variants.py,
tests/test_doc_delete.py, tests/test_adopt_orphans.py, tests/test_crash_injection.py
```

---

### Task 1: Slugs and format inference

**Files:**
- Test: `tests/test_slugs.py`
- Create: `src/shelf/core/slugs.py`; extend `src/shelf/core/ingest.py` (new file this task)

**Interfaces:**
- Produces: `kebab(text) -> str` (≤60, hyphen-boundary truncation); `derive_slug(title, added, override=None) -> str`; `infer_format(path, override=None) -> str` (UsageError on unknown); `pick_primary(formats) -> str`; `doc_rel_dir(doc: Document) -> str` (`docs/repos/<name>/<id>` | `docs/topics/<category>/<id>`); `FORMAT_MAP`, `PRIMARY_ORDER`.

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_slugs.py`:

```python
"""P03-TS01 — slug derivation and format inference."""

import click
import pytest

from shelf.core.ingest import doc_rel_dir, infer_format, pick_primary
from shelf.core.slugs import derive_slug, kebab


def test_kebab_basics():
    assert kebab("Flox CLI Extension System — PRD") == "flox-cli-extension-system-prd"
    assert kebab("  Weird__punctuation!! (v2) ") == "weird-punctuation-v2"


def test_kebab_truncates_at_hyphen_boundary():
    k = kebab("word " * 30)
    assert len(k) <= 60
    assert not k.endswith("-")
    assert "-" in k


def test_derive_slug_date_prefix():
    assert derive_slug("My Doc", "2026-07-18") == "2026-07-18-my-doc"


def test_derive_slug_override_wins():
    assert derive_slug("My Doc", "2026-07-18", override="2026-01-01-custom") == "2026-01-01-custom"


def test_infer_format_map():
    assert infer_format("a.md") == "md"
    assert infer_format("b.HTML") == "html"
    assert infer_format("c.htm") == "html"
    assert infer_format("d.pdf") == "pdf"


def test_infer_format_unknown_raises_usage():
    with pytest.raises(click.UsageError, match="--format"):
        infer_format("e.docx")


def test_infer_format_override():
    assert infer_format("weird.txt", override="md") == "md"


def test_pick_primary_heuristic():
    assert pick_primary(["pdf", "md", "html"]) == "md"
    assert pick_primary(["pdf", "html"]) == "html"
    assert pick_primary(["pdf"]) == "pdf"
    assert pick_primary(["docx"]) == "docx"


def test_doc_rel_dir_both_anchors():
    from shelf.core.catalog import Document, RepoRef

    topical = Document(id="2026-01-01-a", title="A", description="d", kind="spec",
                       category="dev-tooling")
    repo = Document(id="2026-01-01-b", title="B", description="d", kind="spec",
                    repo=RepoRef(name="flox"))
    assert doc_rel_dir(topical) == "docs/topics/dev-tooling/2026-01-01-a"
    assert doc_rel_dir(repo) == "docs/repos/flox/2026-01-01-b"
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_slugs.py -v` → ModuleNotFoundError (`shelf.core.slugs`).
- [ ] **Step 3: Commit red** *(sonnet)* — `git add tests/test_slugs.py && git commit -m "test: add P03-TS01 slug and format-inference tests (red)"` (+ trailer).
- [ ] **Step 4: Implement** *(codex)*

`src/shelf/core/slugs.py`:

```python
"""Slug derivation (PRD §7)."""

import re

KEBAB_MAX = 60


def kebab(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > KEBAB_MAX:
        slug = slug[:KEBAB_MAX]
        if "-" in slug:
            slug = slug.rsplit("-", 1)[0]
    return slug


def derive_slug(title: str, added: str, override: str | None = None) -> str:
    if override:
        return override
    return f"{added}-{kebab(title)}"
```

`src/shelf/core/ingest.py`:

```python
"""Document ingestion helpers (PRD §6, §11.2)."""

from pathlib import Path

import click

from shelf.core.catalog import Document

FORMAT_MAP = {".md": "md", ".html": "html", ".htm": "html", ".pdf": "pdf"}
PRIMARY_ORDER = ["md", "html", "pdf"]


def infer_format(path: str | Path, override: str | None = None) -> str:
    if override:
        return override
    suffix = Path(path).suffix.lower()
    if suffix not in FORMAT_MAP:
        raise click.UsageError(f"cannot infer format of '{path}' — pass --format")
    return FORMAT_MAP[suffix]


def pick_primary(formats: list[str]) -> str:
    for fmt in PRIMARY_ORDER:
        if fmt in formats:
            return fmt
    return formats[0]


def doc_rel_dir(doc: Document) -> str:
    if doc.repo is not None:
        return f"docs/repos/{doc.repo.name}/{doc.id}"
    return f"docs/topics/{doc.category}/{doc.id}"
```

- [ ] **Step 5: Verify pass** — `uv run pytest tests/test_slugs.py tests/ -q` → all green (70).
- [ ] **Step 6: Stage** *(codex stages or stops; controller commits)* — `feat: slug derivation and format inference helpers`.

---

### Task 2: `shelf doc add`

**Files:**
- Test: `tests/test_doc_add.py`
- Create: `src/shelf/cli/doc_add.py`; extend `src/shelf/core/ingest.py` (`infer_repo_url`)
- Modify: `src/shelf/cli/main.py` (register, drop `doc add` stub)

**Interfaces:**
- Consumes: Task 1 helpers; P02 `commit_library`/`library_lock`/`load_catalog(for_write=True)`/`get_library`/`get_config`; `ConflictError`.
- Produces: `doc_add` command per §11.2; `infer_repo_url(source: Path) -> str | None` (git remote of the source file's repo, 5s timeout, None on any failure).

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_doc_add.py`:

```python
"""P03-TS02/TS03 + T01 — shelf doc add: validation order, rollback, source handling."""

import datetime
import json
from pathlib import Path

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


def _src(tmp_path, name="uv-notes.md", text="# hi"):
    f = tmp_path / name
    f.write_text(text)
    return f


def _catalog(root):
    return json.loads((root / "catalog.json").read_text())


def test_add_topical_happy_path_removes_source(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    before = datetime.date.today().isoformat()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    after = datetime.date.today().isoformat()
    assert r.exit_code == 0, r.output
    entry = _catalog(root)["documents"][0]
    assert before <= entry["added"] <= after
    slug = entry["id"]
    assert slug == f"{entry['added']}-uv-notes"
    dest = root / "docs" / "topics" / "dev-tooling" / slug / f"{slug}.md"
    assert dest.read_text() == "# hi"
    assert entry["primary"] == "md"
    assert entry["source"] == str(src)
    assert not src.exists()  # remove-source default true


def test_no_remove_source_keeps_original(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source"])
    assert r.exit_code == 0
    assert src.exists()


def test_multi_variant_single_entry(isolated_env, tmp_path):
    root = _init()
    md = _src(tmp_path, "a.md")
    pdf = _src(tmp_path, "a.pdf", "%PDF")
    r = run(["doc", "add", str(md), str(pdf), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert {f["format"] for f in entry["files"]} == {"md", "pdf"}
    assert entry["primary"] == "md"


def test_duplicate_format_usage_error(isolated_env, tmp_path):
    _init()
    a, b = _src(tmp_path, "a.md"), _src(tmp_path, "b.md")
    r = run(["doc", "add", str(a), str(b), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 2


def test_both_or_neither_anchor_usage_error(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    assert run(["doc", "add", str(src), *BASE]).exit_code == 2
    assert run(["doc", "add", str(src), "--topic", "t", "--repo", "r", *BASE]).exit_code == 2


def test_unknown_topic_needs_create_topic(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "fresh", *BASE, "--no-remove-source"])
    assert r.exit_code == 1
    assert "--create-topic" in r.output
    r = run(["doc", "add", str(src), "--topic", "fresh", "--create-topic", *BASE])
    assert r.exit_code == 0
    assert "fresh" in _catalog(root)["topics"]


def test_unknown_kind_never_created(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", "--kind", "novel",
             "--title", "T", "--description", "d"])
    assert r.exit_code == 1
    assert "novel" not in _catalog(root)["kinds"]


def test_slug_collision_conflict(isolated_env, tmp_path):
    _init()
    a = _src(tmp_path, "a.md")
    fixed = ["--slug", "2026-01-01-fixed"]
    assert run(["doc", "add", str(a), "--topic", "dev-tooling", *BASE, *fixed,
                "--no-remove-source"]).exit_code == 0
    b = _src(tmp_path, "b.md")
    r = run(["doc", "add", str(b), "--topic", "dev-tooling", *BASE, *fixed])
    assert r.exit_code == 5
    assert "--slug" in r.output


def test_repo_anchored_layout(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--repo", "flox", "--repo-url", "https://github.com/flox/flox",
             "--subject", "cli", *BASE])
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert entry["repo"]["name"] == "flox"
    assert "category" not in entry
    slug = entry["id"]
    assert (root / "docs" / "repos" / "flox" / slug / f"{slug}.md").is_file()


def test_repo_without_url_or_remote_errors(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--repo", "flox", *BASE])
    assert r.exit_code == 1
    assert "--repo-url" in r.output


def test_tags_and_assets(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    asset = _src(tmp_path, "diagram.pdf", "%PDF")
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE,
             "--tag", "python", "--tag", "uv", "--assets", str(asset)])
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert entry["tags"] == ["python", "uv"]
    slug = entry["id"]
    assert (root / "docs" / "topics" / "dev-tooling" / slug / "diagram.pdf").is_file()


def test_dry_run_changes_nothing(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--dry-run"])
    assert r.exit_code == 0
    assert "would add" in r.output
    assert (root / "catalog.json").read_text() == before
    assert src.exists()


def test_rollback_on_commit_failure(isolated_env, tmp_path, monkeypatch):
    root = _init()
    src = _src(tmp_path)
    import shelf.cli.doc_add as mod

    def boom(*a, **k):
        raise OSError("injected")

    monkeypatch.setattr(mod, "commit_library", boom)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--slug", "2026-01-01-fixed"])
    assert r.exit_code != 0
    assert (root / "catalog.json").read_text() == before
    assert src.exists()  # source never removed on failure
    assert not (root / "docs" / "topics" / "dev-tooling" / "2026-01-01-fixed").exists()  # rolled back
```

- [ ] **Step 2: Run to verify failure** — `doc add` stub: expect exits 2 (unknown options) / 1.
- [ ] **Step 3: Commit red** *(sonnet)* — `test: add P03-TS02/TS03 doc add tests (red)` (+ trailer).
- [ ] **Step 4: Implement** *(codex)*

Append to `src/shelf/core/ingest.py`:

```python
import subprocess


def infer_repo_url(source: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(source.parent), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
    except OSError:
        return None
    url = out.stdout.strip()
    return url if out.returncode == 0 and url else None
```

`src/shelf/cli/doc_add.py`:

```python
"""shelf doc add — ingest a new document (PRD §11.2)."""

import datetime
import shutil
from pathlib import Path

import click

from shelf.cli.runtime import get_config, get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import Document, FileVariant, RepoRef, commit_library, load_catalog
from shelf.core.errors import ConflictError
from shelf.core.ingest import doc_rel_dir, infer_format, infer_repo_url, pick_primary
from shelf.core.slugs import derive_slug


@click.command("add")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--repo", "repo_", default=None, help="Anchor to this repo.")
@click.option("--repo-url", default=None, help="Repo URL (inferred from the source's git remote when possible).")
@click.option("--subject", default=None, help="Within-repo subject label.")
@click.option("--topic", "topic_", default=None, help="Anchor to this topic.")
@click.option("--create-topic", is_flag=True, help="Authorize creating an unknown topic.")
@click.option("--kind", "kind_", required=True, help="Document kind (must exist).")
@click.option("--tag", "tags_", multiple=True, help="Free-form tag (repeatable).")
@click.option("--title", required=True)
@click.option("--description", required=True)
@click.option("--slug", "slug_", default=None, help="Override the derived slug.")
@click.option("--primary", "primary_", default=None, help="Primary format (default heuristic).")
@click.option("--doc-date", default=None)
@click.option("--source", "source_", default=None)
@click.option("--assets", "assets_", multiple=True, type=click.Path(exists=True),
              help="Files or directories copied into the document folder.")
@click.option("--format", "format_", default=None, help="Override format inference (long-only).")
@click.option("--remove-source/--no-remove-source", "remove_source_", default=None)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def doc_add(ctx, files, repo_, repo_url, subject, topic_, create_topic, kind_, tags_,
            title, description, slug_, primary_, doc_date, source_, assets_, format_,
            remove_source_, dry_run):
    """Add a new document."""
    if (repo_ is None) == (topic_ is None):
        raise click.UsageError("exactly one of --repo or --topic is required")
    paths = [Path(f).resolve() for f in files]
    formats = [infer_format(p, format_) for p in paths]
    if len(set(formats)) != len(formats):
        raise click.UsageError("two files of the same format — run 'shelf doc add' once per document")
    if primary_ is not None and primary_ not in formats:
        raise click.UsageError(f"--primary '{primary_}' is not among the added formats")

    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        if kind_ not in catalog.kinds:
            raise click.ClickException(
                f"kind '{kind_}' is not in the kind list — 'shelf doc add' never creates kinds"
            )
        repo_ref = None
        if repo_ is not None:
            url = repo_url or infer_repo_url(paths[0])
            if url is None:
                raise click.ClickException("cannot infer the repo url — pass --repo-url")
            repo_ref = RepoRef(name=repo_, url=url, subject=subject)
        elif topic_ not in catalog.topics:
            if not create_topic:
                raise click.ClickException(
                    f"unknown topic '{topic_}' — pass --create-topic to create it"
                )
            catalog.topics.append(topic_)

        added = datetime.date.today().isoformat()
        slug = derive_slug(title, added, slug_)
        if any(d.id == slug for d in catalog.documents):
            raise ConflictError(
                f"slug '{slug}' already exists — use --slug or 'shelf doc format add'"
            )
        doc = Document(
            id=slug, title=title, description=description, kind=kind_, tags=list(tags_),
            category=None if repo_ref else topic_, repo=repo_ref, files=[],
            primary=primary_ or pick_primary(formats), added=added,
            doc_date=doc_date, source=source_ or str(paths[0]),
        )
        rel_dir = doc_rel_dir(doc)
        dest = root / rel_dir
        if dest.exists():
            raise ConflictError(f"folder '{rel_dir}' already exists — use --slug")
        doc.files = [FileVariant(format=f, path=f"{rel_dir}/{slug}.{f}") for f in formats]

        if dry_run:
            click.echo(f"would add '{slug}' -> {rel_dir} ({', '.join(formats)})")
            return

        dest.mkdir(parents=True)
        try:
            for p, fmt in zip(paths, formats):
                shutil.copy2(p, dest / f"{slug}.{fmt}")
            for a in assets_:
                ap = Path(a)
                if ap.is_dir():
                    shutil.copytree(ap, dest / ap.name)
                else:
                    shutil.copy2(ap, dest / ap.name)
            catalog.documents.append(doc)
            commit_library(root, catalog)
        except BaseException:
            shutil.rmtree(dest, ignore_errors=True)
            raise

    effective_remove = get_config(ctx).remove_source if remove_source_ is None else remove_source_
    if effective_remove:
        for p in paths:
            p.unlink(missing_ok=True)
    click.echo(f"added '{slug}' ({', '.join(formats)}) -> {rel_dir}")
```

In `src/shelf/cli/main.py`: remove `("add", "Add a new document.")` from the `doc` stub loop; `from shelf.cli.doc_add import doc_add` and `doc.add_command(doc_add)`.

- [ ] **Step 5: Verify pass** — `uv run pytest tests/ -q` → all green (~83).
- [ ] **Step 6: Stage** — `feat: shelf doc add with validation order, rollback, and source handling`.

---

### Task 3: `shelf doc format add`

**Files:**
- Test: `tests/test_doc_variants.py` (format-add half)
- Create: `src/shelf/cli/doc_variants.py`
- Modify: `src/shelf/cli/main.py` (register on `doc format`, drop that stub)

**Interfaces:**
- Produces: `format_add` per §11.3; shared helper `find_doc(catalog, doc_id) -> Document` raising `NotFoundError` (exported for Tasks 4–5).

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_doc_variants.py`:

```python
"""P03 — doc format add (§11.3) and doc format delete (§11.13)."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d",
        "--slug", SLUG]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seeded(tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def _entry(root):
    return json.loads((root / "catalog.json").read_text())["documents"][0]


def test_format_add_appends_variant(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "notes.pdf"
    pdf.write_text("%PDF")
    r = run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"])
    assert r.exit_code == 0, r.output
    entry = _entry(root)
    assert {f["format"] for f in entry["files"]} == {"md", "pdf"}
    assert (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.pdf").is_file()
    assert entry["primary"] == "md"  # unchanged
    assert pdf.exists()


def test_format_add_unknown_id_exits_three(isolated_env, tmp_path):
    _seeded(tmp_path)
    pdf = tmp_path / "x.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", "nope", str(pdf)]).exit_code == 3


def test_format_add_existing_format_needs_replace(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    other = tmp_path / "other.md"
    other.write_text("# new content")
    r = run(["doc", "format", "add", SLUG, str(other), "--no-remove-source"])
    assert r.exit_code == 5
    assert "--replace" in r.output
    r = run(["doc", "format", "add", SLUG, str(other), "--replace", "--no-remove-source"])
    assert r.exit_code == 0
    md = root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.md"
    assert md.read_text() == "# new content"
    assert len([f for f in _entry(root)["files"] if f["format"] == "md"]) == 1


def test_format_add_primary_reassignment_validated(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--primary", "docx"]).exit_code == 2
    r = run(["doc", "format", "add", SLUG, str(pdf), "--primary", "pdf", "--no-remove-source"])
    assert r.exit_code == 0
    assert _entry(root)["primary"] == "pdf"


def test_format_delete_removes_variant_and_file(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    r = run(["doc", "format", "delete", SLUG, "pdf"])
    assert r.exit_code == 0, r.output
    assert {f["format"] for f in _entry(root)["files"]} == {"md"}
    assert not (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.pdf").exists()


def test_format_delete_refuses_last_variant(isolated_env, tmp_path):
    _seeded(tmp_path)
    r = run(["doc", "format", "delete", SLUG, "md"])
    assert r.exit_code == 5
    assert "doc delete" in r.output


def test_format_delete_primary_needs_successor(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    r = run(["doc", "format", "delete", SLUG, "md"])  # md is primary
    assert r.exit_code == 2
    assert "--primary" in r.output
    r = run(["doc", "format", "delete", SLUG, "md", "--primary", "pdf"])
    assert r.exit_code == 0
    assert _entry(root)["primary"] == "pdf"


def test_format_delete_force_drops_dead_entry(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.pdf").unlink()  # dead ref
    r = run(["doc", "format", "delete", SLUG, "pdf"])
    assert r.exit_code == 1  # missing file without --force is an error
    r = run(["doc", "format", "delete", SLUG, "pdf", "--force"])
    assert r.exit_code == 0
    assert {f["format"] for f in _entry(root)["files"]} == {"md"}
```

- [ ] **Step 2: Run to verify failure** — format add/delete are stubs.
- [ ] **Step 3: Commit red** *(sonnet)* — `test: add doc format add/delete tests (red)` (+ trailer).
- [ ] **Step 4: Implement format add only** *(codex — format delete is Task 4's green; both live in this file, but Task 3 lands `format_add` + `find_doc` and Task 4 lands `format_delete`; run only the format-add tests green here)*

`src/shelf/cli/doc_variants.py`:

```python
"""doc format add / delete (PRD §11.3, §11.13)."""

import shutil
from pathlib import Path

import click

from shelf.cli.runtime import get_config, get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import Catalog, Document, FileVariant, commit_library, load_catalog
from shelf.core.errors import ConflictError, NotFoundError
from shelf.core.ingest import doc_rel_dir, infer_format


def find_doc(catalog: Catalog, doc_id: str) -> Document:
    doc = next((d for d in catalog.documents if d.id == doc_id), None)
    if doc is None:
        raise NotFoundError(f"document '{doc_id}' not found — try 'shelf doc list --query {doc_id}'")
    return doc


@click.command("add")
@click.argument("doc_id")
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--assets", "assets_", multiple=True, type=click.Path(exists=True))
@click.option("--format", "format_", default=None)
@click.option("--replace", is_flag=True, help="Overwrite an existing same-format variant.")
@click.option("--primary", "primary_", default=None)
@click.option("--source", "source_", default=None)
@click.option("--remove-source/--no-remove-source", "remove_source_", default=None)
@click.pass_context
def format_add(ctx, doc_id, files, assets_, format_, replace, primary_, source_, remove_source_):
    """Add a format variant to an existing document."""
    paths = [Path(f).resolve() for f in files]
    new_formats = [infer_format(p, format_) for p in paths]
    if len(set(new_formats)) != len(new_formats):
        raise click.UsageError("two files of the same format")

    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        existing = {f.format for f in doc.files}
        clashes = [f for f in new_formats if f in existing]
        if clashes and not replace:
            raise ConflictError(f"format '{clashes[0]}' already exists — pass --replace")
        final_formats = existing | set(new_formats)
        if primary_ is not None and primary_ not in final_formats:
            raise click.UsageError(f"--primary '{primary_}' is not a format the document will have")
        rel_dir = doc_rel_dir(doc)
        dest = root / rel_dir
        created: list[Path] = []
        try:
            for p, fmt in zip(paths, new_formats):
                target = dest / f"{doc.id}.{fmt}"
                if not target.exists():
                    created.append(target)
                shutil.copy2(p, target)
            for a in assets_:
                ap = Path(a)
                target = dest / ap.name
                if ap.is_dir():
                    shutil.copytree(ap, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(ap, target)
            for fmt in new_formats:
                variant = FileVariant(format=fmt, path=f"{rel_dir}/{doc.id}.{fmt}", source=source_)
                doc.files = [f for f in doc.files if f.format != fmt] + [variant]
            if primary_ is not None:
                doc.primary = primary_
            commit_library(root, catalog)
        except BaseException:
            for target in created:
                target.unlink(missing_ok=True)
            raise

    effective_remove = get_config(ctx).remove_source if remove_source_ is None else remove_source_
    if effective_remove:
        for p in paths:
            p.unlink(missing_ok=True)
    click.echo(f"added format(s) {', '.join(new_formats)} to '{doc_id}'")
```

In `main.py`: remove the `doc format` `add` stub; register `format_add` on the `doc_format` group.

- [ ] **Step 5: Verify** — `uv run pytest tests/test_doc_variants.py -k "format_add" -v` green; format-delete tests still red (expected until Task 4); full suite otherwise green.
- [ ] **Step 6: Stage** — `feat: doc format add with replace and primary reassignment`.

---

### Task 4: `shelf doc format delete` and `shelf doc delete`

**Files:**
- Test: `tests/test_doc_delete.py` (doc delete); Task 3's variant tests go green
- Modify: `src/shelf/cli/doc_variants.py` (add `format_delete`), create `src/shelf/cli/doc_delete.py`, `src/shelf/cli/main.py` registrations (drop `doc format delete` + `doc delete` stubs)

**Interfaces:**
- Produces: `format_delete` per §11.13 (last-variant refusal → ConflictError naming `doc delete`; deleting the primary requires `--primary <successor>` else UsageError; `--force` drops an entry whose file is missing); `doc_delete` per §11.10 (non-TTY without `--yes` → exit 2; `--dry-run`; folder removed **after** the catalog commit).

- [ ] **Step 1: Write the failing doc-delete tests** *(sonnet)*

`tests/test_doc_delete.py`:

```python
"""P03-TS04 (delete half) — shelf doc delete."""

import io
import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d",
        "--slug", SLUG]


class TtyInput(io.BytesIO):
    def isatty(self):
        return True


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seeded(tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def test_delete_requires_yes_when_not_tty(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    r = run(["doc", "delete", SLUG])
    assert r.exit_code == 2
    assert "--yes" in r.output
    assert json.loads((root / "catalog.json").read_text())["documents"]


def test_delete_prompts_on_tty_and_accepts_yes(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    r = CliRunner().invoke(cli, ["doc", "delete", SLUG], input=TtyInput(b"y\n"))
    assert r.exit_code == 0, r.output
    assert json.loads((root / "catalog.json").read_text())["documents"] == []


def test_delete_with_yes_removes_entry_and_folder(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    r = run(["doc", "delete", SLUG, "--yes"])
    assert r.exit_code == 0, r.output
    assert json.loads((root / "catalog.json").read_text())["documents"] == []
    assert not (root / "docs" / "topics" / "dev-tooling" / SLUG).exists()


def test_delete_unknown_id_exits_three(isolated_env, tmp_path):
    _seeded(tmp_path)
    assert run(["doc", "delete", "nope", "--yes"]).exit_code == 3


def test_delete_dry_run_changes_nothing(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "delete", SLUG, "--dry-run"])
    assert r.exit_code == 0
    assert "would delete" in r.output
    assert (root / "catalog.json").read_text() == before
    assert (root / "docs" / "topics" / "dev-tooling" / SLUG).exists()


def test_rm_alias(isolated_env, tmp_path):
    _seeded(tmp_path)
    assert run(["doc", "rm", SLUG, "--yes"]).exit_code == 0
```

- [ ] **Step 2: Verify failure; commit red** *(sonnet)* — `test: add doc delete tests (red)` (+ trailer).
- [ ] **Step 3: Implement** *(codex)*

Append to `doc_variants.py`:

```python
@click.command("delete")
@click.argument("doc_id")
@click.argument("fmt")
@click.option("--primary", "primary_", default=None, help="New primary when deleting the current one.")
@click.option("--force", "-f", is_flag=True, help="Drop the entry even if its file is missing.")
@click.pass_context
def format_delete(ctx, doc_id, fmt, primary_, force):
    """Remove one format variant."""
    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        variant = next((f for f in doc.files if f.format == fmt), None)
        if variant is None:
            raise NotFoundError(f"document '{doc_id}' has no '{fmt}' variant")
        if len(doc.files) == 1:
            raise ConflictError("cannot remove the last variant — use 'shelf doc delete'")
        if doc.primary == fmt:
            if primary_ is None:
                raise click.UsageError("deleting the primary variant — pass --primary <successor>")
            if primary_ not in {f.format for f in doc.files if f.format != fmt}:
                raise click.UsageError(f"--primary '{primary_}' is not a remaining format")
        target = root / variant.path
        if not target.exists() and not force:
            raise click.ClickException(
                f"file '{variant.path}' is already missing — pass --force to drop the entry"
            )
        doc.files = [f for f in doc.files if f.format != fmt]
        if primary_ is not None:
            doc.primary = primary_
        commit_library(root, catalog)
        target.unlink(missing_ok=True)
    click.echo(f"removed '{fmt}' from '{doc_id}'")
```

`src/shelf/cli/doc_delete.py`:

```python
"""shelf doc delete (PRD §11.10) and orphan commands (§11.15 — Task 5)."""

import shutil
import sys

import click

from shelf.cli.runtime import get_library
from shelf.cli.doc_variants import find_doc
from shelf.core.atomic import library_lock
from shelf.core.catalog import commit_library, load_catalog
from shelf.core.ingest import doc_rel_dir


def _confirm_or_fail(prompt: str, yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise click.UsageError("refusing to delete without confirmation — pass --yes")
    click.confirm(prompt, abort=True, err=True)


@click.command("delete")
@click.argument("doc_id")
@click.option("-y", "--yes", is_flag=True, help="Assume yes (non-interactive consent).")
@click.option("--dry-run", is_flag=True)
@click.pass_context
def doc_delete(ctx, doc_id, yes, dry_run):
    """Delete a document — its entry and its folder."""
    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        doc = find_doc(catalog, doc_id)
        rel_dir = doc_rel_dir(doc)
        if dry_run:
            click.echo(f"would delete '{doc_id}' and folder {rel_dir}/ "
                       f"({len(doc.files)} variant(s))")
            return
        _confirm_or_fail(f"delete '{doc_id}' and {rel_dir}/ permanently?", yes)
        catalog.documents = [d for d in catalog.documents if d.id != doc_id]
        commit_library(root, catalog)
        shutil.rmtree(root / rel_dir, ignore_errors=True)
    click.echo(f"deleted '{doc_id}'")
```

In `main.py`: drop the `doc format delete` and `doc delete` stubs; register `format_delete` on `doc_format`, and `doc_delete` on `doc` under both `"delete"` and `"rm"`.

- [ ] **Step 4: Verify** — full suite green including all of `tests/test_doc_variants.py`.
- [ ] **Step 5: Stage** — `feat: doc format delete and doc delete with consent gating`.

---

### Task 5: `shelf doc adopt` and `shelf orphan list/delete`

**Files:**
- Test: `tests/test_adopt_orphans.py`
- Create: `src/shelf/cli/doc_adopt.py`; extend `src/shelf/core/ingest.py` (`scan_orphans`), `src/shelf/cli/doc_delete.py` (orphan commands)
- Modify: `src/shelf/cli/main.py` (register; drop `doc adopt`, `orphan list`, `orphan delete` stubs)

**Interfaces:**
- Produces: `scan_orphans(root, catalog) -> list[str]` (sorted rel paths: uncataloged entries directly under each bucket group, stray files under `docs/` and bucket roots); `doc_adopt` per §11.15 (anchor+slug from the folder path `docs/(repos|topics)/<group>/<slug>`; classification flags required; files registered as-is; topic governance honored; `--repo-url` optional); `orphan_list` (`--json`), `orphan_delete <path>` (ConflictError if cataloged; consent gating like `doc delete`; no catalog/index write).

- [ ] **Step 1: Write the failing tests** *(sonnet)*

`tests/test_adopt_orphans.py`:

```python
"""P03-T06 — doc adopt and orphan list/delete (§11.15)."""

import json

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


def _orphan_folder(root, slug="2026-01-01-strays"):
    d = root / "docs" / "topics" / "dev-tooling" / slug
    d.mkdir(parents=True)
    (d / f"{slug}.md").write_text("# stray")
    return d


def test_orphan_list_detects_uncataloged_folder(isolated_env):
    root = _init()
    d = _orphan_folder(root)
    r = run(["orphan", "list"])
    assert r.exit_code == 0
    assert "2026-01-01-strays" in r.output
    j = run(["orphan", "list", "--json"])
    assert str(d.relative_to(root)) in json.loads(j.output)


def test_orphan_list_empty_after_adopt(isolated_env):
    root = _init()
    _orphan_folder(root)
    r = run(["doc", "adopt", "docs/topics/dev-tooling/2026-01-01-strays",
             "--kind", "reference", "--title", "Strays", "--description", "d"])
    assert r.exit_code == 0, r.output
    entry = json.loads((root / "catalog.json").read_text())["documents"][0]
    assert entry["id"] == "2026-01-01-strays"
    assert entry["category"] == "dev-tooling"
    assert entry["files"][0]["path"] == "docs/topics/dev-tooling/2026-01-01-strays/2026-01-01-strays.md"
    assert run(["orphan", "list"]).output == ""


def test_adopt_slug_collision_conflicts(isolated_env):
    root = _init()
    _orphan_folder(root)
    assert run(["doc", "adopt", "docs/topics/dev-tooling/2026-01-01-strays",
                "--kind", "reference", "--title", "S", "--description", "d"]).exit_code == 0
    assert run(["doc", "adopt", "docs/topics/dev-tooling/2026-01-01-strays",
                "--kind", "reference", "--title", "S", "--description", "d"]).exit_code == 5


def test_adopt_unknown_topic_governed(isolated_env):
    root = _init()
    d = root / "docs" / "topics" / "brand-new" / "2026-01-01-x"
    d.mkdir(parents=True)
    (d / "2026-01-01-x.md").write_text("x")
    r = run(["doc", "adopt", "docs/topics/brand-new/2026-01-01-x",
             "--kind", "reference", "--title", "X", "--description", "d"])
    assert r.exit_code == 1
    assert "--create-topic" in r.output
    r = run(["doc", "adopt", "docs/topics/brand-new/2026-01-01-x", "--create-topic",
             "--kind", "reference", "--title", "X", "--description", "d"])
    assert r.exit_code == 0


def test_adopt_requires_known_format_file(isolated_env):
    root = _init()
    d = root / "docs" / "topics" / "dev-tooling" / "2026-01-01-empty"
    d.mkdir(parents=True)
    (d / "notes.docx").write_text("x")
    r = run(["doc", "adopt", "docs/topics/dev-tooling/2026-01-01-empty",
             "--kind", "reference", "--title", "E", "--description", "d"])
    assert r.exit_code == 1


def test_orphan_delete_refuses_cataloged_path(isolated_env, tmp_path):
    root = _init()
    src = tmp_path / "real.md"
    src.write_text("# real")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", "--kind", "reference",
                "--title", "Real", "--description", "d"]).exit_code == 0
    entry = json.loads((root / "catalog.json").read_text())["documents"][0]
    folder = "/".join(entry["files"][0]["path"].split("/")[:-1])
    r = run(["orphan", "delete", folder, "--yes"])
    assert r.exit_code == 5


def test_orphan_delete_removes_stray(isolated_env):
    root = _init()
    d = _orphan_folder(root)
    r = run(["orphan", "delete", str(d.relative_to(root)), "--yes"])
    assert r.exit_code == 0
    assert not d.exists()
    r = run(["orphan", "delete", "docs/topics/nope", "--yes"])
    assert r.exit_code == 3
```

- [ ] **Step 2: Verify failure; commit red** *(sonnet)* — `test: add adopt and orphan tests (red)` (+ trailer).
- [ ] **Step 3: Implement** *(codex)*

Append to `src/shelf/core/ingest.py`:

```python
from shelf.core.catalog import Catalog


def scan_orphans(root: Path, catalog: Catalog) -> list[str]:
    cataloged = {doc_rel_dir(d) for d in catalog.documents}
    orphans: list[str] = []
    docs_dir = root / "docs"
    for bucket in ("repos", "topics"):
        base = docs_dir / bucket
        if not base.is_dir():
            continue
        for group in sorted(base.iterdir()):
            if group.is_file():
                orphans.append(str(group.relative_to(root)))
                continue
            for entry in sorted(group.iterdir()):
                rel = str(entry.relative_to(root))
                if rel not in cataloged:
                    orphans.append(rel)
    for entry in sorted(docs_dir.iterdir()):
        if entry.is_file():
            orphans.append(str(entry.relative_to(root)))
    return sorted(orphans)
```

`src/shelf/cli/doc_adopt.py`:

```python
"""shelf doc adopt — register an existing in-library folder (PRD §11.15)."""

from pathlib import Path

import click

from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import Document, FileVariant, RepoRef, commit_library, load_catalog
from shelf.core.errors import ConflictError
from shelf.core.ingest import FORMAT_MAP, pick_primary


@click.command("adopt")
@click.argument("folder")
@click.option("--kind", "kind_", required=True)
@click.option("--title", required=True)
@click.option("--description", required=True)
@click.option("--tag", "tags_", multiple=True)
@click.option("--create-topic", is_flag=True)
@click.option("--repo-url", default=None)
@click.option("--subject", default=None)
@click.option("--primary", "primary_", default=None)
@click.option("--doc-date", default=None)
@click.pass_context
def doc_adopt(ctx, folder, kind_, title, description, tags_, create_topic,
              repo_url, subject, primary_, doc_date):
    """Register an existing per-document folder without copying."""
    root = get_library(ctx)
    rel = Path(folder)
    if rel.is_absolute():
        rel = rel.relative_to(root)
    parts = rel.parts
    if len(parts) != 4 or parts[0] != "docs" or parts[1] not in ("repos", "topics"):
        raise click.UsageError(
            "folder must be docs/repos/<repo>/<slug> or docs/topics/<topic>/<slug>"
        )
    bucket, group, slug = parts[1], parts[2], parts[3]
    target = root / rel
    if not target.is_dir():
        raise click.ClickException(f"'{rel}' is not a directory inside the library")

    variant_files = sorted(
        p for p in target.iterdir() if p.is_file() and p.suffix.lower() in FORMAT_MAP
    )
    if not variant_files:
        raise click.ClickException(f"'{rel}' contains no known-format files (md/html/pdf)")
    formats = [FORMAT_MAP[p.suffix.lower()] for p in variant_files]

    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        if kind_ not in catalog.kinds:
            raise click.ClickException(f"kind '{kind_}' is not in the kind list")
        if any(d.id == slug for d in catalog.documents):
            raise ConflictError(f"slug '{slug}' already exists in the catalog")
        if bucket == "topics":
            if group not in catalog.topics:
                if not create_topic:
                    raise click.ClickException(
                        f"unknown topic '{group}' — pass --create-topic to create it"
                    )
                catalog.topics.append(group)
            repo_ref = None
            category = group
        else:
            repo_ref = RepoRef(name=group, url=repo_url, subject=subject)
            category = None
        added = slug[:10] if len(slug) >= 10 and slug[4] == "-" and slug[7] == "-" else None
        doc = Document(
            id=slug, title=title, description=description, kind=kind_, tags=list(tags_),
            category=category, repo=repo_ref,
            files=[FileVariant(format=f, path=str(rel / p.name))
                   for p, f in zip(variant_files, formats)],
            primary=primary_ or pick_primary(formats), added=added,
            doc_date=doc_date, source=str(rel),
        )
        catalog.documents.append(doc)
        commit_library(root, catalog)
    click.echo(f"adopted '{slug}' ({', '.join(formats)})")
```

Append to `src/shelf/cli/doc_delete.py`:

```python
import json

from shelf.cli.output import output_options, resolve_format
from shelf.core.errors import ConflictError, NotFoundError
from shelf.core.ingest import scan_orphans


@click.command("list")
@output_options
@click.pass_context
def orphan_list(ctx, output, json_):
    """List uncataloged files under docs/."""
    root = get_library(ctx)
    orphans = scan_orphans(root, load_catalog(root))
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps(orphans, indent=2))
    else:
        for o in orphans:
            click.echo(o)


@click.command("delete")
@click.argument("path")
@click.option("-y", "--yes", is_flag=True)
@click.pass_context
def orphan_delete(ctx, path, yes):
    """Delete an uncataloged file or folder under docs/."""
    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root)
        rel = Path(path)
        if rel.is_absolute():
            rel = rel.relative_to(root)
        target = root / rel
        if not str(rel).startswith("docs/"):
            raise click.UsageError("orphan paths live under docs/")
        if not target.exists():
            raise NotFoundError(f"'{rel}' does not exist")
        cataloged = {doc_rel_dir(d) for d in catalog.documents}
        rel_s = str(rel)
        if rel_s in cataloged or any(rel_s.startswith(c + "/") for c in cataloged):
            raise ConflictError(f"'{rel}' belongs to a cataloged document — not an orphan")
        _confirm_or_fail(f"delete orphan '{rel}' permanently?", yes)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    click.echo(f"deleted orphan '{rel}'")
```

In `main.py`: drop the `doc adopt` and both `orphan` stubs; register `doc_adopt` on `doc`, `orphan_list`/`orphan_delete` on `orphan`.

- [ ] **Step 4: Verify** — full suite green.
- [ ] **Step 5: Stage** — `feat: doc adopt and orphan list/delete`.

---

### Task 6: Crash-injection pass *(opus — the P03 safeguard from the orchestration plan)*

**Files:**
- Test: `tests/test_crash_injection.py` (additive only; no src changes unless failures are found)

Opus authors adversarial failure-injection tests over the §5 ordering, extending this concrete harness (which is part of the task's deliverable, not a placeholder — opus may add scenarios beyond it):

- [ ] **Step 1: Author and run the harness + scenarios** *(opus)*

```python
"""P03 crash-injection: every failure leaves the library untouched or audit-repairable."""

import json

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _library_invariant(root):
    """The §5 invariant: catalog parses and every files[] path exists."""
    catalog = json.loads((root / "catalog.json").read_text())
    for doc in catalog["documents"]:
        for f in doc["files"]:
            assert (root / f["path"]).is_file(), f"dead reference {f['path']}"
    return catalog


@pytest.fixture
def seeded(isolated_env, tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    return default_library_path(), src


def _fail_nth_write(monkeypatch, module, n):
    """Make the nth atomic_write_text call in `module` raise."""
    import shelf.core.catalog as cat_mod

    calls = {"n": 0}
    real = cat_mod.atomic_write_text

    def flaky(path, text):
        calls["n"] += 1
        if calls["n"] == n:
            raise OSError(f"injected at write #{n}")
        real(path, text)

    monkeypatch.setattr(cat_mod, "atomic_write_text", flaky)


def test_add_fails_at_catalog_write_leaves_untouched(seeded, monkeypatch):
    root, src = seeded
    before = (root / "catalog.json").read_text()
    _fail_nth_write(monkeypatch, None, 1)  # catalog write = first
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    assert r.exit_code != 0
    assert (root / "catalog.json").read_text() == before
    assert src.exists()
    _library_invariant(root)


def test_add_fails_at_index_write_catalog_committed(seeded, monkeypatch):
    root, src = seeded
    _fail_nth_write(monkeypatch, None, 2)  # index write = second
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    assert r.exit_code != 0
    catalog = _library_invariant(root)  # catalog valid, files present
    assert len(catalog["documents"]) in (0, 1)  # committed or rolled — never corrupt
```

Opus extends with (at minimum): `doc delete` failure between commit and rmtree (orphan folder detectable by `orphan list`), `format add --replace` interrupted, and one scenario of its own design. Every discovered defect → red test committed → codex fix cycle → re-verify.

- [ ] **Step 2: Commit** — tests-only commit(s) `test: crash-injection pass over the §5 ordering`; any fixes follow the standard fix-dispatch flow.

---

### Task 7: Phase gate (fable + haiku)

- [ ] **Step 1: Verification** *(sonnet or controller)* — full suite, `make check`, `just all` (expect formatter/ty findings over new test files — fix as gate maintenance), live smoke: init → topic add → doc add (real file) → doc format add → doc list → doc view → orphan list → doc delete.
- [ ] **Step 2: Whole-branch review** *(fable)* — triage deferred Minors; confirm every mutating command uses the canonical locked pattern.
- [ ] **Step 3: Version bump** — `0.3.0`, `uv sync`, commit.
- [ ] **Step 4: Status flips** *(haiku)* — P03 `[x]` + Regression line.
- [ ] **Step 5: Merge + tag** — into `main` via `git -C`, tag `v0.3.0`.
- [ ] **Step 6: Push** — with Steve's standing instruction from this phase's kickoff (push when the phase is done), then remove the worktree.
