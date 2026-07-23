# shelf skill

A single Claude Code / Codex skill that drives the [`shelf`](../../README.md)
CLI to manage a personal documentation library — **add, find, edit, remove,
audit, open, and set up** documents. It ships **in the shelf repo** (monorepo):
the same repository is both the `uv`-installable CLI and this plugin.

## Design — one skill, progressive disclosure

One always-on trigger (`SKILL.md`) routes to a per-operation reference loaded on
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

## Prerequisite

The `shelf` CLI must be on `PATH` — the skill invokes it. From this repo:

```bash
uv tool install .        # installs the `shelf` command
```

## Install the plugin

### Claude Code

The repo is a Claude Code plugin: `.claude-plugin/plugin.json` at the root, with
this skill auto-discovered from `skills/shelf/`. Point Claude Code at the repo
(a local marketplace/plugin entry, or a dev symlink of `skills/shelf` into a
skills directory). The `shelf` skill then loads in every session and its trigger
fires for phrasings like "add this doc to my shelf".

### Codex

Codex loads the same `skills/shelf/SKILL.md`. Codex packaging is
`.codex-plugin/plugin.json` at the repo root, alongside the Claude Code
manifest — it points Codex at the skills directory (`"skills": "./skills/"`)
and carries the Codex `interface` block (display name, descriptions, category).

## Handoff completion

`shelf doc add <file>` with missing classification flags launches the configured
agent primed with *"Use the shelf skill to add `<path>` to shelf. Walk me
through classification."* — this skill is what that prompt lands in.

## Verification

Load verification (`skillsmith verify . --deep`, both tools):

| Tool | Version | Static | Deep |
|---|---|---|---|
| claude-code | 2.1.218 | manifest ✓ · skills ✓ | skills ✓ · no findings |
| codex | 0.144.6 | manifest ✓ | skills ✓ · no findings |

Additivity: `just all` → 317 passed, ruff + ty clean; the plugin files
(`skills/`, `.claude-plugin/`, `.codex-plugin/`) live outside `src/` and are
excluded from the built wheel (`uv_build` src layout).
