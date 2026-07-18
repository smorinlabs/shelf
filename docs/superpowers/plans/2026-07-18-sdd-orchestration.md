# Shelf SDD Orchestration Plan (P01–P08)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute each phase's detailed plan task-by-task. This document governs *who* does *what*; each phase also gets a detailed task plan in this directory before its work starts.

**Goal:** Build the `shelf` CLI (SHELF-PRD.md, amendments A+B+C applied) across phases P01–P08 using sub-agent-driven development, with Codex as the implementation engine and Claude-family agents as test authors, verifiers, and gates.

**Architecture:** Sequential phases, each in its own scratch-dir worktree and branch, driven by a fixed six-stage pipeline (brief → red → green → verify → gate → merge/tag). Model assignment follows the SDD Agent/Model Matrix with one deliberate inversion, documented below.

**Tech Stack:** Python ≥3.12, uv (src layout), click, pytest, ruff, ty, just + make, git worktrees; agents: fable (orchestrator), sonnet, opus, haiku, codex.

## Global Constraints

- The PRD (`SHELF-PRD.md`) is the spec of record; the CLI conforms to cli-design-standard v1.4.14 with the three documented waivers in PRD §5.
- Grammar is noun-verb: `doc add/list/view/update/move/delete`, `doc format add/delete`, `doc adopt`, `orphan list/delete`, `topic|kind add/list`, top-level `init/audit/open/path/regen/migrate`.
- Test-first always: no implementation lands before its failing test exists (Steve's process).
- Conventional Commits; each phase tags `v0.N.0` at its gate; pushes/tags only with Steve's confirmation.
- Agents never switch branches in the live checkout (`~/c/shelf`); all mutating work happens in the phase worktree under the scratch dir.
- `make check` then `just all` must be green at every phase gate.
- PROJECTS.md is the task tracker; statuses flip as tasks complete (haiku).

---

## Roles — the matrix, applied

| Agent | Assignment in this plan |
|---|---|
| **fable** (this session) | Orchestrates. Writes each phase's detailed plan and brief; runs phase gates (`/code-review`, PRD spot-check); merges, tags, pushes (with confirmation); final whole-branch review at v0.8.0. |
| **sonnet** | Writes the failing tests (every `P##-TS` item) from the PRD + phase plan, *before* Codex sees the task. Runs verification passes: full pytest, `make check`, `just all`, conformance smoke. |
| **codex** | **All implementation** (Steve's directive) — makes red tests green, task by task, in the phase worktree. Never edits test files. Also co-signs pre-mutation gates for live-state pilots (operational safety review, distinct from code review). |
| **opus** | Escalation debug loops (after two failed verify rounds, with superpowers:systematic-debugging). Live-state pilots: P07 `init --github` against a scratch repo, P08 real handoff launch. P03 crash-injection pass. |
| **haiku** | Mechanical: PROJECTS.md status flips, broken-library fixture generation from recipes (P05), doc syncs. |

**The lens inversion (deliberate deviation from the matrix, same intent).** The matrix normally has Codex adversarially reviewing Claude-authored code. With Codex authoring, the cross-model-family property is preserved by inversion: **sonnet authors the tests as a cross-family contract before Codex sees the task**, and **fable reviews every diff at the gate**. Codex still co-signs *operational* pre-mutation gates (P07/P08 pilots), where the question is "is this safe to run live," not "is my code good." The v0.8.0 whole-branch review adds a fresh-context Codex adversarial pass over the entire branch plus fable's independent review.

---

## The phase pipeline (identical for every phase)

1. **Brief + detailed plan (fable).** Write `docs/superpowers/plans/2026-MM-DD-p0N-<slug>.md` in writing-plans format from the PRD sections + PROJECTS.md `P##` items. The phase's tasks, exact files, and interfaces are locked here.
2. **Worktree (fable).** `git worktree add <scratch>/shelf-p0N -b p0N-<slug> main`. All agents work only in this path.
3. **Red (sonnet).** Write every `P##-TS` failing test per the plan; run to confirm they fail for the right reason; commit test files (`test: …`).
4. **Green (codex).** Implement task-by-task to make tests pass; conventional commits per task; never touches `tests/`. Discovers-a-spec-problem → stop and report to fable, don't improvise.
5. **Verify (sonnet).** Full suite + `make check` + `just all` + conformance smoke. Failures route back to codex (max 2 rounds) → then **opus debug loop**. If a task grows branching logic mid-run, upgrade the tier rather than stretching the recipe.
6. **Gate (fable).** `/code-review` on the branch diff; spot-check against the PRD sections; **haiku** flips PROJECTS.md checkboxes + Regression Test Status; merge to `main` (no branch switch in the live checkout — merge via worktree or `git -C`); tag `v0.N.0`; push branch+tag **only with Steve's confirmation**; remove worktree.

**Failure discipline:** before acting on any agent stop/failure signal, verify actual worktree and test state — signals can be stale. Read-only work (recon, test authoring across independent suites) may parallelize; mutating work is single-writer in the phase worktree, sequential.

---

## Per-phase assignments

| Phase | Version | Character | Dev | Extra safeguards beyond the pipeline |
|---|---|---|---|---|
| **P01** package foundation | v0.1.0 | mechanical-plus | codex | Detailed plan already written: `2026-07-18-p01-package-foundation.md` |
| **P02** config + catalog core | v0.2.0 | standard; the atomicity core | codex | fable reviews the lock/temp-rename design *before* green; sonnet's failure-injection tests (TS02) are the phase's centerpiece |
| **P03** document lifecycle | v0.3.0 | tricky — rollback machinery | codex | **opus** post-implementation crash-injection/property pass over the §5 commit-point ordering |
| **P04** update + move | v0.4.0 | standard | codex | — |
| **P05** audit + regen | v0.5.0 | standard, fixture-heavy | codex | **haiku** generates the broken-library fixture set from a recipe (one fixture per audit check) before red |
| **P06** the UI | v0.6.0 | standard + visual | codex | fable manual browser verification (claude-in-chrome) of core + enhanced modes at the gate — automated tests can't judge the page |
| **P07** git + GitHub | v0.7.0 | **live-state** | codex | Gate-before-mutation: fable + codex concur on the pilot; **opus** pilots `init --github` once against a scratch repo with rollback (`gh repo delete`) before any suite touches the network. GraphQL-avoidant `gh api` REST; ≥20s poll floor |
| **P08** handoff | v0.8.0 | live-state-ish | codex | **opus** pilots one real handoff launch (and the in-session detection path). Then the **final whole-branch review**: fable + fresh-context codex adversarial pass over v0.1.0→v0.8.0 before v1.0 planning |
| P09 template-press layer | v1.0.0 | deferred | — | Blocked on template-press readiness; replan when it lands |

---

## Standing execution notes

- **Codex task packets** include: worktree path, the task's plan section verbatim, the relevant PRD §§, the "never edit tests / stop on spec conflict" rule, and the conventional-commit format with the session trailer.
- **Version floor discipline:** version strings live in `pyproject.toml` only; the phase gate bumps it (`0.N.0`) before tagging.
- **PRD is upstream:** any implementation discovery that contradicts the PRD becomes a mini-amendment (same draft-first flow), never a silent divergence.
- **Session continuity:** each phase's Codex agent is continued via SendMessage where context helps (same phase); a new phase starts a fresh Codex context.
