# P21 — Publishing and GitHub Pages: delivery plan (2026-11-08)

**Design:** `docs/superpowers/specs/2026-11-05-scopes-and-publishing-design.md`, Part 2 (approved 2026-11-05). This plan does not reopen it; it records how the work ships and the points the spec left to implementation.

## Delivery: three PRs, one release (option B, chosen 2026-11-08)

| PR | Branch | Tasks | Content |
|---|---|---|---|
| 1 | `feat/p21-local-publish` | T01–T04, T09 | Schema v2 (`publish`, `shelf_version`) with migration; `--publish` flags; `publish`/`base-url` config keys; `shelf publish` (filter, `_site/`, `.nojekyll`); visibility detection and the `--force` guard; `--dry-run` report; hosted mode and base-URL resolution. Also flips P20 to `[x]` (deferred from the v0.10.0 close-out). |
| 2 | `feat/p21-deploy` | T05, T10, T11, T12 | `shelf pages status | enable`; `shelf github create`; `init --pages` (workflow generator) and `init --readme`; next-step hints. Pilot deploy on `smorinlabs/shelf-pages-pilot` (public, created for the test, deleted after sign-off). |
| 3 | `feat/p21-release` | T06–T08 | Skill and plugin 0.3.0; PRD and README; bump to v0.11.0 and tag. |

`main` carries unreleased publishing code between PR 1 and PR 3; nothing is tagged until PR 3. The version in `pyproject.toml` moves only in PR 3.

## Schema v2 (decided 2026-11-08)

The bump stays. A shelf at v0.10.0 or older refuses to read a v2 catalog instead of reading it, dropping every `publish` field it does not know, and writing it back. Requirement from the owner: **migration from v1 loses no data** (P21-TS13). Every v1 field survives unchanged; the migration only adds `schema_version: 2`, `publish: false` per document, and `shelf_version` at the top level.

## Implementation defaults

| # | Point | Default |
|---|---|---|
| J1 | Existing v1 libraries after upgrading | Reads keep working; writes stop with "run 'shelf migrate'" (exit 5), the existing behavior for a schema bump. |
| J2 | Project config may set `publish` and `base-url` | Yes. Both affect only that repo's own library, unlike `browser`, which runs a command on the reader's machine and stays user-file only. |
| J3 | "View source on GitHub" link target | CI: `$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/blob/$GITHUB_REF_NAME/<library path>/<file>`. Locally: the `origin` remote and the current branch. It follows the branch, not a commit. |
| J4 | Tests that would call `gh`, `git ls-remote`, or read `$GITHUB_EVENT_PATH` | Mocked at one function each; no test touches the network. `conftest.isolated_env` clears the `GITHUB_*` variables so a CI run cannot leak its real event file into guard tests. |
| J5 | Workflow install source | `uv tool install "git+https://github.com/smorinlabs/shelf@v$v"`; the repo is public. |

## Smaller choices made in PR 1

- `shelf publish --out DIR` refuses a `DIR` that is the library root, contains it, or lies inside its `docs/`, and refuses to replace an existing non-empty `DIR` that is not a previous shelf build (one holding `.nojekyll` and `catalog.json`). It never deletes a folder it did not build.
- The filtered catalog keeps only the topics and kinds that published documents use, so the published `index.html` cannot name a topic or kind that belongs only to unpublished documents. Snippets are built from published documents only.
- `render_index` gains `root` (base URL) and `source` (GitHub blob base) arguments. Library writes pass empty strings, so the library's own `index.html` gains only an empty `source` field and the template's Source button, which stays hidden.
- Visibility detection lives in one function returning `public`, `private`, `internal`, or `unknown`; the guard maps everything except `public` to exit 2 without `--force`.
- The site's `catalog.json` sets every document's `source` to null: it is the local path a file was added from (often under the author's home directory). The library catalog keeps it.
- Visibility detection and the Source-link base follow the P20 git-library rule (`is_git_repo`): a user library nested in an unrelated repo, such as a dotfiles repo, is "unknown", so the guard never trusts that repo's visibility.
- `_site/` inside the library root is allowed (a dedicated library repo builds there in CI); audit already checks only `catalog.json`, `index.html`, and `docs/`. `init --pages` (PR 2) should add `_site/` to `.gitignore` so a local preview is never committed.
