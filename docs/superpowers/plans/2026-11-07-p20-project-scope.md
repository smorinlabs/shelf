# P20 — Project-scoped libraries: implementation plan (2026-11-07)

Implements Part 1 of `docs/superpowers/specs/2026-11-05-scopes-and-publishing-design.md`,
plus the two items P22 handed over (P22-TS10 scope question, the `init --scope project`
offer). One branch, one PR, v0.10.0, plugin 0.2.0.

## Decisions the spec leaves open (chosen here)

| # | Question | Choice | Why |
|---|---|---|---|
| I1 | Which config settings apply? | Settings follow the **target library**: a project target uses defaults < user file < project file (R5.1); a user target uses the user file only. `library` is per scope and never merged; `browser` comes from the user file only (a cloned repo must not pick the command `shelf open` runs). `--config PATH` replaces both files, so no project scope is discovered. `init --scope project` writes `remove-source = false` explicitly. | A project's `remove-source = false` must not leak into `doc add --scope user` |
| I0 | Discovery boundary | Walk up from the current directory; check each directory for `.shelf/shelf_config.toml`, and stop after the first directory where `.git` **exists** (a directory, or a file in a git worktree) | Worktrees have a `.git` file; `.shelf/` sits beside `.git` at the top |
| I2 | Where `--scope` lives | A per-command option on every library command (`--scope user\|project`, plus `all` on `doc list`, `doc view`, `path`) | The spec's examples (`doc list --scope all`, `path --scope all`) are per-command |
| I3 | Single-target resolution | `--scope project` → the project library (exit 2 if none; exit 2 with `--library`). `--scope user` → `--library` > `SHELF_LIBRARY` > user config. No `--scope` → `--library` > `SHELF_LIBRARY` > project > user config > error. | The spec's chain; `--library`/env are explicit overrides of the user slot |
| I4 | Reads when `--library`/`SHELF_LIBRARY` is set | Only that library (labeled `user`) | An explicit override names one library |
| I5 | `doc view` id present in both scopes | Exit 5 (conflict), naming both scopes and `--scope` | Never silently pick one copy |
| I6 | `init --scope project` outside a Git repo | Refused (exit 1) | The scope is defined as committed in a repo |
| I7 | Project root | The `git rev-parse --show-toplevel` of the current directory | Discovery stops at `.git`, so the marker must sit at the top |
| I8 | Ignored `index.html` in `--commit` | `git_commit_all` drops paths that are ignored and untracked | `git add` refuses an explicitly named ignored path |
| I9 | `doc move --to-scope` anchor | Keeps the anchor; a missing target topic needs `--create-topic`; exclusive with `--topic`/`--repo` | Same rule as `doc add` |
| I10 | Leftover after a failed `--to-scope` | `audit` reports an id present in both scopes (new check, code `cross-scope-duplicate`) | The spec's recovery path |
| I12 | `doc move --to-scope` when the target lacks the kind | Refused, naming `shelf kind add <kind> --scope <target>` | `doc add` never creates kinds either |
| I13 | Fresh clone without `index.html` (gitignored at project scope) | `open` rebuilds a missing index before serving; `audit` reports it with remediation `shelf regen` | Spec: rebuilt by `regen`, `open`, `publish` |
| I14 | Agent project root | The directory holding `.shelf/` when a project scope is discovered, else the git toplevel | Spec Part 3 |
| I15 | Catalog document order (T06) | Sorted by `id` on every write; the first write after upgrading reorders an existing `catalog.json` once | Date-prefixed ids keep chronological order |
| I11 | `path --scope all` output | One `<scope>\t<path>` line per configured scope | Parseable and readable |

## Order (tests first in each step)

0. conftest: run every test from an empty tmp directory
1. T01 discovery + I1 merge (`core/config.py`, `core/paths.py`, `cli/runtime.py`) — TS01
2. T02 `--scope` on single-target commands — TS02
3. T03 combined reads — TS03
4. T04 `init --scope project` (and I13 `open` rebuild) + `.gitignore` append (also plain `init --git`) + agent offer — TS04
5. TS06 project-scope `--commit` (I8): library in a subfolder of a host repo with an unrelated dirty file; `require_git_if_commit` advice fits project scope
6. T05 `doc move --to-scope` + I10 audit check — TS05
7. T06 sorted catalog documents
8. P22-TS10 agent install scope question
9. T07 skill + plugin README, plugin 0.2.0; T08 PRD + README; T09 release
