"""P07-T02 — cross-command `--commit` / `--commit-message` plumbing (red).

Every mutating command should grow `commit_options` (Task 1) and, once its
`library_lock` is released, optionally run `git_commit_all` with a conventional
`shelf: <verb> <subject>` message. None of that wiring exists yet — these tests
pin the target behavior command-by-command so Task 3 can implement against them.

Expected red modes, per group:
  * Any invocation passing `--commit`/`--commit-message` to a command that
    hasn't grown `commit_options` yet: Click rejects the unknown option,
    exit_code == 2 ("no such option").
  * `default (no --commit)` tests: pass today (no command commits yet either
    way) — they stay green through red and pin the no-flag baseline for green.
  * The git-failure-after-precheck test: fails at `monkeypatch.setattr` with
    AttributeError (module has no `git_commit_all` attribute to patch yet).
"""

import json
import subprocess

import click
import pytest
from click.testing import CliRunner
from conftest import git_init_library

from shelf.cli.main import cli
from shelf.core.paths import default_library_path

SLUG = "2026-01-01-uv-notes"
BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d", "--slug", SLUG]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _src(tmp_path, name="uv-notes.md", text="# hi"):
    f = tmp_path / name
    f.write_text(text)
    return f


def _catalog(root):
    return json.loads((root / "catalog.json").read_text())


def commit_count(root):
    out = subprocess.run(
        ["git", "-C", str(root), "rev-list", "--count", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return int(out)


def last_subject(root):
    return subprocess.run(
        ["git", "-C", str(root), "log", "-1", "--pretty=%s"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def tree_files(root):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-tree", "-r", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return set(out.split())


def is_dirty(root):
    out = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return bool(out.strip())


@pytest.fixture
def git_root(isolated_env, isolated_git_identity):
    """A git-inited shelf library with a `dev-tooling` topic already seeded and
    one baseline commit, ready for `--commit`-flagged mutating commands."""
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    root = default_library_path()
    git_init_library(root)
    return root


def _seed_doc(tmp_path, extra=()):
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source", *extra])
    assert r.exit_code == 0, r.output


# --- doc add ----------------------------------------------------------------


def test_doc_add_commit_creates_one_commit_with_correct_message_and_tree(git_root, tmp_path):
    before = commit_count(git_root)
    src = _src(tmp_path)
    r = run(
        ["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source", "--commit"]
    )
    assert r.exit_code == 0, r.output
    assert commit_count(git_root) == before + 1
    assert last_subject(git_root) == f"shelf: doc add {SLUG}"
    files = tree_files(git_root)
    assert "catalog.json" in files
    assert "index.html" in files
    assert ".shelf.lock" not in files


def test_doc_add_commit_message_overrides_auto_message(git_root, tmp_path):
    src = _src(tmp_path)
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            "dev-tooling",
            *BASE,
            "--no-remove-source",
            "--commit",
            "--commit-message",
            "custom text",
        ]
    )
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == "custom text"


def test_doc_add_default_no_commit_leaves_tree_dirty(git_root, tmp_path):
    before = commit_count(git_root)
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source"])
    assert r.exit_code == 0, r.output
    assert commit_count(git_root) == before  # no new commit
    assert is_dirty(git_root)  # mutation happened, working tree dirty


def test_commit_on_non_git_library_errors_and_makes_no_mutation(isolated_env, tmp_path):
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    root = default_library_path()
    before = (root / "catalog.json").read_text()
    src = _src(tmp_path)
    r = run(
        ["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source", "--commit"]
    )
    assert r.exit_code == 1
    assert "shelf init --git" in r.output
    assert (root / "catalog.json").read_text() == before  # fail fast — no mutation


def test_commit_failure_after_precheck_surfaces_clickexception_but_keeps_mutation(
    git_root, tmp_path, monkeypatch
):
    import shelf.cli.doc_add as mod

    def boom(*a, **k):
        raise click.ClickException("git commit failed: boom")

    monkeypatch.setattr(mod, "git_commit_all", boom)
    src = _src(tmp_path)
    r = run(
        ["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source", "--commit"]
    )
    assert r.exit_code != 0
    assert "boom" in r.output
    # the library-level mutation still landed — audit would flag dirty, not corrupt.
    assert _catalog(git_root)["documents"]
    assert _catalog(git_root)["documents"][0]["id"] == SLUG


# --- doc format add / delete -------------------------------------------------


def test_doc_format_add_single_commit_message(git_root, tmp_path):
    _seed_doc(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    r = run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: doc format add {SLUG} pdf"


def test_doc_format_add_multi_fmt_commit_message_comma_joined_input_order(git_root, tmp_path):
    _seed_doc(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    html = tmp_path / "n.html"
    html.write_text("<html></html>")
    r = run(["doc", "format", "add", SLUG, str(pdf), str(html), "--no-remove-source", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: doc format add {SLUG} pdf,html"


def test_doc_format_delete_commit_message(git_root, tmp_path):
    _seed_doc(tmp_path)
    pdf = tmp_path / "n.pdf"
    pdf.write_text("%PDF")
    assert run(["doc", "format", "add", SLUG, str(pdf), "--no-remove-source"]).exit_code == 0
    r = run(["doc", "format", "delete", SLUG, "pdf", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: doc format delete {SLUG} pdf"
    assert f"docs/topics/dev-tooling/{SLUG}/{SLUG}.pdf" not in tree_files(git_root)


# --- doc update ---------------------------------------------------------------


def test_doc_update_commit_message(git_root, tmp_path):
    _seed_doc(tmp_path)
    r = run(["doc", "update", SLUG, "--title", "New Title", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: doc update {SLUG}"


# --- doc move -------------------------------------------------------------


def test_doc_move_commit_message_and_relocated_tree(git_root, tmp_path):
    _seed_doc(tmp_path)
    r = run(["doc", "move", SLUG, "--topic", "moved-topic", "--create-topic", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: doc move {SLUG}"
    files = tree_files(git_root)
    assert f"docs/topics/moved-topic/{SLUG}/{SLUG}.md" in files
    assert f"docs/topics/dev-tooling/{SLUG}/{SLUG}.md" not in files


# --- doc delete -----------------------------------------------------------


def test_doc_delete_commit_message_and_tree_no_longer_has_folder(git_root, tmp_path):
    _seed_doc(tmp_path)
    r = run(["doc", "delete", SLUG, "--yes", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: doc delete {SLUG}"
    files = tree_files(git_root)
    assert not any(f.startswith(f"docs/topics/dev-tooling/{SLUG}/") for f in files)


# --- doc adopt --------------------------------------------------------------


def test_doc_adopt_commit_message(git_root, tmp_path):
    slug = "2026-01-01-strays"
    d = git_root / "docs" / "topics" / "dev-tooling" / slug
    d.mkdir(parents=True)
    (d / f"{slug}.md").write_text("# stray")
    r = run(
        [
            "doc",
            "adopt",
            f"docs/topics/dev-tooling/{slug}",
            "--kind",
            "reference",
            "--title",
            "Strays",
            "--description",
            "d",
            "--commit",
        ]
    )
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: doc adopt {slug}"


# --- orphan delete ----------------------------------------------------------


def test_orphan_delete_commit_message_names_the_path(git_root):
    rel = "docs/topics/dev-tooling/2026-01-01-strays"
    d = git_root / rel
    d.mkdir(parents=True)
    (d / "strays.md").write_text("# stray")
    r = run(["orphan", "delete", rel, "--yes", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == f"shelf: orphan delete {rel}"


# --- topic add / kind add ----------------------------------------------------


def test_topic_add_commit_message(git_root):
    r = run(["topic", "add", "fresh-topic", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == "shelf: topic add fresh-topic"


def test_kind_add_commit_message(git_root):
    r = run(["kind", "add", "worksheet", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == "shelf: kind add worksheet"


# --- migrate / regen ----------------------------------------------------------


def _downgrade_to_v0(root):
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    del raw["schema_version"]
    path.write_text(json.dumps(raw))


def test_migrate_commit_message(git_root):
    _downgrade_to_v0(git_root)
    r = run(["migrate", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == "shelf: migrate"


def test_regen_commit_message(git_root):
    (git_root / "index.html").unlink()
    r = run(["regen", "--commit"])
    assert r.exit_code == 0, r.output
    assert last_subject(git_root) == "shelf: regen"


# --- default (no --commit) leaves the working tree dirty everywhere ---------


def test_topic_add_default_no_commit_leaves_tree_dirty(git_root):
    before = commit_count(git_root)
    r = run(["topic", "add", "another-topic"])
    assert r.exit_code == 0, r.output
    assert commit_count(git_root) == before
    assert is_dirty(git_root)
