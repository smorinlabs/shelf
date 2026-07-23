# init — create, adopt, and register a library

Owns `shelf init` and `shelf init --adopt`. Two entry points:

- **First-run setup**, reached from `references/add.md` when the user tries to
  add something but no library exists — the user never has to know `shelf init`
  exists.
- **Deliberate setup / repair**, when the user says "set up my shelf", "create a
  shelf library", or "register my shelf on this machine".

## New library → `shelf init`

1. **Propose the on-disk location** — offer the default library path (`shelf
   path` shows where resolution would place it); let the user override.
2. **Ask whether to make it a git repo.** If yes, offer to create the private
   GitHub repo for it. Version control is what enables `--commit` on later
   mutations.
3. Run `shelf init` with the chosen options and confirm the library is
   registered.
4. If this was reached mid-add, return to `references/add.md` and finish the
   add.

## Existing library on a new machine → `shelf init --adopt`

When the library content already exists (e.g. cloned from a private
`shelf-library` repo):

1. Clone / locate the library directory.
2. `shelf init --adopt <path>` registers that existing directory as the library
   on this machine without copying anything.
3. Confirm resolution with `shelf path`.

Run `shelf init --help` for the authoritative flags.
