"""P05-TS01 + TS03 — the five audit checks, remediations, and snapshot-under-lock."""

import json
import subprocess
import threading

from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = [
    "--kind",
    "reference",
    "--title",
    "UV Notes",
    "--description",
    "d",
    "--slug",
    SLUG,
]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _seeded(tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    src = tmp_path / "uv-notes.md"
    src.write_text("# hi")
    assert run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE]).exit_code == 0
    return default_library_path()


def _raw(root):
    return json.loads((root / "catalog.json").read_text())


def _write_raw(root, raw):
    (root / "catalog.json").write_text(json.dumps(raw, indent=2) + "\n")


def _codes(result):
    return {f["code"] for f in json.loads(result.output)}


def test_clean_library_exits_zero(isolated_env, tmp_path):
    _seeded(tmp_path)
    assert run(["regen"]).exit_code == 0  # hand: seeded lib is consistent already
    r = run(["audit"])
    assert r.exit_code == 0, r.output
    assert "consistent" in r.output


def test_orphan_finding(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    stray = root / "docs" / "topics" / "dev-tooling" / "2026-02-02-stray"
    stray.mkdir(parents=True)
    (stray / "x.md").write_text("x")
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "orphan" in _codes(r)
    table = run(["audit"])
    assert "orphan" in table.output and (
        "doc adopt" in table.output or "orphan delete" in table.output
    )


def test_dead_reference_finding(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    (root / "docs" / "topics" / "dev-tooling" / SLUG / f"{SLUG}.md").unlink()
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "dead-reference" in _codes(r)
    assert "format delete" in run(["audit"]).output


def test_malformed_entry_findings(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["documents"][0]["kind"] = "made-up"
    raw["documents"][0]["added"] = "1999-01-01"
    del raw["documents"][0]["description"]
    _write_raw(root, raw)
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    codes = _codes(r)
    assert {"unknown-kind", "added-slug-mismatch", "missing-field"} <= codes


def test_schema_findings(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    del raw["schema_version"]
    _write_raw(root, raw)
    r = run(["audit", "--json"])
    assert "schema-old" in _codes(r)
    assert "migrate" in run(["audit"]).output
    raw = _raw(root)
    raw["schema_version"] = 99
    _write_raw(root, raw)
    assert "schema-newer" in _codes(run(["audit", "--json"]))


def test_index_and_config_findings(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    (root / "index.html").unlink()
    r = run(["audit", "--json"])
    assert "index-missing" in _codes(r)
    assert run(["regen"]).exit_code == 0
    raw = _raw(root)
    raw["topics"].append("hand-added")
    _write_raw(root, raw)
    r = run(["audit", "--json"])
    assert "index-stale" in _codes(r)
    assert "regen" in run(["audit"]).output
    from shelf.core.config import default_config_path

    default_config_path().unlink()
    assert "config-missing" in _codes(run(["--library", str(root), "audit", "--json"]))


def test_template_change_makes_index_stale(isolated_env, tmp_path, monkeypatch):
    _seeded(tmp_path)
    import shelf.core.index as index_mod

    monkeypatch.setattr(
        index_mod, "template_text", lambda: "<html>$fingerprint v2 $doc_count</html>"
    )
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "index-stale" in _codes(r)
    assert run(["regen"]).exit_code == 0
    assert run(["audit"]).exit_code == 0  # fresh under the new template


def _git(root, *args):
    import os

    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", *args], cwd=root, check=True, env=env)


def test_git_dirty_finding_and_pre_commit_skip(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    assert run(["audit"]).exit_code == 0  # committed clean library
    assert run(["topic", "add", "makes-dirty"]).exit_code == 0
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "git-dirty" in _codes(r)
    r = run(["audit", "--pre-commit", "--json"])
    assert r.exit_code == 0, r.output
    assert "git-dirty" not in _codes(r)


def test_audit_blocks_on_lock_no_false_stale(isolated_env, tmp_path):
    """TS03: audit snapshots under the lock; a mid-transaction state is never observed."""
    root = _seeded(tmp_path)
    from shelf.core.atomic import library_lock
    from shelf.core.catalog import load_catalog

    results = {}
    attempting = threading.Event()
    import shelf.core.audit as audit_mod

    real_lock = audit_mod.library_lock

    def signaling_lock(*args, **kwargs):
        attempting.set()
        return real_lock(*args, **kwargs)

    def run_audit_thread():
        results["audit"] = CliRunner().invoke(cli, ["audit"])

    import unittest.mock

    with unittest.mock.patch.object(audit_mod, "library_lock", signaling_lock), library_lock(root):
        # simulate mid-transaction: catalog advanced, index not yet rewritten
        catalog = load_catalog(root, for_write=True)
        catalog.topics.append("mid-transaction")
        from shelf.core.atomic import atomic_write_text
        from shelf.core.catalog import dumps_catalog

        atomic_write_text(root / "catalog.json", dumps_catalog(catalog))
        t = threading.Thread(target=run_audit_thread)
        t.start()
        assert attempting.wait(2)  # audit has reached its lock acquisition
        t.join(timeout=0.3)
        assert t.is_alive()  # audit is blocked on the lock, not reading torn state
        # finish the transaction before releasing
        from shelf.core.index import render_index

        atomic_write_text(root / "index.html", render_index(dumps_catalog(catalog)))
    t.join(timeout=5)
    assert not t.is_alive()
    assert results["audit"].exit_code == 0, results["audit"].output


def test_audit_unresolvable_library_errors_cleanly(isolated_env, tmp_path):
    """Custom library + lost config: clean resolve error, never a traceback."""
    custom = tmp_path / "custom-lib"
    assert run(["init", "--library", str(custom)]).exit_code == 0
    from shelf.core.config import default_config_path

    default_config_path().unlink()
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "shelf init" in r.output
    assert not isinstance(r.exception, FileNotFoundError)


def test_audit_resolvable_root_reports_config_missing(isolated_env, tmp_path):
    custom = tmp_path / "custom-lib"
    assert run(["init", "--library", str(custom)]).exit_code == 0
    from shelf.core.config import default_config_path

    default_config_path().unlink()
    r = run(["--library", str(custom), "audit", "--json"])
    assert r.exit_code == 1
    assert "config-missing" in _codes(r)
    assert not isinstance(r.exception, FileNotFoundError)


def test_audit_orphan_parity_stray_file_under_docs(isolated_env, tmp_path):
    """A stray file directly under docs/ must be found by audit AND orphan list."""
    root = _seeded(tmp_path)
    (root / "docs" / "stray.md").write_text("x")
    r = run(["audit", "--json"])
    assert r.exit_code == 1
    assert "orphan" in _codes(r)
    assert "docs/stray.md" in r.output
    assert "docs/stray.md" in run(["orphan", "list"]).output


def test_audit_git_inited_library_ignores_gitkeep(isolated_env, isolated_git_identity, monkeypatch):
    """P07 regression: `init --git` writes `.gitkeep` placeholders directly under
    docs/repos/ and docs/topics/ so git tracks the empty buckets. They are git
    housekeeping, not orphaned document content, and must not trip the orphan scan.
    """
    monkeypatch.setenv("GIT_AUTHOR_NAME", "t")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "t@t")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "t")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "t@t")
    assert run(["init", "--git"]).exit_code == 0
    root = default_library_path()
    assert (root / "docs" / "repos" / ".gitkeep").is_file()
    assert (root / "docs" / "topics" / ".gitkeep").is_file()
    r = run(["audit"])
    assert r.exit_code == 0, r.output
    assert ".gitkeep" not in r.output


# --- B2: dirty-git subprocess is unwrapped ---------------------------------


def test_git_status_missing_binary_does_not_raw_traceback(
    isolated_env, isolated_git_identity, tmp_path, monkeypatch
):
    """B2: the dirty-git check's subprocess call (audit.py, ~line 227-ish) is
    fully unwrapped. A missing `git` binary must not raw-traceback out of
    `shelf audit` — it must surface cleanly (ClickException/clean exit, or a
    finding), never a bare FileNotFoundError."""
    root = _seeded(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")

    import shelf.core.audit as audit_mod

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(audit_mod.subprocess, "run", fake_run)

    r = run(["audit"])
    assert not isinstance(r.exception, FileNotFoundError)
    assert r.exception is None or isinstance(r.exception, SystemExit)


# --- B4: audit must never raw-traceback on a malformed-but-parseable catalog


def test_audit_never_crashes_on_string_schema_version(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["schema_version"] = "1"
    _write_raw(root, raw)
    r = run(["audit"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_audit_never_crashes_on_null_document(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["documents"] = [None]
    _write_raw(root, raw)
    r = run(["audit"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_audit_never_crashes_on_document_with_string_files(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["documents"][0]["files"] = "oops"
    _write_raw(root, raw)
    r = run(["audit"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


# --- B5: audit must flag a document with neither repo nor category --------


def test_audit_flags_document_with_neither_repo_nor_category(isolated_env, tmp_path):
    """B5: a structurally-malformed document with valid id/title/description/kind
    but NEITHER repo NOR category (and no files) currently produces zero
    findings naming it — audit never notices it has no anchor. Must be flagged.

    Built directly (not via `doc add`/`_seeded`) so there is no on-disk folder
    for this id — otherwise the docs/ orphan scan would flag the *folder* as
    an orphan, masking the real bug: no check ever inspects this document for
    missing repo/category.
    """
    assert run(["init"]).exit_code == 0
    root = default_library_path()
    doc_id = "2026-01-01-no-anchor-doc"
    raw = _raw(root)
    raw["documents"] = [
        {
            "id": doc_id,
            "title": "No Anchor Doc",
            "description": "d",
            "kind": raw["kinds"][0],
            "tags": [],
            "files": [],
        }
    ]
    _write_raw(root, raw)
    r = run(["audit", "--json"])
    assert r.exit_code == 1, r.output
    findings = json.loads(r.output)
    assert any(doc_id in f["detail"] for f in findings), findings


# --- B6: a malformed shelf_config.toml must not raw-traceback -------------


def test_audit_survives_malformed_config_toml(isolated_env, tmp_path):
    """B6: garbage (non-TOML) content in the active shelf_config.toml must not
    raw-traceback a TOMLDecodeError out of `shelf audit`, even when the
    library is given explicitly via --library."""
    root = _seeded(tmp_path)
    from shelf.core.config import default_config_path

    default_config_path().write_text("this is not [valid toml", encoding="utf-8")
    r = run(["--library", str(root), "audit"])

    import tomllib

    assert not isinstance(r.exception, tomllib.TOMLDecodeError)
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_audit_never_crashes_on_scalar_documents(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["documents"] = 5
    _write_raw(root, raw)
    r = run(["audit"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_audit_never_crashes_on_null_documents_container(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["documents"] = None
    _write_raw(root, raw)
    r = run(["audit"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_audit_never_crashes_on_null_topics(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["topics"] = None
    _write_raw(root, raw)
    r = run(["audit"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)


def test_audit_never_crashes_on_scalar_kinds(isolated_env, tmp_path):
    root = _seeded(tmp_path)
    raw = _raw(root)
    raw["kinds"] = 7
    _write_raw(root, raw)
    r = run(["audit"])
    assert r.exit_code == 1, r.output
    assert r.exception is None or isinstance(r.exception, SystemExit)
