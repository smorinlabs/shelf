# P09 — Single `shelf` Skill (Monorepo) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement the code/doc tasks. The skill-authoring task (Task 2) hands off to the **skill-create** skill, which owns the skill's internal design decisions — this plan orchestrates around it. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add a single `shelf` skill to the **shelf repo itself** (monorepo: one repo that is both a `uv`-installable CLI and a Claude Code / Codex plugin), completing P08's handoff so an agent launched by `shelf doc add` lands in a working skill.

**Architecture:** The shelf repo becomes dual-purpose — the existing `src/shelf` package (installed via `uv tool install`) **plus** a plugin defined by `.claude-plugin/plugin.json` + `skills/shelf/` at the repo root. The skill is a **single `shelf` skill with progressive disclosure** (lean `SKILL.md` routing to per-operation `references/*.md`), each shelling out to the `shelf` CLI. The skill itself is authored by **skill-create** (pre-skill design, trigger authoring, collision analysis, references, dual-ecosystem wiring, skill-quality gate); this plan preps the monorepo, sequences skill-create, and wires the CLI-side pieces (handoff prompt, docs) around it.

**Tech Stack:** Claude Code / Codex plugin format (`.claude-plugin/plugin.json`), Markdown skills, the existing Python CLI (click/uv/pytest), the org **skill-create** pipeline.

## Global Constraints

- **Monorepo, additive** — adding the plugin must NOT disturb `src/shelf`, `pyproject.toml`, the justfile, the test suite, or `uv tool install`. The CLI keeps working exactly as at v0.8.0.
- **Single `shelf` skill, progressive disclosure** — one always-on trigger; `SKILL.md` routes to `references/{add,edit,find,remove,audit,open,init}.md` loaded on demand (P09 decision, 2026-07-22).
- **Skill shells out to the `shelf` CLI** — the skill never reimplements library logic; it reads intent → runs the right `shelf` command → confirms (PRD §12).
- **Dual-ecosystem** — the plugin must work as both a Claude Code plugin and a Codex plugin, verified/tested against both (PRD §14.1). Direct install, no marketplace initially (PRD §36).
- **skill-create owns the skill's internal design** — trigger wording, exact placement, collision analysis vs. installed skills, the references split, and the skill-quality gate are skill-create's decisions, not this plan's. This plan must not pre-empt them.
- **Spec departure recorded** — this monorepo layout supersedes PRD §12 / architecture (which specified a *separate* `shelf-skill` repo). Task 5 updates the PRD; the empty `~/c/shelf-skill` repo is abandoned.

---

## File Structure

- **`.claude-plugin/plugin.json`** (repo root, created/wired by skill-create) — the Claude Code plugin manifest; makes the repo a plugin.
- **`skills/shelf/SKILL.md`** (created by skill-create) — the single skill: one trigger, routing body.
- **`skills/shelf/references/{add,edit,find,remove,audit,open,init}.md`** (created by skill-create) — per-operation guides, loaded on demand.
- **Codex plugin manifest/adapter** (path per Codex format, resolved at build time) — the Codex packaging of the same skill.
- **`src/shelf/core/handoff.py`** (modified) — the primed prompt now names the actual skill.
- **`tests/test_handoff.py`** (modified) — the prompt assertion updated to the new skill name.
- **`SHELF-PRD.md`**, **`PROJECTS.md`** (modified) — architecture updated to the monorepo; P09 marked done.

---

### Task 1: Monorepo scaffolding — establish the plugin location, prove additivity

**Files:**
- Create: `.claude-plugin/` directory placeholder at repo root (skill-create fills `plugin.json` in Task 2)
- Test: `tests/test_conformance.py` (or the existing packaging/smoke test) — assert `uv tool install`/import still works

**Interfaces:**
- Produces: the repo-root plugin location that Task 2's skill-create run targets; a green baseline proving the CLI is undisturbed.

- [ ] **Step 1: Confirm the current green baseline**

Run: `make check && just all`
Expected: 317 passing, ruff + ty clean (the v0.8.0 baseline). Record it — Task 1 must not change it.

- [ ] **Step 2: Confirm the plugin location does not collide with the package**

Verify `skills/` and `.claude-plugin/` are absent today and are not swept into the built wheel: check `pyproject.toml`'s package config includes only `src/shelf`. If a build-inclusion glob would pull `skills/` into the wheel, add an exclude.

Run: `uv build 2>&1 | tail -3 && python -c "import zipfile,glob; z=zipfile.ZipFile(sorted(glob.glob('dist/*.whl'))[-1]); print([n for n in z.namelist() if 'skills/' in n or '.claude-plugin' in n] or 'clean: no plugin files in wheel')"`
Expected: `clean: no plugin files in wheel` — the plugin files ride in the repo, not the pip artifact.

- [ ] **Step 3: Commit the baseline note**

```bash
git commit --allow-empty -m "chore(p09): confirm monorepo baseline — CLI green, plugin files excluded from wheel"
```

---

### Task 2: Author the `shelf` skill via skill-create

**This task hands off to the `skill-create` skill.** It owns the skill's internal design; this plan supplies the inputs and the acceptance bar.

**Inputs to give skill-create:**
- One **single `shelf` skill**, **progressive disclosure**: lean `SKILL.md` (one broad-but-reliable trigger covering "add / find / manage / audit documents in your shelf library") routing to `references/{add,edit,find,remove,audit,open,init}.md`.
- Target: **this repo** (monorepo) — plugin manifest + `skills/shelf/` at repo root.
- Behavior: each operation **shells out to the `shelf` CLI** (e.g. `shelf doc add …`, `shelf audit`, `shelf doc list`); the skill drives classification/confirmation, never library mutation directly. Reference the CLI surface in `SHELF-PRD.md` §11.
- Dual-ecosystem: package for **both** Claude Code and Codex (PRD §14.1).

**skill-create owns (do not pre-decide here):** the exact trigger wording, the skill's on-disk name/placement, the conflict/collision analysis against installed skills, the references decomposition, and the skill-quality gate.

- [ ] **Step 1: Run skill-create** with the inputs above; let it run pre-skill design (its ≤3 clarifying questions, four-verdict conflict analysis), author `SKILL.md` + `references/*.md`, wire `.claude-plugin/plugin.json`, and gate with skill-quality.
- [ ] **Step 2: Record the skill's final name** (skill-create decides it) — later tasks reference it as `<SKILL_NAME>`.
- [ ] **Step 3: Verify additivity** — `make check && just all` still green (the skill files are outside `src/`), and `uv tool install .` still places `shelf` on PATH.
- [ ] **Step 4: Commit** the skill-create output.

---

### Task 3: Point the handoff prompt at the real skill

**Files:**
- Modify: `src/shelf/core/handoff.py` (`build_handoff_prompt`)
- Test: `tests/test_handoff.py`

**Interfaces:**
- Consumes: `<SKILL_NAME>` from Task 2 (the skill's final name — `shelf` unless skill-create chose otherwise).

- [ ] **Step 1: Update the failing test** — change the prompt assertion in `tests/test_handoff.py::test_build_handoff_prompt_single_path` from `shelf-add skill` to the new name:

```python
def test_build_handoff_prompt_single_path():
    prompt = handoff.build_handoff_prompt([Path("/tmp/a.md")])
    assert prompt == "Use the shelf skill to add `/tmp/a.md` to shelf. Walk me through classification."
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_handoff.py -k build_handoff_prompt -q`
Expected: FAIL (current prompt still says `shelf-add`).

- [ ] **Step 3: Update `build_handoff_prompt`** in `src/shelf/core/handoff.py` — change the literal `Use the shelf-add skill to add …` to `Use the shelf skill to add …` (keep the sanitized-path interpolation and the trailing "Walk me through classification." unchanged).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_handoff.py -q && uv run pytest -q`
Expected: PASS (full suite green).

- [ ] **Step 5: Commit**

```bash
git add src/shelf/core/handoff.py tests/test_handoff.py
git commit -m "feat(p09): handoff prompt references the single 'shelf' skill"
```

---

### Task 4: Codex packaging + dual-ecosystem verification

**Files:**
- Create/verify: the Codex plugin manifest/adapter (format resolved against current Codex plugin docs at build time, per PRD §14.1)

- [ ] **Step 1: Verify the Claude Code side** — install the repo as a local plugin in a Claude Code session; confirm the `shelf` skill appears and its trigger fires for a representative phrasing ("add this doc to my shelf").
- [ ] **Step 2: Verify the Codex side** — package the same skill for Codex (adapter/manifest per current Codex docs); confirm it loads and the trigger fires in a Codex session.
- [ ] **Step 3: Record the verification** (which versions of each ecosystem, what fired) in the skill's README / a `docs/` note.
- [ ] **Step 4: Commit** the Codex adapter + verification note.

---

### Task 5: Docs — record the monorepo pivot

**Files:**
- Modify: `SHELF-PRD.md` (§12 skill ownership, the `shelf-skill`/architecture sections, §14.1)
- Modify: `PROJECTS.md` (flip P09 to `[x]`, Regression line)

- [ ] **Step 1: Update `SHELF-PRD.md`** — change the architecture from a *separate* `shelf-skill` repo to the **monorepo**: the `shelf` repo is both the CLI and the plugin; the skill is a **single `shelf` skill** (not seven); note `~/c/shelf-skill` is abandoned. Update §14.1 (dual manifests now live in the shelf repo).
- [ ] **Step 2: Flip P09 in `PROJECTS.md`** to `[x]`, with a Regression line: skill authored via skill-create, dual-ecosystem verified, handoff wired, monorepo additive (CLI still green, `uv tool install` works).
- [ ] **Step 3: Commit** the docs.

---

### Task 6: Phase gate — end-to-end verification

- [ ] **Step 1: Additivity** — `make check && just all` green; `uv tool install .` places `shelf` on PATH; `uv build` wheel excludes plugin files (Task 1 Step 2 re-run).
- [ ] **Step 2: End-to-end handoff** (the payoff) — in a shell (not inside an AI session), `shelf doc add <file>` with no classification flags launches the agent; the agent finds the `shelf` skill (via the primed prompt) and can drive `shelf doc add …` to completion. (A shim-based smoke like P08's, plus one real manual run.)
- [ ] **Step 3: Merge + tag** if versioning the plugin; push per standing order; remove any worktree; zombie sweep.

---

## Self-Review

**Spec coverage:** P09 decision (single skill, progressive disclosure) → Task 2. Monorepo + additivity → Tasks 1, 6. Dual manifests (§14.1) → Tasks 2, 4. Handoff completion (§11.2) → Task 3 + Task 6 Step 2. Docs/PRD departure → Task 5. All covered.

**Placeholder scan:** the one deliberate deferral is Task 2's skill internals + Task 4's Codex manifest format — both are explicitly owned by skill-create / build-time verification (PRD §14.1), not TODOs. Task 3 (the only from-scratch code) carries full code + commands.

**Type consistency:** `<SKILL_NAME>` produced by Task 2, consumed by Task 3; Task 3's prompt string matches `build_handoff_prompt`'s existing format (only the skill name changes).

**Note:** this is an orchestration plan — most tasks are wiring/docs, not code-TDD, because the skill authoring is skill-create's job. That is intentional, not a gap.
