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

## Shelf in this repo → `shelf init --scope project`

When the user says "set up shelf in this repo" or "give this project a shelf":

1. Confirm you are inside the right Git repository (`git rev-parse
   --show-toplevel`). The command refuses outside one.
2. Run `shelf init --scope project` (optionally `--library <relative path>`;
   default `shelf`). It writes `.shelf/shelf_config.toml` at the repo top,
   scaffolds the library folder, and appends `.shelf.lock` and the library's
   `index.html` to `.gitignore`. It never runs `git init` and never commits.
3. It then offers to install the shelf skills at project scope
   (`shelf agent install --scope project`), so teammates get them too. Relay
   the offer; pass `--yes` only when the user already said yes.
4. Suggest committing `.shelf/`, the library folder, and `.gitignore` — plus
   `.claude/skills/` and `.agents/skills/` if the skills were installed in step 3.
   Teammates who clone the repo get the library; `shelf open` or
   `shelf regen` rebuilds the gitignored `index.html`.

## Existing library on a new machine → `shelf init --adopt`

When the library content already exists (e.g. cloned from a private
`shelf-library` repo):

1. Clone / locate the library directory.
2. `shelf init --adopt <path>` registers that existing directory as the library
   on this machine without copying anything.
3. Confirm resolution with `shelf path`.

Run `shelf init --help` for the authoritative flags.
