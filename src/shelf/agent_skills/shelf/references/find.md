# find — retrieve shelf content for the current session

Read-only. Triggered when the user wants shelf content now — "what do I have on
X?", "grab my flox PRD from shelf", "use my provider-config notes as context".
Drives `shelf doc list` and `shelf doc view`; never mutates the library. Every
other operation uses this flow internally to resolve an intent to a document id.

## Drive pattern

1. **Query:** `shelf doc list --query <text>`, narrowing with `--repo`,
   `--topic`, `--kind`, or `--tag` as the request implies. Use `--json` when you
   need to parse results. (`shelf doc ls` is an alias.)
2. **Disambiguate** conversationally when matches are plural — show title, kind,
   and anchoring, and let the user pick. Do not guess when it matters.
3. **View:** `shelf doc view <id>` prints one document in full (metadata +
   variants + resolved paths).
4. **Deliver:** read the primary variant at its resolved path and use it as
   context, or hand the absolute path to the user — whichever they asked for.

## Notes

- This is the only reference that never writes. If the user's intent turns out
  to be a change ("...and retitle it"), finish the read, then route to
  `references/edit.md`.
- `shelf path` prints resolved library locations if you need the root directly.

Run `shelf doc list --help` / `shelf doc view --help` for the full surface.
