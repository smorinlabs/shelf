# Library scopes and Pages publishing — design (2026-11-05)

**Goal:** Give shelf the same **user** and **project** scopes that Claude Code skills have, and let either scope's library be published to GitHub Pages without leaking private content. Fulfills **P20** (project scope) and **P21** (publishing), with **P13-T02** (path-scoped commits) as a prerequisite.

**Status:** Approved design (2026-11-05). Not implemented. Until P20 and P21 ship, `SHELF-PRD.md` §4 and §5 describe current behavior.

**Non-goals:** named multi-library support beyond the two scopes (the P12 generalization, left for later); system scope (`$XDG_CONFIG_DIRS`); hosting outside GitHub Pages (the built `_site/` folder can be deployed anywhere, but shelf does not automate that); a `publish-formats` filter (published documents ship every variant).

---

## Background

Shelf today has exactly one library, set by the user config (`$XDG_CONFIG_HOME/shelf/shelf_config.toml`). PRD §5 waives CLI Design Standard rules R5.1/R5.2 ("no project or system config scopes"). P12 tracked multiple libraries as a far-future idea.

Skills have two install scopes: user (`~/.claude/skills/`) and project (`.claude/skills/`, committed in the repo and shared with everyone who works in it). The shelf equivalent has two separate parts:

- **(a) Config scope and discovery:** how the CLI knows a project scope exists.
- **(b) Library location:** where the project library's `catalog.json` and `docs/` live inside the repo.

Existing properties make this feasible. Catalog paths are library-relative. The UI's copy-text feature fetches files by relative path. `page_data["root"]` in `core/index.py` is an existing hook for a base URL.

## Decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Approach | Library committed in the repo, two scopes, `--scope` flag (option B of three; config-only and named-libraries were rejected) |
| D2 | Write target inside a repo with a project library | The project library; `--scope user` overrides |
| D3 | Meaning of "top-level install" | Both: a dedicated repo whose root is the **user** library (today's `shelf init --github`), and a `shelf/` folder in a code repo (the **project** library). Project library ships first. |
| D4 | What gets published | Allowlist per document, plus a library-level `publish` switch. Making everything publishable must be easy to discover. |
| D5 | "Publish everything" scope | Every document and every variant (HTML, Markdown, PDF). No format filter. |
| D6 | Private-repo guard | **Always:** any publish from a private, internal, or unverifiable repo requires `--force`, in both publish modes |
| D7 | Turning on Pages | `shelf init --pages` offers to run the setting change; on "no" it prints the command. `shelf pages enable --print` prints it any time. A failed Action names the fix in its job summary. |
| D8 | Shelf version used by the Action | The version recorded in `catalog.json` (`shelf_version`, written on every library write), overridable by a pin (`SHELF_VERSION`) in the workflow file |
| D9 | `base-url` | Detected automatically; overridable by `--base-url` or the `base-url` config key. `init --pages` does not write it. |

---

## Part 1 — Project scope (P20)

### Discovery and precedence

Following CLI Design Standard R5.2, shelf searches the current directory, then each parent, for `.shelf/shelf_config.toml`, and stops at the first directory containing `.git`.

Library resolution, highest precedence first:

1. `--library PATH`
2. `SHELF_LIBRARY`
3. **Project scope:** the discovered `.shelf/shelf_config.toml`
4. User config (`$XDG_CONFIG_HOME/shelf/shelf_config.toml`, or `--config PATH`, which replaces the discovered files per R5.2)
5. Unconfigured → error with guidance to run `shelf init`

The project config is committed, so its `library` value **must be relative**, resolved against the repo root (the directory containing `.shelf/`). An absolute `library` in a project config is a validation error.

### Layout

A visible `shelf/` folder, not a hidden `.shelf/`, so GitHub's file view, the README, and Pages can all reach it.

```text
my-repo/
├── .shelf/shelf_config.toml   # library = "shelf"   (scope marker + project settings)
├── shelf/                     # the project library (same catalog schema as the user library)
│   ├── catalog.json
│   ├── index.html             # gitignored in project scope
│   └── docs/topics/…
└── README.md                  # optional <!-- shelf:start --> … <!-- shelf:end --> link block
```

### Reads, writes, and library-level commands

| Command type | Behavior |
|---|---|
| `doc list`, `doc view` | Search **both** scopes by default. Each result gets a `scope` field (`project` or `user`); table output adds a scope column. `--scope user\|project\|all` narrows. |
| Mutating commands | Act on **one** library: the project library when discovered, otherwise the user library. `--scope user\|project` overrides. |
| `audit`, `regen`, `open`, `path`, `migrate` | Same single-target rule. `shelf path --scope all` prints both. |
| `doc move ID --to-scope user\|project` | New. Adds to the target library, then deletes from the source. Each step holds its own library lock. If the second step fails, `audit` in the source library reports the leftover copy as a duplicate to remove. |

`--scope project` with no discovered project scope is an error (exit 2), not a silent fallback to the user library.

### Project-scope defaults

| Setting | User scope | Project scope | Why |
|---|---|---|---|
| Anchor | repo or topic | topic only by default; `--repo` still allowed | The repo anchor `docs/repos/<this-repo>/` is redundant inside the repo |
| `remove-source` | `true` | `false` | The source is usually a tracked file in the same repo |
| `index.html` | committed | gitignored; rebuilt by `regen`, `open`, and `publish` | Two branches that each add a document would always conflict on it |
| `--commit` | whole-library commit | path-scoped commit into the host repo | The host repo holds unrelated work |

Defaults live in `.shelf/shelf_config.toml`, so a project can change them.

### `shelf init --scope project`

- Creates `.shelf/shelf_config.toml` (with `library = "shelf"` unless `--library` names another relative path) and the library folder.
- Detects the enclosing Git repo. It does **not** run `git init` inside it.
- **Appends** shelf's entries (`.shelf.lock`, `shelf/index.html`) to the repo's `.gitignore` instead of overwriting it.
- Never writes a `README.md` inside the library folder when the library root is the repo root.
- `--git`/`--github` are rejected with `--scope project` (the repo already exists).

### Skill changes (plugin)

- **find:** queries both scopes and labels each result with its scope.
- **add:** when a project scope exists, always asks which scope to use; suggests **project** when the document concerns the current repo. Never picks silently.
- **init:** gains a "set up shelf in this repo" path.
- Plugin README documents installing the plugin at project scope (`enabledPlugins` and `extraKnownMarketplaces` in the repo's `.claude/settings.json`), so teammates get the skill along with the library.

### Prerequisites

1. **Path-scoped commits (P13-T02).** `git_commit_all` stages with `git add -A` (`core/git.py`). In a project library this would sweep the user's unrelated uncommitted files into a shelf commit. Each command must stage only the paths it touched. Project-scope `--commit` is refused until this ships.
2. **Enclosing-repo detection in `init`** (covered above).
3. **`.gitignore` append, not overwrite** (covered above). This also fixes the dedicated-repo case, where the library root is the repo root.
4. **Catalog merge conflicts.** Concurrent additions on different branches both edit `catalog.json`. Writing the documents array in a deterministic sorted order keeps conflicts small and textual; `audit` validates the result after a merge.

---

## Part 2 — Publishing (P21)

### Why publishing must filter

A GitHub Pages site is public even when its repo is private (the only exception is GitHub Enterprise Cloud access control). The generated `index.html` embeds every document's title, description, tags, and preview snippet, so serving the library folder as-is exposes the whole catalog. Publishing therefore builds a **separate, filtered site**; the library folder is never served directly.

For a project library in a **public** repo, `shelf/` is already readable on GitHub; filtering matters for private repos and for the user library.

### Marking documents

- New catalog field `publish: true|false`, default `false`. This is a schema change from version 1 to 2, applied with the existing `shelf migrate`; version-1 catalogs read as all-`false`.
- A dedicated field, not a `public` tag, because tags are free-form and a tag used for another meaning (for example, public API docs) would publish by accident.
- Set with `doc add --publish` and `doc update --publish | --no-publish`. Shown in `doc view` and `doc list --json`.

### The library-level switch

Config key `publish`, read from the config that selected the library (the project config for a project library, the user config for the user library):

| Value | Publishes |
|---|---|
| `"marked"` (default) | Only documents with `publish: true` |
| `"all"` | Every document, with every variant (HTML, Markdown, PDF) and its assets |

### The private-repo guard

Every `shelf publish` run (except `--dry-run`) checks the visibility of the repo containing the library:

| Visibility | `marked` mode | `all` mode |
|---|---|---|
| Public | Publishes | Publishes |
| Private or internal | **Refuses** (exit 2) without `--force` | **Refuses** (exit 2) without `--force` |
| Unknown | Treated as private | Treated as private |

"Unknown" covers a library outside any Git repo, a repo with no GitHub remote, and any failure to determine visibility.

- **Detection order:** inside GitHub Actions, read `repository.private` from the JSON at `$GITHUB_EVENT_PATH`. Otherwise, run `gh api repos/<owner>/<repo> --jq .visibility` using the `origin` remote. Any failure means unknown.
- **No config key bypasses the guard.** `--force` is a flag only. Following shelf's convention, `--force` overrides a safety guard.
- **CI:** `shelf init --pages` detects the repo's visibility the same way. For a private or unknown repo, it writes `--force` into the generated workflow only when `init --pages --force` is given; without it, `init --pages` refuses with the same message as `publish`. Publishing from a private repo is then a committed, reviewable line in `.github/workflows/shelf-pages.yml`.
- The refusal message names the repo, its detected visibility, how many documents would be published, and the exact command with `--force`.

### Making "publish everything" discoverable

| Where | What it says |
|---|---|
| `shelf publish --dry-run` | Lists the documents that would be published and the detected visibility. Ends with a footer such as: `12 documents not published. To publish everything, set publish = "all" in <config path>. This repo is private: publishing requires --force.` |
| `shelf publish --help` | One worked example per mode, including the `--force` case |
| README "Publishing" section | Both modes, the guard table, and the generated workflow |
| shelf skill | On any publish request, states the library's mode and visibility and how to switch modes |

### `shelf publish --out DIR`

`shelf publish` never creates a repo and never pushes. It builds a folder from a library that already exists, in whichever repo holds it: the dedicated `<you>/shelf-library` repo (user library, created by `shelf init --github`) or the code repo containing `shelf/` (project library).

Default `DIR` is `_site`. It builds:

- a filtered `catalog.json` containing only published documents;
- a filtered `index.html`: topics, kinds, and tags that belong only to unpublished documents are dropped;
- the published documents' files and assets;
- a `.nojekyll` file, so a branch deploy does not run Jekyll (which skips `_`/`.` paths and can convert `.md` files).

The output is a build artifact. It is not committed, and `shelf audit` ignores it.

Run locally, `shelf publish` is a **preview**: the same filter and the same guard, with the result viewable through any static server (for example `python3 -m http.server -d _site`). Deploying happens only through the Action, so every deploy corresponds to a pushed commit.

### How deployment works

```text
 your machine                         GitHub
 shelf doc add --publish … --commit
 git push  ──────────────────────▶  repo main branch (catalog.json + docs/; never _site/)
                                           │  push to main triggers
                                           ▼
                                    Actions runner (temporary)
                                      1. checkout
                                      2. actions/configure-pages  → Pages on? site URL?
                                      3. install shelf (version: see below)
                                      4. shelf publish --out _site  (filter + guard)
                                      5. actions/upload-pages-artifact (zip _site/)
                                      6. actions/deploy-pages
                                           ▼
                                    Pages serves https://<owner>.github.io/<repo>/
```

The site is deployed as an artifact, not committed to a `gh-pages` branch, so filtered output never enters Git history; an un-published document disappears at the next deploy.

**Plan limits:** on GitHub Free, Pages works only for public repos. A private repo needs GitHub Pro, Team, or Enterprise, and its Pages site is still public unless Enterprise Cloud access control is on.

### Hosted-mode UI and `base-url`

`base-url` fills `page_data["root"]` in the published index. With it set, **Copy path** copies the document's URL instead of `/docs/...`, and each document gets a "view source on GitHub" link when the GitHub repo is known. Copy-text needs no change; it already fetches by relative path.

Resolution, highest precedence first:

| # | Source | Use |
|---|---|---|
| 1 | `shelf publish --base-url URL` | One-off override |
| 2 | `base-url` key in the config that selected the library | Lasting override, for example a fixed custom domain |
| 3 | Detected Pages URL | In CI, the `base_url` output of `actions/configure-pages`, passed by the workflow as `--detected-base-url`. Locally, `gh api repos/<owner>/<repo>/pages --jq .html_url`. Both include a custom domain. |
| 4 | None | Copy path copies relative paths |

`init --pages` does **not** write `base-url`; a written value would override detection and hide a later custom-domain change.

### Turning on Pages: `shelf pages`

A workflow deploy needs the repo's Pages source set to "GitHub Actions", a one-time repo setting outside the workflow file.

| Command | Behavior |
|---|---|
| `shelf pages status` | Reports whether Pages is enabled, its source, and its URL. Exits `1` when Pages is not set to deploy from GitHub Actions (a predicate result, R6.2). |
| `shelf pages enable` | Shows the exact command, asks for confirmation, runs it. `--yes` skips the prompt. |
| `shelf pages enable --print` | Prints the command and runs nothing |

The command depends on the current state, which `status` detects:

```bash
gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow   # Pages never enabled
gh api -X PUT  repos/<owner>/<repo>/pages -f build_type=workflow   # enabled, but deploying from a branch
```

### Which shelf version the Action runs

Every library write records the writing version in `catalog.json` as `"shelf_version"` (added with schema version 2). The workflow installs that version unless the workflow file pins one:

```bash
v="${SHELF_VERSION:-$(jq -r '.shelf_version // empty' <library>/catalog.json)}"
uv tool install "git+https://github.com/smorinlabs/shelf@v$v"
```

- **Default:** `SHELF_VERSION` is empty in the generated workflow, so the site is built by the version that last wrote the catalog. Upgrading shelf locally and changing the library moves CI forward.
- **Override:** `shelf init --pages --shelf-version X.Y.Z` writes `SHELF_VERSION: "X.Y.Z"` into the workflow's `env`. The pin lives in the workflow file because the Action can read only the repo, and the user library's config sits outside it (`~/.config`).
- **Minimum version:** a version below v0.10.0 (no publishing support), or a missing `shelf_version` with no pin, stops the run with a message naming the fix.

### `shelf init --pages`

`shelf init --pages [--force] [--shelf-version X.Y.Z]`:

1. Checks repo visibility; a private or unknown repo refuses without `--force` (same message as `publish`). With `--force`, `--force` is written into the workflow's `shelf publish` step.
2. Writes `.github/workflows/shelf-pages.yml`: trigger on pushes to `main` that touch the library (no path filter for the dedicated repo) plus `workflow_dispatch`; permissions `contents: read`, `pages: write`, `id-token: write`; a `pages` concurrency group; the six steps above; the library path for this layout.
3. Runs the `pages status` check. If Pages is not ready, offers to run `pages enable`; on "no", prints the command and `https://github.com/<owner>/<repo>/settings/pages`.
4. Never commits the workflow; the user commits it.

The workflow never commits or pushes, never runs on pull requests, and uses no secrets (deploy authenticates with GitHub's OIDC token).

### Failure reporting in the Action

A step guarded by `if: failure()` writes an `::error::` annotation and a job summary (`$GITHUB_STEP_SUMMARY`) naming the fix, so the cause shows on the failed run itself:

| Failing step | Summary tells you |
|---|---|
| `actions/configure-pages` (Pages off or wrong source) | The exact `gh api` command, `shelf pages enable`, and the settings URL |
| `shelf publish` exit 2 (private-repo guard) | The repo is private; how to add `--force` via `shelf init --pages --force` |
| Version resolution (missing or too-old `shelf_version`) | Upgrade shelf locally and write the library, or set `SHELF_VERSION` |

### `shelf init --readme`

- `shelf init --readme` adds a link-only block to the repo's `README.md`, between `<!-- shelf:start -->` and `<!-- shelf:end -->`: a link to the library folder and, when a base URL resolves (see the `base-url` table), to the Pages site. Re-running updates the block in place.

---

## PRD changes when each project ships

- **P20:** rewrite §4 to the new precedence chain; remove the R5.1/R5.2 waiver in §5 (system scope stays out); close §14.3 by pointing at the two scopes.
- **P21:** narrow the §2 non-goal "Not a hosted service or public site" to "not a hosted service; opt-in static publishing only"; add `shelf publish` and `shelf pages` to §5 and §11; document `publish` and `base-url` in §4; bump §10 to schema version 2 (`publish` per document, `shelf_version` at the top level).
