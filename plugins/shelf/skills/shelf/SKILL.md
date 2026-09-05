---
name: shelf
description: Manage a personal document library through the shelf CLI, adding, finding, editing, removing, auditing, and opening documents. Use when the user says "add this to my shelf", "what do I have in shelf about X", "grab my notes from shelf", or "audit my shelf". Not for merging documents (document-merge) or locating repos (repo-finder).
allowed-tools: Bash, Read, WebFetch
---

# shelf — manage your shelf documentation library

Route the user's intent to the right `shelf` CLI operation, drive classification
and confirmation, and let the CLI own every mutation. One skill, seven
operations, each detailed in a reference loaded on demand.

## Invariants (every operation)

- **Shell out to the `shelf` CLI. Never edit `catalog.json`, `index.html`, or
  any file under the library directly.** The CLI copies documents, writes the
  catalog, regenerates the UI, and (in a git library) commits. The skill reads
  intent, runs the right command, and confirms the result.
- **Preview before mutating.** Where a command supports `--dry-run`, run it
  (add `--json` when parsing) to show the user what will happen, then run for
  real on confirmation.
- **Confirm destructive or ambiguous actions.** Deletes, moves, and any
  plural-match resolution get an explicit confirmation first.
- **Commit when the library is a git repo.** Pass `--commit` on mutating
  commands when the library is version-controlled; omit it otherwise.
- **First run:** if no library is configured (`shelf path` errors, no catalog),
  route through `references/init.md` before the requested operation.

## Routing

Match the user's intent to one row, load **only** that reference, then follow it.

| The user wants to… | Load | Drives (`shelf …`) |
|---|---|---|
| add a document, a new format, a topic, or a kind | `references/add.md` | `doc add`, `doc format add`, `topic add`, `kind add` |
| find / retrieve / use a shelf doc as context | `references/find.md` | `doc list`, `doc view` (read-only) |
| edit metadata, reclassify, retitle, or relocate | `references/edit.md` | `doc update`, `doc move`, `doc format delete` |
| remove / delete a document | `references/remove.md` | `doc delete --yes` |
| audit, repair, regen, migrate, or adopt orphans | `references/audit.md` | `audit`, `regen`, `migrate`, `doc adopt`, `orphan …` |
| open the library UI | `references/open.md` | `open` |
| create, adopt, or register a library | `references/init.md` | `init`, `init --adopt` |

When intent is ambiguous, ask one question to disambiguate, then route. When a
request spans operations (e.g. "add this and then show me what I have"), handle
them one at a time in order.

## Red Flags

| Thought | Reality |
|---|---|
| "I'll just edit `catalog.json` / `index.html` to fix this" | Never. The CLI owns library state; the skill only shells out. |
| "Delete looks clear, skip the confirmation" | Deletes remove the entry *and* its folder. Show exactly what's lost, then confirm. |
| "One match is probably right, run it" | Resolve plural matches with the user before acting on an id. |
| "Run the real add straight away" | Preview with `--dry-run --json` first, then run for real on confirmation. |

## See also

- `references/*.md` — one guide per operation, loaded on demand.
- `shelf --help` / `shelf <cmd> --help` — the authoritative CLI surface; this
  skill drives it and never reimplements it.
