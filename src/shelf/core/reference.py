"""Versioned reference records and a single, inert HTML renderer.

Null means unknown; absence never implies free, open source, or a release date.
"""

import datetime
import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import click

CATEGORIES = [
    "AI Models",
    "AI Models/Speech-to-text",
    "Agent Harnesses & Tools",
    "Skills",
    "Example Projects",
    "Hardware",
    "Hardware/ESP32",
    "Hardware/Raspberry Pi",
    "Learning Electronics",
    "Libraries",
    "Products",
]
TEXT = {"name", "description", "what_it_is", "when_useful", "notes"}
LISTS = {"capabilities", "prerequisites", "limitations", "categories", "tags", "projects"}
DATES = {"saved", "added", "researched", "released"}
PROFILES = {
    "model": {"modalities", "context", "weights", "deployment"},
    "stt": {"languages", "streaming", "timestamps", "diarization", "requirements"},
    "agent_tool": {"integrations", "execution", "permissions"},
    "hardware": {"board", "processor", "voltage", "interfaces", "requirements"},
    "learning": {"level", "equipment", "outcomes", "safety"},
}


def safe_url(value) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        p = urlsplit(value)
        if (
            p.scheme not in {"http", "https"}
            or not p.hostname
            or p.username is not None
            or p.password is not None
            or any(c.isspace() or ord(c) < 32 for c in value)
            or "\\" in value
        ):
            raise ValueError
        _ = p.port
    except (ValueError, AttributeError):
        raise click.ClickException(
            "reference URLs must be absolute HTTP(S), without credentials"
        ) from None
    return value


def identity_url(value: str) -> str:
    p = urlsplit(safe_url(value))
    host = (p.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    port = p.port
    if port is not None and (p.scheme, port) not in {("http", 80), ("https", 443)}:
        host += f":{port}"
    return urlunsplit((p.scheme.lower(), host, p.path.rstrip("/"), p.query, ""))


def validate_record(r: dict) -> dict:
    def fail(message):
        raise click.ClickException(f"invalid reference: {message}")

    def fields(obj, allowed):
        if not isinstance(obj, dict) or set(obj) - allowed:
            fail(f"expected object with fields {sorted(allowed)}")

    def text(value):
        if value is not None and not isinstance(value, str):
            fail("text must be a string or null")

    def date(value):
        text(value)
        if value is not None:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                    raise ValueError
                datetime.date.fromisoformat(value)
            except ValueError:
                fail("dates must be ISO YYYY-MM-DD or null")

    fields(
        r,
        TEXT
        | LISTS
        | {
            "version",
            "entity_url",
            "links",
            "cost",
            "license",
            "dates",
            "sources",
            "related",
            "profiles",
        },
    )
    if type(r.get("version")) is not int or r["version"] != 1:
        fail("unsupported version (expected 1)")
    if not isinstance(r.get("name"), str) or not r["name"].strip():
        fail("name is required")
    safe_url(r.get("entity_url"))
    for key in TEXT:
        text(r.get(key))
    for key in LISTS:
        if not isinstance(r.get(key, []), list) or any(
            not isinstance(v, str) for v in r.get(key, [])
        ):
            fail(f"{key} must be a list of strings")
    for category in r.get("categories", []):
        if category not in CATEGORIES:
            fail(f"unknown category {category}; named projects belong in projects")
    fields(r.get("dates", {}), DATES)
    for value in r.get("dates", {}).values():
        date(value)
    fields(r.get("links", {}), {"homepage", "repository", "docs", "pricing"})
    for values in r.get("links", {}).values():
        if not isinstance(values, list):
            fail("link groups must be lists")
        for value in values:
            safe_url(value)
    for key in ("cost", "license"):
        fact = r.get(key)
        if fact is None:
            continue
        fields(fact, {"summary", "verified", "sources", "source_availability"})
        text(fact.get("summary"))
        text(fact.get("source_availability"))
        date(fact.get("verified"))
        if not isinstance(fact.get("sources", []), list):
            fail("fact sources must be a list")
        for url in fact.get("sources", []):
            safe_url(url)
        if (fact.get("summary") or fact.get("source_availability")) and (
            not fact.get("verified") or not fact.get("sources")
        ):
            fail(f"{key} claims require independent verification date and sources")
    for key in ("sources", "related"):
        if not isinstance(r.get(key, []), list):
            fail(f"{key} must be a list")
        for item in r.get(key, []):
            fields(item, {"label", "url", "accessed"})
            text(item.get("label"))
            safe_url(item.get("url"))
            date(item.get("accessed"))
    fields(r.get("profiles", {}), set(PROFILES))
    for key, profile in r.get("profiles", {}).items():
        fields(profile, PROFILES[key])
        for value in profile.values():
            text(value)
    return r


def read_record(path: str | Path) -> dict:
    try:
        return validate_record(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        raise click.ClickException(f"cannot read reference record: {exc}") from exc


def render_reference(r: dict) -> str:
    validate_record(r)

    def txt(value):
        return escape(value if value is not None else "Unknown")

    def link(url, label=None):
        return (
            f'<a href="{escape(safe_url(url), quote=True)}" rel="noopener noreferrer">'
            f"{txt(label or url)}</a>"
        )

    def section(title, body):
        return f"<section><h2>{txt(title)}</h2>{body}</section>"

    def items(values):
        return (
            "<ul>" + "".join(f"<li>{txt(v)}</li>" for v in values) + "</ul>"
            if values
            else "<p>Unknown</p>"
        )

    body = (
        f"<header><p>Saved reference · v1</p><h1>{txt(r['name'])}</h1>"
        f"<p>{txt(r.get('description'))}</p>"
        f"{link(r['entity_url'], 'Original source')}</header>"
    )
    for key in ("what_it_is", "when_useful", "capabilities", "prerequisites", "limitations"):
        value = r.get(key)
        body += section(
            key.replace("_", " ").title(),
            items(value or []) if key in LISTS else f"<p>{txt(value)}</p>",
        )
    for group in ("homepage", "repository", "docs", "pricing"):
        body += section(
            group.title(),
            (
                "<ul>"
                + "".join(f"<li>{link(u)}</li>" for u in r.get("links", {}).get(group, []))
                + "</ul>"
            )
            if r.get("links", {}).get(group)
            else "<p>Unknown</p>",
        )
    for key in ("cost", "license"):
        fact = r.get(key) or {}
        body += section(
            key.title(),
            f"<p>{txt(fact.get('summary'))}</p><p>Verified: {txt(fact.get('verified'))}</p>"
            + (
                f"<p>Source availability: {txt(fact.get('source_availability'))}</p>"
                if key == "license"
                else ""
            )
            + " ".join(link(u) for u in fact.get("sources", [])),
        )
    for key in ("categories", "tags", "projects"):
        body += section(key.title(), items(r.get(key, [])))
    for profile, values in r.get("profiles", {}).items():
        body += section(
            profile.replace("_", " ").title(),
            "<dl>"
            + "".join(
                f"<dt>{txt(k.replace('_', ' ').title())}</dt><dd>{txt(v)}</dd>"
                for k, v in values.items()
            )
            + "</dl>",
        )
    body += section("User notes", f'<p class="notes">{txt(r.get("notes"))}</p>')
    body += section(
        "Dates",
        "<dl>"
        + "".join(
            f"<dt>{k.title()}</dt><dd>{txt(r.get('dates', {}).get(k))}</dd>" for k in sorted(DATES)
        )
        + "</dl>",
    )
    for key in ("related", "sources"):
        body += section(
            key.title(),
            "<ul>"
            + "".join(
                f"<li>{link(s['url'], s.get('label'))} · Accessed: {txt(s.get('accessed'))}</li>"
                for s in r.get(key, [])
            )
            + "</ul>",
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{txt(r["name"])} — Shelf</title><style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f5f4ef;color:#192d32;font:17px/1.6 system-ui,sans-serif}}
main{{max-width:960px;margin:auto;padding:clamp(16px,4vw,48px);overflow-wrap:anywhere}}
header{{border-bottom:3px solid #29756b;padding-bottom:24px}}
h1{{font-size:clamp(28px,5vw,48px);line-height:1.15}}
section{{background:white;border:1px solid #d8dfda;border-radius:12px;padding:20px;margin:16px 0}}
h2{{font-size:20px;margin:0 0 12px}}a{{color:#126458}}
p{{white-space:pre-wrap}}ul{{padding-left:24px}}
dt{{font-weight:650}}dd{{margin:0 0 12px}}.notes{{white-space:pre-wrap}}
@media(min-width:700px){{dl{{display:grid;grid-template-columns:180px 1fr;gap:8px}}}}
</style></head><body><main>{body}</main></body></html>
"""


def check_reference(r, paths, catalog, old=None, root=None):
    """Validate ingestion before any writes; protect identity and authored content."""
    canonical = identity_url(r["entity_url"])
    urls = {canonical} | {identity_url(u) for values in r.get("links", {}).values() for u in values}
    for doc in catalog.documents:
        if old is not None and doc.id == old.id:
            continue
        candidates = []
        identities = set()
        if doc.source and doc.source.lower().startswith(("https://", "http://")):
            try:
                safe_url(doc.source)
            except click.ClickException:
                pass  # Legacy sources were never constrained to reference URL rules.
            else:
                candidates.append(doc.source)
                identities.add(identity_url(doc.source))
        if doc.reference:
            candidates += [doc.reference["entity_url"]]
            identities.add(identity_url(doc.reference["entity_url"]))
            candidates += [u for values in doc.reference.get("links", {}).values() for u in values]
        if canonical in {identity_url(u) for u in candidates} or urls & identities:
            raise click.ClickException(
                f"reference already exists as '{doc.id}'; refresh that entry"
            )
    html = [p for p in paths if p.suffix.lower() in {".html", ".htm"}]
    if (
        len(paths) != 1
        or len(html) != 1
        or html[0].read_text(encoding="utf-8") != render_reference(r)
    ):
        raise click.ClickException(
            "supply exactly one HTML preview produced by 'shelf reference render'"
        )
    if old is not None and old.reference:
        previous = old.reference
        if (
            old.title != previous["name"]
            or old.description != (previous.get("description") or "Unknown")
            or old.source != previous["entity_url"]
        ):
            raise click.ClickException("reference catalog metadata has hand edits; reconcile first")
        if identity_url(previous["entity_url"]) != identity_url(r["entity_url"]):
            raise click.ClickException("refresh cannot change reference identity")
        if previous.get("notes") != r.get("notes"):
            raise click.ClickException(
                "refresh must preserve user notes; reconcile notes before refreshing"
            )
        for key in ("saved", "added", "released"):
            if previous.get("dates", {}).get(key) != r.get("dates", {}).get(key):
                raise click.ClickException(f"refresh must preserve original {key} date")
        stored = next((f for f in old.files if f.format == "json"), None)
        if stored and read_record(root / stored.path) != previous:
            raise click.ClickException("reference JSON has hand edits; reconcile before refresh")
        variant = next((f for f in old.files if f.format == "html"), None)
        if variant and (root / variant.path).read_text(encoding="utf-8") != render_reference(
            previous
        ):
            raise click.ClickException(
                "reference HTML has hand edits; reconcile and back up before refresh"
            )
    elif old is not None and any(f.format.casefold() in {"html", "json"} for f in old.files):
        raise click.ClickException(
            "existing HTML or JSON is unmanaged; preserve it before adopting a reference"
        )
