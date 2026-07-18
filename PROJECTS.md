# PROJECTS.md — shelf

Plan approved 2026-07-18 (Option A): the `shelf` CLI is built as a minimal py-launch-blueprint-shaped package from day one; the remaining scaffolding is layered on by template-press when it is ready (SHELF-PRD.md §14.6). The `shelf-skill` and `shelf-library` repos get their own plans later. Source spec: `SHELF-PRD.md` (amendments A1–A6 and B1–B15 applied).

---

## [ ] Project P01: Package foundation (v0.1.0)
**Goal**: A src-layout uv package with the blueprint's core conventions — click CLI skeleton, pytest/ruff/ty wired, `just all` + `make check` — installable via `uv tool install`, answering `shelf --version`.

### Tests & Tasks
- [ ] [P01-TS01] CLI smoke tests: `shelf --version` and `shelf --help` exit 0 (click test runner)
- [ ] [P01-T01] Scaffold `pyproject.toml`: src layout, click dependency, dependency-groups (pytest/ruff/ty), `[project.scripts] shelf = "shelf.cli.main:cli"`
- [ ] [P01-T02] Click command tree with stubs for every PRD §11 subcommand
- [ ] [P01-T03] Justfile (`all`: format, lint, typecheck, test) and Makefile (`check`: dependency preflight)
- [ ] Regression Test Status

## [ ] Project P02: Config and catalog core (v0.2.0)
**Goal**: Location resolution (PRD §4), `shelf-config.toml` read/write, catalog model with `schema_version`, atomic save with `.shelf.lock`, and the read surface — `init` (no git) with `--adopt`, `migrate`, `topic`/`kind` add+list, `path`, `list`, `show`.

### Tests & Tasks
- [ ] [P02-TS01] Resolution precedence matrix: `--library` > `SHELF_LIBRARY` > active config > unconfigured error (§4)
- [ ] [P02-TS02] Atomic save: injected failure leaves catalog untouched; lock serializes concurrent writers (§5)
- [ ] [P02-TS03] `shelf list` filter/query matrix (`--query` over id/title/description/tags/subject, `--limit`, `--sort`) and `shelf show` output, `--json` shapes (§11.11)
- [ ] [P02-TS04] Adopt/migrate matrix: valid clone adopts; unsupported schema refused; old schema blocks mutation until `migrate`; read commands stay read-compatible
- [ ] [P02-T01] Config module: XDG paths, `shelf-config.toml` read/write (incl. `handoff_agent`)
- [ ] [P02-T02] Catalog model: `schema_version` 1, topics/kinds/documents, validation (kind exists, topic exists)
- [ ] [P02-T03] `shelf init` — scaffold library, seed six kinds, write config, `--force` (§11.1, git flags deferred to P07)
- [ ] [P02-T04] `shelf topic add|list`, `shelf kind add|list`, `shelf path [config|index]`
- [ ] [P02-T05] `shelf list` and `shelf show <id>`
- [ ] [P02-T06] `shelf init --adopt` — validate + register an existing library (§11.1)
- [ ] [P02-T07] `shelf migrate` + schema refusal rules (§11.14, §10)
- [ ] Regression Test Status

## [ ] Project P03: Document lifecycle (v0.3.0)
**Goal**: `shelf add`, `shelf add-format`, `shelf remove-format`, `shelf remove` per PRD §11.2–.3, §11.13, §11.10 — slug derivation, validation order, copy+rename, rollback, source handling, orphan repairs (`add --in-place`, `remove --orphan`) — with a placeholder index template so the atomic regen contract holds from the start.

### Tests & Tasks
- [ ] [P03-TS01] Slug derivation: date prefix, kebab truncation ~60 chars, same-day collision rejected, `--slug` override (§7)
- [ ] [P03-TS02] `shelf add` validation order and rollback: failure at each stage leaves library untouched (§11.2)
- [ ] [P03-TS03] Source handling: `remove_source` default, `--keep-source`/`--remove-source`, removal only after full success
- [ ] [P03-T01] `shelf add` — anchoring (repo/topic, `--create-topic`), format inference, `--assets`, copy+rename to `<slug>.<ext>`
- [ ] [P03-T02] `shelf add-format` — `--replace`, `--primary`, folder never moves (§11.3)
- [ ] [P03-TS04] `remove-format` rules: last-variant refusal, primary reassignment, `--force` dead-entry drop; `remove` TTY prompt / `--yes`
- [ ] [P03-T03] `shelf remove` — entry + folder deletion, `--dry-run`, TTY prompt / `--yes`, `--orphan` (§11.10)
- [ ] [P03-T05] `shelf remove-format` (§11.13)
- [ ] [P03-T06] `shelf add --in-place` — orphan adoption (§11.2, §11.6)
- [ ] [P03-T04] Placeholder `index.html.tmpl` as package data + regeneration wired into every mutation
- [ ] Regression Test Status

## [ ] Project P04: Edit and move (v0.4.0)
**Goal**: `shelf edit` (pure catalog rewrites, `--force`-gated fields) and `shelf move` (the three relocations with `files[]` path rewrites) per PRD §11.4–.5.

### Tests & Tasks
- [ ] [P04-TS01] Edit field matrix: freely editable vs `--force`-gated vs routed-to-move errors
- [ ] [P04-TS02] Move relocations: topic→topic, repo→repo, topical↔repo-anchored conversions; path rewrites verified
- [ ] [P04-T01] `shelf edit` including `--dry-run` before/after diff
- [ ] [P04-T02] `shelf move` including relocation warning
- [ ] Regression Test Status

## [ ] Project P05: Audit and regen (v0.5.0)
**Goal**: `shelf audit` — all five checks (orphans, dead references, malformed entries incl. added↔slug and old schema, fingerprint staleness, dirty git) with `--json`, `--pre-commit`, and the §11.6 remediation matrix — plus `shelf regen` and the catalog+template fingerprint (PRD §11.6, §11.12).

### Tests & Tasks
- [ ] [P05-TS01] One failing fixture per audit check; clean library passes; exit codes correct
- [ ] [P05-TS02] Fingerprint: mutation → fresh; hand-edited catalog → stale; template change → stale; `shelf regen` → fresh again
- [ ] [P05-TS03] Audit snapshots under the lock — no false stale finding during a concurrent mutation
- [ ] [P05-T01] `shelf audit` with `--json` report, `--pre-commit` mode, and per-finding remediations (§11.6 matrix)
- [ ] [P05-T02] `shelf regen` (§11.12)
- [ ] Regression Test Status

## [ ] Project P06: The UI (v0.6.0)
**Goal**: The real `index.html.tmpl` — search over name/description/tags, subject grouping with kind badges and the kind-view toggle, copy-path in core mode — then the local server and enhanced mode via `shelf open` (PRD §13, §11.7).

### Tests & Tasks
- [ ] [P06-TS01] Generated page embeds catalog metadata only; core-mode path resolution from `file://` location
- [ ] [P06-TS02] Server binds 127.0.0.1, refuses paths outside library root, port fallback
- [ ] [P06-T01] Template: search, grouping (category / repo+subject), kind badge + kind-view toggle, per-variant rows
- [ ] [P06-T02] Server + enhanced mode: copy-contents, inline HTML rendering, absolute-root injection
- [ ] [P06-T03] `shelf open` / `shelf open --static`
- [ ] Regression Test Status

## [ ] Project P07: Git and GitHub integration (v0.7.0)
**Goal**: `--commit`/`--commit-message` plumbing across all mutating commands, and `shelf init --git` / `--github` / `--owner` (PRD §11 conventions, §11.1).

### Tests & Tasks
- [ ] [P07-TS01] `--commit` on non-git library errors; auto-generated messages match `shelf: <verb> <slug>` convention
- [ ] [P07-T01] Commit plumbing in the mutation pipeline (after index regen, before source removal)
- [ ] [P07-T02] `shelf init --git` initial commit; `--github` via `gh repo create` (manual verification)
- [ ] Regression Test Status

## [ ] Project P08: Claude handoff (v0.8.0)
**Goal**: `shelf add` missing-flags handoff — launch the configured agent (`--handoff-agent` flag > `handoff_agent` config > claude; codex allowed) with the primed shelf-add prompt, `--no-handoff` opt-out, and in-session detection via `CLAUDECODE` (Codex equivalent verified) so sessions never nest (PRD §11.2, §14.4).

### Tests & Tasks
- [ ] [P08-TS01] Missing flags + `--no-handoff` → error; inside-session env → error asking for the skill; flags complete → no handoff; agent precedence flag > config > default
- [ ] [P08-T01] Handoff launcher (agent precedence resolution) with primed prompt; session detection
- [ ] Regression Test Status

## [ ] Project P09: Template-press scaffolding layer (v1.0.0)
**Goal**: Layer the remaining py-launch-blueprint scaffolding (CI, release automation, hooks, docs) onto the repo via template-press (PRD §14.6). Blocked until template-press is ready for this use; scope finalized then. Follow-on plans for `shelf-skill` and `shelf-library` start after this.

### Tests & Tasks
- [ ] [P09-T01] Run the template-press pass; reconcile with the existing package (additive files only)
- [ ] [P09-TS01] `make check` and `just all` still pass; `uv tool install` still works
- [ ] Regression Test Status
