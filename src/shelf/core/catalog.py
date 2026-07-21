"""catalog.json model — the single source of truth (PRD §10).

Mutated only via commit_library (§5).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import click

from shelf.core.atomic import atomic_write_text
from shelf.core.errors import SchemaTooOldError
from shelf.core.index import render_index
from shelf.core.preview import build_snippets

CURRENT_SCHEMA_VERSION = 1
CATALOG_FILENAME = "catalog.json"
SEED_KINDS = ["reference", "explainer", "tutorial", "playbook", "spec", "cheatsheet"]


@dataclass
class FileVariant:
    format: str
    path: str
    source: str | None = None


@dataclass
class RepoRef:
    name: str
    url: str | None = None
    subject: str | None = None


@dataclass
class Document:
    id: str
    title: str
    description: str
    kind: str
    tags: list[str] = field(default_factory=list)
    category: str | None = None
    repo: RepoRef | None = None
    files: list[FileVariant] = field(default_factory=list)
    primary: str | None = None
    added: str | None = None
    doc_date: str | None = None
    source: str | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "kind": self.kind,
            "tags": list(self.tags),
        }
        if self.repo is not None:
            out["repo"] = {k: v for k, v in vars(self.repo).items() if v is not None}
        else:
            out["category"] = self.category
        out["files"] = [{k: v for k, v in vars(f).items() if v is not None} for f in self.files]
        out.update(
            primary=self.primary, added=self.added, doc_date=self.doc_date, source=self.source
        )
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> "Document":
        repo = RepoRef(**raw["repo"]) if raw.get("repo") else None
        return cls(
            id=raw["id"],
            title=raw["title"],
            description=raw["description"],
            kind=raw["kind"],
            tags=list(raw.get("tags", [])),
            category=raw.get("category"),
            repo=repo,
            files=[FileVariant(**f) for f in raw.get("files", [])],
            primary=raw.get("primary"),
            added=raw.get("added"),
            doc_date=raw.get("doc_date"),
            source=raw.get("source"),
        )


@dataclass
class Catalog:
    schema_version: int = CURRENT_SCHEMA_VERSION
    topics: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "topics": self.topics,
            "kinds": self.kinds,
            "documents": [d.to_dict() for d in self.documents],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "Catalog":
        return cls(
            schema_version=raw.get("schema_version", 0),
            topics=list(raw.get("topics", [])),
            kinds=list(raw.get("kinds", [])),
            documents=[Document.from_dict(d) for d in raw.get("documents", [])],
        )

    def validate(self) -> None:
        for doc in self.documents:
            if (doc.repo is None) == (doc.category is None):
                raise click.ClickException(
                    f"document '{doc.id}' must have exactly one anchor (repo or category)"
                )
            if doc.kind not in self.kinds:
                raise click.ClickException(
                    f"document '{doc.id}' has kind '{doc.kind}' not in the kind list"
                )
            if doc.category is not None and doc.category not in self.topics:
                raise click.ClickException(
                    f"document '{doc.id}' has category '{doc.category}' not in the topic list"
                )


def dumps_catalog(catalog: Catalog) -> str:
    return json.dumps(catalog.to_dict(), indent=2, ensure_ascii=False) + "\n"


def load_catalog(root: Path, *, for_write: bool = False) -> Catalog:
    raw = json.loads((root / CATALOG_FILENAME).read_text(encoding="utf-8"))
    found = raw.get("schema_version", 0)
    if not isinstance(found, int):
        raise click.ClickException(
            "catalog.json schema_version is not an integer — catalog is malformed"
        )
    if found > CURRENT_SCHEMA_VERSION:
        raise click.ClickException(
            f"catalog schema_version {found} is newer than this shelf understands — upgrade shelf"
        )
    if for_write and found < CURRENT_SCHEMA_VERSION:
        raise SchemaTooOldError(
            f"catalog schema_version {found} is older than current — run 'shelf migrate' first"
        )
    return Catalog.from_dict(raw)


def commit_library(root: Path, catalog: Catalog) -> None:
    """Validate, then write catalog.json (the commit point), then index.html (§5)."""
    catalog.validate()
    catalog.schema_version = CURRENT_SCHEMA_VERSION
    catalog_text = dumps_catalog(catalog)
    snips = build_snippets(root, [doc.to_dict() for doc in catalog.documents])
    index_text = render_index(catalog_text, snips)
    atomic_write_text(root / CATALOG_FILENAME, catalog_text)
    atomic_write_text(root / "index.html", index_text)
