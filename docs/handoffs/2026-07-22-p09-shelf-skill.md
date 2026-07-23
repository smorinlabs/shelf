# Session handoff — P09 shelf-skill (monorepo) — 2026-07-22

## 🎯 Outcome
**Goal:** Execute **P09** — build a **single `shelf` skill** as a **monorepo plugin inside the shelf repo** (authored via **skill-create**), then wire the CLI-side pieces (handoff-prompt change, Codex packaging, PRD/doc updates) and verify additivity + the end-to-end handoff.
**Out of scope:** P10 (taxonomy), P11 (template-press), P12 (multi-library), P13 (D2 concurrency) — all scoped/deferred in `PROJECTS.md`. The `shelf-library` content repo. Any change to shipped v0.8.0 CLI behavior beyond the one handoff-prompt string.

## ⚠ Portability preflight — read first
**✓ Clean & pushed.** `main @ 4edece9`, `+0 -0`; no uncommitted changes, no unpushed commits, no stashes. Everything is on `origin` (`smorinlabs/shelf`). The only local-only things are **this handoff doc until you commit it**, and the empty `~/c/shelf-skill` dir (abandoned — see below; ignore it).

## 🧭 Where you are
- **Repo:** shelf · origin `https://github.com/smorinlabs/shelf.git` · default `main`
- **Branch:** `main @ 4edece9` · repo root (this machine): `/Users/stevemorin/c/shelf` ← may differ on yours; use the repo-relative paths below
- **Build/verify:** `make check && just all` (317 tests, ruff + ty). CLI installs via `uv tool install .`.
- **Latest shipped:** **v0.8.0** (tagged + pushed). P01–P08 all complete.

## 📎 Artifacts & sources of truth
| What | Repo-relative (canonical) | Abs (this machine) | Ref |
|---|---|---|---|
| **P09 plan — the thing to execute** | `docs/superpowers/plans/2026-07-22-p09-shelf-skill.md` | `/Users/stevemorin/c/shelf/docs/superpowers/plans/2026-07-22-p09-shelf-skill.md` | P09 |
| Roadmap + the P09 decision (rationale) | `PROJECTS.md` (P09 entry) | `/Users/stevemorin/c/shelf/PROJECTS.md` | P09 |
| Spec — **needs monorepo update** | `SHELF-PRD.md` §11 (CLI surface the skill drives), §12 (skill ownership — CHANGE to single/monorepo), §14.1 (dual manifests) | `/Users/stevemorin/c/shelf/SHELF-PRD.md` | Task 5 |
| Handoff prompt to change | `src/shelf/core/handoff.py:40` (`"Use the shelf-add skill to add …"`) | `/Users/stevemorin/c/shelf/src/shelf/core/handoff.py` | Task 3 |
| Skill authoring tool | the **skill-create** skill (org pipeline) | — | Task 2 |

## 🔧 State to resume
- **Done:** P01–P08 shipped (v0.8.0). P09 **planned + decided** (shape settled).
- **In flight:** nothing half-coded — the repo is at a clean checkpoint. Next action is running skill-create (plan **Task 2**).
- **Open thread (unanswered):** I asked the user what a pending `/project-add` should capture — candidates: **S1** (assess template-press readiness for the P11 gate) or a **PRD-amendment / monorepo-reconciliation** item. Resolve before/alongside P09.
- **CI/PR:** none — this project ships direct to `main` (branch protection prints a "must use PR" notice but the push succeeds).

## 🧠 Critical context that won't survive a fresh window
- **DECISION (2026-07-22) — single `shelf` skill, progressive disclosure.** One always-on trigger; a lean `SKILL.md` routing to `references/{add,edit,find,remove,audit,open,init}.md` loaded on demand. **Why:** the seven operations are verbs of one tool (shared CLI contract, classification, confirmation), so progressive disclosure gives focused per-op loading **without** seven always-on trigger descriptions — minimal context footprint, least maintenance, fewest collision/manifest surfaces.
- **DECISION (2026-07-22) — MONOREPO.** The skill lives **in the shelf repo** (`.claude-plugin/plugin.json` + `skills/shelf/` at the repo root, alongside `src/shelf`), **not** a separate `shelf-skill` repo. This **supersedes PRD §12 / architecture** (which specified a separate repo). The empty `~/c/shelf-skill` is **abandoned**. PRD update is plan Task 5.
- **skill-create OWNS the skill's internal design** — trigger wording, on-disk placement/name, collision analysis vs. installed skills, the references split, and the skill-quality gate. Do **not** hand-author the SKILL.md; **run skill-create** (plan Task 2). The user explicitly wants skill-create to make those decisions.
- **REJECTED — don't re-derive:** seven individual skills (rejected — seven always-on descriptions pollute context); grouped 2–3 skills (rejected — worst of both: multiple manifests/triggers *and* split shared knowledge); separate `shelf-skill` repo (superseded by monorepo).
- **CONSTRAINTS:** additive — must NOT break `uv tool install` or the 317-test CLI suite, and plugin files (`skills/`, `.claude-plugin/`) must NOT leak into the built wheel (plan Task 1 verifies both). Dual-ecosystem: Claude Code **and** Codex (PRD §14.1). The skill **shells out to the `shelf` CLI** (never reimplements library logic). Direct install, no marketplace (PRD §36).
- **Sequence the user stated:** plan (✅ done) → `/project-add` (⏳ pending the clarification) → **then** skill-create authors the skill → docs updated as those decisions land.

## 👉 First action
1. `Read docs/superpowers/plans/2026-07-22-p09-shelf-skill.md` — the full task list.
2. Do **Task 1** (confirm the monorepo baseline: `make check && just all` green + `uv build` wheel excludes `skills/`/`.claude-plugin/`).
3. Do **Task 2** — invoke **skill-create** for the single `shelf` skill (progressive disclosure, monorepo target, shells out to the CLI, dual-ecosystem).
4. Resolve the open `/project-add` thread with the user.

## ℹ How this was made
digest: skipped (composed from live in-session context) · gathered 2026-07-22 · machine Steves-MacBook-Pro
