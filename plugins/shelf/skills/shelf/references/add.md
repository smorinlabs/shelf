# add — add a document (or format, topic, kind) to the shelf

Owns the governance flows around `shelf doc add`, `shelf doc format add`,
`shelf topic add`, and `shelf kind add`. Triggered when the user has something
to add — a file or URL — either directly in a session or via the `shelf doc add`
handoff (§11.2), which launches the agent primed with "Use the shelf skill to
add `<path>` to shelf. Walk me through classification."

## Preconditions

1. **First run.** If no library is configured (`shelf path` errors, or there is
   no catalog), stop and run `references/init.md` first — set the library up,
   then continue the add.
2. **URL input.** If the input is a URL, not a file, fetch it to a temp file
   yourself (WebFetch), show the user what you retrieved (title, size, format),
   and continue with that file on confirmation. The CLI never fetches.

## Drive pattern

1. **Inspect** the file(s) — read enough to propose a title, description, kind,
   and tags.
2. **New document or new format?** If this is another format of a document
   already in the shelf (e.g. a PDF of an existing Markdown doc), route to
   `shelf doc format add` instead of `doc add`. Resolve the existing id via
   `shelf doc list` (see `references/find.md`) when unsure.
3. **Read the taxonomy:** `shelf topic list` and `shelf kind list`.
4. **Classify** and confirm with the user:
   - **Anchoring** — repo-anchored (`--repo`, optionally `--repo-url`,
     `--subject`) vs. topical (`--topic`). An unknown topic needs
     `--create-topic` to authorize creating it (governed growth — confirm).
   - **`--kind`** (must already exist; if a new kind is warranted, add it first
     with `shelf kind add`).
   - **`--tag`** (repeatable), `--title`, `--description`.
   - **Source disposition** — ask whether to keep or remove the original;
     pass the explicit `--remove-source` or `--no-remove-source`.
5. **Preview:** run the add with `--dry-run --json` and show the user the
   planned destination and catalog entry.
6. **Commit for real** on confirmation with the chosen flags. Add `--commit`
   when the library is a git repo (omit otherwise). The CLI copies the file
   into `docs/repos/…` or `docs/topics/…` and writes the catalog — the skill
   never mutates library state itself.
7. **Confirm** the result (id, resolved path).

## Governance sub-flows

- **New topic:** `shelf topic add <name>` (or authorize inline with
  `--create-topic` on the add). Keep topic growth deliberate.
- **New kind:** `shelf kind add <name>` when a document's kind genuinely does
  not exist yet; surface a trend-triggered suggestion when several recent docs
  imply one.

## Key flags (`shelf doc add FILES...`)

`--repo` / `--repo-url` / `--subject` · `--topic` / `--create-topic` ·
`--kind` · `--tag` (repeatable) · `--title` · `--description` · `--slug` ·
`--primary` · `--assets` · `--source` · `--doc-date` ·
`--remove-source` / `--no-remove-source` · `--dry-run` ·
`--commit` / `--no-commit` · `--handoff-agent` · `--no-handoff`.

Run `shelf doc add --help` for the authoritative list.
