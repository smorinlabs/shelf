"""index.html generation from the packaged template, with fingerprint (PRD §13)."""

import hashlib
import json
from importlib.metadata import version
from importlib.resources import files
from string import Template


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render_index(catalog_text: str) -> str:
    template_text = files("shelf.templates").joinpath("index.html.tmpl").read_text(encoding="utf-8")
    fingerprint = (
        f"shelf:fingerprint catalog=sha256:{_sha256(catalog_text)} "
        f"template=sha256:{_sha256(template_text)} version={version('shelf')}"
    )
    doc_count = len(json.loads(catalog_text).get("documents", []))
    return Template(template_text).substitute(fingerprint=fingerprint, doc_count=doc_count)
