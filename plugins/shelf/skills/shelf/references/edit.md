# edit — change a document's metadata or location

Triggered by intent-language edits: "reclassify X as a tutorial", "tighten the
description on Y", "retitle that doc", "move my auth notes under the security
topic", "rename that slug". Owns `shelf doc update`, `shelf doc move`,
`shelf doc rename`, and variant maintenance via
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

Repo names may be `<repo>` or `<owner>/<repo>` (`--repo obra/superpowers`).

## Slug changes → `shelf doc rename`

The slug is the document's id and folder name. To change it, run
`shelf doc rename <id> <new-slug>`: the folder and the `<slug>.<ext>` variant
files are renamed together, and the catalog and index are updated.

1. Preview with `--dry-run` and show the old and new id and folder.
2. A new slug without a date gets the document's `added` date prefixed, with
   a warning; a new slug with a different date sets `added` to that date.
3. An existing slug or folder is refused. Absolute paths copied for the old
   folder stop resolving — say so.
4. Add `--commit` when the library is a git repo.

## Between scopes → `shelf doc move --to-scope`

Moving a document from the user library into the repo's project library (or
back) is `shelf doc move <id> --to-scope project|user`, run with `--scope` set
to the library it is in now when the id exists in both. It keeps the anchor;
the target needs the document's kind (`shelf kind add <kind> --scope <target>`)
and its topic (pass `--create-topic` after confirming). Preview with
`--dry-run`. If it reports that the source copy was not removed, run the
`shelf doc delete` it names.

## Variant maintenance → `shelf doc format delete`

Removing an obsolete format variant (e.g. drop a stale PDF, keep the Markdown)
is `shelf doc format delete <id> <format>`. Show exactly which variant goes,
confirm, then run it.

Run `shelf doc update --help` / `shelf doc move --help` / `shelf doc rename --help` /
`shelf doc format delete --help` for the authoritative flags.
