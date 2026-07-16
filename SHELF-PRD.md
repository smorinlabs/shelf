# Shelf — Product Requirements Document

*A private documentation library and management toolkit.*

---

## 1. Overview

**Shelf** is a private personal documentation library. It holds reference docs, published HTML documents, and Markdown explainers and tutorials — copied and organized into the library so the content is self-contained and more or less static. A generated single-page HTML interface provides search and access; a `shelf` CLI manages the library; and a plugin exposes management skills to AI coding tools.

Shelf is delivered as **three repositories**:

- `shelf` — the management CLI and the UI template.
- `shelf-skill` — a plugin exposing the management skills to Claude Code and Codex.
- `shelf-library` — the document content itself.

The library content is the user's data. By default it is stored in the standard per-user data location and accessed through the CLI and the UI; a CLI command reveals its path.

---

## 2. Goals and Non-Goals

### Goals

- A single, self-contained, private library of reference documentation.
- A generated single-page `index.html` UI with autocomplete search over name, description, and tags, organized by subject, with per-file copy actions.
- A `shelf` CLI that is the single writer of the catalog and the only thing that mutates library state.
- Management skills usable from any other repository, in both Claude Code and Codex.
- Reproducible, self-contained tooling (uv inline-scripts).
- Stable file paths, so references handed out by the UI remain valid over time.
- A machine-portable library — no machine-specific data is committed.

### Non-Goals

- Not a hosted service or public site.
- No marketplace distribution initially — the `shelf-skill` plugin is installed directly; a marketplace manifest can be added later.
- No automated ingestion — every catalog mutation is user-initiated. The UI and skills assist, but the human stays in the loop and confirms classification.
- No heavy build pipeline. The only runtime is an optional lightweight local server for the UI's enhanced mode (§13).

---

## 3. Repository Architecture

Shelf is split across three repositories. The CLI is a tool that releases on its own cadence; the plugin is a thin AI-tool integration; the library is user content.

### `shelf` — CLI and UI template

```
shelf/
├── bin/
│   └── shelf                     # CLI entry point — a uv inline-script
├── templates/
│   └── index.html.tmpl           # the UI template (rendered into the library)
├── scripts/
│   └── serve.py                   # local UI server — a uv inline-script
└── README.md
```

### `shelf-skill` — plugin for Claude Code and Codex

A thin plugin: skills only, no content. Its skills shell out to the `shelf` CLI.

```
shelf-skill/
├── .claude-plugin/
│   └── plugin.json                # Claude Code plugin manifest
├── skills/
│   ├── shelf-add/SKILL.md
│   ├── shelf-edit/SKILL.md
│   ├── shelf-init/SKILL.md
│   ├── shelf-audit/SKILL.md
│   └── shelf-open/SKILL.md
└── README.md
```

The same skill definitions must work as both a **Claude Code plugin** and a **Codex plugin**. Exact manifest formats and any per-ecosystem adapter files are verified against current Claude Code and Codex plugin documentation at build time, and the plugin is tested against both (see §14).

### `shelf-library` — the document content

```
shelf-library/                     # default on-disk location: ${XDG_DATA_HOME:-~/.local/share}/shelf
├── catalog.json                   # source of truth
├── index.html                     # generated UI — committed, regenerated on every mutation
├── docs/
│   ├── repos/
│   │   └── <repo-name>/<YYYY-MM-DD-slug>/...
│   └── topics/
│       └── <topic>/<YYYY-MM-DD-slug>/...
└── README.md
```

`catalog.json`, `index.html`, and all of `docs/` are committed when the library is a git repo. `index.html` is generated from the template in the `shelf` repo and rewritten on every mutating command. Making the library a git repo (and creating a GitHub remote) is offered, optionally, at `shelf init` (§11.1).

### Tooling primitives

Every user-facing capability is a **skill** — slash commands are deprecated in favor of skills, so the surface is uniform. `shelf-add`, `shelf-edit`, and `shelf-init` carry judgment; `shelf-audit` and `shelf-open` are thin skills wrapping deterministic CLI calls. All skills use the **`shelf-` prefix**.

---

## 4. Configuration and Location Resolution

This section answers "how does shelf know where to keep and find `catalog.json` and `index.html`."

`catalog.json` and `index.html` are user content and live in the library. `index.html` is *generated* from a template that ships with the `shelf` CLI. The CLI must therefore locate the library.

### Config file

XDG-based, TOML: `${XDG_CONFIG_HOME:-~/.config}/shelf/config.toml`. Created by `shelf init`. It holds the library path and user defaults:

```toml
library = "/Users/<user>/.local/share/shelf"
remove_source = true          # default for `shelf add` / `shelf add-format`
server_port = 8765            # local UI server port
browser = "Google Chrome"     # browser for `shelf open` on macOS
```

### Library path resolution

Highest precedence first:

1. `--library <path>` — CLI flag.
2. `SHELF_LIBRARY` — environment variable.
3. The `library` key in the **active config file**, where the active config file is `--config <path>` if given, otherwise `${XDG_CONFIG_HOME:-~/.config}/shelf/config.toml`.
4. None of the above → the library is unconfigured. The CLI exits with guidance to run `shelf init`; the `shelf-add` skill triggers first-run setup automatically (§12).

This provides a **direct** override (`--library` / `SHELF_LIBRARY`) and an **indirect** one — `XDG_CONFIG_HOME` relocates the config directory, and the config file carries the library path.

The design assumes a single library. Multiple named libraries could be added later without breaking this scheme.

### Default library location

`${XDG_DATA_HOME:-~/.local/share}/shelf` — the standard per-user data location for a CLI application. `shelf init` creates the library there unless `--library` specifies otherwise.

### `shelf path`

Because the library lives in a non-obvious location, the CLI reveals it: `shelf path` prints the resolved library root; `shelf path config` prints the config file path; `shelf path index` prints the generated `index.html` path.

### Machine portability

Nothing machine-specific is committed. `catalog.json` stores only library-relative paths. The UI resolves the library's absolute path at view time (§13), so the `shelf-library` repository clones cleanly to any machine.

---

## 5. The `shelf` CLI

The CLI is the **single writer** of `catalog.json` and the only thing that mutates library state. Skills call the CLI rather than editing `catalog.json` directly — this allows validated writes and is far more context-efficient for the skill.

Every **mutating subcommand** (`init`, `add`, `add-format`, `edit`, `move`, `remove`, `topic add`, `kind add`) performs two actions as one atomic unit: it updates `catalog.json`, and it regenerates `index.html` from the template. Any failure rolls back, leaving no partial state.

### Subcommands

Detailed in §11.

- `shelf init` — create and register a library.
- `shelf add` — add a new document (one or more format files → one entry).
- `shelf add-format` — add a format variant to an existing document.
- `shelf edit` — change a document's metadata (pure catalog changes).
- `shelf move` — relocate a document (topic, repo, or anchoring change).
- `shelf remove <id>` — remove a document (entry + folder).
- `shelf audit` — run the library consistency check.
- `shelf open` — open the UI (§13).
- `shelf path [config|index]` — print resolved locations.
- `shelf topic add <name>` / `shelf topic list` — manage topic buckets.
- `shelf kind add <name>` / `shelf kind list` — manage kinds.

The CLI validates every write: a document's `category` must exist in the topic list, its `kind` must exist in the kind list.

### Runtime

The CLI and the auxiliary UI server are **uv inline-script files**: a `#!/usr/bin/env -S uv run --script` shebang with a PEP 723 `# /// script` dependency block. Self-contained and reproducible, with no virtualenv to manage.

---

## 6. Storage Model and Directory Layout

### Two stable top-level roots

Documents are either specific to a source repository or purely topical. This maps onto two roots under `docs/` that never change:

- `docs/repos/<repo-name>/` — repo-anchored documents.
- `docs/topics/<topic>/` — topical documents.

`repos/` buckets **self-populate**: the CLI creates `repos/<repo-name>/` on the first document added for that repo. `topics/` buckets are a **controlled, coarse, rarely-changing list** the user maintains (§9).

### Per-document folders

Each logical document gets its own folder, holding all of its format variants and any supporting assets (for example, images referenced by a published HTML file). Catalog entry ↔ directory is strictly one-to-one: adding a document creates a folder, removing it deletes a folder, and the audit walks folders.

### Path stability

Physical location is permanent; classification is metadata. The copy-path action hands out paths that get pasted into skills and other repositories, so a document's folder must not move when it is re-tagged. Re-tagging is a metadata change. Relocating a document between buckets is the deliberate, rare `shelf move` operation (§11.5).

---

## 7. Document Identity and Slugs

A document's slug is its stable identifier (`id`) and its folder name. Variant files share the slug as their stem.

- **Format:** `YYYY-MM-DD-<kebab-title>` — date prefix, then the kebab-cased title or subject.
- **Date:** the date the document was **added to shelf** — always known, unambiguous, and never becomes wrong. The date prefix makes slug collisions unlikely; an exact collision (the same title added on the same day) is detected and rejected at `shelf add` (§11.2). The content's own publication date, when relevant, is stored separately as `doc_date`.
- The kebab title is truncated to roughly 60 characters.
- The slug is auto-derived from the title, with a `--slug` override at `shelf add`.
- **The slug is immutable.** It is the permanent `id`; neither `shelf edit` nor `shelf move` ever re-slugs a document.

Example: `docs/repos/flox-cli/2026-05-22-cli-extension-prd/2026-05-22-cli-extension-prd.md`

---

## 8. Classification Model

A document is classified along the following axes.

- **`category`** — the topic bucket. Exactly one per topical document. Primary grouping in the UI, drawn from the controlled topic list, CLI-validated. Topical documents only.
- **`repo`** — an optional object. Its **presence is the discriminator**: present → repo-anchored, lives under `docs/repos/`; absent → `category` required, lives under `docs/topics/`.
- **`kind`** — what the document *is*. A small, mostly fixed set: `reference`, `explainer`, `tutorial`, `playbook`, `spec`, `cheatsheet`. Shown as a badge; also a UI grouping dimension (§13).
- **`tags`** — free-form, multiple, assigned on demand by the skill with no list and no confirmation. Tags carry all fine-grained, cross-cutting classification and power search.

### The `repo` cross-reference

```json
"repo": {
  "name": "thoth",
  "url": "https://github.com/<owner>/thoth",
  "subject": "provider-config"
}
```

`subject` is a short, **free-form** within-repo label, not a sentence. When a repo accumulates multiple documents, `subject` becomes a sub-heading under that repo's group in the UI. When a repo has only a document or two, `repo` can carry just `name` and `url`.

---

## 9. Taxonomy Governance

The topic and kind lists are stored as **top-level arrays in `catalog.json`**. Both have a CLI add subcommand and CLI validation. The difference is the skill's behavior.

### Topics — governed growth, no seed

A new library starts with **zero topics**; there is no seed set. Topics grow only by confirmed steps: `shelf-add` checks the existing list first; if a topic fits, it is used; if nothing fits, the skill **proposes** a name, the user confirms, and `shelf topic add` creates it explicitly. Topics are never silently invented. This keeps buckets coarse and stable instead of sprawling into near-duplicates.

### Kinds — seeded, deliberate growth

`shelf init` seeds the kind list with `reference`, `explainer`, `tutorial`, `playbook`, `spec`, `cheatsheet`. The set is small and stable — the *forms* a document takes do not proliferate.

`shelf-add` treats the kind set as effectively closed: it selects the best-fitting existing kind and does not propose a new one for a single awkward fit. It **may suggest** `shelf kind add` if it notices a **trend** — a recurring document type repeatedly force-fit across recent entries. The suggestion is trend-triggered, not misfit-triggered, and acting on it still requires user confirmation. If one document genuinely resists every kind, the skill flags it and asks the user to pick the closest or add one deliberately — it never invents one.

### Tags — the pressure-release valve

Tags are free-form and assigned on demand with no list and no confirmation. All on-demand classification energy goes here, leaving topics coarse and governed.

---

## 10. The `catalog.json` Schema

`catalog.json` is the single source of truth, written only by the CLI. It carries the topic and kind lists and the document entries. It contains **no machine-specific data** — only library-relative paths — so it is fully portable.

```json
{
  "topics": ["agentic-infra", "claude-code", "dev-tooling"],
  "kinds": ["reference", "explainer", "tutorial", "playbook", "spec", "cheatsheet"],
  "documents": [
    {
      "id": "2026-05-22-cli-extension-prd",
      "title": "Flox CLI Extension System — PRD",
      "description": "...",
      "kind": "spec",
      "tags": ["rust", "cli", "extensions"],
      "repo": {
        "name": "flox-cli",
        "url": "https://github.com/flox/flox",
        "subject": "cli-extensions"
      },
      "files": [
        { "format": "md",  "path": "docs/repos/flox-cli/2026-05-22-cli-extension-prd/2026-05-22-cli-extension-prd.md" },
        { "format": "pdf", "path": "docs/repos/flox-cli/2026-05-22-cli-extension-prd/2026-05-22-cli-extension-prd.pdf", "source": "/Users/<user>/Downloads/cli-extension-prd.pdf" }
      ],
      "primary": "md",
      "added": "2026-05-22",
      "doc_date": null,
      "source": "/Users/<user>/Downloads/cli-extension-prd.md"
    }
  ]
}
```

Notes:

- A **topical** entry omits `repo` and instead carries `category` (a value from `topics`).
- `files[]` lists every format variant — `format`, library-relative `path`, and an optional per-variant `source`.
- `primary` names the variant the UI links on click.
- `added` is the shelf-add date (also encoded in the slug); `doc_date` optionally records when the content itself was authored.
- `source` (document-level) records where the original came from; it is **retained even after the original file is removed**, as a provenance record.
- There is no `root` field — the UI resolves the library's absolute path at view time (§13).

---

## 11. Command Reference

Common conventions: every mutating command supports `--commit` (default `--no-commit`; the auto-generated message describes the change, e.g. `shelf: add <slug>`), `--commit-message`, `--dry-run`, `--json`, `-y/--yes`, and `-q/-v`. `--commit` requires the library to be a git repository and errors otherwise; `shelf init` is the exception — its initial commit is governed by `--git` (§11.1), not `--commit`. Every mutating command updates `catalog.json` and regenerates `index.html` atomically.

### 11.1 `shelf init`

Creates a library and registers it in the config file.

```
shelf init [--library <path>] [--git] [--github] [--owner <gh-owner>] [--force]
```

- `--library <path>` — where to create the library; defaults to `${XDG_DATA_HOME:-~/.local/share}/shelf`.
- `--git` — initialize the library as a git repository.
- `--github` — create a private GitHub repository and set it as the remote, via `gh repo create <owner>/shelf-library --private`. Implies `--git`. Both `--git` and `--github` are optional and offered, not assumed.
- `--owner <gh-owner>` — GitHub owner for `--github`; defaults to the authenticated `gh` user.

Behavior: scaffolds `catalog.json` (empty `topics`, `kinds` seeded with the six default kinds, empty `documents`), `docs/repos/`, `docs/topics/`, the generated `index.html`, and a README; then writes `${XDG_CONFIG_HOME:-~/.config}/shelf/config.toml` with `library` pointing at the new library. With `--git`, the scaffolded files are recorded as the library's initial commit. Refuses to overwrite an existing configured library unless `--force`.

### 11.2 `shelf add`

Adds a **new document**.

```
shelf add <file>... (--repo <name> | --topic <name>) --kind <kind>
          --title <text> --description <text> [options]
```

All positional files are **format variants of one document** → one entry. Format is inferred from extension (`.md`, `.html`/`.htm`, `.pdf`). Two files of the same format is an error. For two documents, run `shelf add` twice.

**Interactive handoff** — when the required classification flags are missing, `shelf add` does not error: it launches `claude` with a primed introductory prompt that references the `shelf-add` skill and passes the input file paths (for example: *"Use the shelf-add skill to add `/Users/<user>/Downloads/cli-extension-prd.md` to shelf. Walk me through classification."*). The user lands in an interactive Claude Code session where the skill drives classification, confirmation, and the eventual fully-flagged CLI call. `--no-claude` suppresses the handoff, making missing flags an error. When the CLI is already running inside a Claude Code or Codex session (detected via environment, §14), it never nests a session — it errors with a message asking the assistant to invoke the `shelf-add` skill directly. This makes the `shelf` CLI the single entry point whether the user starts in the shell or in an AI session: fully-flagged invocations run non-interactively; judgment-needing invocations hand off to the skill, which lives in exactly one place.

**Input** — `<file>...` (≥1); `--assets <path>` (repeatable; files or directories copied into the document folder so HTML relative links resolve); `--format <ext>` (override inference).

**Anchoring** — exactly one of: `--repo <name>` (with `--repo-url <url>`, inferred from the git remote of the repository containing the source file when there is one, otherwise required, and `--subject <label>`); or `--topic <name>` (with `--create-topic` to authorize creating an unknown topic — without it, an unknown topic is an error).

**Classification** — `--kind <kind>` (required; must exist; `shelf add` never creates kinds); `--tag <tag>` (repeatable, free-form).

**Identity/metadata** — `--title` (required), `--description` (required), `--slug` (override), `--primary <format>` (default heuristic: md, else html, else pdf, else first), `--doc-date <YYYY-MM-DD>`, `--source <text>` (default: absolute path of the first input file).

**Source handling** — by default the original input files are **removed** after a fully successful add; this default is the `remove_source` config key. `--keep-source` / `--remove-source` override it explicitly. The `shelf-add` skill asks the user and passes the explicit flag.

**Behavior** — validation order: exactly one anchor; kind exists; topic exists or `--create-topic`; no duplicate format; slug/folder free. Duplicate slug → error pointing at `--slug` or `shelf add-format`. Atomic with rollback; files copied (never moved) and renamed to `<slug>.<ext>`; source removal runs only after copy, catalog write, index regeneration, and any commit all succeed.

```
shelf add ./cli-extension-prd.md ./cli-extension-prd.pdf \
  --repo flox-cli --repo-url https://github.com/flox/flox \
  --subject cli-extensions --kind spec --primary md \
  --title "Flox CLI Extension System — PRD" \
  --description "Porting the gh extension model into the Flox CLI." --commit
```

### 11.3 `shelf add-format`

Adds a **new format variant to an existing document**.

```
shelf add-format <id> <file>... [options]
```

`<id>` is the exact slug of an existing document. Positional files are new variants of that document; format is inferred. Adding a format the document already has is an error unless `--replace`.

It never re-anchors or re-classifies — `--repo`/`--topic`, `kind`, `tags`, `title`, and `slug` are fixed at `add` time.

**Options** — `--assets <path>` (repeatable); `--format <ext>`; `--replace` (overwrite an existing same-format variant); `--primary <format>` (set/change the primary; must be a format the document will have after the operation); `--source <text>` (recorded on the new file entry); `--keep-source`/`--remove-source` (same default-remove behavior as `shelf add`).

**Behavior** — `<id>` exists; each new format absent unless `--replace`; new files copied into the document's existing folder and renamed to `<slug>.<ext>` (the folder never moves); appended to `files[]`; atomic with rollback.

```
shelf add-format 2026-05-22-cli-extension-prd ./cli-extension-prd.pdf --commit
```

### 11.4 `shelf edit`

Changes a document's metadata. Covers only changes that are a **pure `catalog.json` rewrite** — no files move.

```
shelf edit <id> [field options...] [--force] [options]
```

**Freely editable** — `--title` (display title only; never re-slugs or moves the folder), `--description`, `--kind` (validated), `--add-tag`/`--remove-tag` (repeatable) / `--set-tags <a,b,c>`, `--primary <format>` (must be a format the document has), `--doc-date <YYYY-MM-DD>` / `--clear-doc-date`, `--source`, and for repo-anchored documents `--repo-url` / `--subject` / `--clear-subject`.

**`--force`-gated** — fields that are dangerous but do not move files: `--added <date>` (coupled to the slug; editing it desynchronizes the slug) and low-level `files[]` corrections. These warn and require `--force`.

**Not editable here** — the topic, the repo, and topical↔repo anchoring all relocate the document's folder and belong to `shelf move`; attempting them errors and points there. The `id`/slug is immutable.

**Behavior** — `<id>` must exist; at least one field option required (or `-i` for a guided edit on a TTY); pure atomic `catalog.json` rewrite plus `index.html` regeneration; `--dry-run` shows a before/after diff.

```
shelf edit 2026-05-22-cli-extension-prd \
  --kind reference --add-tag rust --remove-tag draft \
  --description "Reference for the Flox CLI extension system." --commit
```

### 11.5 `shelf move`

Relocates a document — the changes `shelf edit` excludes because they move files on disk.

```
shelf move <id> (--topic <name> [--create-topic] | --repo <name> [--repo-url <url>] [--subject <label>])
```

Handles the three relocation operations: change a document's topic; change its repo; switch its anchoring (passing `--topic` for a currently repo-anchored document converts it to topical and drops the `repo` object; passing `--repo` for a topical document does the reverse).

**Behavior** — `<id>` must exist; physically moves the document folder from the old bucket to the new one, updates every `files[]` path, and updates `catalog.json`; honors governed growth (`--create-topic` for an unknown topic). It **warns** that absolute paths previously copied from the UI for this document will no longer resolve — accepted as rare by design. Atomic with rollback; `--dry-run` shows the old and new paths.

```
shelf move 2026-05-22-cli-extension-prd --topic dev-tooling --create-topic --commit
```

### 11.6 `shelf audit`

Deterministic consistency check. Suitable as a pre-commit hook; exits non-zero when any problem is found.

It flags:

1. Files present under `docs/` but missing from the catalog (orphans).
2. Catalog entries whose `files[]` point at files that do not exist (dead references).
3. Entries that are malformed or uncategorized — missing required fields, a `kind` not in the kind list, a `category` not in the topic list, or a per-document folder that does not match its anchoring.
4. Missing or unparseable `config.toml`, `catalog.json`, or `index.html`, and an `index.html` that is stale relative to `catalog.json`.
5. When the library is a git repository, uncommitted (dirty) changes to `catalog.json`, `index.html`, or `docs/`. This check is skipped in pre-commit mode (`--pre-commit`) — as a hook, the staged changes are precisely what is being committed, so flagging them would make every commit fail.

`--json` emits a structured report.

### 11.7 `shelf open`

Opens the UI.

```
shelf open [--static]
```

By default `shelf open` starts the local server (`scripts/serve.py`, on the configured `server_port`, reusing an already-running instance) and opens the configured browser to `http://localhost:<port>` — **enhanced mode**, with copy-contents and inline HTML rendering. `--static` instead opens the on-disk `index.html` directly as a `file://` page — **core mode** (browse, search, copy-path). If the configured port is occupied, the server falls back to the next free port. Works from any directory because the CLI resolves the library location.

### 11.8 `shelf path`

Prints resolved locations: `shelf path` → library root; `shelf path config` → config file; `shelf path index` → generated `index.html`.

### 11.9 `shelf topic` and `shelf kind`

`shelf topic add <name>` / `shelf topic list`; `shelf kind add <name>` / `shelf kind list`. Both `add` forms append to the relevant top-level array in `catalog.json` after validation. Topic creation is the explicit step in governed growth; kind creation is deliberate and rare.

### 11.10 `shelf remove`

`shelf remove <id>` removes a document — deletes its entry from the catalog and its folder from `docs/`. Atomic; `--dry-run` previews; `--commit` available.

---

## 12. Skills

The skills live in the `shelf-skill` plugin and shell out to the `shelf` CLI. The plugin targets **both Claude Code and Codex**; the same skill definitions are packaged for each, with manifests verified and tested against both at build time.

### `shelf-add` (skill)

Triggered when the user indicates they have a document to add — either directly inside a Claude Code/Codex session, or via the `shelf add` interactive handoff (§11.2), which launches Claude Code with this skill primed.

1. **First-run setup.** If no library is configured, the skill runs the init flow before anything else — it proposes the default on-disk location, asks whether to make it a git repo, and if so offers to create the private GitHub repo — then invokes `shelf init` and continues. This is the primary path by which a library comes to exist; the user never has to know `shelf init` exists.
2. Determines whether this is a **new document** or a **new format for an existing document** and routes to `shelf add` or `shelf add-format`.
3. Classifies it — repo-anchored vs. topical, `kind`, `tags` — running the topic governed-growth flow and surfacing a trend-triggered kind suggestion when warranted.
4. Invokes the CLI, which copies the document into `docs/repos/...` or `docs/topics/...` and writes the catalog — the skill never mutates library state itself (§5).
5. Confirms the result, and asks whether to remove the original source (passing `--keep-source`/`--remove-source` accordingly).

**Drive pattern** — inspect the file(s) → `shelf topic list` / `shelf kind list` → propose classification → call the CLI with `--dry-run --json` to preview → on confirmation, the real run with the chosen flags, adding `--commit` when the library is a git repository.

### `shelf-edit` (skill)

Edits document metadata. The user can speak in intent ("reclassify X as a tutorial", "tighten the description on Y") and the skill resolves the `id` and fields and calls `shelf edit`. When the request is actually a relocation (a different topic or repo), the skill explains that this moves the document and routes to `shelf move` instead.

### `shelf-init` (skill)

A deliberate, re-runnable setup path — for repairing configuration or creating a library outside the first-run flow. It wraps the same `shelf init` CLI as the `shelf-add` first-run path, so there is no duplicated logic; it is the secondary entry point.

### `shelf-audit` and `shelf-open` (skills)

Thin skills wrapping deterministic CLI calls. `shelf-audit` runs `shelf audit`, summarizes the report, and offers fixes for findings; the underlying `shelf audit` subcommand can also run directly as a pre-commit hook (§11.6) so the catalog cannot silently drift. `shelf-open` runs `shelf open`.

### Cross-tool usage

Installed as a plugin, the skills are available in every Claude Code or Codex session regardless of the current repository. They are defined and version-controlled in `shelf-skill` but usable everywhere. Outside AI sessions, the same operations are reachable through the standalone `shelf` CLI, which hands off to Claude Code when judgment is needed (§11.2).

---

## 13. The `index.html` UI

A generated single-page interface for finding and accessing documents.

### Generated static file, optionally served

`index.html` is **generated by the CLI from a template** (`templates/index.html.tmpl` in the `shelf` repo) and **regenerated on every mutating command**. The generated file is committed in `shelf-library` and lives on disk alongside the docs — so it can be viewed without running anything. Only the **catalog metadata** is embedded into it; document contents are never bulk-embedded.

The UI runs in one of two modes:

- **Core mode** (`file://`) — the file is opened directly (double-click, or `shelf open --static`). Search, browse, and **copy absolute path** all work with no server.
- **Enhanced mode** (served) — `shelf open` runs a lightweight local server and opens the browser to `http://localhost:<port>`. In addition to everything in core mode, this enables **copy contents** and **inline rendering of HTML documents** with their assets, because the page can fetch document files over HTTP.

The split exists because browsers block a `file://` page from fetching neighboring files. Copy-contents is therefore an enhanced-mode feature; the UI hides or disables it in core mode.

### Search and organization

- **Search:** autocomplete / fuzzy matching over document name, description, and tags.
- **Primary organization:** grouped by subject — topical documents by `category`, repo-anchored documents under their repo with `subject` sub-headings. `kind` is shown as a badge.
- **Alternative view:** a toggle re-groups the same documents by `kind`.
- **Per-variant rows:** each format variant has its own copy actions.

### Copy actions

- **Copy absolute path** — all variants, both modes. The library's absolute root is resolved at view time: in core mode the page reads its own `file://` location (it physically sits at the library root) and strips the filename; in enhanced mode the server injects the absolute root. Either way, no absolute path is committed. The button concatenates that root with the variant's library-relative path.
- **Copy contents** — Markdown and HTML variants, enhanced mode only. Copies the raw file text, read on the fly.

---

## 14. Open / Deferred Items

1. **Plugin manifests.** The exact `.claude-plugin/plugin.json` fields, the Codex plugin manifest/adapter format, and how the `shelf` CLI is placed on `PATH` (`uv tool install` vs. symlink) are verified against current Claude Code and Codex plugin documentation at build time. The plugin is built to support and is tested against both ecosystems.
2. **Local server port.** Default `8765` from config, with fallback to the next free port when occupied. Confirm whether a fixed port with an error is preferred over automatic fallback.
3. **Multiple libraries.** The design assumes a single library. Named multi-library support is deferred; the resolution scheme in §4 can accommodate it later without breaking changes.
4. **AI-session detection for the handoff.** The exact mechanism by which `shelf add` detects it is already running inside a Claude Code or Codex session (environment variable vs. parent-process inspection) is verified at build time, so the CLI never nests an interactive session (§11.2).
