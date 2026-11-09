"""Catalog schema migrations — one forward step per source version."""

from collections.abc import Callable


def _v0_add_schema_version(raw: dict) -> dict:
    raw["schema_version"] = 1
    return raw


def _v1_add_publish(raw: dict) -> dict:
    """Schema 2 (P21): every document starts unpublished; nothing else changes."""
    for doc in raw.get("documents", []):
        doc.setdefault("publish", False)
    raw["schema_version"] = 2
    return raw


MIGRATIONS: dict[int, Callable[[dict], dict]] = {
    0: _v0_add_schema_version,
    1: _v1_add_publish,
}
