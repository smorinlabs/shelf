"""index.html generation and fingerprinting (PRD §13)."""

import hashlib
import json
import re
from importlib.metadata import version
from importlib.resources import files

_FINGERPRINT_RE = re.compile(
    r"shelf:fingerprint catalog=sha256:([0-9a-f]{64}) "
    r"template=sha256:([0-9a-f]{64}) version=\S+"
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def template_text() -> str:
    return files("shelf.templates").joinpath("index.html.tmpl").read_text(encoding="utf-8")


def parse_fingerprint(html: str) -> tuple[str, str] | None:
    match = _FINGERPRINT_RE.search(html)
    return (match.group(1), match.group(2)) if match else None


def render_index(catalog_text: str, snippets: dict[str, str] | None = None) -> str:
    raw = json.loads(catalog_text)
    page_docs = []
    for doc in raw.get("documents", []):
        repo = doc.get("repo")
        if repo is not None:
            anchor = {
                "type": "repo",
                "group": repo["name"],
                "subject": repo.get("subject") or "",
            }
        else:
            anchor = {
                "type": "topic",
                "group": doc.get("category", ""),
                "subject": "",
            }

        formats = []
        for variant in doc.get("files", []):
            fmt = variant["format"]
            base = "docs/repos" if anchor["type"] == "repo" else "docs/topics"
            formats.append(
                {
                    "f": fmt,
                    "primary": fmt == doc.get("primary"),
                    "text": fmt in {"md", "html"},
                    "path": f"{base}/{anchor['group']}/{doc['id']}/{doc['id']}.{fmt}",
                }
            )

        page_docs.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "description": doc["description"],
                "kind": doc["kind"],
                "anchor": anchor,
                "tags": list(doc.get("tags", [])),
                "formats": formats,
                "primary": doc.get("primary"),
                "snippet": (snippets or {}).get(doc["id"], ""),
            }
        )

    page_data = {
        "root": "",
        "docs": page_docs,
        "topics": list(raw.get("topics", [])),
        "kinds": list(raw.get("kinds", [])),
    }
    data = json.dumps(page_data, ensure_ascii=False)
    data = (
        data.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )

    tmpl = template_text()
    fingerprint = (
        f"shelf:fingerprint catalog=sha256:{_sha256(catalog_text)} "
        f"template=sha256:{_sha256(tmpl)} version={version('shelf')}"
    )
    rendered = tmpl.replace("__SHELF_FINGERPRINT__", fingerprint)
    rendered = rendered.replace("$fingerprint", fingerprint)
    rendered = rendered.replace("__SHELF_DOC_COUNT__", str(len(page_docs)))
    rendered = rendered.replace("$doc_count", str(len(page_docs)))
    return rendered.replace("__SHELF_DATA__", data)
