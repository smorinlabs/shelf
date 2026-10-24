# shelf

**A private reference library that you and your coding agents can both use.**

You collect good documents all the time: a PRD for the repo you're working in,
an explainer you finally understood, a cheatsheet, an HTML report someone
published. They end up in `~/Downloads`, in chat threads, or in tabs you
eventually close. When you later want your agent to *"use my notes on uv
packaging"*, they are gone.

shelf gives those documents a permanent home. You tell Claude Code or Codex
*"add this to my shelf"*. The agent classifies the document with you, then
files it at a stable path in a library that you own. Later, from any repo, you
ask *"what do I have in shelf about provider config?"*. The agent finds the
document and reads it into the session.

```text
you ▸  add ~/Downloads/cli-extension-prd.md to my shelf
agent ▸  This looks like a spec for the flox-cli repo. I'd file it under
         repo flox-cli, subject "cli-extensions", kind "spec",
         tags rust, cli, extensions. Keep the original file? [preview shown]
you ▸  yes, keep it
agent ▸  Added 2026-10-24-cli-extension-prd → docs/repos/flox-cli/…  (committed)

        … a week later, in a different repo …

you ▸  grab my flox extension PRD from shelf and use it as context
agent ▸  Found 2026-10-24-cli-extension-prd (spec, flox-cli). Reading it now.
```

## Why shelf

- **Built for agents, and safe for them.** One skill works in both Claude Code
  and Codex. It proposes a classification, previews every change with
  `--dry-run`, and asks before anything destructive. All writes go through the
  `shelf` CLI, so an agent never hand-edits your catalog.
- **Paths that never break.** Every document lives at a permanent path such as
  `docs/topics/dev-tooling/2026-06-03-uv-inline-scripts/…`. Changing a title,
  kind, or tags is a metadata change, and the file stays where it is. Paths you
  pasted into other repos or skills keep working.
- **A searchable library in one HTML file.** Every change regenerates
  `index.html`. The page offers search, grouping by subject or kind, and
  copy-path buttons. Open it by double-clicking it, or run `shelf open` to also
  get copy-contents and inline HTML rendering.
- **Your data in plain files.** The library is a folder: `catalog.json`,
  `index.html`, and `docs/`. You can make it a private Git or GitHub repo with
  one flag. It holds no machine-specific paths, so you can clone it to a new
  machine and register it there.
- **The library audits itself.** `shelf audit` checks for orphan files, broken
  references, malformed entries, a stale index, and uncommitted changes. Every
  finding comes with the command that fixes it. You can also run the audit as a
  Git pre-commit hook.
- **You stay in control.** shelf never ingests anything on its own, never
  invents topics without asking, and never re-slugs a document.

> [!WARNING]
> **`shelf doc add` deletes the original file by default**, after the document
> has been copied into the library and everything else has succeeded.
> To keep the original, pass `--no-remove-source`, or set
> `remove-source = false` in the [config file](#configuration). The shelf skill
> always asks you which you want.

---

## Contents

- [Quick start](#quick-start)
- [Installation](#installation)
- [Using shelf from Claude Code and Codex](#using-shelf-from-claude-code-and-codex)
- [Core concepts](#core-concepts)
- [Configuration](#configuration)
- [Command reference](#command-reference)
- [Exit codes](#exit-codes)
- [The library UI](#the-library-ui)
- [Git and GitHub](#git-and-github)
- [Auditing and repair](#auditing-and-repair)
- [Moving to a new machine](#moving-to-a-new-machine)
- [Development](#development)

---

## Quick start

Install the CLI, create a library, add one document, and browse it:

```bash
uv tool install git+https://github.com/smorinlabs/shelf
shelf init --git                          # library at ~/.local/share/shelf, as a Git repo

shelf doc add ./uv.md \
  --topic dev-tooling --create-topic \
  --kind explainer --tag python --tag uv \
  --title "uv Inline Scripts" \
  --description "PEP 723 scripts with uv" \
  --no-remove-source --commit
# added '2026-10-24-uv-inline-scripts' (md) -> docs/topics/dev-tooling/2026-10-24-uv-inline-scripts

shelf doc list
# 2026-10-24-uv-inline-scripts	uv Inline Scripts	explainer	topic:dev-tooling

shelf open                                # browse and search in your browser
```

If you leave out the classification flags (`shelf doc add ./uv.md`), shelf
starts your coding agent and lets it walk you through classification. See
[The `doc add` handoff](#the-doc-add-handoff).

---

## Installation

### Requirements

| Requirement | Needed for |
|---|---|
| macOS or Linux | Everything. Windows is not supported. |
| Python ≥ 3.12 and [`uv`](https://docs.astral.sh/uv/) | Installing and running the CLI |
| `git` | Optional: version-controlling the library (`--git`, `--commit`) |
| [`gh`](https://cli.github.com/), authenticated | Optional: `shelf init --github` |
| Claude Code or Codex | Optional: the skill and the `doc add` handoff |

### Install the CLI

From GitHub:

```bash
uv tool install git+https://github.com/smorinlabs/shelf
```

From a local clone:

```bash
git clone https://github.com/smorinlabs/shelf && cd shelf
uv tool install .
```

Either command puts `shelf` on your `PATH`. Check the install with
`shelf --version`.

To run from a working copy without installing, create an executable
`~/.local/bin/shelf` wrapper. It runs the repo's CLI through `uv` and keeps
your current directory, which `doc add` needs to infer repo URLs:

```bash
#!/bin/sh
exec uv run --project /path/to/shelf shelf "$@"
```

### Create your library

```bash
shelf init                 # plain folder at ${XDG_DATA_HOME:-~/.local/share}/shelf
shelf init --git           # … also initialized as a Git repo with a first commit
shelf init --github        # … also pushed to a new private GitHub repo <you>/shelf-library
```

You can skip this step if you use the agent. The first time you ask it to add
something, the skill runs setup for you.

---

## Using shelf from Claude Code and Codex

This repo is also a plugin **marketplace** named `shelf`. It contains one
plugin, `shelf`, which holds a single `shelf` skill. The skill needs the
`shelf` CLI on your `PATH`.

**Claude Code**

```text
/plugin marketplace add https://github.com/smorinlabs/shelf
/plugin install shelf@shelf
```

**Codex**

```bash
codex plugin marketplace add https://github.com/smorinlabs/shelf
codex plugin add shelf@shelf
```

After installing, talk to the agent in plain language. The skill matches your
request to one operation and loads only that operation's instructions:

| You say something like… | The skill runs |
|---|---|
| "add this PDF to my shelf", "file this under the thoth repo" | `doc add`, `doc format add`, `topic add`, `kind add` |
| "what do I have on uv?", "use my flox PRD as context" | `doc list`, `doc view` (read-only) |
| "make that a tutorial", "move it to the dev-tooling topic" | `doc update`, `doc move`, `doc format delete` |
| "remove the old auth guide" | `doc delete --yes`, after showing you exactly what will go |
| "audit my shelf", "fix the stale index" | `audit`, `regen`, `migrate`, `doc adopt`, `orphan …` |
| "open my shelf" | `open` |
| "set up shelf on this machine" | `init`, `init --adopt` |

The skill follows four rules on every operation:

1. Every change goes through the CLI.
2. It previews with `--dry-run` before mutating.
3. It confirms deletes, moves, and ambiguous matches with you.
4. It passes `--commit` when the library is a Git repo.

The plugin's layout, local-development symlinks, and cross-tool verification
are documented in [`plugins/shelf/README.md`](plugins/shelf/README.md).

### The `doc add` handoff

The CLI and the skill share one entry point. When you run `shelf doc add` in a
normal terminal without the classification flags (`--kind`, `--title`,
`--description`, and one of `--repo` / `--topic`), shelf replaces itself with
your agent. It opens the agent with this prompt:

```text
Use the shelf skill to add `/path/to/file.md` to shelf. Walk me through classification.
```

Which agent starts is decided in this order:

1. `--handoff-agent claude|codex`
2. `handoff-agent` in the config file
3. `claude` (the default)

| Situation | Result |
|---|---|
| All classification flags given | Normal non-interactive add; no handoff |
| Flags missing, ordinary terminal | Launches the handoff agent |
| Flags missing, `--no-handoff` or `--no-input` | Error, exit `2` |
| Flags missing, already inside Claude Code (`CLAUDECODE` set) or Codex (`CODEX_THREAD_ID` set) | Error asking the assistant to use the `shelf` skill. shelf never nests an agent session. |

---

## Core concepts

### The library

```text
~/.local/share/shelf/              # default location; `shelf path` prints yours
├── catalog.json                   # source of truth, written only by the CLI
├── index.html                     # generated UI, rewritten on every change
├── README.md
└── docs/
    ├── repos/<repo-name>/<YYYY-MM-DD-slug>/…     # repo-anchored documents
    └── topics/<topic>/<YYYY-MM-DD-slug>/…        # topical documents
```

The **CLI is the only writer.** Every mutating command updates `catalog.json`
and regenerates `index.html` as one atomic unit. The steps run in this order:

1. Stage all new files and render the new catalog and index to temporary files.
2. Rename the new `catalog.json` into place. This is the commit point.
3. Rename the new `index.html` into place.

A failure before step 2 leaves the library untouched. A failure after it
leaves state that `shelf audit` detects and can repair. Writers hold an
exclusive lock, `.shelf.lock`, so two commands never interleave.

### Documents, slugs, and variants

- **A document is one folder.** The folder holds every format variant of the
  document (`.md`, `.html`, `.pdf`) and any assets, such as images an HTML
  page references.
- **The slug is the document's permanent id and its folder name.** Its format
  is `YYYY-MM-DD-<kebab-title>`. The date is the day you added the document.
  The title part comes from the title, truncated to about 60 characters.
  `--slug` overrides it. After creation, the slug never changes, and every
  variant file is named `<slug>.<ext>`.
- **`primary`** is the variant the UI opens on click. The default is `md`,
  else `html`, else `pdf`.
- **`added`** is the date in the slug. **`doc_date`** optionally records when
  the content itself was written.

### Classification

| Axis | Values | Governed by |
|---|---|---|
| **Anchor** | *Repo-anchored*: `--repo <name>`, plus `--repo-url` and an optional `--subject` label. *Topical*: `--topic <name>`. Exactly one per document. | The anchor decides the folder: `docs/repos/` or `docs/topics/`. |
| **Topic** | A coarse bucket, such as `dev-tooling` | **Governed growth.** A new library has zero topics. A topic is created only by `shelf topic add` or `--create-topic`, never silently. |
| **Kind** | What the document *is*. Seeded with `reference`, `explainer`, `tutorial`, `playbook`, `spec`, `cheatsheet`. | **Effectively closed.** `doc add` never creates kinds; `shelf kind add` does. |
| **Tags** | Free-form, any number | No list and no confirmation. Tags carry fine-grained classification and feed search. |

For repo-anchored documents, `--repo-url` is inferred from the Git remote of
the repository that contains the source file. A `subject` becomes a
sub-heading under the repo's group in the UI.

### Paths stay stable

Location is permanent, and classification is metadata. Changing a title,
kind, tags, or description never moves a file. The only command that moves a
folder is `shelf doc move`, which changes a document's topic, repo, or anchor
type. It warns you that previously copied absolute paths will stop resolving.

---

## Configuration

`shelf init` writes `${XDG_CONFIG_HOME:-~/.config}/shelf/shelf_config.toml`:

```toml
library = "/Users/you/.local/share/shelf"   # library root
remove-source = true                        # default for doc add / doc format add
server-port = 8765                          # preferred port for `shelf open`
browser = "Google Chrome"                   # written by init; not yet used (see below)
handoff-agent = "claude"                    # claude | codex, for the doc add handoff
```

| Key | Default | Effect |
|---|---|---|
| `library` | set by `init` | Library root. See the resolution order below. |
| `remove-source` | `true` | Whether `doc add` and `doc format add` delete the original files after success. `--remove-source` / `--no-remove-source` override it per command. |
| `server-port` | `8765` | Port that `shelf open` tries first. If the port is busy, shelf uses a free port chosen by the operating system. |
| `browser` | `"Google Chrome"` | Not read by the current CLI. `shelf open` uses the system default browser. |
| `handoff-agent` | `"claude"` | Agent started by the `doc add` handoff. |

**Where shelf looks for the library**, highest precedence first:

1. `--library <path>`
2. the `SHELF_LIBRARY` environment variable
3. `library` in the active config file. The active file is `--config <path>`
   if given, otherwise the default path above.
4. If none of these is set, the command fails and tells you to run `shelf init`.

| Environment variable | Effect |
|---|---|
| `SHELF_LIBRARY` | Overrides the library path |
| `XDG_CONFIG_HOME` | Moves the config directory (default `~/.config`) |
| `XDG_DATA_HOME` | Moves the default library location used by `shelf init` (default `~/.local/share`) |

Print the resolved locations with:

```bash
shelf path            # library root
shelf path config     # config file
shelf path index      # generated index.html
```

---

## Command reference

`shelf --help` and `shelf <command> --help` are authoritative. This section
explains what each command does.

```text
shelf
├── init                         create, adopt, and register a library
├── doc
│   ├── add <files>…             add a new document
│   ├── format add <id> <files>… add format variants to a document
│   ├── format delete <id> <fmt> remove one format variant
│   ├── update <id>              change metadata (no files move)
│   ├── move <id>                change topic / repo / anchor (folder moves)
│   ├── delete <id>   (rm)       delete a document and its folder
│   ├── list          (ls)       filter and query documents
│   ├── view <id>                print one document in full
│   └── adopt <folder>           register an existing folder under docs/
├── topic add <name> | list      manage topic buckets
├── kind  add <name> | list      manage kinds
├── orphan list | delete <path>  manage uncataloged files under docs/
├── audit                        consistency check
├── regen                        regenerate index.html
├── migrate                      upgrade catalog.json's schema
├── open                         open the library UI
└── path [config|index]          print resolved locations
```

Running `shelf` alone prints help and exits `0`. Running a group alone, such
as `shelf doc`, prints that group's help and exits `2`.

### Conventions

**Global options** go before the subcommand, as in
`shelf --library ~/other doc list`:

| Option | Meaning |
|---|---|
| `-h, --help` | Show help |
| `-V, --version` | Print `shelf <version>` |
| `--library PATH` | Library path override |
| `--config PATH` | Use this config file instead of the default |
| `-v, --verbose` | More diagnostic detail; repeatable |
| `-q, --quiet` | Suppress non-essential output |
| `--debug` | Maximum diagnostics |
| `--no-input` | Never prompt; fail instead. Also disables the `doc add` handoff. |

**Shared command options:**

| Option | On | Meaning |
|---|---|---|
| `--commit` / `--no-commit` | every mutating command | Record the change as a Git commit. The default is off. The automatic message is `shelf: <verb> <slug>`. Requires a Git library. |
| `--commit-message TEXT` | every mutating command | Replace the automatic commit message |
| `--dry-run` | `doc add`, `update`, `move`, `delete`; `regen`; `migrate` | Show what would happen, then change nothing |
| `-o, --output table\|json`, `--json` | `doc list`, `doc view`, `topic list`, `kind list`, `orphan list`, `audit` | `table` is for humans and may change between releases. `json` is stable within a major version. `--json` is shorthand for `-o json`. `migrate --json` prints a machine-readable report. |
| `-y, --yes` | `doc delete`, `orphan delete` | Consent without prompting. Required when not on a TTY. |
| `-f, --force` | `doc update`, `doc format delete` | Override a safety guard. It never counts as consent. |

### `shelf init`

Creates a library and registers it in the config file.

```bash
shelf init [--library PATH] [--git] [--github] [--owner OWNER] [--force]
shelf init --adopt PATH
```

- The new library contains `catalog.json` (no topics, six seeded kinds, no
  documents), `docs/repos/`, `docs/topics/`, `index.html`, and a `README.md`.
- `--library PATH` sets where to create it. The default is
  `${XDG_DATA_HOME:-~/.local/share}/shelf`.
- `--git` initializes a Git repository and records the scaffold as the first
  commit.
- `--github` implies `--git`, runs `gh repo create <owner>/shelf-library --private`,
  and sets the new repo as `origin`.
- `--owner` sets the GitHub owner. The default is the user `gh` is
  authenticated as.
- `--force` re-initializes over an existing configured library. Without it,
  `init` refuses.
- `--adopt PATH` registers an **existing** library, such as a clone, and
  creates nothing. It first checks that `catalog.json` parses, that its schema
  version is supported, and that `docs/repos/` and `docs/topics/` exist.

If `--github` fails after GitHub has created the repository, delete that
repository by hand. shelf does not roll back external effects.

### `shelf doc add`

Adds a **new document**. Every file you pass becomes a format variant of that
one document.

```bash
shelf doc add FILE… (--repo NAME | --topic NAME) --kind KIND \
  --title TEXT --description TEXT [options]
```

| Group | Options |
|---|---|
| Anchor (exactly one) | `--repo NAME`, with `--repo-url URL` (inferred from the source file's Git remote when possible) and `--subject LABEL`; **or** `--topic NAME`, with `--create-topic` to allow a new topic |
| Classification | `--kind KIND` (must already exist); `--tag TAG` (repeatable) |
| Identity | `--title`, `--description`, `--slug` (override the derived slug), `--primary FMT`, `--doc-date YYYY-MM-DD`, `--source TEXT` (provenance; the default is the first input file's absolute path) |
| Input | `--assets PATH` (repeatable; files or folders copied into the document folder so relative links in HTML work); `--format EXT` (override the format inferred from the extension) |
| Source handling | `--remove-source` / `--no-remove-source`. When neither is given, the `remove-source` config key decides, and its default is to remove. |
| Handoff | `--handoff-agent claude\|codex`; `--no-handoff` |

The format comes from the file extension: `.md`, `.html` / `.htm`, or `.pdf`.
Passing two files with the same format is an error. Adding the same title on
the same day collides with the existing slug. Pass `--slug`, or use
`doc format add` if you meant to add a variant.

Files are **copied** into the library. Source removal happens only after the
copy, the catalog write, the index regeneration, and any commit have all
succeeded.

```bash
shelf doc add ./cli-extension-prd.md ./cli-extension-prd.pdf \
  --repo flox-cli --repo-url https://github.com/flox/flox \
  --subject cli-extensions --kind spec --primary md \
  --title "Flox CLI Extension System — PRD" \
  --description "Porting the gh extension model into the Flox CLI." \
  --no-remove-source --commit
```

### `shelf doc format add` / `shelf doc format delete`

```bash
shelf doc format add ID FILE… [--replace] [--primary FMT] [--assets PATH] \
  [--format EXT] [--source TEXT] [--remove-source|--no-remove-source]
shelf doc format delete ID FMT [--primary FMT] [--force]
```

- `format add` copies new variants into the document's existing folder as
  `<slug>.<ext>`. The folder never moves.
- A format the document already has is rejected unless you pass `--replace`.
- `format add` never changes the document's anchor, kind, tags, or title.
- `format delete` removes one variant's file and its catalog entry.
- `format delete` refuses to remove the last variant; use `doc delete` for
  that.
- Deleting the current primary variant requires `--primary` to name the new
  one.
- `--force` drops a catalog entry whose file is already missing. This repairs
  a dead reference.

### `shelf doc update`

Changes metadata only. It rewrites the catalog and never moves files.

```bash
shelf doc update ID [field options] [--dry-run]
```

| Freely editable | `--title`, `--description`, `--kind`, `--add-tag` / `--remove-tag` (repeatable), `--set-tags a,b,c`, `--primary`, `--doc-date` / `--clear-doc-date`, `--source`, and for repo-anchored documents `--repo-url`, `--subject` / `--clear-subject` |
|---|---|
| Needs `--force` | `--added DATE`. This puts the slug's date prefix out of sync with `added`. |
| Rejected | `--topic`, `--repo`. These move the folder, so use `shelf doc move`. |

A new `--title` changes only the display title. The slug stays the same.
`--dry-run` prints a before/after line for each field, for example:

```text
tags: ['python', 'uv'] -> ['python', 'uv', 'pep723']
```

### `shelf doc move`

Relocates a document folder and rewrites its file paths.

```bash
shelf doc move ID (--topic NAME [--create-topic] | --repo NAME [--repo-url URL] [--subject LABEL]) [--dry-run]
```

`doc move` handles three cases:

- Moving to a different topic.
- Moving to a different repo.
- Switching anchor type. Passing `--topic` to a repo-anchored document makes
  it topical; passing `--repo` to a topical document does the reverse.

The slug stays the same. Absolute paths that were copied from the UI for this
document stop working after the move.

### `shelf doc delete` (alias `rm`)

```bash
shelf doc delete ID [--yes] [--dry-run]
```

Deletes the catalog entry **and** the document's folder, including every
variant and asset. On a TTY it asks for confirmation. Without a TTY, it
requires `--yes`.

### `shelf doc list` (alias `ls`) and `shelf doc view`

Both are read-only.

```bash
shelf doc list [--repo NAME] [--topic NAME] [--kind KIND] [--tag TAG]… \
               [--query TEXT] [--limit N] [--sort-by added|title] [--json]
shelf doc view ID [--json]
```

- Filters are combined with AND.
- `--query` is a substring match over the id, title, description, tags, and
  repo subject.
- The default sort is `added`, newest first.

The table output prints one line per document, with tab-separated id, title,
kind, and anchor:

```text
2026-10-24-uv-inline-scripts	uv Inline Scripts	explainer	topic:dev-tooling
```

`doc view` prints the whole entry. Each item in `files` includes `abs_path`,
the resolved absolute path, so a script or agent can read the file directly.
Scripts should read documents with `doc list` / `doc view --json` rather than
parsing `catalog.json`.

### `shelf doc adopt`

```bash
shelf doc adopt FOLDER --kind KIND --title TEXT --description TEXT \
  [--tag TAG]… [--create-topic] [--repo-url URL] [--subject LABEL] [--primary FMT] [--doc-date DATE]
```

Registers a per-document folder that already exists under `docs/` without
copying it. shelf takes the anchor from the folder's location and the slug
from the folder's name. This is how you repair an orphan that you want to keep.

### `shelf topic` and `shelf kind`

```bash
shelf topic add NAME     shelf topic list [--json]
shelf kind  add NAME     shelf kind  list [--json]
```

There is no rename or remove command for topics or kinds yet.

### `shelf orphan`

```bash
shelf orphan list [--json]
shelf orphan delete PATH [--yes]
```

An **orphan** is a file or folder under `docs/` with no catalog entry.
`list` shows the same orphans that audit check 1 finds. `delete` removes one,
and refuses any path that the catalog references.

### `shelf audit`

```bash
shelf audit [--pre-commit] [--json]
```

Runs the [consistency checks](#auditing-and-repair). It exits `0` when the
library is consistent and `1` when there are findings. `--pre-commit` skips the
uncommitted-changes check.

### `shelf regen`

```bash
shelf regen [--dry-run] [--commit]
```

Rewrites `index.html` from the current catalog and the installed template, and
never touches `catalog.json`. Run it after upgrading shelf, or when audit
reports a stale index.

### `shelf migrate`

```bash
shelf migrate [--dry-run] [--json] [--commit]
```

Upgrades `catalog.json` to the current `schema_version` and regenerates the
index. It does nothing when the schema is already current. Read commands work
on older supported schemas. Mutating commands refuse an old schema until you
migrate. Every command refuses a schema newer than the CLI supports.

### `shelf open`

```bash
shelf open [--static]
```

Opens the library UI. See [The library UI](#the-library-ui).

---

## Exit codes

| Code | Meaning | Example |
|---|---|---|
| `0` | Success | `shelf audit` on a consistent library |
| `1` | Error, or audit findings | `shelf audit` found an orphan; no library configured |
| `2` | Usage error | Unknown flag; a bare group like `shelf doc`; missing classification flags with `--no-handoff` |
| `3` | Not found | `shelf doc view nope` → `Error: document 'nope' not found — try 'shelf doc list --query nope'` |
| `5` | Conflict or precondition failed | A catalog schema that must be migrated first |

---

## The library UI

`index.html` sits at the library root and is regenerated on every change. It
embeds the catalog metadata and a short preview of each document: the first
heading and paragraph. It does not embed full document contents. The UI
offers:

- Fuzzy search over title, description, and tags.
- Grouping by subject: topical documents under their topic, repo documents
  under their repo with `subject` sub-headings. A toggle regroups by kind.
- One row per format variant, each with its own copy actions.

| Mode | How to open | Search and browse | Copy absolute path | Copy contents and inline HTML |
|---|---|---|---|---|
| **Core** | `shelf open --static`, or double-click `index.html` | ✓ | ✓ | — |
| **Enhanced** | `shelf open` | ✓ | ✓ | ✓ |

Browsers block a `file://` page from reading the files next to it. That is
why copy-contents and inline HTML rendering need enhanced mode, which serves
the library over HTTP.

`shelf open` behaves as follows:

- If a shelf server is already answering on `server-port`, it opens the
  browser there.
- Otherwise it starts a local server, falling back to a free port if
  `server-port` is busy.
- The server binds `127.0.0.1` only and refuses any path outside the library.

The library's absolute path is worked out when the page is viewed, so no
absolute path is ever committed.

---

## Git and GitHub

Version control is optional, and you enable it once:

```bash
shelf init --git                     # new library as a Git repo
shelf init --github --owner my-org   # … plus a private GitHub repo as origin
```

Then pass `--commit` on any mutating command to record that change as a commit:

```bash
shelf doc update 2026-10-24-uv-inline-scripts --kind tutorial --commit
# commit message: "shelf: …" (override with --commit-message)
```

`--commit` on a library that is not a Git repo is an error. shelf does not
push; run `git -C "$(shelf path)" push` when you want to.

**Pre-commit hook.** To stop anyone, including you, from committing an
inconsistent library, add the audit to `.git/hooks/pre-commit` in the library:

```bash
#!/bin/sh
exec shelf audit --pre-commit
```

`--pre-commit` skips the dirty-tree check, because the hook runs on exactly
the uncommitted changes being committed.

---

## Auditing and repair

`shelf audit` runs five checks:

| # | Finds | Fix |
|---|---|---|
| 1 | **Orphans**: files under `docs/` with no catalog entry | `shelf orphan list`, then `shelf doc adopt <folder>` to keep it or `shelf orphan delete <path>` to remove it |
| 2 | **Dead references**: catalog files that do not exist | `shelf doc format delete <id> <fmt> --force` |
| 3 | **Malformed entries**: missing fields, unknown kind or topic, folder not matching the anchor, `added` not matching the slug date, old schema | `shelf doc update …`; for the schema, `shelf migrate` |
| 4 | **Missing, unparseable, or stale files**: config, catalog, or an `index.html` that no longer matches the catalog or template | config: `shelf init --adopt <path>`; index: `shelf regen` |
| 5 | **Uncommitted changes** to `catalog.json`, `index.html`, or `docs/` (Git libraries only; skipped with `--pre-commit`) | `git -C "$(shelf path)" add -A && git -C "$(shelf path)" commit` |

Each finding prints the fix next to it:

```text
$ shelf audit
check 1 [orphan]: docs/topics/dev-tooling/stray
  fix: inspect with 'shelf orphan list'; adopt with 'shelf doc adopt' or delete with 'shelf orphan delete'
$ echo $?
1
```

`shelf audit --json` prints each finding as an object with the fields `check`,
`code`, `detail`, and `remediation`. A consistent library prints `[]`. In an
agent session, "audit my shelf" runs the audit, summarizes it, and offers each
fix in turn.

---

## Moving to a new machine

The library holds no machine-specific paths. The one exception is the
`source` provenance field, which is never used to locate files. Setting up a
second machine takes two commands:

```bash
git clone git@github.com:<you>/shelf-library.git ~/.local/share/shelf
shelf init --adopt ~/.local/share/shelf
```

`--adopt` validates the clone and writes the config file. It changes nothing
inside the library.

---

## Development

```text
shelf/                               # monorepo: CLI + plugin + marketplace
├── src/shelf/                       # the Python package (the only thing in the wheel)
│   ├── cli/                         # click command tree
│   ├── core/                        # config, catalog, paths, slugs, atomic writes, audit, git
│   ├── server/                      # local server for `shelf open`
│   └── templates/index.html.tmpl    # UI template, rendered into each library
├── tests/                           # pytest suite
├── plugins/shelf/                   # the Claude Code / Codex plugin and its skill
├── .claude-plugin/marketplace.json  # Claude Code marketplace catalog
├── .agents/plugins/marketplace.json # Codex marketplace catalog
├── SHELF-PRD.md                     # product requirements and design rationale
└── PROJECTS.md                      # roadmap and project tracking
```

```bash
make check     # check the toolchain: uv, just, git, Python ≥ 3.12
just all       # format, lint (ruff), type-check (ty), and test (pytest)
just test      # tests only
```

Contribution notes:

- `shelf --help` is the authoritative command surface.
- [`SHELF-PRD.md`](SHELF-PRD.md) records the design and the reasons behind it.
- [`PROJECTS.md`](PROJECTS.md) tracks what has shipped and what is planned:
  taxonomy rename/remove, and multiple libraries.
- The CLI follows the org CLI Design Standard. The documented waivers are in
  PRD §5.

---

Built by Steve Morin ([smorinlabs](https://github.com/smorinlabs)).
