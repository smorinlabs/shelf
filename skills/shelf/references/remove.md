# remove — delete a document from the shelf

Owns destructive removal. Triggered by "remove that doc", "delete the old auth
guide from shelf", "drop the stale provider notes". Drives
`shelf doc delete <id> --yes`. This is irreversible on disk — treat it as such.

## Drive pattern

1. **Resolve intent to an id** via `shelf doc list` (see `references/find.md`).
   Never delete on a fuzzy match — if more than one document could be meant,
   list the candidates and have the user pick.
2. **Show exactly what will be deleted** — the catalog entry *and* its folder,
   with every format variant and asset under it. Use `shelf doc view <id>` to
   enumerate what is there.
3. **Confirm** explicitly with the user.
4. **Delete:** `shelf doc delete <id> --yes` (`shelf doc rm` is an alias). Add
   `--commit` when the library is a git repo so the removal is recorded.
5. **Confirm** the result.

## Red flags

| Thought | Reality |
|---|---|
| "They said delete, just run it" | Show the entry, folder, variants, and assets first — then confirm. |
| "The query returned one row, that's the one" | Confirm anyway when the user named it loosely; a wrong id deletes the wrong doc. |

Run `shelf doc delete --help` for the authoritative flags.
