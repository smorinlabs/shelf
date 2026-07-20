"""P06-T02 — index.html data binding: PAGE JSON, snippets, hooks, safety (red)."""

import hashlib
import json
import re

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
