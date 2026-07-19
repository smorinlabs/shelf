"""Slug derivation (PRD §7)."""

import re

KEBAB_MAX = 60


def kebab(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > KEBAB_MAX:
        slug = slug[:KEBAB_MAX]
        if "-" in slug:
            slug = slug.rsplit("-", 1)[0]
    return slug


def derive_slug(title: str, added: str, override: str | None = None) -> str:
    if override:
        return override
    return f"{added}-{kebab(title)}"
