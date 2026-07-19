"""Catalog model: round-trip, validation, schema gates, atomic commit, fingerprint."""

import json
import re
from typing import Any

import click
import pytest

from shelf.core.catalog import (
    CATALOG_FILENAME,
    SEED_KINDS,
    Catalog,
    Document,
    FileVariant,
    RepoRef,
    commit_library,
    load_catalog,
)
from shelf.core.errors import SchemaTooOldError


def _doc(**over: Any) -> Document:
    base: dict[str, Any] = dict(
        id="2026-01-01-a",
        title="A",
        description="d",
        kind="spec",
        tags=["t"],
        category="dev-tooling",
        files=[
            FileVariant(format="md", path="docs/topics/dev-tooling/2026-01-01-a/2026-01-01-a.md")
        ],
        primary="md",
        added="2026-01-01",
    )
    base.update(over)
    return Document(**base)


def _catalog(**over: Any) -> Catalog:
    base: dict[str, Any] = dict(topics=["dev-tooling"], kinds=list(SEED_KINDS), documents=[_doc()])
    base.update(over)
    return Catalog(**base)


def test_round_trip(tmp_path):
    cat = _catalog()
    commit_library(tmp_path, cat)
    loaded = load_catalog(tmp_path)
    assert loaded.schema_version == 1
    assert loaded.topics == ["dev-tooling"]
    assert loaded.documents[0].id == "2026-01-01-a"
    assert loaded.documents[0].files[0].format == "md"


def test_serialized_shape(tmp_path):
    commit_library(tmp_path, _catalog())
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    assert list(raw)[0] == "schema_version"
    doc = raw["documents"][0]
    assert "repo" not in doc  # topical entry omits repo (§10)
    assert doc["category"] == "dev-tooling"


def test_repo_anchored_omits_category(tmp_path):
    doc = _doc(category=None, repo=RepoRef(name="flox", url="https://x", subject="cli"))
    commit_library(tmp_path, _catalog(documents=[doc]))
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    entry = raw["documents"][0]
    assert "category" not in entry
    assert entry["repo"]["name"] == "flox"


def test_validate_rejects_unknown_kind(tmp_path):
    with pytest.raises(click.ClickException, match="kind"):
        commit_library(tmp_path, _catalog(documents=[_doc(kind="nope")]))


def test_validate_rejects_unknown_category(tmp_path):
    with pytest.raises(click.ClickException, match="topic"):
        commit_library(tmp_path, _catalog(documents=[_doc(category="nope")]))


def test_validate_requires_exactly_one_anchor(tmp_path):
    both = _doc(repo=RepoRef(name="x"))
    with pytest.raises(click.ClickException, match="anchor"):
        commit_library(tmp_path, _catalog(documents=[both]))


def test_newer_schema_refused(tmp_path):
    commit_library(tmp_path, _catalog())
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    raw["schema_version"] = 99
    (tmp_path / CATALOG_FILENAME).write_text(json.dumps(raw))
    with pytest.raises(click.ClickException, match="newer"):
        load_catalog(tmp_path)


def test_older_schema_read_ok_write_refused(tmp_path):
    commit_library(tmp_path, _catalog())
    raw = json.loads((tmp_path / CATALOG_FILENAME).read_text())
    del raw["schema_version"]  # pre-versioned catalog == v0
    (tmp_path / CATALOG_FILENAME).write_text(json.dumps(raw))
    assert load_catalog(tmp_path).documents  # read path works
    with pytest.raises(SchemaTooOldError, match="migrate"):
        load_catalog(tmp_path, for_write=True)


def test_commit_writes_index_with_fingerprint(tmp_path):
    commit_library(tmp_path, _catalog())
    html = (tmp_path / "index.html").read_text()
    m = re.search(
        r"<!-- shelf:fingerprint catalog=sha256:([0-9a-f]{64}) "
        r"template=sha256:([0-9a-f]{64}) version=(\d+\.\d+\.\d+) -->",
        html,
    )
    assert m, html


def test_commit_point_ordering(tmp_path, monkeypatch):
    """A failure writing the index leaves a valid, current catalog (stale index)."""
    commit_library(tmp_path, _catalog())
    import shelf.core.catalog as cat_mod

    real = cat_mod.atomic_write_text

    def fail_on_index(path, text):
        if path.name == "index.html":
            raise OSError("injected index failure")
        real(path, text)

    monkeypatch.setattr(cat_mod, "atomic_write_text", fail_on_index)
    newer = _catalog(topics=["dev-tooling", "extra"])
    with pytest.raises(OSError):
        commit_library(tmp_path, newer)
    assert "extra" in load_catalog(tmp_path).topics  # catalog committed first
