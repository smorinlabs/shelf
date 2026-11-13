"""P25-TS01 + TS07 — undated --slug values get the added date; the audit hint is a real date."""

import datetime
import json
import re

import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.paths import default_library_path
from shelf.core.slugs import apply_date_rule

BASE = ["--kind", "reference", "--title", "UV Notes", "--description", "d"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def run(args, **kw):
    return CliRunner().invoke(cli, args, **kw)


def _init():
    assert run(["init"]).exit_code == 0
    assert run(["topic", "add", "dev-tooling"]).exit_code == 0
    return default_library_path()


def _src(tmp_path):
    f = tmp_path / "notes.md"
    f.write_text("# hi")
    return f


def _catalog(root):
    return json.loads((root / "catalog.json").read_text())


@pytest.mark.parametrize(
    ("slug", "expected", "applied"),
    [
        ("superpowers", ("2026-11-12-superpowers", "2026-11-12"), True),
        ("2026-11-12-superpowers", ("2026-11-12-superpowers", "2026-11-12"), False),
        ("1999-05-05-old", ("1999-05-05-old", "1999-05-05"), False),
        ("2026-11-12", ("2026-11-12", "2026-11-12"), False),
        # Not real dates, or not followed by '-': dated as if no date were there.
        ("2026-13-45-x", ("2026-11-12-2026-13-45-x", "2026-11-12"), True),
        ("2026-W46-4-x", ("2026-11-12-2026-W46-4-x", "2026-11-12"), True),
        ("2026-11-12x", ("2026-11-12-2026-11-12x", "2026-11-12"), True),
    ],
)
def test_apply_date_rule(slug, expected, applied):
    assert apply_date_rule(slug, "2026-11-12") == (*expected, applied)


def test_undated_slug_is_dated_with_a_rename_warning(isolated_env, tmp_path):
    root = _init()
    today = datetime.date.today().isoformat()
    r = run(["doc", "add", str(_src(tmp_path)), "--topic", "dev-tooling", *BASE, "--slug", "sp"])
    assert r.exit_code == 0, r.output
    entry = _catalog(root)["documents"][0]
    assert entry["id"] == f"{today}-sp"
    assert entry["added"] == today
    assert (
        f"warning: slug 'sp' had no date; stored as '{today}-sp'. "
        f"Rename with: shelf doc rename {today}-sp <new-slug>"
    ) in r.stderr
    assert run(["audit"]).exit_code == 0


def test_dated_slug_is_kept_without_a_warning(isolated_env, tmp_path):
    root = _init()
    r = run(
        ["doc", "add", str(_src(tmp_path)), "--topic", "dev-tooling", *BASE]
        + ["--slug", "2026-01-01-kept"]
    )
    assert r.exit_code == 0, r.output
    assert _catalog(root)["documents"][0]["id"] == "2026-01-01-kept"
    assert "warning" not in r.stderr


def test_dry_run_shows_the_final_id_and_the_warning(isolated_env, tmp_path):
    root = _init()
    today = datetime.date.today().isoformat()
    before = (root / "catalog.json").read_text()
    r = run(
        ["doc", "add", str(_src(tmp_path)), "--topic", "dev-tooling", *BASE]
        + ["--slug", "sp", "--dry-run"]
    )
    assert r.exit_code == 0, r.output
    assert f"would add '{today}-sp'" in r.stdout
    assert "had no date" in r.stderr
    assert (root / "catalog.json").read_text() == before


@pytest.mark.parametrize(
    ("doc_id", "added"),
    [
        ("superpowers-notes", "2026-11-12"),  # undated id
        ("2026-01-01-notes", "2026-02-02"),  # dated id, other date
        ("2026-01-01", "2026-02-02"),  # bare date id
        ("superpowers-notes", "not-a-date"),  # broken added, undated id
        ("2026-01-01-notes", "garbage"),  # broken added, dated id
    ],
)
def test_added_slug_mismatch_hint_only_suggests_real_dates(isolated_env, tmp_path, doc_id, added):
    root = _init()
    r = run(
        ["doc", "add", str(_src(tmp_path)), "--topic", "dev-tooling", *BASE]
        + ["--slug", "2026-01-01-seed"]
    )
    assert r.exit_code == 0, r.output
    raw = _catalog(root)
    doc = raw["documents"][0]
    folder = root / "docs" / "topics" / "dev-tooling"
    (folder / doc["id"]).rename(folder / doc_id)
    (folder / doc_id / f"{doc['id']}.md").rename(folder / doc_id / f"{doc_id}.md")
    doc.update(id=doc_id, added=added)
    doc["files"][0]["path"] = f"docs/topics/dev-tooling/{doc_id}/{doc_id}.md"
    (root / "catalog.json").write_text(json.dumps(raw, indent=2) + "\n")

    findings = json.loads(run(["audit", "--json"]).output)
    hints = [f["remediation"] for f in findings if f["code"] == "added-slug-mismatch"]
    assert len(hints) == 1, findings
    hint = hints[0]
    added_values = re.findall(r"--added (\S+?)['\s]", hint + " ")
    assert all(DATE_RE.match(v) or v == "<YYYY-MM-DD>" for v in added_values), hint
    renamed = re.search(r"shelf doc rename \S+ (\S+?)'", hint)
    if renamed:
        assert DATE_RE.match(renamed.group(1)[:10]), hint
        assert renamed.group(1)[:10] == added
