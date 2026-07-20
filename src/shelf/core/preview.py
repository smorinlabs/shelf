"""Safe, bounded preview snippets for catalog documents."""

import html
import re
from html.parser import HTMLParser
from pathlib import Path

_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "dl",
    "dt",
    "dd",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class _HTMLTextExtractor(HTMLParser):
    """Collect visible text while retaining whitespace at block boundaries."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return " ".join("".join(self.parts).split())


def _inline_markup(text: str) -> str:
    return _INLINE_CODE.sub(r"<code>\1</code>", text)


def _markdown_blocks(escaped_text: str) -> list[str]:
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    fenced_lines: list[str] = []
    in_fence = False
    fence_seen = False

    def flush_paragraph() -> None:
        if paragraph:
            content = _inline_markup(" ".join(line.strip() for line in paragraph))
            blocks.append(f"<p>{content}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            items = "".join(f"<li>{_inline_markup(item)}</li>" for item in list_items)
            blocks.append(f"<ul>{items}</ul>")
            list_items.clear()

    for line in escaped_text.splitlines():
        if in_fence:
            if line.strip() == "```":
                content = "\n".join(fenced_lines)
                blocks.append(f"<pre>{content}</pre>")
                fenced_lines.clear()
                in_fence = False
            else:
                fenced_lines.append(line)
            continue

        if not fence_seen and line.strip() == "```":
            flush_paragraph()
            flush_list()
            fence_seen = True
            in_fence = True
            continue

        if not line.strip():
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline_markup(heading.group(2))}</h{level}>")
            continue

        list_item = re.match(r"^\s*[-*]\s+(.+?)\s*$", line)
        if list_item:
            flush_paragraph()
            list_items.append(list_item.group(1))
            continue

        flush_list()
        paragraph.append(line)

    if in_fence:
        content = "\n".join(fenced_lines)
        blocks.append(f"<pre>{content}</pre>")
    flush_paragraph()
    flush_list()
    return blocks


def _bounded_blocks(blocks: list[str], max_chars: int) -> str:
    kept: list[str] = []
    length = 0
    for block in blocks:
        if length + len(block) > max_chars:
            break
        kept.append(block)
        length += len(block)
    return "".join(kept)


def _bounded_escaped_text(text: str, max_chars: int) -> str:
    """Escape the longest text prefix that leaves room for a paragraph wrapper."""
    budget = max_chars - len("<p></p>")
    if budget <= 0:
        return ""

    escaped_chars: list[str] = []
    length = 0
    for char in text:
        escaped = html.escape(char)
        if length + len(escaped) > budget:
            break
        escaped_chars.append(escaped)
        length += len(escaped)
    return "".join(escaped_chars).rstrip()


def extract_snippet(text: str, fmt: str = "md", *, max_chars: int = 600) -> str:
    """Return safe, minimally formatted HTML bounded at a complete block."""
    if not text.strip() or max_chars <= 0:
        return ""

    if fmt == "html":
        parser = _HTMLTextExtractor()
        parser.feed(text)
        parser.close()
        plain_text = parser.text()
        escaped_text = _bounded_escaped_text(plain_text, max_chars)
        return f"<p>{escaped_text}</p>" if escaped_text else ""

    escaped_text = html.escape(text)
    return _bounded_blocks(_markdown_blocks(escaped_text), max_chars)


def build_snippets(root: Path, docs: list[dict]) -> dict[str, str]:
    """Build a preview snippet for every raw catalog document."""
    from shelf.core.preview import extract_snippet

    snippets: dict[str, str] = {}
    for doc in docs:
        doc_id = doc["id"]
        files = doc.get("files", [])
        variant = next(
            (entry for entry in files if entry.get("format") == doc.get("primary")),
            files[0] if files else None,
        )
        if variant is None:
            snippets[doc_id] = ""
            continue

        try:
            text = (root / variant["path"]).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            snippets[doc_id] = ""
            continue

        snippets[doc_id] = extract_snippet(text, variant["format"])

    return snippets
