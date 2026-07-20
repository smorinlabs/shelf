"""P06-T01 — preview snippet extraction (extract_snippet, build_snippets)."""

from html.parser import HTMLParser
from pathlib import Path

from shelf.core.preview import build_snippets, extract_snippet

MD_SAMPLE = """# Heading

A paragraph of text.

- item one
- item two

Inline `code` here.

```
fenced content line
```
"""


def _assert_balanced_html(html: str) -> None:
    """Fail if any tag is unclosed or mismatched — guards against mid-tag truncation."""

    class _Checker(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack: list[str] = []

        def handle_starttag(self, tag, attrs):
            self.stack.append(tag)

        def handle_endtag(self, tag):
            assert self.stack and self.stack[-1] == tag, f"mismatched </{tag}> in: {html!r}"
            self.stack.pop()

    checker = _Checker()
    checker.feed(html)
    checker.close()
    assert checker.stack == [], f"unclosed tags {checker.stack} in: {html!r}"


class TestExtractSnippetMarkdown:
    def test_renders_heading_paragraph_list_inline_code_and_fence(self):
        html = extract_snippet(MD_SAMPLE, "md")
        assert "<h1>Heading</h1>" in html
        assert "<p>A paragraph of text.</p>" in html
        assert "<li>item one</li>" in html
        assert "<li>item two</li>" in html
        assert "<ul>" in html and "</ul>" in html
        assert "<code>code</code>" in html
        assert "<pre>" in html and "</pre>" in html
        assert "fenced content line" in html
        _assert_balanced_html(html)

    def test_h2_and_h3_headings(self):
        assert "<h2>Sub</h2>" in extract_snippet("## Sub\n\nbody text.", "md")
        assert "<h3>SubSub</h3>" in extract_snippet("### SubSub\n\nbody text.", "md")

    def test_asterisk_list_marker_also_renders_as_li(self):
        html = extract_snippet("* item one\n* item two", "md")
        assert "<li>item one</li>" in html
        assert "<li>item two</li>" in html

    def test_fenced_block_content_is_escaped(self):
        md = '```\n<tag> & "quotes"\n```'
        html = extract_snippet(md, "md")
        assert "&lt;tag&gt;" in html
        assert "<tag>" not in html
        _assert_balanced_html(html)

    def test_script_tag_in_source_is_escaped_not_live(self):
        html = extract_snippet("Some <script>alert(1)</script> text here.", "md")
        assert "<script>" not in html
        assert "</script>" not in html
        assert "&lt;script&gt;" in html
        _assert_balanced_html(html)

    def test_bold_tag_in_source_is_escaped_not_live(self):
        html = extract_snippet("Text with <b>bold</b> literal tag inside.", "md")
        assert "<b>" not in html
        assert "&lt;b&gt;" in html
        _assert_balanced_html(html)

    def test_default_max_chars_renders_short_input_untruncated(self):
        html = extract_snippet("# Hi\n\nShort body.")
        assert "<h1>Hi</h1>" in html
        assert "<p>Short body.</p>" in html

    def test_max_chars_truncates_on_block_boundary_never_mid_tag(self):
        paragraphs = [
            f"Paragraph number {i} contains some filler words to pad it out nicely for the test."
            for i in range(20)
        ]
        long_md = "\n\n".join(paragraphs)

        full = extract_snippet(long_md, "md", max_chars=100_000)
        truncated = extract_snippet(long_md, "md", max_chars=200)

        assert len(truncated) < len(full)
        _assert_balanced_html(truncated)
        assert f"<p>{paragraphs[0]}</p>" in truncated  # first block kept whole
        assert paragraphs[-1] not in truncated  # a later block is dropped entirely
        # every paragraph that shows up at all shows up complete — never sliced mid-sentence
        for para in paragraphs:
            if para in truncated:
                assert f"<p>{para}</p>" in truncated

    def test_empty_and_whitespace_input_returns_empty_string(self):
        assert extract_snippet("", "md") == ""
        assert extract_snippet("   \n\t  ", "md") == ""


class TestExtractSnippetHtml:
    def test_strips_tags_to_text_and_wraps_in_paragraph(self):
        html_input = "<div><h1>Title</h1> <p>Hello <b>world</b>, this is <i>great</i>.</p></div>"
        result = extract_snippet(html_input, "html")
        assert result.startswith("<p>")
        assert result.endswith("</p>")
        assert "Title" in result
        assert "Hello" in result and "world" in result and "great" in result
        assert "<h1>" not in result
        assert "<b>" not in result and "<i>" not in result
        assert "<div>" not in result
        _assert_balanced_html(result)

    def test_empty_and_whitespace_input_returns_empty_string(self):
        assert extract_snippet("", "html") == ""
        assert extract_snippet("   ", "html") == ""


def _write(root: Path, rel_path: str, content: str) -> None:
    path = root / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class TestBuildSnippets:
    def test_returns_nonempty_snippet_for_seeded_doc(self, tmp_path):
        doc = {
            "id": "doc-1",
            "primary": "md",
            "files": [{"format": "md", "path": "docs/topics/x/doc-1/doc-1.md"}],
        }
        _write(tmp_path, doc["files"][0]["path"], "# Doc One\n\nThis is the body of doc one.")

        result = build_snippets(tmp_path, [doc])

        assert set(result) == {"doc-1"}
        assert result["doc-1"] != ""
        assert "Doc One" in result["doc-1"]

    def test_missing_file_maps_to_empty_string(self, tmp_path):
        doc = {
            "id": "doc-missing",
            "primary": "md",
            "files": [{"format": "md", "path": "docs/topics/x/doc-missing/doc-missing.md"}],
        }
        # deliberately do not create the file on disk

        result = build_snippets(tmp_path, [doc])

        assert result == {"doc-missing": ""}

    def test_reads_only_the_primary_variant(self, tmp_path):
        doc = {
            "id": "doc-2",
            "primary": "md",
            "files": [
                {"format": "md", "path": "docs/topics/x/doc-2/doc-2.md"},
                {"format": "html", "path": "docs/topics/x/doc-2/doc-2.html"},
            ],
        }
        _write(
            tmp_path,
            "docs/topics/x/doc-2/doc-2.md",
            "# Primary Content\n\nPrimary body marker PRIMARYMARK.",
        )
        _write(
            tmp_path,
            "docs/topics/x/doc-2/doc-2.html",
            "<h1>Secondary Content</h1><p>SECONDARYMARK body.</p>",
        )

        result = build_snippets(tmp_path, [doc])

        assert "PRIMARYMARK" in result["doc-2"]
        assert "SECONDARYMARK" not in result["doc-2"]
