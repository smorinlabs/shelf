# audit — check and repair the library

Owns the repair flows: `shelf audit`, `shelf regen`, `shelf migrate`,
`shelf doc adopt`, and `shelf orphan list | delete`. Triggered by "audit my
shelf", "is my catalog consistent?", "fix the shelf", "the index looks stale",
"what uncataloged files are lying around?".

## Drive pattern

1. **Audit:** `shelf audit` (add `--json` / `-o json` to parse). It runs the
   consistency check across the catalog, on-disk documents, and the generated
   `index.html` fingerprint.
2. **Summarize** the report for the user — what is consistent, what drifted.
3. **Offer each finding's remediation** and run it on confirmation:
   - **Stale `index.html`** (template or CLI upgrade) → `shelf regen`.
   - **Old catalog schema** → `shelf migrate`.
   - **Uncataloged files / orphans** → `shelf orphan list` to show them, then
     either `shelf doc adopt <path>` to register an existing per-document folder
     in place, or `shelf orphan delete` to remove stray files. Confirm before
     deleting.
   - **Dirty git state** (library is a repo with uncommitted changes) → offer a
     `git` commit run *in the library*.

## Pre-commit hook

`shelf audit --pre-commit` skips the dirty-git check and is meant to run as a
git pre-commit hook in the library, so the catalog cannot silently drift. If the
user wants that guard, help them wire it as a hook rather than running it ad hoc.

Run `shelf audit --help`, `shelf orphan --help`, `shelf doc adopt --help` for
the authoritative flags.
