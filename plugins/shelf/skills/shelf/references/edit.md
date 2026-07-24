# edit — change a document's metadata or location

Triggered by intent-language edits: "reclassify X as a tutorial", "tighten the
description on Y", "retitle that doc", "move my auth notes under the security
topic". Owns `shelf doc update`, `shelf doc move`, and variant maintenance via
`shelf doc format delete`. The user speaks in intent; resolve the id and fields
and call the conforming command.

## Metadata edits → `shelf doc update`

1. Resolve the document id via `shelf doc list` (see `references/find.md`) when
   the user names it by description rather than id.
2. Map the intent to fields — title, description, kind, tags — and run
   `shelf doc update <id>` with the matching flags. Preview with `--dry-run`
   when available; confirm the change.
3. Add `--commit` when the library is a git repo.

## Relocation → `shelf doc move`

A change of **topic or repo anchoring is a move, not an update.** When the
request is really a relocation:

1. Explain that this *moves* the document (its folder path changes under
   `docs/…`), so links to the old path break.
2. Run `shelf doc move <id>` with the new anchoring on confirmation
   (`--commit` for a git library).

## Variant maintenance → `shelf doc format delete`

Removing an obsolete format variant (e.g. drop a stale PDF, keep the Markdown)
is `shelf doc format delete <id> <format>`. Show exactly which variant goes,
confirm, then run it.

Run `shelf doc update --help` / `shelf doc move --help` /
`shelf doc format delete --help` for the authoritative flags.
