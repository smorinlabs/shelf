"""P03-TS01 — slug derivation and format inference."""

import click
import pytest

from shelf.core.ingest import doc_rel_dir, infer_format, pick_primary
from shelf.core.slugs import derive_slug, kebab


def test_kebab_basics():
    assert kebab("Flox CLI Extension System — PRD") == "flox-cli-extension-system-prd"
    assert kebab("  Weird__punctuation!! (v2) ") == "weird-punctuation-v2"


def test_kebab_truncates_at_hyphen_boundary():
    k = kebab("word " * 30)
    assert len(k) <= 60
    assert not k.endswith("-")
    assert "-" in k


def test_derive_slug_date_prefix():
    assert derive_slug("My Doc", "2026-07-18") == "2026-07-18-my-doc"


def test_derive_slug_override_wins():
    assert derive_slug("My Doc", "2026-07-18", override="2026-01-01-custom") == "2026-01-01-custom"


def test_infer_format_map():
    assert infer_format("a.md") == "md"
    assert infer_format("b.HTML") == "html"
    assert infer_format("c.htm") == "html"
    assert infer_format("d.pdf") == "pdf"


def test_infer_format_unknown_raises_usage():
    with pytest.raises(click.UsageError, match="--format"):
        infer_format("e.docx")


def test_infer_format_override():
    assert infer_format("weird.txt", override="md") == "md"


def test_pick_primary_heuristic():
    assert pick_primary(["pdf", "md", "html"]) == "md"
    assert pick_primary(["pdf", "html"]) == "html"
    assert pick_primary(["pdf"]) == "pdf"
    assert pick_primary(["docx"]) == "docx"


def test_doc_rel_dir_both_anchors():
    from shelf.core.catalog import Document, RepoRef

    topical = Document(id="2026-01-01-a", title="A", description="d", kind="spec",
                       category="dev-tooling")
    repo = Document(id="2026-01-01-b", title="B", description="d", kind="spec",
                    repo=RepoRef(name="flox"))
    assert doc_rel_dir(topical) == "docs/topics/dev-tooling/2026-01-01-a"
    assert doc_rel_dir(repo) == "docs/repos/flox/2026-01-01-b"
