# Shelf skills

Claude Code / Codex skills that drive the [`shelf`](../../README.md)
CLI to manage a personal documentation library — **add, find, edit, remove,
audit, open, and set up** documents. It ships **in the shelf repo** (monorepo):
the same repository is the `uv`-installable CLI, a **plugin**, and its own
**marketplace**.

## Design — library management and reference authoring

The `shelf` trigger (`SKILL.md`) routes to a per-operation reference loaded on
demand, so a session only pays for the operation at hand:

| Reference | Operation | Drives (`shelf …`) |
|---|---|---|
| `references/add.md` | add a document / format / topic / kind | `doc add`, `doc format add`, `topic add`, `kind add` |
| `references/find.md` | find / retrieve (read-only) | `doc list`, `doc view` |
| `references/edit.md` | edit metadata / relocate | `doc update`, `doc move`, `doc format delete` |
| `references/remove.md` | delete a document | `doc delete --yes` |
| `references/audit.md` | audit / repair / regen / migrate / orphans | `audit`, `regen`, `migrate`, `doc adopt`, `orphan …` |
| `references/open.md` | open the library UI | `open` |
| `references/init.md` | create / adopt a library | `init`, `init --adopt` |

**Invariant:** every operation shells out to the `shelf` CLI; the skill
classifies intent and confirms, and never edits the catalog or library files
directly.

## Prerequisite — the `shelf` CLI on `PATH`

The skill invokes `shelf`, so it must resolve. Either:

- **Install it:** `uv tool install .` from the repo root, or
- **Local-run wrapper (no install):** a `~/.local/bin/shelf` that execs
  `uv run --project <repo> shelf "$@"` — runs the repo's entry point via `uv`
  while preserving your cwd (so the CLI's git-remote / repo inference works).

## Repo layout — marketplace + plugin

```
shelf/                                  ← repo root = the marketplace
├── .claude-plugin/marketplace.json     ← Claude catalog (primary)
├── .agents/plugins/marketplace.json    ← Codex catalog
├── .agents/skills/shelf                → plugins/shelf/skills/shelf
├── .agents/skills/shelf-reference      → plugins/shelf/skills/shelf-reference
└── plugins/shelf/                      ← the plugin
    ├── .claude-plugin/plugin.json      ← superset manifest (primary, real file)
    ├── .codex-plugin/plugin.json       → ../.claude-plugin/plugin.json  (symlink)
    └── skills/
        ├── shelf/                      ← management skill + guides
        └── shelf-reference/            ← authoring skill + assets/reference.html
```

The plugin manifest is a single **symlinked superset** — Claude Code ignores
the Codex-only key it doesn't use, so one file serves both (verified strict-clean
via `skillsmith verify --deep --strict`). Codex display metadata (displayName,
category) lives in the Codex marketplace catalog, not the manifest.

## Install

The repo is a marketplace named `shelf` whose single plugin is `shelf`.

**Claude Code:**
```bash
/plugin marketplace add https://github.com/smorinlabs/shelf   # or a local clone path
/plugin install shelf@shelf
# CLI equivalent: claude plugin marketplace add <path> && claude plugin install shelf@shelf
```

**Codex:**
```bash
codex plugin marketplace add https://github.com/smorinlabs/shelf   # or a local clone path
codex plugin add shelf@shelf
```

**Local development (dev-symlink, no marketplace):** for iterating on the skill,
symlink it so edits are live in every session:
```bash
skillsmith dev shelf --source plugins/shelf/skills/shelf --tool claude-code
skillsmith dev shelf --source plugins/shelf/skills/shelf --tool codex
```

## Handoff completion

`shelf doc add <file>` with missing classification flags launches the configured
agent primed with *"Use the shelf skill to add `<path>` to shelf. Walk me
through classification."* — this skill is what that prompt lands in.

## Verification

Installed and run **end-to-end on both ecosystems** (2026-07-24):

| Tool | Version | Install | Skill runs |
|---|---|---|---|
| Claude Code | 2.1.218 | `/plugin install shelf@shelf` ✓ | headless session invoked the skill → ran `shelf --version` / `doc list` ✓ |
| Codex | 0.145.0 | `codex plugin add shelf@shelf` ✓ | `codex exec` exposed the skill → ran `shelf --version` / `doc list` ✓ |

`skillsmith verify --deep --strict plugins/shelf` → both tools pass, no findings.
Additivity: `just all` → 317 passed, ruff + ty clean; the plugin files
(`plugins/`, `.claude-plugin/`, `.agents/`) live outside `src/` and are excluded
from the built wheel (`uv_build` src layout).

## Research a reference versus save a file

Use `shelf` to save an existing file or manage the library. Use `shelf-reference` to
research a supplied resource link and synthesize an original HTML reference page.
It loads shelf's existing add/find/edit guides via sibling paths, authors outside
the library using `assets/reference.html`, previews the result/diff, then saves with
ordinary `shelf doc add` or `shelf doc format add ID FILE --replace`. No Python,
catalog schema, sidecar, renderer command, server or index changes are involved.

The template separates researched facts, cost, license, citations, research date,
original saved date and user notes, with optional resource-specific sections. Updates
preserve notes, hand edits, IDs and original dates; ambiguity requires reconciliation.
Deduplication and preservation are skill responsibilities, not new CLI guarantees.

Manual creation needs no provenance tag. Automated creation requires exactly
`automated` and the explicitly supplied job name (for example `daily-email`) as
provenance tags, plus ordinary subject tags. Updates retain original creation tags:
an automated refresh of a manual entry does not add automation tags. Unknown history
is not inferred. Use `--tag` on creation and `--add-tag` for approved subject enrichment;
never replace all tags during refresh. Filter a creation job exactly with
`shelf doc list --tag automated --tag daily-email --json`.

Both plugin manifests already discover `./skills/`; no metadata change is needed.
The historical host-install verification above covers the original shelf skill only.
The new authoring skill requires a separate live Claude Code/Codex smoke test before
claiming host integration; local symlink and copied-plugin resource checks are separate.
