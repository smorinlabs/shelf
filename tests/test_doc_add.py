"""P03-TS02/TS03 + T01 — shelf doc add: validation order, rollback, source handling."""

import datetime
import json

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core import handoff as handoff_mod
from shelf.core.paths import default_library_path

BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


def _src(tmp_path, name="uv-notes.md", text="# hi"):
    f = tmp_path / name
    f.write_text(text)
    return f


def _catalog(root):
    return json.loads((root / "catalog.json").read_text())


def test_add_topical_happy_path_removes_source(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    before = datetime.date.today().isoformat()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    after = datetime.date.today().isoformat()
    assert r.exit_code == 0, r.output
    entry = _catalog(root)["documents"][0]
    assert before <= entry["added"] <= after
    slug = entry["id"]
    assert slug == f"{entry['added']}-uv-notes"
    dest = root / "docs" / "topics" / "dev-tooling" / slug / f"{slug}.md"
    assert dest.read_text() == "# hi"
    assert entry["primary"] == "md"
    assert entry["source"] == str(src)
    assert not src.exists()  # remove-source default true


def test_no_remove_source_keeps_original(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--no-remove-source"])
    assert r.exit_code == 0
    assert src.exists()


def test_multi_variant_single_entry(isolated_env, tmp_path):
    root = _init()
    md = _src(tmp_path, "a.md")
    pdf = _src(tmp_path, "a.pdf", "%PDF")
    r = run(["doc", "add", str(md), str(pdf), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert {f["format"] for f in entry["files"]} == {"md", "pdf"}
    assert entry["primary"] == "md"


def test_duplicate_format_usage_error(isolated_env, tmp_path):
    _init()
    a, b = _src(tmp_path, "a.md"), _src(tmp_path, "b.md")
    r = run(["doc", "add", str(a), str(b), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 2


def test_both_anchors_usage_error(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "t", "--repo", "r", *BASE])
    assert r.exit_code == 2


def test_unknown_topic_needs_create_topic(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "fresh", *BASE, "--no-remove-source"])
    assert r.exit_code == 1
    assert "--create-topic" in r.output
    r = run(["doc", "add", str(src), "--topic", "fresh", "--create-topic", *BASE])
    assert r.exit_code == 0
    assert "fresh" in _catalog(root)["topics"]


def test_unknown_kind_never_created(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            "dev-tooling",
            "--kind",
            "novel",
            "--title",
            "T",
            "--description",
            "d",
        ]
    )
    assert r.exit_code == 1
    assert "novel" not in _catalog(root)["kinds"]


def test_slug_collision_conflict(isolated_env, tmp_path):
    _init()
    a = _src(tmp_path, "a.md")
    fixed = ["--slug", "2026-01-01-fixed"]
    assert (
        run(
            ["doc", "add", str(a), "--topic", "dev-tooling", *BASE, *fixed, "--no-remove-source"]
        ).exit_code
        == 0
    )
    b = _src(tmp_path, "b.md")
    r = run(["doc", "add", str(b), "--topic", "dev-tooling", *BASE, *fixed])
    assert r.exit_code == 5
    assert "--slug" in r.output


def test_repo_anchored_layout(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--repo",
            "flox",
            "--repo-url",
            "https://github.com/flox/flox",
            "--subject",
            "cli",
            *BASE,
        ]
    )
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert entry["repo"]["name"] == "flox"
    assert "category" not in entry
    slug = entry["id"]
    assert (root / "docs" / "repos" / "flox" / slug / f"{slug}.md").is_file()


def test_repo_without_url_or_remote_errors(isolated_env, tmp_path):
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--repo", "flox", *BASE])
    assert r.exit_code == 1
    assert "--repo-url" in r.output


def test_tags_and_assets(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    asset = _src(tmp_path, "diagram.pdf", "%PDF")
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            "dev-tooling",
            *BASE,
            "--tag",
            "python",
            "--tag",
            "uv",
            "--assets",
            str(asset),
        ]
    )
    assert r.exit_code == 0
    entry = _catalog(root)["documents"][0]
    assert entry["tags"] == ["python", "uv"]
    slug = entry["id"]
    assert (root / "docs" / "topics" / "dev-tooling" / slug / "diagram.pdf").is_file()


def test_dry_run_changes_nothing(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--dry-run"])
    assert r.exit_code == 0
    assert "would add" in r.output
    assert (root / "catalog.json").read_text() == before
    assert src.exists()


def test_rollback_on_commit_failure(isolated_env, tmp_path, monkeypatch):
    root = _init()
    src = _src(tmp_path)
    import shelf.cli.doc_add as mod

    def boom(*a, **k):
        raise OSError("injected")

    monkeypatch.setattr(mod, "commit_library", boom)
    before = (root / "catalog.json").read_text()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--slug", "2026-01-01-fixed"])
    assert r.exit_code != 0
    assert (root / "catalog.json").read_text() == before
    assert src.exists()  # source never removed on failure
    # staged folder rolled back:
    assert not (root / "docs" / "topics" / "dev-tooling" / "2026-01-01-fixed").exists()


def test_explicit_dated_slug_sets_added(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    r = run(
        ["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--slug", "1999-05-05-old-doc"]
    )
    assert r.exit_code == 0, r.output
    assert _catalog(root)["documents"][0]["added"] == "1999-05-05"


def test_explicit_undated_slug_keeps_today(isolated_env, tmp_path):
    root = _init()
    src = _src(tmp_path)
    before = datetime.date.today().isoformat()
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE, "--slug", "custom-name-here"])
    after = datetime.date.today().isoformat()
    assert r.exit_code == 0, r.output
    assert before <= _catalog(root)["documents"][0]["added"] <= after


def test_full_flags_do_not_hand_off(isolated_env, tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    root = _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--topic", "dev-tooling", *BASE])
    assert r.exit_code == 0, r.output
    assert fired == []  # full flags never hand off
    assert _catalog(root)["documents"]  # the add really happened


def test_missing_all_flags_launch_handoff(isolated_env, tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append((a, list(p))))
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src)])  # no classification flags at all
    assert r.exit_code == 0, r.output
    assert len(fired) == 1
    agent, paths = fired[0]
    assert agent == "claude"  # config default
    assert paths[0].name == src.name


@pytest.mark.parametrize("drop", ["anchor", "--kind", "--title", "--description"])
def test_each_missing_required_flag_triggers_handoff(isolated_env, tmp_path, monkeypatch, drop):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    _init()
    src = _src(tmp_path)
    args = [
        "doc",
        "add",
        str(src),
        "--topic",
        "dev-tooling",
        "--kind",
        "reference",
        "--title",
        "T",
        "--description",
        "d",
    ]
    if drop == "anchor":
        args = [a for a in args if a not in ("--topic", "dev-tooling")]
    else:
        i = args.index(drop)
        del args[i : i + 2]
    r = run(args)
    assert r.exit_code == 0, r.output
    assert fired == ["claude"]  # any single missing required flag → handoff


def test_handoff_agent_flag_overrides_config(isolated_env, tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--handoff-agent", "codex"])
    assert r.exit_code == 0
    assert fired == ["codex"]


def test_config_handoff_agent_used_when_no_flag(isolated_env, tmp_path, monkeypatch):
    from shelf.core.config import default_config_path, load_config, save_config

    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    _init()
    cfgp = default_config_path()
    cfg = load_config(cfgp)
    cfg.handoff_agent = "codex"
    save_config(cfgp, cfg)
    src = _src(tmp_path)
    r = run(["doc", "add", str(src)])  # no --handoff-agent flag
    assert r.exit_code == 0
    assert fired == ["codex"]  # config value reaches the resolver


def test_no_handoff_missing_flags_exit_2(isolated_env, tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--no-handoff"])
    assert r.exit_code == 2
    assert "missing required classification" in r.output
    assert fired == []


def test_no_input_implies_no_handoff(isolated_env, tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    _init()
    src = _src(tmp_path)
    r = run(["--no-input", "doc", "add", str(src)])
    assert r.exit_code == 2
    assert fired == []


def test_inside_claude_session_exit_1(isolated_env, tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    monkeypatch.setenv("CLAUDECODE", "1")
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src)])
    assert r.exit_code == 1
    assert "shelf skill" in r.output and "Claude Code" in r.output
    assert fired == []


def test_inside_codex_session_exit_1(isolated_env, tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    monkeypatch.setenv("CODEX_THREAD_ID", "abc")
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src)])
    assert r.exit_code == 1
    assert "Codex" in r.output
    assert fired == []


def test_suppression_wins_over_session(isolated_env, tmp_path, monkeypatch):
    # PRD §5: --no-input + missing classification exits 2 even inside a session.
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    monkeypatch.setenv("CLAUDECODE", "1")
    _init()
    src = _src(tmp_path)
    r = run(["--no-input", "doc", "add", str(src)])
    assert r.exit_code == 2
    assert fired == []


def test_dry_run_with_missing_flags_still_hands_off(isolated_env, tmp_path, monkeypatch):
    # --dry-run affects library mutation only; the handoff decision precedes it.
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    _init()
    src = _src(tmp_path)
    r = run(["doc", "add", str(src), "--dry-run"])
    assert r.exit_code == 0
    assert fired == ["claude"]


def test_empty_title_and_description_do_not_create_malformed_document(
    isolated_env, tmp_path, monkeypatch
):
    """Data-safety regression: the handoff-trigger check only tests `title is None`
    / `description is None`, not emptiness. `--title "" --description ""` sails
    past it and derive_slug("", added) produces a bare 'YYYY-MM-DD-' slug — a
    malformed document must never be silently committed.
    """
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    root = _init()
    src = _src(tmp_path)
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            "dev-tooling",
            "--kind",
            "reference",
            "--title",
            "",
            "--description",
            "",
        ]
    )
    assert _catalog(root)["documents"] == []
    assert fired == ["claude"] or r.exit_code != 0


def test_whitespace_only_title_does_not_create_malformed_document(
    isolated_env, tmp_path, monkeypatch
):
    fired = []
    monkeypatch.setattr(handoff_mod, "run_handoff", lambda a, p: fired.append(a))
    root = _init()
    src = _src(tmp_path)
    r = run(
        [
            "doc",
            "add",
            str(src),
            "--topic",
            "dev-tooling",
            "--kind",
            "reference",
            "--title",
            "   ",
            "--description",
            "d",
        ]
    )
    assert _catalog(root)["documents"] == []
    assert fired == ["claude"] or r.exit_code != 0
