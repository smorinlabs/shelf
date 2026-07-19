"""The audit engine (PRD §11.6) — raw-level inspection, findings never crashes."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import shelf.core.index as index_mod
from shelf.core.atomic import library_lock
from shelf.core.catalog import CURRENT_SCHEMA_VERSION
from shelf.core.index import _sha256, parse_fingerprint


@dataclass
class Finding:
    check: int
    code: str
    detail: str
    remediation: str


REQUIRED_FIELDS = ("id", "title", "description", "kind")


def _doc_dir(doc: dict) -> str | None:
    if isinstance(doc.get("repo"), dict) and doc["repo"].get("name"):
        return f"docs/repos/{doc['repo']['name']}/{doc.get('id')}"
    if doc.get("category"):
        return f"docs/topics/{doc['category']}/{doc.get('id')}"
    return None


def run_audit(root: Path, config_path: Path, *, pre_commit: bool = False) -> list[Finding]:
    findings: list[Finding] = []

    with library_lock(root):
        try:
            catalog_text = (root / "catalog.json").read_text(encoding="utf-8")
        except OSError:
            return [
                Finding(
                    4,
                    "catalog-unparseable",
                    "catalog.json is missing or unreadable",
                    "restore it from git history or a backup",
                )
            ]
        try:
            index_text = (root / "index.html").read_text(encoding="utf-8")
        except OSError:
            index_text = None

    if not config_path.is_file():
        findings.append(
            Finding(
                4,
                "config-missing",
                str(config_path),
                "register the library with 'shelf init --adopt <path>'",
            )
        )
    try:
        raw = json.loads(catalog_text)
    except json.JSONDecodeError as exc:
        findings.append(
            Finding(
                4,
                "catalog-unparseable",
                str(exc),
                "restore catalog.json from git history or a backup",
            )
        )
        return findings

    schema = raw.get("schema_version", 0)
    if schema > CURRENT_SCHEMA_VERSION:
        findings.append(Finding(3, "schema-newer", f"schema_version {schema}", "upgrade shelf"))
    elif schema < CURRENT_SCHEMA_VERSION:
        findings.append(Finding(3, "schema-old", f"schema_version {schema}", "run 'shelf migrate'"))

    topics = set(raw.get("topics", []))
    kinds = set(raw.get("kinds", []))
    cataloged_dirs: set[str] = set()
    for doc in raw.get("documents", []):
        doc_id = doc.get("id", "<missing id>")
        for field in REQUIRED_FIELDS:
            if not doc.get(field):
                findings.append(
                    Finding(
                        3,
                        "missing-field",
                        f"{doc_id}: {field}",
                        f"repair with 'shelf doc update {doc_id}'",
                    )
                )
        if doc.get("kind") and doc["kind"] not in kinds:
            findings.append(
                Finding(
                    3,
                    "unknown-kind",
                    f"{doc_id}: {doc['kind']}",
                    f"fix with 'shelf doc update {doc_id} --kind <kind>'",
                )
            )
        has_repo = isinstance(doc.get("repo"), dict)
        if not has_repo and doc.get("category") and doc["category"] not in topics:
            findings.append(
                Finding(
                    3,
                    "unknown-category",
                    f"{doc_id}: {doc['category']}",
                    "add the topic or move the document",
                )
            )
        added = doc.get("added")
        if added and isinstance(doc_id, str) and len(doc_id) >= 10 and doc_id[:10] != added:
            findings.append(
                Finding(
                    3,
                    "added-slug-mismatch",
                    f"{doc_id}: added={added}",
                    f"repair with 'shelf doc update {doc_id} --added {doc_id[:10]} --force'",
                )
            )
        expected_dir = _doc_dir(doc)
        if expected_dir:
            cataloged_dirs.add(expected_dir)
            for variant in doc.get("files", []):
                path = variant.get("path", "")
                if not path.startswith(expected_dir + "/"):
                    findings.append(
                        Finding(
                            3,
                            "anchor-mismatch",
                            f"{doc_id}: {path}",
                            f"relocate with 'shelf doc move {doc_id}'",
                        )
                    )
                if path and not (root / path).is_file():
                    findings.append(
                        Finding(
                            2,
                            "dead-reference",
                            f"{doc_id}: {path}",
                            (
                                f"drop with 'shelf doc format delete {doc_id} "
                                f"{variant.get('format', '?')} --force'"
                            ),
                        )
                    )

    docs_dir = root / "docs"
    if docs_dir.is_dir():
        for bucket in ("repos", "topics"):
            base = docs_dir / bucket
            if not base.is_dir():
                continue
            for group in sorted(base.iterdir()):
                if group.is_file():
                    findings.append(
                        Finding(
                            1,
                            "orphan",
                            str(group.relative_to(root)),
                            (
                                "inspect with 'shelf orphan list'; "
                                "adopt with 'shelf doc adopt' or "
                                "delete with 'shelf orphan delete'"
                            ),
                        )
                    )
                    continue
                for entry in sorted(group.iterdir()):
                    rel = str(entry.relative_to(root))
                    if rel not in cataloged_dirs:
                        findings.append(
                            Finding(
                                1,
                                "orphan",
                                rel,
                                (
                                    "inspect with 'shelf orphan list'; "
                                    "adopt with 'shelf doc adopt' or "
                                    "delete with 'shelf orphan delete'"
                                ),
                            )
                        )
        for entry in sorted(docs_dir.iterdir()):
            if entry.is_file():
                findings.append(
                    Finding(
                        1,
                        "orphan",
                        str(entry.relative_to(root)),
                        (
                            "inspect with 'shelf orphan list'; "
                            "adopt with 'shelf doc adopt' or "
                            "delete with 'shelf orphan delete'"
                        ),
                    )
                )

    if index_text is None:
        findings.append(Finding(4, "index-missing", "index.html", "regenerate with 'shelf regen'"))
    else:
        parsed = parse_fingerprint(index_text)
        if parsed is None or parsed != (
            _sha256(catalog_text),
            _sha256(index_mod.template_text()),
        ):
            findings.append(
                Finding(
                    4,
                    "index-stale",
                    "fingerprint mismatch",
                    "regenerate with 'shelf regen'",
                )
            )

    if not pre_commit and (root / ".git").exists():
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "status",
                "--porcelain",
                "--",
                "catalog.json",
                "index.html",
                "docs",
            ],
            capture_output=True,
            text=True,
        )
        if out.returncode == 0 and out.stdout.strip():
            findings.append(
                Finding(
                    5,
                    "git-dirty",
                    out.stdout.strip().splitlines()[0] + " ...",
                    "commit the library changes (git add / git commit)",
                )
            )

    return findings
