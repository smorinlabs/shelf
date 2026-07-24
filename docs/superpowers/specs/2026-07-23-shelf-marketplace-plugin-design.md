# Shelf as a dual marketplace + plugin — design (2026-07-23)

**Goal:** Make the `shelf` repo a spec-compliant **marketplace *and* plugin** for **both Claude Code and Codex**, so others can install the `shelf` skill through each ecosystem's native flow — while keeping **Claude Code as the canonical/primary layout and Codex symlinking into it where the formats allow.** Fulfills **P14**.

**Non-goals:** the `shelf-library` content repo; changing CLI behavior; publishing to any *hosted* third-party marketplace (self-hosted/in-repo marketplace only); resolving Codex bug [#22078](https://github.com/openai/codex/issues/22078) (worked around, not fixed).

---

## Background

P09 shipped a single `shelf` skill as an in-repo plugin (`.claude-plugin/plugin.json` + `.codex-plugin/plugin.json` + `skills/shelf/` at the repo root) and dev-installed it via `skillsmith` (filesystem symlinks into `~/.claude/skills` and `~/.agents/skills`). That works for *use* but is not a *marketplace*, so others can't `/plugin install` (Claude) or `codex plugin add` (Codex).

Two research findings shape this work:

1. **Both ecosystems put the plugin in a *subdirectory* of the marketplace**, not at the repo root. Claude's example uses `plugins/<plugin>/`; Codex states "a repo cannot simultaneously be both the marketplace root and a single plugin root." So the plugin moves into `plugins/shelf/` and the repo root becomes the marketplace.
2. **Neither ecosystem installs a plugin without a marketplace catalog**, but the catalog can be **local / in-repo** (Claude: `.claude-plugin/marketplace.json`; Codex: `.agents/plugins/marketplace.json`). No hosted registry is required.

**Caveat (documented, not fixed):** Codex's local-marketplace path has an open bug (#22078) where a plugin shows enabled but its skills aren't exposed in sessions. The in-repo `.agents/skills` filesystem-discovery symlink is the reliable fallback.

---

## Target layout

```
shelf/                                   ← repo root = the marketplace
├── .claude-plugin/marketplace.json      ← Claude catalog (PRIMARY)
├── .agents/plugins/marketplace.json     ← Codex catalog (parallel; different schema)
├── .agents/skills/shelf                 → symlink → ../../plugins/shelf/skills/shelf  (Codex discovery fallback)
├── plugins/
│   └── shelf/                           ← the plugin, self-contained
│       ├── .claude-plugin/plugin.json   ← superset manifest (PRIMARY, real file)
│       ├── .codex-plugin/plugin.json    → symlink → ../.claude-plugin/plugin.json
│       ├── README.md
│       └── skills/
│           └── shelf/                    ← SKILL.md + references/ (the one shared skill tree)
├── src/shelf/                           ← the CLI — untouched, still the only thing in the wheel
├── tests/  pyproject.toml  justfile  SHELF-PRD.md  PROJECTS.md  …
```

The plugin dirs (`plugins/`, `.claude-plugin/`, `.agents/`) live at the repo root, outside `src/`, so `uv_build`'s src layout still excludes them from the wheel (re-verified in the plan).

---

## Component design

### 1. Plugin manifest — one symlinked superset file (tested)

`plugins/shelf/.claude-plugin/plugin.json` is the single real manifest; `plugins/shelf/.codex-plugin/plugin.json` is a **symlink** to it. This is "Claude primary, Codex symlinks in" applied to the manifest, not just the skills.

The superset carries the keys both tools accept, and **omits `interface`**:

```json
{ "name": "shelf", "version": "0.1.0", "description": "…",
  "author": { "name": "Steve Morin" },
  "keywords": ["shelf","documentation","library","catalog","cli","codex","claude-code"],
  "skills": "./skills/" }
```

**Evidence (probed 2026-07-23 with `skillsmith verify --deep --strict`):**
- Superset **with** `interface` → Codex `pass`, Claude `warn` ("unknown field `interface`, ignored"), fails `--strict`.
- Superset **without** `interface` → **both `pass`, strict-clean** (Claude silently ignores `skills`; Codex tolerates `author`/`keywords`).

Codex's display metadata (`displayName`, descriptions, `category`) is **not lost** — it relocates to the Codex marketplace catalog (below), where catalog-display metadata belongs.

### 2. Two marketplace catalogs — parallel files (schemas genuinely differ)

The two catalog schemas differ enough that they can't be one file; both are authored from the same values, Claude first.

**Claude — `.claude-plugin/marketplace.json` (primary):**
```json
{ "name": "shelf",
  "owner": { "name": "Steve Morin" },
  "plugins": [ { "name": "shelf", "source": "./plugins/shelf",
                 "description": "…", "version": "0.1.0" } ] }
```
`shelf` is not a reserved Claude marketplace name. Install: `/plugin marketplace add <repo|local>` → `/plugin install shelf@shelf`.

**Codex — `.agents/plugins/marketplace.json` (parallel):**
```json
{ "name": "shelf",
  "interface": { "displayName": "Shelf" },
  "plugins": [ { "name": "shelf",
    "source": { "source": "local", "path": "./plugins/shelf" },
    "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
    "category": "Development", "version": "0.1.0", "description": "…" } ] }
```
Install: `codex plugin marketplace add <repo|local>` → `codex plugin add shelf@shelf`.

### 3. Symlink strategy

- **Skills:** one shared tree at `plugins/shelf/skills/shelf/`; both manifests reference it (no per-manifest copy).
- **Plugin manifest:** `.codex-plugin/plugin.json` → `../.claude-plugin/plugin.json` (symlink; tested).
- **Codex discovery fallback:** committed in-repo symlink `.agents/skills/shelf → ../../plugins/shelf/skills/shelf`, so Codex finds the skill by filesystem discovery **without** the marketplace — the hedge against #22078.
- **Marketplace catalogs:** parallel real files (different schemas), Claude authored first.
- **Machine-level `skillsmith` placements:** repoint `~/.claude/skills/shelf` and `~/.agents/skills/shelf` from today's `skills/shelf` to `plugins/shelf/skills/shelf` (one `skillsmith` re-adopt).

### 4. Naming & versioning

Marketplace `shelf`, plugin `shelf` (so `shelf@shelf` in both ecosystems). Plugin stays `v0.1.0`. CLI version (`pyproject.toml`) is unchanged.

---

## The one empirically-unresolved corner — RESOLVED (2026-07-24)

**Codex `source.path` resolution** was ambiguous in the docs. Resolved empirically against Codex 0.145.0 and a working marketplace on the machine (`py-launch-blueprint`):
- **`source.path` is relative to the repo root** — `"./plugins/shelf"` is correct (matches `py-launch-blueprint`'s `"./plugins/astral"`). Codex resolved it to `<repo>/plugins/shelf`.
- **`policy.authentication` must be `ON_INSTALL` or `ON_USE`** — the docs' `ON_FIRST_USE` is invalid and was rejected. Using `ON_INSTALL`.
- **`category`** set to `"Development"` (a known-valid value).
- **Bug #22078 did not manifest** on Codex 0.145.0 — `codex exec` exposed the installed plugin's skill and followed it. The `.agents/skills` discovery symlink remains as a belt-and-suspenders fallback.

---

## Verification plan

- `just all` → 317 passing, ruff + ty clean (unchanged CLI).
- `uv build` wheel excludes `plugins/`, `.claude-plugin/`, `.agents/` (src layout).
- `skillsmith verify --deep --strict plugins/shelf` → claude-code + codex both `pass`.
- Empirical: `claude plugin marketplace add .` and `codex plugin marketplace add .` against the local repo resolve the plugin; record what worked. (Full `/plugin install` / `codex plugin add` confirmation where the tooling allows.)
- README documents both install flows, the CLI prerequisite (local-run wrapper or `uv tool install`), and the #22078 fallback.

## Success criteria

1. Repo is a compliant marketplace containing the self-contained `shelf` plugin, for both ecosystems.
2. Plugin manifest is a single symlinked superset file, strict-clean on both tools.
3. Claude install path works: `/plugin marketplace add` → `/plugin install shelf@shelf`.
4. Codex has a working path (marketplace `codex plugin add` where #22078 permits, else the `.agents/skills` discovery symlink), documented.
5. Additive: CLI green, wheel clean, `shelf` still installs/runs.

## Risks

- **Codex #22078** — local-marketplace skills may not surface; mitigated by the discovery symlink.
- **Codex `source.path`** — resolved empirically; layout may need a small adjustment.
- **`skillsmith` repoint** — after merge + `git pull` in the main checkout, re-adopt the placements to the new skills path.
