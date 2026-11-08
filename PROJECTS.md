# PROJECTS.md — shelf

Plan approved 2026-07-18 (Option A): the `shelf` CLI is built as a minimal py-launch-blueprint-shaped package from day one; the remaining scaffolding is layered on by template-press when it is ready (SHELF-PRD.md §14.6). The `shelf-skill` and `shelf-library` repos get their own plans later. Source spec: `SHELF-PRD.md` (amendments A1–A6, B1–B15, and C1–C6 applied; CLI grammar conforms to cli-design-standard v1.4.14).

---

## [x] Project P01: Package foundation (v0.1.0)
**Goal**: A src-layout uv package with the blueprint's core conventions — click CLI skeleton, pytest/ruff/ty wired, `just all` + `make check` — installable via `uv tool install`, answering `shelf --version`.

### Tests & Tasks
- [x] [P01-TS01] CLI smoke tests: `shelf --version` and `shelf --help` exit 0 (click test runner)
- [x] [P01-TS02] Standard-conformance smoke (R9.14 seed): bare `shelf` → help/exit 0; unknown command → exit 2; `-V` prints `shelf <semver>`; `--help` on stdout
- [x] [P01-T01] Scaffold `pyproject.toml`: src layout, click dependency, dependency-groups (pytest/ruff/ty), `[project.scripts] shelf = "shelf.cli.main:cli"`
- [x] [P01-T02] Click command tree with stubs for every PRD §11 subcommand
- [x] [P01-T03] Justfile (`all`: format, lint, typecheck, test) and Makefile (`check`: dependency preflight)
- [x] Regression Test Status — 9/9 passing (smoke + conformance) at v0.1.0; `make check` and `just all` green

## [x] Project P02: Config and catalog core (v0.2.0)
**Goal**: Location resolution (PRD §4), `shelf_config.toml` read/write (kebab keys), catalog model with `schema_version`, atomic save with `.shelf.lock`, standard option tiers, and the read surface — `init` (no git) with `--adopt`, `migrate`, `topic`/`kind` add+list, `path`, `doc list`, `doc view`.

### Tests & Tasks
- [x] [P02-TS01] Resolution precedence matrix: `--library` > `SHELF_LIBRARY` > active config > unconfigured error (§4)
- [x] [P02-TS02] Atomic save: injected failure leaves catalog untouched; lock serializes concurrent writers (§5)
- [x] [P02-TS03] `shelf doc list` filter/query matrix (`--query` over id/title/description/tags/subject, `--limit`, `--sort-by`) and `shelf doc view` output, `-o/--output` + `--json` shapes (§11.11)
- [x] [P02-TS04] Adopt/migrate matrix: valid clone adopts; unsupported schema refused; old schema blocks mutation until `migrate`; read commands stay read-compatible
- [x] [P02-T01] Config module: XDG paths, `shelf_config.toml` read/write, kebab keys (incl. `handoff-agent`)
- [x] [P02-T02] Catalog model: `schema_version` 1, topics/kinds/documents, validation (kind exists, topic exists)
- [x] [P02-T03] `shelf init` — scaffold library, seed six kinds, write config, `--force` (§11.1, git flags deferred to P07)
- [x] [P02-T04] `shelf topic add|list`, `shelf kind add|list`, `shelf path [config|index]`
- [x] [P02-T05] `shelf doc list` (alias `ls`) and `shelf doc view <id>`
- [x] [P02-T06] `shelf init --adopt` — validate + register an existing library (§11.1)
- [x] [P02-T07] `shelf migrate` + schema refusal rules (§11.14, §10)
- [x] [P02-T08] Standard option tiers (§11 conventions): global core (`-V`, repeatable `-v`, `--debug`, `--no-input`), `-o/--output table|json` with `--json` shorthand
- [x] Regression Test Status — 61/61 passing at v0.2.0; `make check` and `just all` (format+lint+ty+test) green; live CLI smoke verified

## [x] Project P03: Document lifecycle (v0.3.0)
**Goal**: `shelf doc add`, `doc format add`, `doc format delete`, `doc delete` per PRD §11.2–.3, §11.13, §11.10 — slug derivation, validation order, copy+rename, rollback, source handling, orphan repairs (`doc adopt`, `orphan list|delete`, §11.15) — with a placeholder index template so the atomic regen contract holds from the start.

### Tests & Tasks
- [x] [P03-TS01] Slug derivation: date prefix, kebab truncation ~60 chars, same-day collision rejected, `--slug` override (§7)
- [x] [P03-TS02] `shelf doc add` validation order and rollback: failure at each stage leaves library untouched (§11.2)
- [x] [P03-TS03] Source handling: `remove-source` default, `--remove-source`/`--no-remove-source`, removal only after full success
- [x] [P03-T01] `shelf doc add` — anchoring (repo/topic, `--create-topic`), format inference, `--assets`, copy+rename to `<slug>.<ext>`
- [x] [P03-T02] `shelf doc format add` — `--replace`, `--primary`, folder never moves (§11.3)
- [x] [P03-TS04] `doc format delete` rules: last-variant refusal, primary reassignment, `--force` dead-entry drop; `doc delete` TTY prompt / `--yes`
- [x] [P03-T03] `shelf doc delete` (alias `rm`) — entry + folder deletion, `--dry-run`, TTY prompt / `--yes` (§11.10)
- [x] [P03-T05] `shelf doc format delete` (§11.13)
- [x] [P03-T06] `shelf doc adopt` + `shelf orphan list|delete` (§11.15)
- [x] [P03-T04] Index regeneration already wired via commit_library (landed in P02); extend the placeholder template only as needed
- [x] Regression Test Status — 121/121 passing at v0.3.0 incl. 12-test opus crash-injection suite; `make check` and `just all` green; live lifecycle smoke verified

## [x] Project P04: Edit and move (v0.4.0)
**Goal**: `shelf doc update` (pure catalog rewrites, `--force`-gated fields) and `shelf doc move` (the three relocations with `files[]` path rewrites) per PRD §11.4–.5.

### Tests & Tasks
- [x] [P04-TS01] Update field matrix: freely editable vs `--force`-gated vs routed-to-move errors
- [x] [P04-TS02] Move relocations: topic→topic, repo→repo, topical↔repo-anchored conversions; path rewrites verified
- [x] [P04-T01] `shelf doc update` including `--dry-run` before/after diff
- [x] [P04-T02] `shelf doc move` including relocation warning
- [x] Regression Test Status — 147/147 passing at v0.4.0; witness double-fault hardening closes the P03 2b residual; `make check` and `just all` green; live update+move smoke verified

## [x] Project P05: Audit and regen (v0.5.0)
**Goal**: `shelf audit` — all five checks (orphans, dead references, malformed entries incl. added↔slug and old schema, fingerprint staleness, dirty git) with `--json`, `--pre-commit`, and the §11.6 remediation matrix — plus `shelf regen` and the catalog+template fingerprint (PRD §11.6, §11.12).

### Tests & Tasks
- [x] [P05-TS01] One failing fixture per audit check; clean library passes; exit codes correct
- [x] [P05-TS02] Fingerprint: mutation → fresh; hand-edited catalog → stale; template change → stale; `shelf regen` → fresh again
- [x] [P05-TS03] Audit snapshots under the lock — no false stale finding during a concurrent mutation
- [x] [P05-T01] `shelf audit` with `--json` report, `--pre-commit` mode, and per-finding remediations (§11.6 matrix)
- [x] [P05-T02] `shelf regen` (§11.12)
- [x] Regression Test Status — 166/166 passing at v0.5.0; `make check` and `just all` green (unpiped); live break-and-remediate smoke verified across orphan and stale-index findings

## [x] Project P06: The UI (v0.6.0)
**Goal**: The real `index.html.tmpl` — search over name/description/tags, subject grouping with kind badges and the kind-view toggle, copy-path in core mode — then the local server and enhanced mode via `shelf open` (PRD §13, §11.7).

### Tests & Tasks
- [x] [P06-TS01] Generated page embeds catalog metadata only; core-mode path resolution from `file://` location
- [x] [P06-TS02] Server binds 127.0.0.1, refuses paths outside library root, port fallback
- [x] [P06-T01] Template: search, grouping (category / repo+subject), kind badge + kind-view toggle, per-variant rows
- [x] [P06-T02] Server + enhanced mode: copy-contents, inline HTML rendering, absolute-root injection
- [x] [P06-T03] `shelf open` / `shelf open --static`
- [x] Regression Test Status — 205/205 passing at v0.6.0; `make check` and `just all` green (unpiped); manual browser verification passed (enhanced mode live, core mode verified) with one gate finding found-and-fixed (fenced-code preview rendering)

## [x] Project P07: Git and GitHub integration (v0.7.0)
**Goal**: `--commit`/`--commit-message` plumbing across all mutating commands, and `shelf init --git` / `--github` / `--owner` (PRD §11 conventions, §11.1).

### Tests & Tasks
- [x] [P07-TS01] `--commit` on non-git library errors; auto-generated messages match `shelf: <verb> <slug>` convention
- [x] [P07-T01] Commit plumbing in the mutation pipeline (commit runs OUTSIDE the library lock, after `commit_library`, before source removal — hook-safe)
- [x] [P07-T02] `shelf init --git` initial commit; `--github` via `gh repo create` (manual verification)
- [x] Regression Test Status — 252/252 passing at v0.7.0; `make check` and `just all` green (unpiped); LIVE `--github` pilot RAN (created private `smorin/shelf-library`, verified repo+origin+`shelf: init` commit, handed to user for manual deletion); pilot found+fixed a raw-traceback bug — `_gh` / `git_init` / `git remote add` now surface a clean `ClickException`; two cosmetic Minors (redundant `.strip()`, `--owner` without `--github`) deferred to P08

## [x] Project P08: Claude handoff (v0.8.0)
**Goal**: `shelf doc add` missing-flags handoff — launch the configured agent (`--handoff-agent` flag > `handoff-agent` config > claude; codex allowed) with the primed shelf-add prompt, `--no-handoff` opt-out (`--no-input` implies it), and in-session detection via `CLAUDECODE` (Codex equivalent verified) so sessions never nest (PRD §11.2, §14.4). CLI-side only — the `shelf-add` skill is deferred to the `shelf-skill` repo (§12).

### Tests & Tasks
- [x] [P08-TS01] Missing flags + `--no-handoff` → error; inside-session env → error asking for the skill; flags complete → no handoff; agent precedence flag > config > default; `--no-input` implies `--no-handoff` (suppression before session detection, PRD §5); blank/whitespace title/description also trigger handoff
- [x] [P08-T01] Handoff launcher (`core/handoff.py`: agent precedence resolution, primed prompt with sanitized paths, `os.execvp` seam) with session detection (`CLAUDECODE` / `CODEX_THREAD_ID`, build-verified against Codex CLI 0.144.6)
- [x] Regression Test Status — 316/316 passing at v0.8.0; `make check` and `just all` green (unpiped); LIVE hermetic handoff pilot 10/10 (both agent shims, both session markers, all four decision-table paths). FINAL whole-branch adversarial review (fable + codex, fresh context) over v0.1.0→v0.8.0 found 21 findings + 2 re-review blockers + 2 residuals — ALL fixed and re-verified: orphan-delete path-traversal/case-insensitive/ancestor wipes closed (identity-based, (st_dev,st_ino)); audit never-crashes on any parseable-but-malformed catalog; all git/gh/handoff subprocesses surface clean `ClickException`; `format add --replace` atomic (backup+restore); UI metadata HTML-escaped (XSS closed, empirically verified) + search-by-description + real copy-text + recorded variant paths; D2 (`git add -A` concurrency) accepted+documented as a single-user limitation. Two carried P07 Minors (redundant `.strip()`, `--owner` without `--github`) also fixed.

## [x] Project P09: shelf skill — single `shelf` skill, monorepo (plugin v0.1.0)
**Goal**: A single `shelf` skill exposing shelf's operations to Claude Code **and** Codex, shelling out to the `shelf` CLI, completing P08's handoff (the launched agent needs a skill to land in). **Monorepo (P09, 2026-07-22):** the plugin lives in the `shelf` repo itself — `.claude-plugin/` + `.codex-plugin/` + `skills/shelf/` at the root — not a separate `~/c/shelf-skill` repo (abandoned). The plugin is versioned independently (v0.1.0), outside the shelf-CLI version sequence; its files are excluded from the built wheel (`uv_build` src layout).

**Decision (2026-07-22): single `shelf` skill with progressive disclosure.** One always-on trigger + a lean `SKILL.md` that routes to per-operation `references/*.md` loaded on demand. Chosen over seven individual skills (PRD §12) and a grouped middle: the seven operations are verbs of one tool (shared CLI contract, classification, confirmation), so progressive disclosure delivers focused per-op loading **without** seven always-on trigger descriptions — minimal context footprint, least maintenance, fewest manifest/collision surfaces, idiomatic. The one cost — a broad trigger that must fire reliably — is an authoring/testing task, not a blocker.

### Tests & Tasks
- [x] [P09-T01] Single `shelf` skill authored via **skill-create**: lean `SKILL.md` (one trigger; routing table; invariants) + `references/{add,edit,find,remove,audit,open,init}.md`, each shelling out to the `shelf` CLI
- [x] [P09-T02] Dual plugin manifests (`.claude-plugin/plugin.json` + `.codex-plugin/plugin.json`), verified via `skillsmith verify --deep` — claude-code 2.1.218 + codex 0.144.6 both pass, no findings (PRD §14.1)
- [x] [P09-T03] Handoff prompt in `core/handoff.py` ("shelf-add skill" → "shelf skill") + the in-session guard message in `cli/doc_add.py`; tests updated first (TDD)
- [x] [P09-TS01] **skill-quality PASS** — collision-free trigger vs 202 installed skills (create-new verdict), clean secrets/placeholders, least-privilege `allowed-tools` (Bash/Read/WebFetch); per-tool load verified
- [x] Regression Test Status — `just all` → **317 passed, ruff + ty clean** (additive: plugin files outside `src/`, excluded from the wheel); end-to-end handoff smoke green (real `shelf doc add` → handoff → agent primed to invoke the `shelf` skill)

**Out of scope**: the `shelf-library` content repo (stand up separately via `init --git`/`--adopt`). Fuller PRD/doc reconciliation of the monorepo pivot → **P14**.

---

## [ ] Project P10: Taxonomy maintenance (version TBD — next free when it ships)
**Goal**: Add the deferred taxonomy-maintenance commands (PRD §14.5): `topic rename` (folder moves under `docs/topics/` + catalog `category` updates + regen), `topic remove`, `kind remove`. Follows the existing mutation pipeline (advisory lock, atomic commit-point, audit-detectable), with in-use guards.

### Tests & Tasks
- [ ] [P10-T01] `topic rename <old> <new>` — move folders, rewrite affected catalog categories, regen; reject on target-exists / in-use conflicts
- [ ] [P10-T02] `topic remove` / `kind remove` — refuse while in use by any document, else drop from the taxonomy
- [ ] Regression Test Status

---

## [ ] Project P11: Template-press scaffolding layer (v1.0.0)
**Goal**: (moved from P09) Layer the remaining py-launch-blueprint scaffolding — CI, release automation, hooks, docs — onto the repo via template-press (PRD §14.6), additively (no disturbing `src/shelf` or `uv tool install`). Cuts **v1.0.0** — the "conventional org project" graduation. Blocked until template-press is confirmed ready for the layer-onto-existing-repo case; scope finalized then.

### Tests & Tasks
- [ ] [P11-T01] Run the template-press pass (dry-run first); reconcile with the existing package (additive files only)
- [ ] [P11-TS01] `make check` and `just all` still pass; `uv tool install` still works
- [ ] Regression Test Status

---

## [>] Project P12: Multiple libraries (far out) → continued by P20
**Redirect (2026-11-05)**: the concrete need appeared as user + project scopes; see **P20**. Fully named libraries remain a possible later generalization of P20's two scopes.

**Goal**: (far-future idea, PRD §14.3) Named multi-library support. The current design assumes a single library; the §4 resolution scheme can accommodate named libraries later **without breaking changes**. Not scoped — revisit only when a real multi-library need appears.

---

## [ ] Project P13: Concurrency-safe git commits (D2 — optional/deferred; T02 required by P20, ships as v0.8.4)
**Goal**: (final-review D2, currently accept+documented) Isolate each command's commit from a concurrent second shelf process so the post-lock `git add -A` can no longer sweep another process's change into this commit. Single-user is the intended model, so this is **optional** — pursue only if real multi-process/automation use appears. No data-loss risk today; the impact is muddled git-history attribution only.

**Approach**:
- **Git-serialization lock**: a separate advisory flock (e.g. `.shelf.gitlock`, distinct from the library lock so a `shelf audit` pre-commit hook — which takes the *library* lock — can't deadlock) held around `git add … && git commit`.
- **Path-scoped add**: `git_commit_all(root, message)` → `git_commit_all(root, message, paths=None)`; each mutating command passes the exact paths it touched (catalog.json, index.html, its doc folder); `init` keeps `-A`.
- Thread `paths` through every commit caller (doc add/update/move/delete, format add/delete, taxonomy add, regen/migrate, orphan delete).

### Tests & Tasks
- [ ] [P13-T01] `.shelf.gitlock` advisory lock around add+commit (proven not to deadlock with the pre-commit `shelf audit` hook)
- [x] [P13-T02] Path-scoped `git_commit_all(paths)`; thread through all callers — **promoted 2026-11-05: prerequisite of P20, ships alone as v0.8.4.** A project library shares the host repo, where `git add -A` would sweep the user's unrelated uncommitted files into a shelf commit
- [x] [P13-TS02] Path-scoped commit test: an unrelated dirty file in the library's repo stays unstaged and out of the shelf commit
      Done 2026-11-06 (v0.8.4): `git add -A -- <paths>` + `git commit --only -- <paths>`; missing-and-untracked paths skipped; `catalog.json` anchors an otherwise-empty commit; `init` keeps `-A`. 347 tests passing; live smoke confirmed an unstaged edit and an untracked file stay out of a `doc add --commit`
- [ ] [P13-TS01] Concurrency isolation test: two shelf processes → each commit contains only its own changes (no mixed/empty commits)

---

## [x] Project P14: Reconcile PRD & docs with the monorepo skill pivot
**Goal**: Align all specs/docs with the monorepo pivot (supersedes PRD §12, §14.1).

**Notes**:
- 2026-07-22 P09 decision pivoted the skill from a separate `shelf-skill` repo to a **monorepo** (plugin inside the shelf repo); the abandoned `~/c/shelf-skill` repo is superseded.
- P09 Task 5 makes only the *minimal* in-plan PRD edits — this project is the *fuller* reconciliation pass across every spec/doc.
- Audit scope: PRD §12 (skill ownership), §14.1 (dual manifests), §36 (marketplace note), the architecture sections, and any lingering "separate `shelf-skill` repo" references.
- **Decision**: §36's "no marketplace initially" does **not** hold under the monorepo — re-specify direct-install accordingly.
- **Decision**: delete the abandoned `~/c/shelf-skill` repo as part of this reconciliation.

**Done (2026-07-24)**:
- PRD §12 rewritten to the single `shelf` skill + per-operation references — the seven-skill ownership table and `### shelf-*` subsections replaced; a naming note maps any lingering `shelf-<verb>` mention to its reference; inline `shelf-<verb> skill` phrasings reconciled.
- §2 marketplace non-goal updated: the repo **self-hosts its own marketplace** for both ecosystems, superseding "no marketplace initially" — the marketplace + plugin itself shipped in PR #2 (`feat(p14): dual marketplace + plugin`).
- Abandoned `~/c/shelf-skill` directory deleted.
- §14.1 (dual manifests) and the §1/§3 architecture were already reconciled in P09.

---

## [x] Project P15: Shorten the shelf skill description to action-scoped triggers (plugin v0.1.1)
**Goal**: Rewrite the `shelf` skill's frontmatter description to the fleet shape — what it does, "use when" a specific action, "not for" its two real sibling collisions (document-merge, repo-finder) — from 853 to 333 characters, so it survives Claude Code's skill-listing budget and Codex's description truncation. Body, references, and CLI behavior unchanged.

**Notes**:
- Motivated by Eric Provencher's "Rethinking skills and prompts for GPT-6 Astra" and Claude Code's 1%-of-context skill-listing budget, under which this skill had been reduced to a bare name.
- The Claude and Codex plugin manifests were out of sync (0.1.0 vs 0.1.1); both now read 0.1.1.

### Tests & Tasks
- [x] [P15-T01] Rewrite the description; fold trigger phrases to four; keep the two sibling exclusions
- [x] [P15-T02] Align both plugin manifests and the marketplace entries at 0.1.1
- [x] [P15-TS01] `make check` and `just all` green; PR merged and main fast-forwarded

---

## [x] Project P16: Complete README — pitch and full manual (docs only, no version bump)
**Goal/Requirement**: Replace the placeholder `README.md` (a lone `# shelf` heading) with a README that first introduces and sells shelf — AI-first: a personal reference library your coding agents can use — and then serves as the full user manual.
- Command reference built from `shelf --help` (authoritative), not the PRD, where the two diverge
- Prominent warning that `doc add` removes the source file by default
- Plugin/skill install summarized with a link to `plugins/shelf/README.md`

**Out of Scope**
- CLI or plugin code changes; version bump or tag
- Reconciling PRD/`--help` divergences (`doc update -i`, `regen --json`, unused `browser` config key)

### Tests & Tasks
- [x] [P16-T01] Write `README.md`: pitch, quick start, install, concepts, configuration, command reference, exit codes, UI, git, audit, AI integration, new machine, development
- [x] [P16-TS01] Every documented command and flag checked against `shelf <cmd> --help`; quick-start transcript re-run in a scratch library
- [x] [P16-TS02] `make check` and `just all` green; PR merged and main fast-forwarded

---

## [x] Project P17: Reconcile PRD with CLI behavior (v0.8.1)
**Goal/Requirement**: Close the five gaps between `SHELF-PRD.md` and the code found while writing the README (P16).
- `shelf open` honors the `browser` config key; unset means the system default browser. The legacy value `browser = "Google Chrome"`, which `shelf init` always wrote, is treated as unset, and `init` no longer writes it.
- The ⌘K palette search in `index.html` is fuzzy (in-order character match with consecutive, word-start, and title bonuses), and results are ranked by score.
- `shelf regen --json` prints a machine-readable report, like `migrate --json`.
- PRD: the busy-port fallback describes an OS-chosen free port; `doc update -i` is removed.

**Out of Scope**
- Other PRD or README wording; the closed PR #8 (structured references)

### Tests & Tasks
- [x] [P17-TS01] Config: `browser` defaults to unset; legacy "Google Chrome" loads as unset; `init` writes no `browser` key
- [x] [P17-TS02] `shelf open`: unset browser uses the system default; a set browser is used (macOS `open -a`, elsewhere `webbrowser.get`); an unknown browser exits 1 with a clear error
- [x] [P17-TS03] `regen --json` and `regen --dry-run --json` print `{"index", "dry_run"}`
- [x] [P17-TS04] Fuzzy scorer, run under Node from the rendered `index.html`: subsequence matches, non-matches rejected, title and contiguous matches rank higher, multi-word queries AND together
- [x] [P17-T01] Implement `browser` config handling and `shelf open` browser selection
- [x] [P17-T02] Implement `regen --json`
- [x] [P17-T03] Implement fuzzy scoring and ranked palette results in `index.html.tmpl`
- [x] [P17-T04] Update `SHELF-PRD.md` (port fallback, remove `-i`) and `README.md` (browser, search, `regen --json`)
- [x] [P17-T05] Bump to v0.8.1; `make check` and `just all` green; PR merged; tag `v0.8.1` pushed

---

## [x] Project P18: Post-0.8.1 cleanups (v0.8.2)
**Goal/Requirement**: Fix three small defects found during P17.
- `SHELF-PRD.md` says `shelf open` opens `http://localhost:<port>`; the code opens `http://127.0.0.1:<port>`, matching the server's bind address. The PRD is corrected.
- The ⌘K palette preview line uses `/\\s+/g`, which matches a literal backslash and `s`, not whitespace. It becomes `/\s+/g`, so whitespace runs collapse before the 64-character cut.
- `pyproject.toml` pins `uv_build>=0.10.5,<0.11.0`, which excludes the installed uv 0.11.29 and makes every `uv build` warn and fetch an old backend. The range becomes `>=0.11.29,<0.12.0`.

**Out of Scope**
- Any other template, PRD, or build changes

### Tests & Tasks
- [x] [P18-TS01] Rendered `index.html` collapses whitespace in palette previews with `/\s+/g` and no longer contains `/\\s+/g`
- [x] [P18-T01] Fix the preview regex in `index.html.tmpl`
- [x] [P18-T02] Change `localhost` to `127.0.0.1` in `SHELF-PRD.md` §11.7 and §14
- [x] [P18-T03] Widen the `uv_build` range; `uv build` prints no version warning
- [x] [P18-T04] Bump to v0.8.2; `make check` and `just all` green; PR merged; tag `v0.8.2` pushed

---

## [x] Project P19: Sidebar footer shows real values (v0.8.3)
**Goal/Requirement**: Remove two mockup leftovers from the UI sidebar footer in `index.html.tmpl` (found by CodeRabbit on PR #12).
- Enhanced mode shows the page's real host (`location.host`, for example `127.0.0.1:8765` or the fallback port) instead of the literal `localhost:8765`.
- The constant `13 files` count is removed; the footer keeps the real document count.

**Out of Scope**
- Adding a real file count; other footer or sidebar changes

### Tests & Tasks
- [x] [P19-TS01] Rendered `index.html` footer uses `location.host` and contains neither `localhost:8765` nor `13 files`
- [x] [P19-T01] Fix the footer line in `index.html.tmpl`
- [x] [P19-T02] Bump to v0.8.3; `make check` and `just all` green; PR merged; tag `v0.8.3` pushed

---

## [~] Project P20: Project-scoped libraries (v0.10.0, plugin v0.2.0)
**Goal/Requirement**: Give shelf a **project** scope beside the existing **user** scope, like Claude Code skills. Design: `docs/superpowers/specs/2026-11-05-scopes-and-publishing-design.md` (Part 1). Approved 2026-11-05.
- Discovery per CLI Design Standard R5.2: search the current directory and its parents for `.shelf/shelf_config.toml`, stopping at `.git`; its `library` is a relative path (default `shelf`)
- Precedence: `--library` → `SHELF_LIBRARY` → project scope → user config → error
- `doc list` / `doc view` search both scopes and label each result with `scope`; mutating and library-level commands act on one library (project when discovered); `--scope user|project|all` overrides
- `doc move --to-scope user|project` moves a document between libraries
- `shelf init --scope project`: no nested `git init`, appends to `.gitignore`, project defaults (topic anchors, `remove-source = false`, `index.html` gitignored)
- Skill: find labels scope; add always asks which scope when a project scope exists; init gains the project path; plugin README documents project-scope plugin install

**Out of Scope**
- Named libraries beyond the two scopes (P12 generalization); system scope (`$XDG_CONFIG_DIRS`)
- Publishing (P21)

### Tests & Tasks
- [x] [P20-T00] Prerequisite: P13-T02 path-scoped commits merged and released (v0.8.4, PR #17, 2026-11-06)
- [x] [P20-TS01] Discovery: nearest `.shelf/shelf_config.toml` wins; search stops at `.git`; absolute `library` in a project config is rejected; `--config` replaces discovered files
- [x] [P20-TS02] Precedence matrix: `--library` > `SHELF_LIBRARY` > project > user > unconfigured error; `--scope project` without a project scope exits 2
- [x] [P20-TS03] Combined reads: `doc list`/`doc view` return both scopes with a `scope` field (table and JSON); `--scope` narrows
- [x] [P20-TS04] `init --scope project`: inside an existing repo creates no nested `.git`; appends to an existing `.gitignore` without losing lines; writes project defaults; rejects `--git`/`--github`
- [x] [P20-TS05] `doc move --to-scope`: document lands in the target and leaves the source; an injected failure after the add leaves an audit-detectable duplicate
- [x] [P20-TS06] Project-scope `--commit` stages only shelf paths in the host repo
- [x] [P20-T01] Project config discovery and relative `library` resolution (`core/config.py`, `core/paths.py`)
- [x] [P20-T02] `--scope` option and single-target resolution for mutating and library-level commands
- [x] [P20-T03] Combined-scope `doc list` / `doc view` with the `scope` field
- [x] [P20-T04] `init --scope project` with enclosing-repo detection and `.gitignore` append (also fixes the overwrite in plain `init`)
- [x] [P20-T05] `doc move --to-scope`
- [x] [P20-T06] Deterministic sorted document order in `catalog.json` to reduce merge conflicts
- [x] [P20-T07] Skill updates (`find`, `add`, `init` references) and plugin README; bump plugin to 0.2.0
- [x] [P20-T08] PRD: rewrite §4 precedence, remove the R5.1/R5.2 waiver in §5, close §14.3; README configuration section
      Done 2026-11-07: decisions I0–I15 in `docs/superpowers/plans/2026-11-07-p20-project-scope.md`; P22-TS10 (scope question) and the `agent status` project-shelf note shipped here
- [ ] [P20-T09] Bump to v0.10.0; `make check` and `just all` green; PR merged; tag `v0.10.0` pushed
- [ ] Regression Test Status

### Deliverable
```bash
$ cd my-repo && shelf init --scope project
initialized project library at my-repo/shelf
$ shelf doc list --scope all
2026-11-05-api-guide	API Guide	explainer	topic:api	project
2026-10-24-uv-inline-scripts	uv Inline Scripts	explainer	topic:dev-tooling	user
```

### Automated Verification
- `just all` passes, including the P20-TS* tests
- `make check` passes

### Manual Verification
- In a scratch repo with uncommitted files, `shelf doc add … --commit` commits only shelf paths
- The skill asks which scope to use when adding inside a repo that has a project library

---

## [ ] Project P21: Publishing and GitHub Pages (v0.11.0, plugin v0.3.0)
**Goal/Requirement**: Publish a library (user or project scope) as a filtered static site, deployable to GitHub Pages, without leaking private documents. Design: `docs/superpowers/specs/2026-11-05-scopes-and-publishing-design.md` (Part 2). Approved 2026-11-05.
- `shelf publish` never creates a repo or pushes; it builds `_site/` from the library in whichever repo holds it. Locally it is a preview; deploys happen only through the Action (artifact deploy, never a `gh-pages` branch)
- Per-document `publish: true|false` catalog field (schema v1 → v2 via `shelf migrate`), set with `doc add --publish` and `doc update --publish|--no-publish`
- Config switch `publish = "marked"` (default) | `"all"`; `"all"` publishes every document and every variant (HTML, Markdown, PDF)
- **Private-repo guard, always on:** any publish from a private, internal, or unverifiable repo exits 2 unless `--force` is passed, in both modes; no config key bypasses it
- Discoverability: `publish --dry-run` footer, `--help` examples, README section, and the skill all explain how to publish everything and when `--force` is required
- `shelf publish --out _site` builds a filtered catalog, filtered `index.html` (no topic/kind/tag leakage from unpublished documents), published files, and `.nojekyll`
- `base-url`: detected automatically (CI: `actions/configure-pages` output; locally: `gh api …/pages`), overridable by `--base-url` or the `base-url` config key; `init --pages` never writes it. Hosted UI copies URLs and links to GitHub source
- `shelf pages status [--json]`: the seven-step readiness checklist (library, Git repo, GitHub repo, plan, Pages enabled, workflow pushed, documents to publish), each failing step with its fix command; exit 1 when any step fails
- `shelf pages enable [--yes] | enable --print`: turn Pages on (POST or PUT `build_type=workflow`) or print the command
- `shelf github create [--owner] [--name] [--public] [--dry-run]`: separate command that creates the GitHub repo for a user library (initializing Git if needed); refuses for project libraries; `init --pages` never creates repos
- Flags: `--yes` is consent; `--force` is only the private-repo guard override; `--no-input` prints commands instead of asking or running them
- One-line next-step hints (suppressed by `-q`) after `doc add|update --publish` and local `shelf publish` when deploy is not set up
- `shelf init --pages [--force] [--shelf-version X.Y.Z]` generates an Actions workflow (`configure-pages` → install shelf → `shelf publish` → `upload-pages-artifact` → `deploy-pages`), then offers `pages enable`; on "no" it prints the command
- The Action installs the `shelf_version` recorded in `catalog.json` (written on every library write) unless `SHELF_VERSION` pins one in the workflow file; versions below v0.11.0 or a missing value stop the run
- On failure, the Action's job summary and an `::error::` annotation name the fix (Pages off, private-repo guard, version resolution)
- `shelf init --readme` adds a link-only README block

**Out of Scope**
- Hosting outside GitHub Pages (the `_site/` folder is portable, but not automated)
- A `publish-formats` filter

### Tests & Tasks
- [ ] [P21-TS01] Schema v2 migration: v1 catalogs migrate with `publish: false`; `doc add --publish` and `doc update --publish|--no-publish` set the field
- [ ] [P21-TS02] Filtering: `marked` mode includes only `publish: true` documents; `all` includes every document and variant; the published index contains no title, tag, topic, kind, or snippet from an unpublished document
- [ ] [P21-TS03] Guard matrix: public → publishes; private, internal, or unknown → exit 2 without `--force` in both modes, publishes with it; `--dry-run` never requires `--force`; detection reads `$GITHUB_EVENT_PATH` first, then `gh`, and any failure counts as unknown
- [ ] [P21-TS04] `--dry-run` output lists documents, visibility, the not-published count, and the publish-everything footer (with the `--force` note for private repos)
- [ ] [P21-TS05] `_site` contains `.nojekyll`; base-URL precedence `--base-url` > config > detected (`--detected-base-url` in CI, `gh` locally) > none; Copy path yields URLs when one resolves
- [ ] [P21-TS06] `init --pages` writes the workflow; for a private repo it refuses without `--force` and writes `--force` into the workflow with it; `--shelf-version` writes the `SHELF_VERSION` pin; it never writes `base-url`; `init --readme` inserts and updates the marked block idempotently
- [ ] [P21-TS07] `shelf_version` is written on every library write; the workflow's version step uses the pin when set, else the catalog value, and fails with a named fix when the value is missing or below v0.11.0
- [ ] [P21-TS08] `pages status` exit codes (0 ready, 1 not ready); `pages enable` chooses POST vs PUT by state, asks before running, `--yes` skips, `--print` runs nothing; `init --pages` offers enable and prints the command on "no"
- [ ] [P21-TS10] Readiness checklist: steps evaluate in order and later steps report `skipped` after a failure; `--json` carries `status` and `fix`; hints appear after `doc add|update --publish` and local `publish` only when deploy is not set up, and `-q` suppresses them
- [ ] [P21-TS11] `github create`: initializes Git when missing, runs `gh repo create … --private --source --push` (`--public` honored), `--dry-run` runs nothing, refuses for a project library with exit 2
- [ ] [P21-TS12] Flag semantics: `init --pages --yes` runs `pages enable` without asking but still refuses a private repo without `--force`; `--no-input` prints commands and runs none
- [ ] [P21-TS09] Generated workflow: `if: failure()` step writes an annotation and job summary with the fix for each failing step (configure-pages, guard exit 2, version resolution)
- [ ] [P21-T01] Catalog schema v2 + migration + `--publish` flags
- [ ] [P21-T02] `shelf publish` site builder with filtered catalog and index
- [ ] [P21-T03] Visibility detection and the `--force` guard
- [ ] [P21-T04] Hosted mode in `index.html.tmpl` and base-URL resolution (`--base-url`, config, `--detected-base-url`, `gh` detection)
- [ ] [P21-T05] `init --pages` workflow generator (version step with `SHELF_VERSION` pin, failure-summary step) and `init --readme` block
- [ ] [P21-T09] `shelf_version` written by every library write (`commit_library`) as part of schema v2
- [ ] [P21-T10] `shelf pages status | enable | enable --print` with the readiness checklist
- [ ] [P21-T11] `shelf github create`
- [ ] [P21-T12] Next-step hints in `doc add`, `doc update`, and `publish`
- [ ] [P21-T06] Skill: publish routing, mode and visibility reporting; bump plugin to 0.3.0
- [ ] [P21-T07] PRD (§2 non-goal, §4, §5, §10, §11) and README "Publishing" section
- [ ] [P21-T08] Bump to v0.11.0; `make check` and `just all` green; PR merged; tag `v0.11.0` pushed
- [ ] Regression Test Status

### Deliverable
```bash
$ shelf publish --dry-run
would publish 3 of 15 documents (mode: marked) from smorin/shelf-library (private)
12 documents not published. To publish everything, set publish = "all" in ~/.config/shelf/shelf_config.toml.
This repo is private: publishing requires --force.
$ shelf publish --out _site
error: smorin/shelf-library is private; publishing 3 documents requires --force (exit 2)
```

### Automated Verification
- `just all` passes, including the P21-TS* tests
- `make check` passes

### Manual Verification
- A pilot deploy of a test repo to GitHub Pages serves the filtered index; copy-text and Copy path work on the hosted page
- With Pages disabled on the pilot repo, the failed run's summary shows the `gh api` command; `shelf pages enable` fixes it and a re-run deploys

---

## [x] Project P22: Install agent skills from the CLI — `shelf agent` (v0.9.0; plugin unchanged)
**Release order (2026-11-07)**: P22 ships first as v0.9.0; P20 moves to v0.10.0 and P21 to v0.11.0.
**Goal/Requirement**: Let the CLI install its own skills (`shelf`, `shelf-reference`) for Claude Code and Codex/Cursor at user or project scope, as copies matched to the CLI version or as dev-mode symlinks into a checkout, never replacing a placement shelf did not install unless forced. Modeled on `baml agent install`. Design: `docs/superpowers/specs/2026-11-05-scopes-and-publishing-design.md` (Part 3). Approved 2026-11-06; `shelf skill` is an alias for `shelf agent`; default scope `user`, asking about project scope inside a repo with a project shelf.
- `shelf agent install [--scope user|project] [--dev [--source PATH]] [--force] [--dry-run]`, `shelf agent status [--json]`, `shelf agent uninstall`; `shelf skill …` is an alias
- Writes both `.claude/skills/<name>` and `.agents/skills/<name>`; user scope under `~`, project scope at the `.shelf/` directory or Git repo root (refused for no repo, `$HOME` repos, and non-ancestor repo roots)
- Copy mode: bundled package data plus a `.shelf-agent.json` stamp; dev mode: absolute symlinks at user scope, relative symlinks at project scope only when the source is inside the same repo
- Skip-unless-forced: foreign copies, symlinks to other targets, mode switches, and an enabled `shelf@shelf` plugin are skipped (exit 1, with reason) unless `--force`; replacements go to `shelf-old_skills/<name>`; symlinks are unlinked, never followed
- Per-skill status lines, `--dry-run`, restart reminder; stale-copy note in `agent status` and `audit`

**Out of Scope**
- Downloading skills from GitHub (`--source` URL/archive); prefixing skill names; agents beyond Claude Code and the `.agents/skills` readers (Codex, Cursor, OpenCode)

### Tests & Tasks
- [x] [P22-TS01] Scope roots: user → `~/.claude/skills` and `~/.agents/skills`; project → `.shelf/` dir or repo root; refused outside a repo, for a `$HOME` repo root, and for a non-ancestor repo root
- [x] [P22-TS02] Copy mode: installs bundled skills with stamp; re-run reports `unchanged`; newer CLI reports `updated`; unrelated skills untouched
- [x] [P22-TS03] Dev mode: `--source` and auto-detected checkout; invalid source exits 2; user scope writes absolute links; project scope writes relative links only for an in-repo source, else exits 2; no stamp written through a link
- [x] [P22-TS04] Classification matrix: each destination state from the spec table produces the right action with and without `--force`; skipped placements give exit 1 and name the flag
- [x] [P22-TS05] Safety: replacing or uninstalling a symlink never modifies its target; backup slot holds exactly the previous placement; an injected failure mid-swap restores it
- [x] [P22-TS06] `--dry-run` writes nothing and prints `would …` lines; `agent status --json` reports kind, target, version, stale
- [x] [P22-TS07] Packaging: the wheel contains the skills; the packaged copy matches `plugins/shelf/skills/` byte for byte
- [x] [P22-TS10] (moved to P20: needs project-shelf discovery) Scope question: without `--scope` inside a repo with a project shelf, a TTY asks (yes → project, no/Enter → user); `--no-input`/no TTY installs at user scope and prints the project-scope command; `--scope` and `--yes` behave as specified (no question, `--yes` does not answer it); no project shelf → no question
- [x] [P22-TS09] Alias: `shelf skill install|status|uninstall` behaves identically to `shelf agent …` and appears in `--help`; `agent status` notes a missing project-scope skill in a repo with a project library
- [x] [P22-TS08] Adoption: on a machine whose placements are symlinks to the same checkout (the current dev setup), `install --dev --source <checkout>` reports `unchanged` and changes nothing
- [x] [P22-T01] Bundle the skills as package data with the sync test
- [x] [P22-T02] Scope-root resolution
- [x] [P22-T03] Destination classification, backup slot, atomic swap, symlink-safe removal
- [x] [P22-T04] `agent install` (copy and dev modes) with status output and `--dry-run`
- [x] [P22-T05] `agent status` and `agent uninstall`
- [x] [P22-T06] Stale-copy note in `shelf audit`; the `init --scope project` offer shipped in P20 (v0.10.0)
- [x] [P22-T07] README and plugin README: the two install paths (plugin, `shelf agent install`) and when to use each; PRD §5, §11, §12
- [x] [P22-T08] Bump to v0.9.0; `make check` and `just all` green; PR merged; tag pushed
- [x] Regression Test Status — 383 passing at v0.9.0 (30 new in `tests/test_agent.py`); `make check` and `just all` green; dry runs against this machine's real skill folders: `--dev --source ~/c/shelf` reports all four dev links `unchanged`, copy mode skips all four with `--force` named, nothing written

### Deliverable
```bash
$ shelf agent install
Installed shelf agent skills (scope: user, mode: copy, v0.x.y)
  Claude Code (~/.claude/skills)
    shelf             created
    shelf-reference   created
  Codex / Cursor (~/.agents/skills)
    shelf             created
    shelf-reference   created
Restart any running agent session to pick up changes.
```

### Automated Verification
- `just all` passes, including the P22-TS* tests
- `make check` passes

### Manual Verification
- On this machine, `shelf agent install --dev --source ~/c/shelf` leaves the existing dev links unchanged; `shelf agent install` (copy) skips them and names `--force`
- A fresh Claude Code and Codex session each load the installed `shelf` skill

---

## [x] Project P23: One master copy of the skills, synced by a pre-commit hook (v0.9.1)
**Goal/Requirement**: The skills exist twice since P22: `plugins/shelf/skills/` for the marketplace and `src/shelf/agent_skills/` inside the Python package for `shelf agent install`. Make `plugins/shelf/skills/` the single master and keep the package copy generated from it automatically. Decided 2026-11-07.
- `scripts/sync_agent_skills.py` rebuilds the package copy from the master; `--check` reports drift; `--staged` rebuilds from the staged master so unstaged edits never enter a commit
- `lefthook.yml` pre-commit hook runs `--staged`: a staged master change syncs and stages the copy; a staged edit to the copy alone fails with guidance to edit the master
- A `GENERATED.md` marker in the package copy names the master
- README Development section and plugin README document which copy is the master

**Out of Scope**
- A single physical copy. Tested 2026-11-07 on branch `exp/single-copy-skills`: a package-side symlink breaks `uv build` ("Is a directory"); a plugin-side symlink works for Claude Code, but Codex 0.166.0 installs the plugin silently **without** its skills (control install from real files: 10/10 files). Switching to hatchling was rejected (abandons uv_build; editable installs miss mapped files).

### Tests & Tasks
- [x] [P23-TS01] Sync rebuilds the copy from the master and writes `GENERATED.md`; `--check` exits 0 in sync and 1 with the master named after a drift
- [x] [P23-TS02] `--staged`: a staged master edit is copied and the copy staged; an unstaged master edit is not copied
- [x] [P23-TS03] `--staged`: an edit to the copy alone fails (exit 1) naming the master and leaves the edit in place; nothing staged in either folder is a no-op
- [x] [P23-TS04] `lefthook.yml` wires the pre-commit command to `scripts/sync_agent_skills.py --staged`
- [x] [P23-T01] `scripts/sync_agent_skills.py`; `just sync-agent-skills` calls it; `just install-hooks` runs `lefthook install`
- [x] [P23-T02] `lefthook.yml` pre-commit hook
- [x] [P23-T03] Docs: README Development section, plugin README
- [x] [P23-T04] Bump to v0.9.1; `make check` and `just all` green; PR merged; tag `v0.9.1` pushed
- [x] Regression Test Status — 398 passing at v0.9.1 (8 new in `tests/test_skill_sync.py`); `make check` and `just all` green; live lefthook v2.2.2 smoke in a scratch clone: a master edit committed both copies, an edit to the copy alone was refused

---

## Backlog — minor
- [ ] **Skill-text fixes from the PR #18 review** (CodeRabbit, found when the skills were copied into the package; the text predates P22). Edit `plugins/shelf/skills/shelf/references/`, then `just sync-agent-skills` and bump the plugin version:
      - `add.md`: when the agent fetches a URL to a temp file, pass the URL as `--source` so the catalog keeps it
      - `init.md`: `shelf path` errors when no library exists; state the default path (`${XDG_DATA_HOME:-~/.local/share}/shelf`) directly
      - `open.md`: `shelf open` serves in the foreground; say how the agent keeps it running and reads the bound URL, or use `--static`
      - `remove.md`: `doc view` lists variants but not assets; list the folder's contents before asking to delete it
- [x] **UI favicon 404** (found in the P08 browser smoke): FIXED — `index.html.tmpl` now declares `<link rel="icon" href="data:,">`, so browsers no longer request `/favicon.ico` (no 404) in either core `file://` or enhanced mode. Regression-tested (`test_index_declares_a_favicon_to_avoid_a_404`).
- [x] Live browser smoke of the P08 UI hardening (C1 XSS / C3 copy-text / C4 search) — DONE; all three verified live with screenshots.
