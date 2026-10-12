"""Reference contract, ingestion, refresh and both plugin ecosystems."""

import copy
import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from shelf.cli.main import cli
from shelf.core.catalog import load_catalog
from shelf.core.paths import default_library_path
from shelf.core.reference import read_record, render_reference, validate_record

FIXTURES = Path(__file__).parent / "fixtures" / "references"


def run(args):
    return CliRunner().invoke(cli, args)


def stage(tmp_path, record):
    record_path = tmp_path / "record.json"
    record_path.write_text(json.dumps(record))
    preview = tmp_path / "preview.html"
    result = run(["reference", "render", str(record_path), str(preview)])
    assert result.exit_code == 0, result.output
    return preview, record_path


def add(preview, record_path, record, *extra):
    return run(
        [
            "doc",
            "add",
            str(preview),
            "--reference-record",
            str(record_path),
            "--topic",
            record["categories"][0].split("/")[0],
            "--create-topic",
            "--kind",
            "reference",
            "--title",
            record["name"],
            "--description",
            record["description"],
            "--no-remove-source",
            *extra,
        ]
    )


@pytest.mark.parametrize("fixture", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.stem)
def test_fixture_lifecycle(tmp_path, fixture):
    assert run(["init"]).exit_code == 0
    root = default_library_path()
    record = read_record(fixture)
    preview, record_path = stage(tmp_path, record)
    before = (root / "catalog.json").read_bytes()
    assert add(preview, record_path, record, "--dry-run").exit_code == 0
    assert (root / "catalog.json").read_bytes() == before
    result = add(preview, record_path, record)
    assert result.exit_code == 0, result.output
    doc = load_catalog(root).documents[0]
    assert doc.reference == record
    assert {f.format for f in doc.files} == {"html", "json"}
    assert doc.source == record["entity_url"]
    assert "Fixture project" in doc.tags
    assert record["categories"][0] in doc.tags
    assert run(["regen"]).exit_code == 0
    assert run(["audit"]).exit_code == 0
    assert "Open reference" in (root / "index.html").read_text()
    from shelf.core.index import render_index

    index = render_index((root / "catalog.json").read_text(), {doc.id: "STYLE_SENTINEL"})
    assert "STYLE_SENTINEL" not in index
    assert "Original source" in (root / "index.html").read_text()
    assert add(preview, record_path, record, "--slug", "another-id").exit_code != 0
    record["description"] = "Refreshed fixture, still no product claims."
    record["dates"]["researched"] = "2026-10-12"
    preview, record_path = stage(tmp_path, record)
    command = [
        "doc",
        "format",
        "add",
        doc.id,
        str(preview),
        "--reference-record",
        str(record_path),
        "--replace",
        "--no-remove-source",
    ]
    result = run(command)
    assert result.exit_code == 0, result.output
    updated = load_catalog(root).documents[0]
    assert updated.reference == record
    assert updated.added == doc.added and updated.doc_date == doc.doc_date
    assert updated.reference is not None and doc.reference is not None
    assert updated.reference["notes"] == doc.reference["notes"]
    assert run(["audit"]).exit_code == 0
    pair = {f.format: str(root / f.path) for f in updated.files}
    result = run(
        [
            "doc",
            "format",
            "add",
            doc.id,
            pair["html"],
            "--reference-record",
            pair["json"],
            "--replace",
        ]
    )
    assert "outside the library" in result.output
    # Content files and embedded record remain in agreement.
    files = {v.format: root / v.path for v in updated.files}
    assert read_record(files["json"]) == record
    assert files["html"].read_text() == render_reference(record)
    for key in ("saved", "added", "released"):
        changed = copy.deepcopy(record)
        changed["dates"][key] = "1999-01-01"
        stage(tmp_path, changed)
        assert "preserve original" in run(command).output
    changed = copy.deepcopy(record)
    changed["notes"] = "accidental overwrite"
    stage(tmp_path, changed)
    assert "preserve user notes" in run(command).output
    stage(tmp_path, record)
    files["html"].write_text(files["html"].read_text() + "hand edit")
    assert "hand edits" in run(command).output
    assert load_catalog(root).documents[0].reference == record
    files["html"].write_text(render_reference(record))
    changed["notes"] = "hand edited JSON"
    files["json"].write_text(json.dumps(changed))
    assert "hand edits" in run(command).output
    assert run(["doc", "format", "add", doc.id, str(preview), "--replace"]).exit_code != 0
    assert run(["doc", "format", "delete", doc.id, "json"]).exit_code != 0


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html,hi",
        "//evil.test",
        "https://user:pass@example.com",
        "https://@example.com",
        "https://example.com/\nx",
        "https://example.com\\evil",
        None,
        [],
        3,
    ],
)
def test_unsafe_urls(url):
    record = read_record(FIXTURES / "agent-tool.json")
    record["entity_url"] = url
    with pytest.raises(click.ClickException):
        validate_record(record)


def test_schema_and_escaping():
    record = read_record(FIXTURES / "stt-model.json")
    record["name"] = '<script>alert("x")</script>'
    record["notes"] = '<form><img onerror="evil()"></form>'
    html = render_reference(record)
    assert "<script" not in html and "<form" not in html and "<img" not in html
    assert "&lt;script&gt;" in html and "&lt;form&gt;" in html
    assert "Content-Security-Policy" in html and "viewport" in html
    assert "Unknown" in html
    for patch in (
        {"version": 2},
        {"surprise": 1},
        {"dates": {"saved": "yesterday"}},
        {"cost": {"summary": "free"}},
        {"profiles": {"stt": {"unknown": "x"}}},
    ):
        with pytest.raises(click.ClickException):
            validate_record(record | patch)
    verified = {
        "summary": "Synthetic claim",
        "verified": "2026-10-12",
        "sources": ["https://example.com/terms"],
    }
    assert validate_record(record | {"cost": verified})["license"] is None


def test_grouped_url_dedup_and_tampered_input(tmp_path):
    run(["init"])
    record = read_record(FIXTURES / "agent-tool.json")
    preview, record_path = stage(tmp_path, record)
    preview.write_text(preview.read_text() + "<script>bad()</script>")
    assert add(preview, record_path, record).exit_code != 0
    preview, record_path = stage(tmp_path, record)
    assert add(preview, record_path, record).exit_code == 0
    record["entity_url"] = "https://EXAMPLE.com/agent-tool/docs/#anchor"
    preview, record_path = stage(tmp_path, record)
    assert "already exists" in add(preview, record_path, record).output


def test_plugin_discovery():
    repo = Path(__file__).parents[1]
    for ecosystem in (".claude-plugin", ".codex-plugin"):
        manifest = json.loads((repo / "plugins/shelf" / ecosystem / "plugin.json").read_text())
        skill = repo / "plugins/shelf" / manifest["skills"] / "shelf-reference/SKILL.md"
        assert skill.is_file()
        assert "name: shelf-reference" in skill.read_text()
    for marketplace in (".agents/plugins", ".claude-plugin"):
        manifest = json.loads((repo / marketplace / "marketplace.json").read_text())
        source = manifest["plugins"][0]["source"]
        assert (source["path"] if isinstance(source, dict) else source) == "./plugins/shelf"


def test_v1_migration_preserves_unknown_dates_and_notes(tmp_path):
    run(["init"])
    root = default_library_path()
    record = read_record(FIXTURES / "hardware.json")
    preview, record_path = stage(tmp_path, record)
    assert add(preview, record_path, record).exit_code == 0
    path = root / "catalog.json"
    raw = json.loads(path.read_text())
    raw["schema_version"] = 1
    path.write_text(json.dumps(raw))
    before = copy.deepcopy(raw["documents"])
    assert load_catalog(root).schema_version == 1
    assert "migrate" in run(["topic", "add", "another-topic"]).output
    assert run(["migrate"]).exit_code == 0
    assert json.loads(path.read_text())["documents"] == before


def test_refresh_rollback_restores_pair(tmp_path, monkeypatch):
    from shelf.cli import doc_variants

    run(["init"])
    root = default_library_path()
    record = read_record(FIXTURES / "agent-tool.json")
    preview, record_path = stage(tmp_path, record)
    assert add(preview, record_path, record).exit_code == 0
    doc = load_catalog(root).documents[0]
    paths = [root / f.path for f in doc.files] + [root / "catalog.json", root / "index.html"]
    before = {p: p.read_bytes() for p in paths}
    record["description"] = "Updated fixture"
    stage(tmp_path, record)

    def fail(*args):
        raise OSError("simulated pre-commit failure")

    monkeypatch.setattr(doc_variants, "commit_library", fail)
    result = run(
        [
            "doc",
            "format",
            "add",
            doc.id,
            str(preview),
            "--reference-record",
            str(record_path),
            "--replace",
            "--no-remove-source",
        ]
    )
    assert result.exit_code != 0
    assert {p: p.read_bytes() for p in paths} == before


def test_review_guards_and_shared_links(tmp_path):
    run(["init"])
    root = default_library_path()
    record = read_record(FIXTURES / "agent-tool.json")
    record["links"]["pricing"] = ["https://example.com/shared-pricing"]
    preview, record_path = stage(tmp_path, record)
    assert add(preview, record_path, record).exit_code == 0
    doc = load_catalog(root).documents[0]
    malicious = tmp_path / (doc.id + ".html")
    malicious.write_text("<script>attack()</script>")
    note = tmp_path / "note.md"
    note.write_text("new format")
    result = run(["doc", "format", "add", doc.id, str(note), "--assets", str(malicious)])
    assert "do not accept --assets" in result.output
    for fmt in ("HTML", "Json"):
        result = run(["doc", "format", "add", doc.id, str(note), "--format", fmt, "--replace"])
        assert "require --reference-record" in result.output
    assert (root / doc.files[0].path).read_text() == render_reference(record)
    for option in ("--title", "--description", "--source"):
        assert "requires --reference-record" in run(["doc", "update", doc.id, option, "x"]).output
    # Shared provider pricing does not merge separate entities.
    record2 = read_record(FIXTURES / "hardware.json")
    record2["links"]["pricing"] = record["links"]["pricing"]
    preview, record_path = stage(tmp_path, record2)
    assert add(preview, record_path, record2).exit_code == 0
    record2["entity_url"] = "https://EXAMPLE.com:443/agent-tool/#fragment"
    preview, record_path = stage(tmp_path, record2)
    assert "already exists" in add(preview, record_path, record2).output


def test_legacy_sources_and_unmanaged_json(tmp_path):
    run(["init"])
    root = default_library_path()
    source = tmp_path / "handwritten.json"
    source.write_text('{"notes":"hand authored"}')
    args = [
        "doc",
        "add",
        str(source),
        "--format",
        "json",
        "--topic",
        "Products",
        "--create-topic",
        "--kind",
        "reference",
        "--title",
        "Legacy",
        "--description",
        "Legacy data",
        "--source",
        "https://user:password@example.com/private",
        "--no-remove-source",
    ]
    assert run(args).exit_code == 0
    legacy = load_catalog(root).documents[0]
    record = read_record(FIXTURES / "agent-tool.json")
    preview, record_path = stage(tmp_path, record)
    result = run(
        [
            "doc",
            "format",
            "add",
            legacy.id,
            str(preview),
            "--reference-record",
            str(record_path),
            "--replace",
            "--no-remove-source",
        ]
    )
    assert "unmanaged" in result.output
    assert (root / legacy.files[0].path).read_bytes() == source.read_bytes()
    assert add(preview, record_path, record).exit_code == 0


def test_installed_skill_contains_schema_and_fixtures(tmp_path):
    import shutil

    plugin = Path(__file__).parents[1] / "plugins/shelf"
    installed = tmp_path / "installed"
    shutil.copytree(plugin, installed, symlinks=True)
    for ecosystem in (".claude-plugin", ".codex-plugin"):
        manifest = json.loads((installed / ecosystem / "plugin.json").read_text())
        refs = installed / manifest["skills"] / "shelf-reference/references"
        assert (refs / "record-schema.md").is_file()
        for fixture in FIXTURES.glob("*.json"):
            assert read_record(refs / fixture.name) == read_record(fixture)


@pytest.mark.parametrize("operation", ["add", "refresh"])
@pytest.mark.parametrize("phase", ["first-file", "second-file", "catalog"])
def test_process_exit_recovery(tmp_path, operation, phase):
    import subprocess
    import sys

    from shelf.core.reference_transaction import JOURNAL

    run(["init"])
    root = default_library_path()
    record = read_record(FIXTURES / "agent-tool.json")
    preview, record_path = stage(tmp_path, record)
    if operation == "refresh":
        assert add(preview, record_path, record).exit_code == 0
        doc = load_catalog(root).documents[0]
        record["description"] = "Crash recovery fixture update"
        stage(tmp_path, record)
        command = [
            "doc",
            "format",
            "add",
            doc.id,
            str(preview),
            "--reference-record",
            str(record_path),
            "--replace",
            "--no-remove-source",
        ]
    else:
        command = [
            "doc",
            "add",
            str(preview),
            "--reference-record",
            str(record_path),
            "--topic",
            "Products",
            "--create-topic",
            "--kind",
            "reference",
            "--title",
            record["name"],
            "--description",
            record["description"],
            "--no-remove-source",
        ]
    catalog_before = (root / "catalog.json").read_bytes()
    child = """
import importlib, os, sys
from shelf.cli.main import cli
from shelf.core import catalog
module_name = "shelf.cli.doc_add" if sys.argv[1] == "add" else "shelf.cli.doc_variants"
module = importlib.import_module(module_name)
phase = sys.argv[2]
real = module.write_reference_file
count = 0
def write(path, text):
    global count
    real(path, text)
    count += 1
    if (phase == "first-file" and count == 1) or (phase == "second-file" and count == 2):
        os._exit(73)
module.write_reference_file = write
real_catalog = catalog.atomic_write_text
def catalog_write(path, text):
    real_catalog(path, text)
    if phase == "catalog" and path.name == "catalog.json":
        os._exit(73)
catalog.atomic_write_text = catalog_write
cli.main(args=sys.argv[3:])
"""
    result = subprocess.run(
        [sys.executable, "-c", child, operation, phase, "--library", str(root), *command],
        capture_output=True,
        timeout=15,
    )
    assert result.returncode == 73, result.stderr.decode()
    assert (root / JOURNAL).exists()
    assert "reference-transaction-pending" in run(["audit"]).output
    for command in (["regen"], ["migrate"], ["topic", "add", "blocked"]):
        assert "reference recover" in run(command).output
    # Interrupt recovery after restoring one member; retry must be safe.
    if phase == "second-file" and operation == "refresh":
        recovery_child = """
import os, sys
from shelf.cli.main import cli
from shelf.core import reference_transaction as tx
real = tx.write_reference_file
def write(path, text):
    real(path, text)
    if path.suffix == ".html" and path.name != "index.html":
        os._exit(74)
tx.write_reference_file = write
cli.main(args=["--library", sys.argv[1], "reference", "recover"])
"""
        result = subprocess.run([sys.executable, "-c", recovery_child, str(root)], timeout=15)
        assert result.returncode == 74
    result = run(["reference", "recover"])
    assert result.exit_code == 0, result.output
    assert not (root / JOURNAL).exists()
    if phase != "catalog":
        assert (root / "catalog.json").read_bytes() == catalog_before
    else:
        assert load_catalog(root).documents[0].reference == record
    for doc in load_catalog(root).documents:
        pair = {f.format: root / f.path for f in doc.files}
        assert read_record(pair["json"]) == doc.reference
        assert doc.reference is not None
        assert pair["html"].read_text() == render_reference(doc.reference)
    assert run(["audit"]).exit_code == 0
    assert "no pending" in run(["reference", "recover"]).output


def test_recovery_refuses_hand_edits_and_serves_503(tmp_path):
    import urllib.error
    import urllib.request

    from shelf.core.atomic import library_lock
    from shelf.core.reference_transaction import begin_transaction, recover_transaction
    from shelf.server.serve import serve

    run(["init"])
    root = default_library_path()
    record = read_record(FIXTURES / "hardware.json")
    preview, record_path = stage(tmp_path, record)
    assert add(preview, record_path, record).exit_code == 0
    doc = load_catalog(root).documents[0]
    with library_lock(root):
        begin_transaction(root, doc, [preview, record_path], ["html", "json"])
    html = root / next(f.path for f in doc.files if f.format == "html")
    html.write_text("keep these hand edits")
    with pytest.raises(click.ClickException, match="hand edits"):
        with library_lock(root):
            recover_transaction(root)
    assert html.read_text() == "keep these hand edits"
    assert "reference-inconsistent" in run(["audit"]).output
    server, port = serve(root, 0)
    try:
        for route in ("/", "/index.html", "/catalog.json"):
            with pytest.raises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(f"http://127.0.0.1:{port}{route}")
            assert error.value.code == 503
    finally:
        server.shutdown()
        server.server_close()
