# Shelf — Product Requirements Document

*A private documentation library and management toolkit.*

---

## 1. Overview

**Shelf** is a private personal documentation library. It holds reference docs, published HTML documents, and Markdown explainers and tutorials — copied and organized into the library so the content is self-contained and more or less static. A generated single-page HTML interface provides search and access; a `shelf` CLI manages the library; and a plugin exposes management and retrieval skills to AI coding tools.

Shelf is delivered as **two repositories** (P09, 2026-07-22 — the plugin moved into the `shelf` repo; the separate `shelf-skill` repo is abandoned):

- `shelf` — a **monorepo**: the management CLI, the UI template, **and** the Claude Code / Codex plugin (a single `shelf` skill).
- `shelf-library` — the document content itself.

The library content is the user's data. By default it is stored in the standard per-user data location and accessed through the CLI and the UI; a CLI command reveals its path.

---

## 2. Goals and Non-Goals

### Goals

- A single, self-contained, private library of reference documentation.
- A generated single-page `index.html` UI with autocomplete search over title, description, and tags, organized by subject, with per-file copy actions.
- A `shelf` CLI that is the single writer of the catalog and the only thing that mutates library state.
- Management and retrieval skills usable from any other repository, in both Claude Code and Codex.
- Reproducible, self-contained tooling (a uv-managed package installed via `uv tool install`).
- Stable file paths, so references handed out by the UI remain valid over time.
- A machine-portable library — no machine-specific data is committed.

### Non-Goals

- Not a hosted service or public site.
- No marketplace distribution initially — the plugin ships in the `shelf` repo and is installed directly. *(P09: whether "no marketplace initially" still holds under the monorepo is re-specified under P14.)*
- No automated ingestion — every catalog mutation is user-initiated. The UI and skills assist, but the human stays in the loop and confirms classification. (A user-confirmed URL fetch performed by the `shelf` skill is user-initiated, not automated.)
- No heavy build pipeline. The only runtime is an optional lightweight local server for the UI's enhanced mode (§13).
- No Windows support. macOS is the primary platform; Linux is expected to work.

---

## 3. Repository Architecture

Shelf is split across two repositories. The `shelf` repo is a **monorepo** — the CLI (releases on its own cadence) **and** the plugin (a thin AI-tool integration) — while `shelf-library` holds user content. **P09 (2026-07-22): the plugin moved into the `shelf` repo; the previously-specified separate `shelf-skill` repo is abandoned.**

### `shelf` — CLI, UI template, and the plugin (monorepo)

```
shelf/                            # monorepo: uv-installable CLI + Claude Code / Codex plugin
├── pyproject.toml                # [project.scripts] shelf = "shelf.cli.main:cli"
├── src/shelf/                    # the CLI package — the ONLY thing in the built wheel
│   ├── cli/                      # click command tree
│   ├── core/                     # config, catalog, paths, slugs, atomic writes
│   ├── server/                   # local UI server (enhanced mode)
│   └── templates/
│       └── index.html.tmpl       # package data — rendered into the library
├── .claude-plugin/plugin.json    # Claude Code plugin manifest (skills auto-discovered)
├── .codex-plugin/plugin.json     # Codex plugin manifest ("skills": "./skills/")
├── skills/shelf/                 # the single `shelf` skill (SKILL.md + references/)
├── tests/
└── README.md
```

The plugin files (`skills/`, `.claude-plugin/`, `.codex-plugin/`) ride in the repo (git) but are **excluded from the built wheel** — `uv_build`'s src layout packages only `src/shelf`.

### The plugin — a **single `shelf` skill**

**P09:** the plugin is a **single `shelf` skill** with progressive disclosure — a lean `SKILL.md` (one always-on trigger) routing to per-operation references loaded on demand — **not** seven `shelf-*` skills. It shells out to the `shelf` CLI and never mutates library state directly.

```
skills/shelf/
├── SKILL.md                       # one trigger; routing table; invariants
└── references/                    # add · edit · find · remove · audit · open · init
```

The same skill works as both a **Claude Code plugin** (`.claude-plugin/plugin.json`, skills auto-discovered) and a **Codex plugin** (`.codex-plugin/plugin.json`, `"skills": "./skills/"` + `interface` block). Both manifests live at the repo root; formats are verified against current plugin docs and both ecosystems tested at build time — via `skillsmith verify --deep` (see §14).

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

`catalog.json`, `index.html`, and all of `docs/` are committed when the library is a git repo. `index.html` is generated from the template that ships with the `shelf` CLI and rewritten on every mutating command. Making the library a git repo (and creating a GitHub remote) is offered, optionally, at `shelf init` (§11.1).

### Tooling primitives

Every user-facing capability is reachable through the CLI; **the skill owns the capabilities that need judgment or conversation**. The command↔skill ownership table in §12 is normative — commands marked direct-CLI deliberately have no skill. Slash commands are deprecated in favor of skills. **P09:** the seven `shelf-*` skills were consolidated into a **single `shelf` skill** (progressive disclosure); §12's ownership rows now map each capability to a `references/*.md` within it.

---

## 4. Configuration and Location Resolution

This section answers "how does shelf know where to keep and find `catalog.json` and `index.html`."

`catalog.json` and `index.html` are user content and live in the library. `index.html` is *generated* from a template that ships with the `shelf` CLI. The CLI must therefore locate the library.

### Config file

XDG-based, TOML: `${XDG_CONFIG_HOME:-~/.config}/shelf/shelf_config.toml` — the CLI Design Standard's canonical `<tool>_config.toml` name (R5.2), which keeps the file self-identifying when copied or grepped. Created by `shelf init`. It holds the library path and user defaults, with kebab-case keys for flag/env/config name parity (R3.8):

```toml
library = "/Users/<user>/.local/share/shelf"
remove-source = true          # default for `doc add` / `doc format add`
server-port = 8765            # local UI server port
browser = "Google Chrome"     # browser for `shelf open` on macOS
handoff-agent = "claude"      # agent launched by the `doc add` handoff: claude | codex
```

### Library path resolution

Highest precedence first:

1. `--library <path>` — CLI flag.
2. `SHELF_LIBRARY` — environment variable.
3. The `library` key in the **active config file**, where the active config file is `--config <path>` if given, otherwise `${XDG_CONFIG_HOME:-~/.config}/shelf/shelf_config.toml`.
4. None of the above → the library is unconfigured. The CLI exits with guidance to run `shelf init`; the `shelf-add` skill triggers first-run setup automatically (§12).

This provides a **direct** override (`--library` / `SHELF_LIBRARY`) and an **indirect** one — `XDG_CONFIG_HOME` relocates the config directory, and the config file carries the library path.

The design assumes a single library. Multiple named libraries could be added later without breaking this scheme.

### Default library location

`${XDG_DATA_HOME:-~/.local/share}/shelf` — the standard per-user data location for a CLI application. `shelf init` creates the library there unless `--library` specifies otherwise.

### `shelf path`

Because the library lives in a non-obvious location, the CLI reveals it: `shelf path` prints the resolved library root; `shelf path config` prints the config file path; `shelf path index` prints the generated `index.html` path.

### Machine portability

Nothing machine-specific that is ever resolved is committed. `catalog.json` stores only library-relative paths; the one exception is the inert `source` provenance field (§10), which may record absolute paths from the machine where a document was added and is never resolved. The UI resolves the library's absolute path at view time (§13), so the `shelf-library` repository clones cleanly to any machine — where `shelf init --adopt <path>` registers it (§11.1).

---

## 5. The `shelf` CLI

The CLI is the **single writer** of `catalog.json` and the only thing that mutates library state. Skills call the CLI rather than editing `catalog.json` directly — this allows validated writes and is far more context-efficient for the skill.

Every **mutating subcommand** (`init`, `doc add`, `doc format add`, `doc format delete`, `doc update`, `doc move`, `doc delete`, `doc adopt`, `orphan delete`, `topic add`, `kind add`, `migrate`) performs two actions as one atomic unit: it updates `catalog.json`, and it regenerates `index.html` from the template. The exception is `shelf regen` (§11.12), which rewrites only `index.html`.

Atomicity is achieved by ordering, with the catalog write as the **commit point**. Everything is prepared first — files staged, the new `catalog.json` and `index.html` rendered to temp files — then `catalog.json` is atomically renamed into place, then `index.html`. Failure before the commit point discards the staged work and leaves the library untouched. Failure after it leaves the catalog authoritative and some derived or residual state to reconcile, and every such state is **audit-detectable and repairable**: a stale index (check 4 → `shelf regen`), a duplicate folder from an interrupted `doc move` or an undeleted folder from an interrupted `doc delete` (check 1 → orphan remediation, §11.6), an uncommitted library after a failed `--commit` (check 5). Source removal (§11.2) runs only after everything else has succeeded. External effects are not rolled back: a failed `shelf init --github` may leave a created GitHub repository to remove manually. Every command that writes library files — the mutating commands and `shelf regen` — takes an exclusive advisory lock (`.shelf.lock` at the library root); `shelf audit` acquires it briefly to snapshot, so it never observes a mid-transaction state.

### Subcommands

Detailed in §11.

- `shelf init` — create, adopt, and register a library.
- `shelf doc add <file>...` — add a new document (one or more format files → one entry).
- `shelf doc format add <id> <file>...` — add a format variant to an existing document.
- `shelf doc format delete <id> <format>` — remove a format variant from a document.
- `shelf doc update <id>` — change a document's metadata (pure catalog changes).
- `shelf doc move <id>` — relocate a document (topic, repo, or anchoring change).
- `shelf doc delete <id>` — delete a document (entry + folder); alias `rm`.
- `shelf doc list` — filter and query documents; alias `ls`.
- `shelf doc view <id>` — print one document in full.
- `shelf doc adopt <folder>` — register an existing in-library folder (orphan adoption).
- `shelf orphan list` / `shelf orphan delete <path>` — manage uncataloged files.
- `shelf audit` — run the library consistency check.
- `shelf open` — open the UI (§13).
- `shelf path [config|index]` — print resolved locations.
- `shelf regen` — regenerate `index.html` from the current catalog.
- `shelf migrate` — migrate the catalog to the current schema version.
- `shelf topic add <name>` / `shelf topic list` — manage topic buckets.
- `shelf kind add <name>` / `shelf kind list` — manage kinds.

The CLI validates every write: a topical document's `category` must exist in the topic list, and every document's `kind` must exist in the kind list.

### Runtime

The CLI is a Python package in the **src layout**, following py-launch-blueprint conventions (click, uv-managed, pytest/ruff/ty). It installs as a tool — `uv tool install shelf` (or from git) — which places `shelf` on `PATH`. The UI server is part of the package and is started by `shelf open`; there is no separate script to manage. The UI template ships inside the package and is read via `importlib.resources`, so a tool-installed CLI renders `index.html` with no repo checkout present.

### Standards conformance

The CLI conforms to the org **CLI Design Standard** (cli-standards repo, v1.4.14). The standard's §6 (exit codes), §7 (streams, machine-error schema, help shape, bare/unknown invocation), §8 (interaction and safety), and R9.6 (signals) apply **by reference**. Specific bindings: a nonexistent `<id>` exits `3`; `shelf audit` exits `1` when findings exist (a documented predicate result per R6.2 — no stderr error object accompanies it); bare `shelf` prints help and exits `0`; a bare group (`shelf doc`) is a usage error, exit `2`; `doc delete` prompts on a TTY with `--yes` as non-interactive consent; under `--no-input` the CLI never prompts and never launches the handoff — missing classification flags exit `2`.

**Documented waivers** (rule / deviation / rationale — owner Steve, 2026-07-18):

- **R2.1 — `add` instead of `create`** for `doc add`, `topic add`, `kind add`. Shelf ingests existing artifacts rather than creating them, and "add to shelf" is the product's language; one waiver covers all three for consistency.
- **R2.2 — `regen` abbreviation.** Rare, mostly skill-invoked maintenance command; the abbreviation is well understood in context.
- **R5.1/R5.2 — no project or system config scopes.** Shelf is a per-user library tool; only the user scope (`$XDG_CONFIG_HOME/shelf/shelf_config.toml`) and the `--config` override exist.

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

Physical location is permanent; classification is metadata. The copy-path action hands out paths that get pasted into skills and other repositories, so a document's folder must not move when it is re-tagged. Re-tagging is a metadata change. Relocating a document between buckets is the deliberate, rare `shelf doc move` operation (§11.5).

---

## 7. Document Identity and Slugs

A document's slug is its stable identifier (`id`) and its folder name. Variant files share the slug as their stem.

- **Format:** `YYYY-MM-DD-<kebab-title>` — date prefix, then the kebab-cased title or subject.
- **Date:** the date the document was **added to shelf** — always known, unambiguous, and never becomes wrong. The date prefix makes slug collisions unlikely; an exact collision (the same title added on the same day) is detected and rejected at `shelf doc add` (§11.2). The content's own publication date, when relevant, is stored separately as `doc_date`.
- The kebab title is truncated to roughly 60 characters.
- The slug is auto-derived from the title, with a `--slug` override at `shelf doc add`.
- **The slug is immutable.** It is the permanent `id`; neither `shelf doc update` nor `shelf doc move` ever re-slugs a document.

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
  "schema_version": 1,
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
    },
    {
      "id": "2026-06-03-uv-inline-scripts-explainer",
      "title": "uv Inline Scripts — Explainer",
      "description": "...",
      "category": "dev-tooling",
      "kind": "explainer",
      "tags": ["python", "uv", "packaging"],
      "files": [
        { "format": "md", "path": "docs/topics/dev-tooling/2026-06-03-uv-inline-scripts-explainer/2026-06-03-uv-inline-scripts-explainer.md" }
      ],
      "primary": "md",
      "added": "2026-06-03",
      "doc_date": null,
      "source": "/Users/<user>/Downloads/uv-scripts.md"
    }
  ]
}
```

Notes:

- `schema_version` tracks the catalog format. Read commands operate on older supported schemas without writing; mutating commands refuse an older schema and point at `shelf migrate` (§11.14); every command refuses a newer one.
- A **topical** entry omits `repo` and instead carries `category` (a value from `topics`).
- `files[]` lists every format variant — `format`, library-relative `path`, and an optional per-variant `source`.
- `primary` names the variant the UI links on click.
- `added` is the shelf-add date (also encoded in the slug); `doc_date` optionally records when the content itself was authored.
- `source` (document-level) records where the original came from; it is **retained even after the original file is removed**, as a provenance record. It is inert — never resolved — and may contain absolute paths from the machine where the document was added (§4).
- There is no `root` field — the UI resolves the library's absolute path at view time (§13).

---

## 11. Command Reference

Common conventions — the CLI implements the CLI Design Standard's option tiers (R4.1):

- **Global core**: `-h/--help`, `-V/--version` (`-v` is *not* version), `-v/--verbose` (repeatable), `-q/--quiet`, `--config <path>`, `--debug`, `--no-input` (never prompt; fail instead — it also implies `--no-handoff`, §11.2).
- **Result output**: `-o/--output <table|json>` — `table` is the human default and may change between releases; `json` is machine-stable within a major version. `--json` is exact shorthand for `-o json`; every `--json` reference in this document means this pair. The enum is extensible (`jsonl`, `name` may be added later).
- **Safety/action**: `--dry-run`; `-f/--force` (guard override — protected or inconsistent state; never implies consent); `-y/--yes` (consent to prompts).
- **Mutations**: every mutating command supports `--commit` (default off; the auto-generated message describes the change, e.g. `shelf: doc add <slug>`) and `--commit-message`. `--commit` requires the library to be a git repository and errors otherwise; `shelf init` is the exception — its initial commit is governed by `--git` (§11.1), not `--commit`. Every mutating command updates `catalog.json` and regenerates `index.html` atomically (`shelf regen`, §11.12, rewrites only `index.html`).

### 11.1 `shelf init`

Creates a library and registers it in the config file.

```
shelf init [--library <path>] [--adopt <path>] [--git] [--github] [--owner <gh-owner>] [--force]
```

- `--library <path>` — where to create the library; defaults to `${XDG_DATA_HOME:-~/.local/share}/shelf`.
- `--git` — initialize the library as a git repository.
- `--github` — create a private GitHub repository and set it as the remote, via `gh repo create <owner>/shelf-library --private`. Implies `--git`. Both `--git` and `--github` are optional and offered, not assumed.
- `--owner <gh-owner>` — GitHub owner for `--github`; defaults to the authenticated `gh` user.
- `--adopt <path>` — register an **existing** library instead of scaffolding one: validate it (parseable `catalog.json`, supported `schema_version`, `docs/repos/` and `docs/topics/` present), then write `shelf_config.toml` pointing at it. Touches nothing inside the library. Mutually exclusive with `--git`, `--github`, and `--force`. This is the new-machine flow: clone `shelf-library`, then `shelf init --adopt <path>`.

Behavior: scaffolds `catalog.json` (empty `topics`, `kinds` seeded with the six default kinds, empty `documents`), `docs/repos/`, `docs/topics/`, the generated `index.html`, and a README; then writes `${XDG_CONFIG_HOME:-~/.config}/shelf/shelf_config.toml` with `library` pointing at the new library. With `--git`, the scaffolded files are recorded as the library's initial commit. Refuses to overwrite an existing configured library unless `--force`.

### 11.2 `shelf doc add`

Adds a **new document**.

```
shelf doc add <file>... (--repo <name> | --topic <name>) --kind <kind>
              --title <text> --description <text> [options]
```

All positional files are **format variants of one document** → one entry. Format is inferred from extension (`.md`, `.html`/`.htm`, `.pdf`). Two files of the same format is an error. For two documents, run `shelf doc add` twice.

**Interactive handoff** — when the required classification flags are missing, `shelf doc add` does not error: it launches the configured **handoff agent** — `--handoff-agent <claude|codex>` flag, else the `handoff-agent` key in `shelf_config.toml`, else `claude` — with a primed introductory prompt that references the `shelf` skill and passes the input file paths (for example: *"Use the shelf skill to add `/Users/<user>/Downloads/cli-extension-prd.md` to shelf. Walk me through classification."*). The user lands in an interactive session where the skill drives classification, confirmation, and the eventual fully-flagged CLI call. `--no-handoff` suppresses the handoff, making missing flags an error; `--no-input` implies it (§5, standards conformance). When the CLI is already running inside a Claude Code or Codex session (detected via environment, §14), it never nests a session — it errors with a message asking the assistant to invoke the `shelf` skill directly. This makes the `shelf` CLI the single entry point whether the user starts in the shell or in an AI session: fully-flagged invocations run non-interactively; judgment-needing invocations hand off to the skill, which lives in exactly one place.

**Input** — `<file>...` (≥1); `--assets <path>` (repeatable; files or directories copied into the document folder so HTML relative links resolve); `--format <ext>` (long-only, since `-f` is `--force`; overrides inference). Registering a folder already inside the library is `shelf doc adopt` (§11.15).

**Anchoring** — exactly one of: `--repo <name>` (with `--repo-url <url>`, inferred from the git remote of the repository containing the source file when there is one, otherwise required, and `--subject <label>`); or `--topic <name>` (with `--create-topic` to authorize creating an unknown topic — without it, an unknown topic is an error).

**Classification** — `--kind <kind>` (required; must exist; `shelf doc add` never creates kinds); `--tag <tag>` (repeatable, free-form).

**Identity/metadata** — `--title` (required), `--description` (required), `--slug` (override), `--primary <format>` (default heuristic: md, else html, else pdf, else first), `--doc-date <YYYY-MM-DD>`, `--source <text>` (default: absolute path of the first input file).

**Source handling** — by default the original input files are **removed** after a fully successful add; this default is the `remove-source` config key. `--remove-source` / `--no-remove-source` override it explicitly (R3.6 negation). The `shelf-add` skill asks the user and passes the explicit flag.

**Behavior** — validation order: exactly one anchor; kind exists; topic exists or `--create-topic`; no duplicate format; slug/folder free. Duplicate slug → error pointing at `--slug` or `shelf doc format add`. Atomic with rollback; files copied (never moved) and renamed to `<slug>.<ext>`; source removal runs only after copy, catalog write, index regeneration, and any commit all succeed.

```
shelf doc add ./cli-extension-prd.md ./cli-extension-prd.pdf \
  --repo flox-cli --repo-url https://github.com/flox/flox \
  --subject cli-extensions --kind spec --primary md \
  --title "Flox CLI Extension System — PRD" \
  --description "Porting the gh extension model into the Flox CLI." --commit
```

### 11.3 `shelf doc format add`

Adds a **new format variant to an existing document**.

```
shelf doc format add <id> <file>... [options]
```

`<id>` is the exact slug of an existing document. Positional files are new variants of that document; format is inferred. Adding a format the document already has is an error unless `--replace`.

It never re-anchors or re-classifies — `--repo`/`--topic`, `kind`, `tags`, and `title` are unchanged by this command (they are edited via `shelf doc update`, §11.4); only the slug is immutable (§7).

**Options** — `--assets <path>` (repeatable); `--format <ext>`; `--replace` (overwrite an existing same-format variant); `--primary <format>` (set/change the primary; must be a format the document will have after the operation); `--source <text>` (recorded on the new file entry); `--remove-source`/`--no-remove-source` (same default-remove behavior as `shelf doc add`).

**Behavior** — `<id>` exists; each new format absent unless `--replace`; new files copied into the document's existing folder and renamed to `<slug>.<ext>` (the folder never moves); appended to `files[]`; atomic with rollback.

```
shelf doc format add 2026-05-22-cli-extension-prd ./cli-extension-prd.pdf --commit
```

### 11.4 `shelf doc update`

Changes a document's metadata. Covers only changes that are a **pure `catalog.json` rewrite** — no files move.

```
shelf doc update <id> [field options...] [--force] [options]
```

**Freely editable** — `--title` (display title only; never re-slugs or moves the folder), `--description`, `--kind` (validated), `--add-tag`/`--remove-tag` (repeatable) / `--set-tags <a,b,c>`, `--primary <format>` (must be a format the document has), `--doc-date <YYYY-MM-DD>` / `--clear-doc-date`, `--source`, and for repo-anchored documents `--repo-url` / `--subject` / `--clear-subject`.

**`--force`-gated** — fields that are dangerous but do not move files: `--added <date>` (coupled to the slug; editing it desynchronizes the slug) and low-level `files[]` corrections. These warn and require `--force`.

**Not editable here** — the topic, the repo, and topical↔repo anchoring all relocate the document's folder and belong to `shelf doc move`; attempting them errors and points there. The `id`/slug is immutable.

**Behavior** — `<id>` must exist; at least one field option required (or `-i` for a guided edit on a TTY); pure atomic `catalog.json` rewrite plus `index.html` regeneration; `--dry-run` shows a before/after diff.

```
shelf doc update 2026-05-22-cli-extension-prd \
  --kind reference --add-tag rust --remove-tag draft \
  --description "Reference for the Flox CLI extension system." --commit
```

### 11.5 `shelf doc move`

Relocates a document — the changes `shelf doc update` excludes because they move files on disk.

```
shelf doc move <id> (--topic <name> [--create-topic] | --repo <name> [--repo-url <url>] [--subject <label>])
```

Handles the three relocation operations: change a document's topic; change its repo; switch its anchoring (passing `--topic` for a currently repo-anchored document converts it to topical and drops the `repo` object; passing `--repo` for a topical document does the reverse).

**Behavior** — `<id>` must exist; physically moves the document folder from the old bucket to the new one, updates every `files[]` path, and updates `catalog.json`; honors governed growth (`--create-topic` for an unknown topic). It **warns** that absolute paths previously copied from the UI for this document will no longer resolve — accepted as rare by design. Atomic with rollback; `--dry-run` shows the old and new paths.

```
shelf doc move 2026-05-22-cli-extension-prd --topic dev-tooling --create-topic --commit
```

### 11.6 `shelf audit`

Deterministic consistency check. Suitable as a pre-commit hook; exits non-zero when any problem is found.

It flags:

1. Files present under `docs/` but missing from the catalog (orphans).
2. Catalog entries whose `files[]` point at files that do not exist (dead references).
3. Entries that are malformed or uncategorized — missing required fields, a `kind` not in the kind list, a `category` not in the topic list, a per-document folder that does not match its anchoring, an `added` date that does not match the slug's date prefix, or a `schema_version` older than current.
4. Missing or unparseable `shelf_config.toml`, `catalog.json`, or `index.html`, and an `index.html` whose embedded catalog fingerprint does not match the current `catalog.json` — stale; fixed by `shelf regen` (§11.12).
5. When the library is a git repository, uncommitted (dirty) changes to `catalog.json`, `index.html`, or `docs/`. This check is skipped in pre-commit mode (`--pre-commit`) — as a hook, the staged changes are precisely what is being committed, so flagging them would make every commit fail.

Each finding has a legal remediation, so the `shelf-audit` skill can offer fixes without ever mutating the library itself:

| Finding | Remediation |
|---|---|
| 1. Orphan files | list with `shelf orphan list`; adopt in place — `shelf doc adopt <folder>` (§11.15) — or delete — `shelf orphan delete <path>` |
| 2. Dead `files[]` references | `shelf doc format delete <id> <format> --force` (§11.13) |
| 3. Malformed or uncategorized entries | `shelf doc update`; an old `schema_version` → `shelf migrate` (§11.14) |
| 4. Missing, unparseable, or stale files | config → `shelf init --adopt`; index → `shelf regen` (§11.12) |
| 5. Dirty git state | the `shelf-audit` skill offers `git add` / `git commit` run in the library — recording history is not library mutation |

`--json` emits a structured report.

### 11.7 `shelf open`

Opens the UI.

```
shelf open [--static]
```

By default `shelf open` starts the local server (part of the shelf package, on the configured `server-port`, reusing an already-running instance) and opens the configured browser to `http://localhost:<port>` — **enhanced mode**, with copy-contents and inline HTML rendering. `--static` instead opens the on-disk `index.html` directly as a `file://` page — **core mode** (browse, search, copy-path). If the configured port is occupied, the server falls back to the next free port. Works from any directory because the CLI resolves the library location. The server binds `127.0.0.1` only and refuses to serve any path outside the library root.

### 11.8 `shelf path`

Prints resolved locations: `shelf path` → library root; `shelf path config` → config file; `shelf path index` → generated `index.html`.

### 11.9 `shelf topic` and `shelf kind`

`shelf topic add <name>` / `shelf topic list`; `shelf kind add <name>` / `shelf kind list`. Both `add` forms append to the relevant top-level array in `catalog.json` after validation. Topic creation is the explicit step in governed growth; kind creation is deliberate and rare.

### 11.10 `shelf doc delete`

`shelf doc delete <id>` (alias `rm`) deletes a document — its entry from the catalog and its folder from `docs/`. Atomic; `--dry-run` previews; `--commit` available. On a TTY it prompts before deleting; non-interactive invocation requires `--yes`. Deleting uncataloged files is `shelf orphan delete` (§11.15).

### 11.11 `shelf doc list` and `shelf doc view`

Read-only; neither touches the library.

```
shelf doc list [--repo <name>] [--topic <name>] [--kind <kind>] [--tag <tag>]
               [--query <text>] [--limit <n>] [--sort-by added|title] [--json]
shelf doc view <id> [--json]
```

`shelf doc list` (alias `ls`) prints matching documents (id, title, kind, anchor). Filters AND together; `--query` substring-matches over id, title, description, tags, and repo `subject`; `--limit <n>` caps results and `--sort-by added|title` orders them (default `added`, newest first). `shelf doc view` prints a single entry in full, including `files[]` with both library-relative and resolved absolute paths. These are the intended way for skills to resolve ids and inspect state — a skill should never need to open `catalog.json` itself.

### 11.12 `shelf regen`

Regenerates `index.html` from the current catalog and the installed template. It never touches `catalog.json`. This is the escape hatch for CLI/template upgrades, when no mutation has occurred to trigger regeneration. Supports `--dry-run`, `--commit`, `--json`.

### 11.13 `shelf doc format delete`

```
shelf doc format delete <id> <format> [--primary <format>] [--force]
```

Removes one format variant: deletes the file and its `files[]` entry. Refuses to remove the last variant (that is `shelf doc delete`). Removing the current primary requires `--primary` to name the successor. `--force` also drops an entry whose file is already missing — the dead-reference repair (§11.6). Atomic; `--dry-run`, `--commit` as usual.

### 11.14 `shelf migrate`

Migrates `catalog.json` to the current `schema_version`, atomically, then regenerates `index.html`. No-op when already current. Supports `--dry-run`, `--json`, `--commit`.

### 11.15 `shelf doc adopt` and `shelf orphan`

```
shelf doc adopt <folder> --kind <kind> --title <text> --description <text> [options]
shelf orphan list [--json]
shelf orphan delete <path> [--yes]
```

`shelf doc adopt` registers an existing per-document folder already under `docs/` without copying: anchoring is derived from the folder's location, the slug from the folder name; classification flags are required as for `shelf doc add`. This is the orphan-adoption repair (§11.6). `shelf orphan list` enumerates files under `docs/` with no catalog entry — the same detection as audit check 1. `shelf orphan delete` deletes such a file or folder and errors if the path is referenced by the catalog. Both `doc adopt` and `orphan delete` are mutating commands with the usual conventions; `orphan delete` prompts on a TTY.

---

## 12. Skills

**P09 (2026-07-22) — superseded: one skill, not seven.** The seven `shelf-*` skills below were consolidated into a **single `shelf` skill** (progressive disclosure) that lives in the `shelf` repo (monorepo, §3). Each owner in the table maps to a `references/*.md` within that skill; the drive patterns are unchanged. The full rewrite of this table is tracked as **P14**.

The skill lives in the `shelf` repo's plugin and shells out to the `shelf` CLI. The plugin targets **both Claude Code and Codex**; the same skill is packaged for each, with manifests verified and tested against both at build time.

The ownership table is normative — every CLI capability either has a skill owner or is deliberately direct-CLI:

| CLI surface | Skill owner |
|---|---|
| `init`, `init --adopt` | `shelf-init` (first-run path: `shelf-add`) |
| `doc add`, `doc format add`, `topic add`, `kind add` | `shelf-add` (governance flows) |
| `doc update`, `doc move`, `doc format delete` | `shelf-edit` (owns relocation intents; routes to `doc move`) |
| `doc delete` | `shelf-remove` |
| `audit`, `regen`, `migrate`, `doc adopt`, `orphan list|delete` | `shelf-audit` (repair flows) |
| `open` | `shelf-open` |
| `doc list`, `doc view` | `shelf-find` (also used internally by every skill) |
| `path`, `topic list`, `kind list` | direct CLI — no skill |

Skill names follow the user's intent language ("edit the description", "remove that doc"), not CLI verb spellings — the skill translates intent to the conforming command.

### `shelf-add` (skill)

Triggered when the user indicates they have a document to add — either directly inside a Claude Code/Codex session, or via the `shelf doc add` interactive handoff (§11.2), which launches the configured agent with this skill primed.

1. **First-run setup.** If no library is configured, the skill runs the init flow before anything else — it proposes the default on-disk location, asks whether to make it a git repo, and if so offers to create the private GitHub repo — then invokes `shelf init` and continues. This is the primary path by which a library comes to exist; the user never has to know `shelf init` exists.
2. **URL inputs.** When the input is a URL rather than a file, the skill fetches it to a temporary file, shows the user what it retrieved (title, size, format), and on confirmation continues with that file. The CLI never fetches.
3. Determines whether this is a **new document** or a **new format for an existing document** and routes to `shelf doc add` or `shelf doc format add`.
4. Classifies it — repo-anchored vs. topical, `kind`, `tags` — running the topic governed-growth flow and surfacing a trend-triggered kind suggestion when warranted — and asks whether to keep or remove the original source, so the explicit `--remove-source`/`--no-remove-source` flag is part of the invocation.
5. Invokes the CLI, which copies the document into `docs/repos/...` or `docs/topics/...` and writes the catalog — the skill never mutates library state itself (§5).
6. Confirms the result.

**Drive pattern** — inspect the file(s) → `shelf topic list` / `shelf kind list` → propose classification → call the CLI with `--dry-run --json` to preview → on confirmation, the real run with the chosen flags, adding `--commit` when the library is a git repository.

### `shelf-edit` (skill)

Edits document metadata. The user can speak in intent ("reclassify X as a tutorial", "tighten the description on Y") and the skill resolves the `id` and fields and calls `shelf doc update`. When the request is actually a relocation (a different topic or repo), the skill explains that this moves the document and routes to `shelf doc move` instead. It also owns variant maintenance: removing an obsolete format variant runs `shelf doc format delete` (§11.13).

### `shelf-init` (skill)

A deliberate, re-runnable setup path — for repairing configuration or creating a library outside the first-run flow. It wraps the same `shelf init` CLI as the `shelf-add` first-run path, so there is no duplicated logic; it is the secondary entry point. It also owns the new-machine flow: clone `shelf-library`, then `shelf init --adopt <path>` (§11.1).

### `shelf-find` (skill)

Triggered when the user wants shelf content in the current session — "what do I have on X?", "grab my flox PRD from shelf", "use my provider-config notes as context". Read-only. Drive pattern: `shelf doc list --query` (narrowing with `--repo`/`--topic`/`--kind`/`--tag`) → disambiguate conversationally when matches are plural → `shelf doc view <id>` → read the primary variant at its resolved path, or hand the path to the user. It never mutates the library.

### `shelf-remove` (skill)

Owns destructive removal. Resolves intent ("remove the old auth guide") to an id via `shelf doc list`, shows exactly what will be deleted — the entry and its folder with every variant and asset — asks for confirmation, then calls `shelf doc delete <id> --yes` (adding `--commit` when the library is a git repository).

### `shelf-audit` and `shelf-open` (skills)

Thin skills wrapping deterministic CLI calls. `shelf-audit` runs `shelf audit`, summarizes the report, and offers each finding's remediation from the §11.6 matrix — `shelf regen`, `shelf migrate`, orphan adoption or deletion, and (for dirty git state) a `git` commit run in the library; the underlying `shelf audit` subcommand can also run directly as a pre-commit hook (§11.6) so the catalog cannot silently drift. `shelf-open` runs `shelf open`.

### Cross-tool usage

Installed as a plugin, the skill is available in every Claude Code or Codex session regardless of the current repository. It is defined and version-controlled in the `shelf` repo (monorepo) but usable everywhere. Outside AI sessions, the same operations are reachable through the standalone `shelf` CLI, which hands off to the configured agent when judgment is needed (§11.2).

---

## 13. The `index.html` UI

A generated single-page interface for finding and accessing documents.

### Generated static file, optionally served

`index.html` is **generated by the CLI from a template** (`index.html.tmpl`, shipped as package data with the CLI) and **regenerated on every mutating command**. The generated file is committed in `shelf-library` and lives on disk alongside the docs — so it can be viewed without running anything. Only the **catalog metadata** and a short, bounded per-document **preview snippet** (the first heading and paragraph, capped) are embedded into it; full document contents are never bulk-embedded. The bounded snippet lets the UI show a peek of each document — including in core `file://` mode, where fetching neighbouring files is blocked (§13 modes). The generator also embeds a fingerprint: a content hash of `catalog.json` plus a content hash of the template that rendered it (the shelf version is embedded alongside for display). Staleness is therefore deterministic — `shelf audit` recomputes both hashes and compares (§11.6), and `shelf regen` (§11.12) refreshes the file after a CLI or template upgrade.

The UI runs in one of two modes:

- **Core mode** (`file://`) — the file is opened directly (double-click, or `shelf open --static`). Search, browse, and **copy absolute path** all work with no server.
- **Enhanced mode** (served) — `shelf open` runs a lightweight local server and opens the browser to `http://localhost:<port>`. In addition to everything in core mode, this enables **copy contents** and **inline rendering of HTML documents** with their assets, because the page can fetch document files over HTTP.

The split exists because browsers block a `file://` page from fetching neighboring files. Copy-contents is therefore an enhanced-mode feature; the UI hides or disables it in core mode.

### Search and organization

- **Search:** autocomplete / fuzzy matching over document title, description, and tags.
- **Primary organization:** grouped by subject — topical documents by `category`, repo-anchored documents under their repo with `subject` sub-headings. `kind` is shown as a badge.
- **Alternative view:** a toggle re-groups the same documents by `kind`.
- **Per-variant rows:** each format variant has its own copy actions.

### Copy actions

- **Copy absolute path** — all variants, both modes. The library's absolute root is resolved at view time: in core mode the page reads its own `file://` location (it physically sits at the library root) and strips the filename; in enhanced mode the server injects the absolute root. Either way, no absolute path is committed. The button concatenates that root with the variant's library-relative path.
- **Copy contents** — Markdown and HTML variants, enhanced mode only. Copies the raw file text, read on the fly.

---

## 14. Open / Deferred Items

1. **Plugin manifests — resolved (P09).** The dual manifests live in the `shelf` repo (monorepo, §3): `.claude-plugin/plugin.json` (skills auto-discovered from `skills/`) and `.codex-plugin/plugin.json` (`"skills": "./skills/"` + an `interface` block). Both verified via `skillsmith verify --deep` — claude-code and codex both pass, no findings. (PATH placement: the CLI installs via `uv tool install`, §5.)
2. **Local server port.** Default `8765` from config, with fallback to the next free port when occupied. Confirm whether a fixed port with an error is preferred over automatic fallback.
3. **Multiple libraries.** The design assumes a single library. Named multi-library support is deferred; the resolution scheme in §4 can accommodate it later without breaking changes.
4. **AI-session detection for the handoff.** The exact mechanism by which `shelf doc add` detects it is already running inside a Claude Code or Codex session (environment variable vs. parent-process inspection) is verified at build time, so the CLI never nests an interactive session (§11.2). Claude Code sets `CLAUDECODE=1` in its sessions — the candidate mechanism; the Codex equivalent is identified at build time.
5. **Taxonomy maintenance.** `topic rename`, `topic remove`, and `kind remove` do not exist; a topic rename implies folder moves under `docs/topics/`. Deferred deliberately.
6. **Scaffolding sequencing.** The `shelf` repo starts with py-launch-blueprint's core conventions only (src layout, click, pytest/ruff/ty, just + make check). The remaining scaffolding — CI, release automation, hooks, docs — is layered on by template-press when it is ready; those files are additive and do not disturb the package.
