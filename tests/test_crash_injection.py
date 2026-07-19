"""P03 crash-injection: every failure leaves the library untouched or audit-repairable.

Adversarial failure-injection over the §5 commit ordering. Injection is always
monkeypatch-based (deterministic; no timing games): a chosen ``atomic_write_text``
call, ``shutil`` operation, or a crash between the commit point and a post-commit
cleanup step is forced to raise, then the §5 invariant is re-checked.

Two tests are RED on purpose — they pin the CORRECT behavior for defects found in
this pass (see the task-6 report). They stay red until the implementer fixes src/.
"""

import json

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _library_invariant(root):
    """The §5 invariant: catalog parses and every files[] path exists."""
    catalog = json.loads((root / "catalog.json").read_text())
    for doc in catalog["documents"]:
        for f in doc["files"]:
            assert (root / f["path"]).is_file(), f"dead reference {f['path']}"
    return catalog


def _orphans(root):
    """The set of paths `shelf orphan list` reports — the §5(c) detectability surface."""
    r = run(["orphan", "list", "--json"])
    assert r.exit_code == 0, r.output
    return set(json.loads(r.output))


@pytest.fixture
def seeded(isolated_env, tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    return default_library_path(), src


def _add_doc(tmp_path, slug="2026-01-01-uv-notes", text="# original"):
    """Land one committed md document and return (slug, its on-disk folder)."""
    src = tmp_path / "seed.md"
    src.write_text(text)
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            "dev-tooling",
            *BASE,
            "--slug",
            slug,
            "--no-remove-source",
        ]
    )
    assert r.exit_code == 0, r.output
    return slug, default_library_path() / "docs" / "topics" / "dev-tooling" / slug


def _fail_nth_write(monkeypatch, module, n):
    """Make the nth atomic_write_text call in commit_library raise (1=catalog, 2=index)."""
    import shelf.core.catalog as cat_mod

    calls = {"n": 0}
    real = cat_mod.atomic_write_text

    def flaky(path, text):
        calls["n"] += 1
        if calls["n"] == n:
            raise OSError(f"injected at write #{n}")
        real(path, text)

    monkeypatch.setattr(cat_mod, "atomic_write_text", flaky)


# --------------------------------------------------------------------------- #
# Scenario 1 — the brief's harness: doc add failing at write #1 and write #2.
# --------------------------------------------------------------------------- #


def test_add_fails_at_catalog_write_leaves_untouched(seeded, monkeypatch):
    """Failure BEFORE the commit point (catalog write) → library untouched."""
    root, src = seeded
    before = (root / "catalog.json").read_text()
    _fail_nth_write(monkeypatch, None, 1)  # catalog write = first
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    assert r.exit_code != 0
    assert (root / "catalog.json").read_text() == before
    assert src.exists()
    _library_invariant(root)
    assert _orphans(root) == set()  # staged folder rolled back, no residue


def test_add_fails_at_index_write_catalog_committed(seeded, monkeypatch):
    """FINDING #1 (RED): a post-commit index-write failure must leave the catalog
    authoritative with its files intact (a stale index → `shelf regen`, §5).

    The current doc_add rolls back with `rmtree(dest)` on ANY exception — including
    one raised AFTER the catalog commit point — destroying the just-committed
    document folder and producing a dead reference. _library_invariant catches it.
    """
    root, src = seeded
    _fail_nth_write(monkeypatch, None, 2)  # index write = second (post-commit)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    assert r.exit_code != 0
    catalog = _library_invariant(root)  # catalog valid, files present
    assert len(catalog["documents"]) in (0, 1)  # committed or rolled — never corrupt


# --------------------------------------------------------------------------- #
# Scenario 2 — doc delete crash between commit and rmtree → orphan folder.
# --------------------------------------------------------------------------- #


def test_delete_crash_after_commit_leaves_detectable_orphan(seeded, tmp_path, monkeypatch):
    """Crash after the catalog commit but before the folder is removed. §5 accepts
    the residual folder — and it MUST be visible to `shelf orphan list` (check 1)."""
    root, _ = seeded
    slug, folder = _add_doc(tmp_path)
    rel = f"docs/topics/dev-tooling/{slug}"

    import shelf.cli.doc_delete as dmod

    def crash(*a, **k):
        raise OSError("crash after commit, before rmtree completed")

    monkeypatch.setattr(dmod.shutil, "rmtree", crash)
    r = run(["doc", "delete", slug, "--yes"])
    assert r.exit_code != 0

    catalog = _library_invariant(root)
    assert all(d["id"] != slug for d in catalog["documents"])  # catalog committed
    assert folder.is_dir()  # folder is residue
    assert rel in _orphans(root)  # residue is audit-detectable


# --------------------------------------------------------------------------- #
# Scenario 3 — format add --replace interrupted after overwrite, before commit.
# --------------------------------------------------------------------------- #


def test_format_add_replace_interrupted_before_commit_is_accepted(seeded, tmp_path, monkeypatch):
    """The plan's accepted edge: with --replace, the file is overwritten in place
    before the commit point. A pre-commit failure leaves an UNCHANGED catalog
    referencing UPDATED content — no dead refs, no orphans, audit-clean."""
    root, _ = seeded
    slug, folder = _add_doc(tmp_path, text="# original")
    before = (root / "catalog.json").read_text()

    new_md = tmp_path / "new.md"
    new_md.write_text("# UPDATED")
    _fail_nth_write(monkeypatch, None, 1)  # catalog write fails, after copy2 overwrote
    r = run(["doc", "format", "add", slug, str(new_md), "--replace", "--no-remove-source"])
    assert r.exit_code != 0

    assert (root / "catalog.json").read_text() == before  # catalog unchanged
    assert (folder / f"{slug}.md").read_text() == "# UPDATED"  # accepted residue
    _library_invariant(root)  # path still valid — no dead reference
    assert _orphans(root) == set()  # audit-clean


# --------------------------------------------------------------------------- #
# Scenario 4 — asset rollback (doc add vs. format add asymmetry).
# --------------------------------------------------------------------------- #


def test_add_with_assets_rolls_back_whole_folder(seeded, tmp_path, monkeypatch):
    """doc add stages into a FRESH folder; a pre-commit failure rmtrees the whole
    thing — assets included. Library untouched, source preserved."""
    root, src = seeded
    before = (root / "catalog.json").read_text()
    asset = tmp_path / "diagram.pdf"
    asset.write_text("%PDF")
    _fail_nth_write(monkeypatch, None, 1)  # catalog write fails, after assets copied
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--assets", str(asset)])
    assert r.exit_code != 0

    assert (root / "catalog.json").read_text() == before
    assert src.exists()
    _library_invariant(root)
    assert _orphans(root) == set()  # staged folder + asset fully rolled back


def test_format_add_asset_failure_residue_must_be_detectable(seeded, tmp_path, monkeypatch):
    """FINDING #2 (RED): format add copies --assets into the document's EXISTING
    folder but never records them in the `created` rollback list. A pre-commit
    failure unlinks the new variant file yet leaves the asset behind — inside a
    cataloged folder, where `shelf orphan list` never descends. §5(c) requires all
    residue be audit-detectable; this asset is invisible AND not rolled back.

    Pins the correct behavior: the leftover asset is either rolled back or reported
    by orphan list. Currently it is neither.
    """
    root, _ = seeded
    slug, folder = _add_doc(tmp_path)  # md-only document

    new_pdf = tmp_path / "variant.pdf"
    new_pdf.write_text("%PDF")
    asset = tmp_path / "orphan-asset.png"
    asset.write_text("PNGDATA")

    _fail_nth_write(monkeypatch, None, 1)  # catalog write fails, after asset copied
    r = run(
        [
            "doc",
            "format",
            "add",
            slug,
            str(new_pdf),
            "--assets",
            str(asset),
            "--no-remove-source",
        ]
    )
    assert r.exit_code != 0

    # Catalog rolled back, new variant file unlinked — those parts are correct.
    catalog = _library_invariant(root)
    assert all(f["format"] != "pdf" for f in catalog["documents"][0]["files"])
    assert not (folder / f"{slug}.pdf").exists()

    # The asset, however, is untracked residue. §5(c): it must be gone or detectable.
    leftover = folder / "orphan-asset.png"
    rel = f"docs/topics/dev-tooling/{slug}/orphan-asset.png"
    assert (not leftover.exists()) or (rel in _orphans(root)), (
        "format add left an asset inside a cataloged folder — invisible to "
        "orphan list and not rolled back (§5(c) violation)"
    )


# --------------------------------------------------------------------------- #
# Scenario 5 — self-designed injections.
# --------------------------------------------------------------------------- #


def test_add_multi_variant_copy_failure_leaves_untouched(seeded, tmp_path, monkeypatch):
    """A crash INSIDE shutil.copy2 mid multi-variant add (2nd file) → the fresh
    folder is rmtreed, catalog untouched, both source files preserved."""
    root, src = seeded
    before = (root / "catalog.json").read_text()
    pdf = tmp_path / "uv-notes.pdf"
    pdf.write_text("%PDF")

    import shelf.cli.doc_add as amod

    real_copy = amod.shutil.copy2
    calls = {"n": 0}

    def flaky_copy(a, b, *args, **kw):
        calls["n"] += 1
        if calls["n"] == 2:  # second variant copy
            raise OSError("injected mid-copy")
        return real_copy(a, b, *args, **kw)

    monkeypatch.setattr(amod.shutil, "copy2", flaky_copy)
    r = run(["doc", "add", str(src), str(pdf), "--topic", "dev-tooling", *BASE])
    assert r.exit_code != 0

    assert (root / "catalog.json").read_text() == before
    assert src.exists() and pdf.exists()  # sources never removed on failure
    _library_invariant(root)
    assert _orphans(root) == set()


def test_adopt_crash_at_index_write_keeps_files_intact(seeded, monkeypatch):
    """adopt never copies/moves files, so a post-commit index-write failure is
    inherently safe: catalog committed, the pre-existing folder's files intact,
    only the index stale (→ `shelf regen`). No rollback needed, invariant holds."""
    root, _ = seeded
    slug = "2026-02-02-adopt-me"
    folder = root / "docs" / "topics" / "dev-tooling" / slug
    folder.mkdir(parents=True)
    (folder / f"{slug}.md").write_text("# adopt me")

    _fail_nth_write(monkeypatch, None, 2)  # index write = post-commit
    r = run(
        [
            "doc",
            "adopt",
            f"docs/topics/dev-tooling/{slug}",
            "--kind",
            "reference",
            "--title",
            "Adopt",
            "--description",
            "d",
        ]
    )
    assert r.exit_code != 0

    catalog = _library_invariant(root)  # committed doc's files present
    assert any(d["id"] == slug for d in catalog["documents"])
    assert (folder / f"{slug}.md").is_file()


def test_stale_lock_file_does_not_block_next_command(seeded, tmp_path):
    """A crashed lock holder leaves .shelf.lock on disk (it is never unlinked) while
    the OS releases the advisory flock. The next mutating command must still proceed."""
    root, _ = seeded
    from shelf.core.atomic import library_lock

    with library_lock(root):  # acquire + release — reproduces the post-crash file state
        pass
    assert (root / ".shelf.lock").exists()

    slug, _ = _add_doc(tmp_path)  # a full mutating command must succeed
    catalog = _library_invariant(root)
    assert any(d["id"] == slug for d in catalog["documents"])


# --------------------------------------------------------------------------- #
# Re-verification probes against the F1/F2 fix (commit 66b6332, committed-check).
# --------------------------------------------------------------------------- #


def test_add_catalog_promotion_crash_stays_old_and_rolls_back(seeded, monkeypatch):
    """Probe of the fix's pre-commit direction: a crash INSIDE the catalog atomic
    write (os.replace fails, so catalog.json stays the OLD version) is correctly read
    by the committed-check as 'not committed' → the staged folder is rolled back and
    the library is untouched. Confirms the on-disk-catalog check reads OLD == absent."""
    root, src = seeded
    before = (root / "catalog.json").read_text()

    import shelf.core.atomic as atomic_mod

    real_replace = atomic_mod.os.replace

    def flaky_replace(tmp, path):
        if str(path).endswith("catalog.json"):
            raise OSError("crash before catalog promotion")
        return real_replace(tmp, path)

    monkeypatch.setattr(atomic_mod.os, "replace", flaky_replace)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--slug", "2026-09-09-probe"])
    assert r.exit_code != 0

    assert (root / "catalog.json").read_text() == before  # catalog stayed OLD
    assert not (root / "docs" / "topics" / "dev-tooling" / "2026-09-09-probe").exists()
    assert src.exists()
    _library_invariant(root)
    assert _orphans(root) == set()


def test_format_add_replace_with_new_asset_precommit_leaks_residue(seeded, tmp_path, monkeypatch):
    """FINDING #3 (RED): committed-check regression re-opens the F2 class for --replace.

    `doc format add <id> <same-format> --replace --assets <new>` stages the new asset
    into `created`, but the fix's committed-check tests
    `new_formats ⊆ committed_doc.files` — which is TRUE even in the OLD (uncommitted)
    catalog for --replace, since the format already existed. So a single pre-commit
    catalog-write failure is MISREAD as 'committed', the `created` rollback is skipped,
    and the new asset is left inside the cataloged folder — invisible to
    `shelf orphan list` (§5c). Reachable via one realistic fault (unlike the load-in-
    handler double-fault, which needs a valid-yet-unreadable catalog simultaneously).

    Distinct from the accepted --replace edge (decision 2), which sanctions an
    overwritten *variant file* under an unchanged catalog — not un-tracked assets.
    """
    root, _ = seeded
    slug, folder = _add_doc(tmp_path)  # md-only document
    before = (root / "catalog.json").read_text()

    new_md = tmp_path / "new.md"
    new_md.write_text("# UPDATED")
    asset = tmp_path / "orphan-asset.png"
    asset.write_text("PNGDATA")

    _fail_nth_write(monkeypatch, None, 1)  # catalog write fails — single, pre-commit fault
    r = run(
        [
            "doc",
            "format",
            "add",
            slug,
            str(new_md),
            "--replace",
            "--assets",
            str(asset),
            "--no-remove-source",
        ]
    )
    assert r.exit_code != 0

    assert (root / "catalog.json").read_text() == before  # catalog rolled back
    _library_invariant(root)  # overwritten md still referenced & present (accepted edge)

    leftover = folder / "orphan-asset.png"
    rel = f"docs/topics/dev-tooling/{slug}/orphan-asset.png"
    assert (not leftover.exists()) or (rel in _orphans(root)), (
        "format add --replace left a new asset inside a cataloged folder — invisible "
        "to orphan list and not rolled back (§5c; committed-check regression for --replace)"
    )


def test_format_add_replace_byte_identical_commit_is_safe(seeded, tmp_path, monkeypatch):
    """Adversarial probe of the byte-snapshot witness (commit ad9a80b): the witness
    can read 'not committed' even when the catalog write PHYSICALLY happened, because
    a --replace of the same format on a single-variant doc (no --source/--primary
    change) produces a BYTE-IDENTICAL catalog. This test proves that misclassification
    is BENIGN.

    When the catalog bytes are unchanged, nothing catalog-referenced can be in
    `created` (any new variant would change the bytes), so `created` holds only the
    un-referenced asset. A post-'commit' index-write failure therefore: keeps the
    overwritten variant (accepted edge, decision 2), rolls back only the asset, leaves
    no dead refs, no orphans, and no stale index (the catalog never changed). The
    witness is sound: bytes-change is a faithful commit witness, and byte-identical is
    safe to treat as not-committed.
    """
    root, _ = seeded
    slug, folder = _add_doc(tmp_path)  # single md variant, variant.source is None
    before = (root / "catalog.json").read_text()

    new_md = tmp_path / "new.md"
    new_md.write_text("# UPDATED CONTENT")
    asset = tmp_path / "pic.png"
    asset.write_text("PNGDATA")

    _fail_nth_write(monkeypatch, None, 2)  # index write fails; catalog write wrote identical bytes
    r = run(
        [
            "doc",
            "format",
            "add",
            slug,
            str(new_md),
            "--replace",
            "--assets",
            str(asset),
            "--no-remove-source",
        ]
    )
    assert r.exit_code != 0

    assert (root / "catalog.json").read_text() == before  # byte-identical → unchanged
    assert (folder / f"{slug}.md").read_text() == "# UPDATED CONTENT"  # overwrite persists
    assert not (folder / "pic.png").exists()  # un-referenced asset rolled back — no residue
    _library_invariant(root)
    assert _orphans(root) == set()
