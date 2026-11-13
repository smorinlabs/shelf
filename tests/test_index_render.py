"""P06-T02 — index.html data binding: PAGE JSON, snippets, hooks, safety (red)."""

import hashlib
import json
import re
import shutil
import subprocess

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

TOPIC = "guides"

# Non-greedy + DOTALL: stops at the first literal `;` after the marker. None of this
# file's seeded titles/bodies contain a `;`, so that first `;` is always the JS
# statement terminator — never a `;` inside a JSON string value.
_PAGE_RE = re.compile(r"const PAGE = (.*?);", re.DOTALL)

DOC_SPECS = [
    {
        "title": "Getting Started Guide",
        "kind": "reference",
        "body": "# Getting Started Guide\n\nThis document explains how to get set up quickly.",
    },
    {
        "title": "Deploying To Production",
        "kind": "tutorial",
        "body": "# Deploying To Production\n\nStep by step instructions for shipping safely.",
    },
    {
        "title": "Config Reference",
        "kind": "explainer",
        "body": "# Config Reference\n\nA rundown of every configuration option and its default.",
    },
]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", TOPIC]).exit_code == 0
    return default_library_path()


def _add_doc(tmp_path, *, title, kind, body, name):
    src = tmp_path / name
    src.write_text(body, encoding="utf-8")
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            TOPIC,
            "--kind",
            kind,
            "--title",
            title,
            "--description",
            f"About {title}",
        ]
    )
    assert r.exit_code == 0, r.output


def _seed_docs(tmp_path):
    for i, spec in enumerate(DOC_SPECS):
        _add_doc(
            tmp_path,
            title=spec["title"],
            kind=spec["kind"],
            body=spec["body"],
            name=f"doc-{i}.md",
        )


def _extract_page_json_text(html_text: str) -> str:
    match = _PAGE_RE.search(html_text)
    assert match is not None, "no `const PAGE = ...;` data site found in index.html"
    return match.group(1)


def _extract_page(html_text: str) -> dict:
    return json.loads(_extract_page_json_text(html_text))


@pytest.fixture
def seeded_index(isolated_env, tmp_path):
    """A real library, seeded with 3 docs via the CLI, then regenerated."""
    root = _init()
    _seed_docs(tmp_path)
    assert run(["regen"]).exit_code == 0
    return root


def test_page_docs_ids_titles_kinds_match_catalog(seeded_index):
    root = seeded_index
    catalog = json.loads((root / "catalog.json").read_text())
    page = _extract_page((root / "index.html").read_text())

    catalog_by_id = {d["id"]: d for d in catalog["documents"]}
    assert len(catalog_by_id) == len(DOC_SPECS)
    assert {d["id"] for d in page["docs"]} == set(catalog_by_id)
    for pdoc in page["docs"]:
        cdoc = catalog_by_id[pdoc["id"]]
        assert pdoc["title"] == cdoc["title"]
        assert pdoc["kind"] == cdoc["kind"]


def test_every_doc_carries_a_nonempty_snippet_for_a_real_md_file(seeded_index):
    root = seeded_index
    page = _extract_page((root / "index.html").read_text())

    assert len(page["docs"]) == len(DOC_SPECS)
    for doc in page["docs"]:
        assert "snippet" in doc
        assert doc["snippet"] != ""


def test_page_root_is_the_empty_placeholder_in_the_committed_file(seeded_index):
    root = seeded_index
    page = _extract_page((root / "index.html").read_text())
    assert page["root"] == ""


def test_fingerprint_parses_and_matches_catalog_and_template_hashes(seeded_index):
    from shelf.core.index import parse_fingerprint, template_text

    root = seeded_index
    catalog_text = (root / "catalog.json").read_text()
    html_text = (root / "index.html").read_text()

    parsed = parse_fingerprint(html_text)
    assert parsed is not None
    cat_hash, tmpl_hash = parsed
    assert cat_hash == hashlib.sha256(catalog_text.encode()).hexdigest()
    assert tmpl_hash == hashlib.sha256(template_text().encode()).hexdigest()


def test_page_contains_the_app_hooks(seeded_index):
    root = seeded_index
    html_text = (root / "index.html").read_text()

    assert 'id="kopen"' in html_text
    assert 'id="viewseg"' in html_text
    assert 'id="tree"' in html_text
    assert 'class="prevopen"' in html_text
    assert "metaKey" in html_text  # the CmdK keydown handler


def test_bulk_document_body_is_not_embedded_in_index_html(isolated_env, tmp_path):
    """Preview snippets are bounded — full document bodies never land in the page."""
    root = _init()
    sentinel = "ZZZ_SENTINEL_LONG_BODY_MARKER"
    filler = "Padding text that pushes the sentinel well past the bounded snippet cap. " * 12
    assert len(filler) > 600  # sanity: filler alone already exceeds the 600-char snippet cap
    body = (
        f"# Overflowing Doc\n\n{filler}\n\n{sentinel} tail text that must never reach the page.\n"
    )
    _add_doc(tmp_path, title="Overflowing Doc", kind="reference", body=body, name="overflow.md")
    assert run(["regen"]).exit_code == 0

    html_text = (root / "index.html").read_text()
    page = _extract_page(html_text)

    doc = next(d for d in page["docs"] if d["title"] == "Overflowing Doc")
    assert doc["snippet"] != ""
    assert len(doc["snippet"]) < len(body)  # bounded — not the full body
    assert sentinel not in html_text  # the sentinel itself never reaches the page at all


def test_script_safety_escapes_close_script_tag_and_line_separator(isolated_env, tmp_path):
    root = _init()
    title = "Weird </script> Title \u2028-line-separator With A Line Separator"
    _add_doc(
        tmp_path,
        title=title,
        kind="reference",
        body="# Weird\n\nOrdinary body text for this document.",
        name="weird.md",
    )
    assert run(["regen"]).exit_code == 0

    html_text = (root / "index.html").read_text()
    page_json_text = _extract_page_json_text(html_text)

    assert "</script>" not in page_json_text
    assert "\u2028" not in page_json_text  # must be the \u2028 escape, not raw U+2028

    page = json.loads(page_json_text)  # still valid JSON despite the escaping
    titles = {doc["title"] for doc in page["docs"]}
    assert title in titles  # round-trips back to the exact original title


def test_render_index_without_snippets_is_backward_compatible(isolated_env, tmp_path):
    from shelf.core.index import parse_fingerprint, render_index

    root = _init()
    _add_doc(
        tmp_path,
        title="Solo Doc",
        kind="reference",
        body="# Solo\n\nJust a small document body for this test.",
        name="solo.md",
    )
    catalog_text = (root / "catalog.json").read_text()

    page_html = render_index(catalog_text)  # no snippets arg — the P05 call site
    page = _extract_page(page_html)

    assert page["docs"], "expected at least one doc in the catalog"
    assert all(doc["snippet"] == "" for doc in page["docs"])
    assert parse_fingerprint(page_html) is not None


def _minimal_catalog_text(
    *,
    doc_id,
    category,
    files,
    primary="md",
    title="Doc Title",
    description="A description",
    kind="reference",
    tags=None,
):
    """A hand-built catalog.json body — enough for render_index() to consume
    without going through the CLI, so a FileVariant's recorded `path` can be
    made non-canonical on purpose (P08-C2)."""
    catalog = {
        "documents": [
            {
                "id": doc_id,
                "title": title,
                "description": description,
                "kind": kind,
                "tags": tags or [],
                "category": category,
                "files": files,
                "primary": primary,
            }
        ],
        "topics": [category],
        "kinds": [kind],
    }
    return json.dumps(catalog)


def test_format_path_uses_the_recorded_variant_path_not_a_reconstructed_one():
    """P08-C2: index.py rebuilds each format's page path as
    `<base>/<group>/<id>/<id>.<fmt>`, ignoring the FileVariant's recorded
    `path` entirely. A document whose file actually lives under a
    non-canonical filename (e.g. renamed, or kept as the original upload
    name) must still be linked at its real, recorded path — not a
    fabricated one that 404s."""
    from shelf.core.index import render_index

    doc_id = "2026-01-01-doc"
    recorded_path = f"docs/topics/guides/{doc_id}/original-name.md"
    catalog_text = _minimal_catalog_text(
        doc_id=doc_id,
        category="guides",
        files=[{"format": "md", "path": recorded_path}],
    )

    page = _extract_page(render_index(catalog_text))

    doc = next(d for d in page["docs"] if d["id"] == doc_id)
    md = next(f for f in doc["formats"] if f["f"] == "md")
    assert md["path"] == recorded_path


def test_row_template_html_escapes_title_via_an_escape_helper(seeded_index):
    """P08-C1 (structural): rowHTML currently interpolates `${d.title}` (and
    d.id / d.tags) raw into an innerHTML template literal, so an untrusted
    title can inject markup/script into the page. Pins that an
    esc()/escapeHtml() JS helper exists and that rowHTML applies it to the
    title. (Full XSS behavior is verified in-browser, not here.)"""
    root = seeded_index
    html_text = (root / "index.html").read_text()

    assert re.search(r"function\s+(?:esc|escapeHtml)\s*\(", html_text), (
        "expected an esc()/escapeHtml() JS helper function definition in index.html"
    )

    match = re.search(
        r"function rowHTML\(d\)\{(.*?)function renderList\(\)\{", html_text, re.DOTALL
    )
    assert match is not None, "could not locate the rowHTML template function in index.html"
    row_body = match.group(1)
    assert "esc(d.title)" in row_body or "escapeHtml(d.title)" in row_body, (
        "rowHTML must apply the escape helper to d.title, not interpolate it raw"
    )


def test_search_scorematch_includes_description_in_the_haystack(seeded_index):
    """P08-C4 (structural): the ⌘K palette's scoreMatch() only matches
    against title+tags+id+subject — document descriptions are invisible to
    search even though they carry real content. Pins that scoreMatch's
    haystack includes d.description."""
    root = seeded_index
    html_text = (root / "index.html").read_text()

    match = re.search(r"function scoreMatch\(d, q\)\{(.*?)\}", html_text, re.DOTALL)
    assert match is not None, "could not locate the scoreMatch function in index.html"
    assert "d.description" in match.group(1), (
        "scoreMatch's haystack must include d.description so search can match on it"
    )


def test_index_declares_a_favicon_to_avoid_a_404(seeded_index):
    """P08 smoke follow-up: with no declared icon, browsers auto-request
    /favicon.ico → a 404 on every load. The template declares an inline icon
    so no /favicon.ico request is made (works in core file:// and enhanced)."""
    root = seeded_index
    html_text = (root / "index.html").read_text()
    assert re.search(r'<link[^>]+rel="icon"', html_text), (
        'expected <link rel="icon"> in index.html so browsers do not request /favicon.ico'
    )


_FUZZY_RE = re.compile(r"/\* fuzzy:start \*/(.*?)/\* fuzzy:end \*/", re.DOTALL)

_FUZZY_CHECKS = r"""
const assert = (cond, msg) => { if (!cond) { console.error("FAIL: " + msg); process.exit(1); } };
const doc = (id, title, extra = {}) =>
  ({ id, title, description: "", tags: [], anchor: { subject: "" }, ...extra });

assert(fuzzyScore("uv inline scripts", "uvscr") > 0, "in-order characters match");
assert(fuzzyScore("uv inline scripts", "rcs") === 0, "out-of-order characters do not match");
assert(fuzzyScore("uv inline scripts", "xyz") === 0, "absent characters do not match");
assert(fuzzyScore("config reference", "conf") > fuzzyScore("cats on nice fur", "conf"),
  "a contiguous match outranks a scattered one");
assert(fuzzyScore("uv inline scripts", "scr") > fuzzyScore("describe", "scr"),
  "a match at a word start outranks one mid-word");

const inTitle = doc("a", "Deploy guide");
const inDescription = doc("b", "Shipping notes", { description: "how to deploy" });
assert(scoreMatch(inTitle, "deploy") > scoreMatch(inDescription, "deploy"),
  "a title match outranks a description match");
assert(scoreMatch(doc("c", "Notes", { tags: ["python"] }), "pyth") > 0, "tags are searched");
assert(scoreMatch(doc("d", "Notes", { anchor: { subject: "provider-config" } }), "provcfg") > 0,
  "the repo subject is searched");

const uv = doc("e", "uv Inline Scripts");
assert(scoreMatch(uv, "uv scripts") > 0, "every query word matching is a match");
assert(scoreMatch(uv, "uv zzz") === 0, "query words AND together");

const ranked = rankDocs([inDescription, doc("f", "Unrelated"), inTitle], "deploy");
assert(ranked.length === 2, "non-matching documents are dropped");
assert(ranked[0] === inTitle && ranked[1] === inDescription, "results are ranked best first");
console.log("ok");
"""


def test_palette_search_is_fuzzy_and_ranked(seeded_index, tmp_path):
    """P17-TS04: the ⌘K palette matches characters in order (fuzzy), weights titles,
    contiguous runs, and word starts, ANDs query words, and ranks results. The scorer
    is pulled out of the rendered index.html and run under Node."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    html_text = (seeded_index / "index.html").read_text()
    match = _FUZZY_RE.search(html_text)
    assert match is not None, "index.html must mark the scorer with /* fuzzy:start */ … end"
    script = tmp_path / "fuzzy_check.js"
    script.write_text(match.group(1) + _FUZZY_CHECKS, encoding="utf-8")

    result = subprocess.run([node, str(script)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "ok"


def test_palette_preview_collapses_whitespace(seeded_index):
    """P18-TS01: the palette preview must collapse whitespace with /\\s+/g. The
    template is copied verbatim, so a doubled backslash would reach the browser and
    match a literal backslash followed by "s" instead of whitespace."""
    html_text = (seeded_index / "index.html").read_text()
    assert '.replace(/\\s+/g," ")' in html_text
    assert "/\\\\s+/g" not in html_text


def test_sidebar_footer_shows_real_values(seeded_index):
    """P19-TS01: the sidebar footer must not carry mockup constants. Enhanced mode
    shows the real host (127.0.0.1 and the configured or fallback port), and the
    footer shows no fixed file count."""
    html_text = (seeded_index / "index.html").read_text()
    footer = next(line for line in html_text.splitlines() if 'getElementById("sidefoot")' in line)
    assert "location.host" in footer
    assert "localhost:8765" not in footer
    assert "13 files" not in footer
    assert "3 docs" in footer


def test_page_docs_carry_the_added_date():
    """P24-TS02: the list and the palette show when a document was added."""
    from shelf.core.index import render_index

    catalog = json.loads(
        _minimal_catalog_text(
            doc_id="2026-01-01-doc",
            category="guides",
            files=[{"format": "md", "path": "docs/topics/guides/2026-01-01-doc/x.md"}],
        )
    )
    undated = dict(catalog["documents"][0], id="undated-doc")
    catalog["documents"][0]["added"] = "2026-01-01"
    catalog["documents"].append(undated)

    page = _extract_page(render_index(json.dumps(catalog)))

    added = {d["id"]: d["added"] for d in page["docs"]}
    assert added == {"2026-01-01-doc": "2026-01-01", "undated-doc": None}


_PREVIEW_RE = re.compile(r"/\* preview:start \*/(.*?)/\* preview:end \*/", re.DOTALL)

_PREVIEW_CHECKS = r"""
const assert = (cond, msg) => { if (!cond) { console.error("FAIL: " + msg); process.exit(1); } };

assert(docURL("docs/topics/a b/x#1/x?.md") === "docs/topics/a%20b/x%231/x%3F.md",
  "docURL encodes each segment and keeps the slashes");
assert(!docURL("docs/x.md").startsWith("/"), "docURL stays relative to the index page");

assert(renderModeFor("html", true) === "iframe", "html renders when served");
assert(renderModeFor("html", false) === "iframe", "html renders from file://");
assert(renderModeFor("md", true) === "markdown", "markdown renders when served");
assert(renderModeFor("md", false) === null, "markdown cannot be fetched from file://");
assert(renderModeFor("pdf", true) === null, "other formats keep the snippet only");

const store = () => { const m = {}; return {
  getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } }; };
const s = store();
assert(loadPreviewMode(s) === "snippet", "the default mode is snippet");
savePreviewMode(s, "rendered");
assert(loadPreviewMode(s) === "rendered", "the chosen mode round-trips");
s.setItem("shelf.previewMode", "bogus");
assert(loadPreviewMode(s) === "snippet", "an unknown stored value falls back to snippet");
const blocked = () => { throw new Error("blocked"); };
const broken = { getItem: blocked, setItem: blocked };
assert(loadPreviewMode(broken) === "snippet", "a throwing storage reads as snippet");
savePreviewMode(broken, "rendered");
assert(loadPreviewMode(null) === "snippet", "missing storage reads as snippet");

assert(formatAdded("2026-11-12") === "Nov 12, 2026", "ISO dates format as Mon D, YYYY");
assert(formatAdded("2026-01-05") === "Jan 5, 2026", "day has no leading zero");
assert(formatAdded(null) === "", "a missing date shows nothing");
assert(formatAdded("someday") === "", "an unparseable date shows nothing");
console.log("ok");
"""


def test_preview_helpers_behave(seeded_index, tmp_path):
    """P24-TS03: the pure helpers behind Open, the Rendered toggle, and added dates,
    pulled out of the rendered index.html and run under Node."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH")
    html_text = (seeded_index / "index.html").read_text()
    match = _PREVIEW_RE.search(html_text)
    assert match is not None, "index.html must mark the helpers with /* preview:start */ … end"
    script = tmp_path / "preview_check.js"
    script.write_text(match.group(1) + _PREVIEW_CHECKS, encoding="utf-8")

    result = subprocess.run([node, str(script)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr or result.stdout
    assert result.stdout.strip() == "ok"


def test_detail_pane_has_open_toggle_and_safe_iframes(seeded_index):
    """P24-TS04: Open per format row, the Snippet/Rendered toggle, iframes that can
    never reach the Shelf page, and pinned CDN scripts."""
    html_text = (seeded_index / "index.html").read_text()

    match = re.search(r"function renderPreview\(d\)\{(.*?)\n\}\n", html_text, re.DOTALL)
    assert match is not None, "could not locate renderPreview in index.html"
    preview = match.group(1)
    assert 'target="_blank"' in preview and ">Open</a>" in preview
    assert "docURL(x.path)" in preview
    assert 'data-mode="snippet"' in preview and 'data-mode="rendered"' in preview

    sandboxes = re.findall(r'sandbox="([^"]*)"', html_text)
    assert len(sandboxes) == 2, sandboxes
    assert all("allow-same-origin" not in s for s in sandboxes)
    assert sum("allow-scripts" in s for s in sandboxes) == 1, "only the HTML iframe runs scripts"
    scripted = next(s for s in sandboxes if "allow-scripts" in s)
    assert "allow-popups-to-escape-sandbox" not in scripted, (
        "a popup escaping the HTML iframe would be same-origin with Shelf and reach it via opener"
    )

    keydown = re.search(r'else if\(k==="Enter" && visRows\[sel\](.*?)\{', html_text)
    assert keydown is not None and 'closest("a,button")' in keydown.group(1), (
        "Enter on a focused link or button must activate it, not copy the selected path"
    )

    for lib in ("marked@12.0.2", "dompurify@3.1.6"):
        line = next(ln for ln in html_text.splitlines() if lib in ln)
        assert "cdn.jsdelivr.net/npm/" in line and "sha384-" in line, line


def test_list_and_palette_show_the_added_date(seeded_index):
    """P24-TS04: list rows and ⌘K results render the added date."""
    html_text = (seeded_index / "index.html").read_text()
    row = re.search(r"function rowHTML\(d\)\{(.*?)function renderList\(\)\{", html_text, re.DOTALL)
    palette = re.search(r"function renderPalette\(q\)\{(.*?)\n\}\n", html_text, re.DOTALL)
    assert row is not None and palette is not None
    assert "formatAdded(d.added)" in row.group(1)
    assert "formatAdded(d.added)" in palette.group(1)
