"""Slug derivation (PRD §7)."""

import datetime
import re
from typing import TypeGuard

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


_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_iso_date(value: object) -> TypeGuard[str]:
    """True for a real calendar date written exactly as YYYY-MM-DD."""
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def date_prefix(slug: str) -> str | None:
    """The slug's leading YYYY-MM-DD date, when it is a real date followed by '-' or nothing."""
    head = slug[:10]
    if is_iso_date(head) and (len(slug) == 10 or slug[10] == "-"):
        return head
    return None


def apply_date_rule(slug: str, added: str) -> tuple[str, str, bool]:
    """Return (slug, added, dated). A slug that starts with a date keeps it, and that date
    becomes `added`; any other slug gets `added` prefixed (dated=True)."""
    existing = date_prefix(slug)
    if existing is not None:
        return slug, existing, False
    return f"{added}-{slug}", added, True


def undated_warning(given: str, stored: str) -> str:
    return (
        f"warning: slug '{given}' had no date; stored as '{stored}'. "
        f"Rename with: shelf doc rename {stored} <new-slug>"
    )
