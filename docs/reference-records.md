# Structured references (first pass)

`reference` is an optional catalog field with its own `version: 1`. Catalog schema
2 prevents older writers from silently discarding it. Schema 0/1 remains readable;
run `shelf migrate --dry-run`, then `shelf migrate` before writing older libraries.
Migration preserves documents and dates, and adds no invented reference facts.

Use `shelf reference render record.json preview.html`, then the normal `doc add`
or `doc format add <id> preview.html --replace` with `--reference-record record.json`.
The JSON is stored as a tracked file variant alongside the generated HTML. Inputs
must exactly match the renderer. Metadata and files use existing rollback paths.
No downloaded HTML is accepted as a reference template. No scripts, forms, fonts,
trackers or network-loaded assets are included. Text is escaped and all links must
be credential-free absolute HTTP(S) URLs. URLs are validated, not fetched by CLI.

Version 1 fields (unknown text/date/fact = null; unknown lists = []):

- Required: `version` (1), `name` (nonempty string), `entity_url` (canonical URL).
- Text: `description`, `what_it_is`, `when_useful`, `notes`.
- String lists: `capabilities`, `prerequisites`, `limitations`, `categories`, `tags`,
  `projects` (named projects, any names).
- `links`: lists of URLs under `homepage`, `repository`, `docs`, `pricing`.
- `cost`, `license`: null or objects with `summary`, `verified` (ISO date), `sources`
  (URLs), `source_availability` (text; normally license only). A summary requires
  its own verification date and sources. Neither field implies the other.
- `dates`: `saved`, `added`, `researched`, `released`, each ISO date or null.
  These are historical reference dates. Catalog `added` separately records Shelf
  ingestion; legacy `doc_date` is retained unchanged, never interpreted as release.
- `sources`, `related`: lists of `{label, url, accessed}` objects; accessed is an
  ISO date or null. Related links are explicit, not inferred product identities.
- `profiles`: optional objects with nullable text fields:
  `model` (modalities, context, weights, deployment),
  `stt` (languages, streaming, timestamps, diarization, requirements),
  `agent_tool` (integrations, execution, permissions),
  `hardware` (board, processor, voltage, interfaces, requirements),
  `learning` (level, equipment, outcomes, safety).

Unknown keys and unsupported versions are rejected, not discarded. Categories:
`AI Models`, `AI Models/Speech-to-text`, `Agent Harnesses & Tools`, `Skills`,
`Example Projects`, `Hardware`, `Hardware/ESP32`, `Hardware/Raspberry Pi`,
`Learning Electronics`, `Libraries`, `Products`. Use flat topic names such as `AI Models` or `Hardware`; slash-separated category
labels are collection tags, not filesystem topic paths. Choose one existing/new topic as
anchor; categories and project connections also become searchable/filterable tags.

Refresh preserves identity, user notes and historical saved/added/released dates;
changing those needs an explicit future reconciliation workflow. It also refuses
hand-edited managed HTML or JSON. Existing unstructured HTML is not overwritten
when attaching a reference. Keep originals and resolve conflicts before retrying.
The research date, researched facts and links can change. Normal reference format
replacement requires the record; deletion of managed HTML/JSON is disallowed.

Deduplication compares canonical and grouped URLs against existing reference URLs
and safe legacy document source URLs (host case, default ports, trailing slash and fragments normalized).
It does not prove two unrelated URLs denote the same entity; the skill must resolve
identity before ingestion. Fixtures in `tests/fixtures/references` use reserved
example.com URLs and are not product claims. They intentionally leave facts unknown.


## Recovery and update boundaries

Reference ingestion and refresh persist `.shelf-reference-transaction.json` before
writing either content file. The journal holds the previous bytes and proposed pair;
HTML and JSON are individually atomically replaced and fsynced. The catalog remains
the commit point. If a process stops, `shelf reference recover` restores the previous
pair before catalog commit, or verifies the new pair after catalog commit, then
regenerates the index and removes the journal. Recovery can be retried if interrupted.
It refuses unexpected catalog changes or hand-edited content rather than overwrite it.

While a journal is pending, normal mutations, migration and index regeneration are
blocked; audit reports the pending transaction and Shelf's HTTP server returns 503.
Direct filesystem readers do not acquire Shelf's lock and can see intermediate files;
this is a recoverable multi-file transaction, not filesystem-wide snapshot isolation.
For a failed recovery, keep the journal and reconcile/restore the conflicting bytes
before retrying. Never delete the journal to bypass conflict protection.

Managed references reject asset uploads, unmanaged HTML/JSON adoption, and ordinary
`doc update --title/--description/--source`; update those through the reviewed record.
Notes and historical dates remain protected during refresh. Catalog tags are merged
conservatively to preserve user tags; remove outdated classification tags explicitly
with `shelf doc update <id> --remove-tag <tag>` after reviewing a reclassification.

Duplicate checks require a canonical identity match (either entity URL may match the
other record's grouped links). Shared grouped-to-grouped pricing/docs URLs alone do
not merge different products. Default ports normalize; meaningful query strings and
HTTP versus HTTPS remain distinct. The skill must resolve aliases and exact identity.
Local index links encode path segments so spaces, #, ?, % and Unicode route correctly.

Stage all proposed reference inputs outside the library. Ingestion rejects in-library
inputs so source cleanup cannot accidentally delete a saved HTML/JSON pair. Audit
also checks reference schema and agreement between catalog, JSON and generated HTML.
