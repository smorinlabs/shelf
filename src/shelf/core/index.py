"""index.html generation and fingerprinting (PRD §13)."""

import hashlib
import json
import re
from importlib.metadata import version
from importlib.resources import files
from string import Template

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


def render_index(catalog_text: str) -> str:
    tmpl = template_text()
    fingerprint = (
        f"shelf:fingerprint catalog=sha256:{_sha256(catalog_text)} "
        f"template=sha256:{_sha256(tmpl)} version={version('shelf')}"
    )
    doc_count = len(json.loads(catalog_text).get("documents", []))
    return Template(tmpl).substitute(fingerprint=fingerprint, doc_count=doc_count)
