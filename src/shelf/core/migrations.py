"""Catalog schema migrations — one forward step per source version."""

from collections.abc import Callable


def _v0_add_schema_version(raw: dict) -> dict:
    raw["schema_version"] = 1
    return raw


MIGRATIONS: dict[int, Callable[[dict], dict]] = {0: _v0_add_schema_version}
