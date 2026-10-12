"""Durable recovery for the reference HTML/JSON pair and catalog commit point.

Callers hold library_lock. A pending journal blocks subsequent catalog mutations.
Recovery never overwrites bytes that are neither the old nor proposed version.
"""

import hashlib
import json
import os
from pathlib import Path

import click

from shelf.core.atomic import atomic_write_text
from shelf.core.reference import render_reference

JOURNAL = ".shelf-reference-transaction.json"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_reference_file(path: Path, text: str) -> None:
    atomic_write_text(path, text)
    _sync_directory(path.parent)


def clear_transaction(root: Path) -> None:
    (root / JOURNAL).unlink(missing_ok=True)
    _sync_directory(root)


def begin_transaction(root: Path, doc, paths: list[Path], formats: list[str]) -> dict:
    if (root / JOURNAL).exists():
        raise click.ClickException("pending reference transaction; run 'shelf reference recover'")
    variants = {f.format: f.path for f in doc.files}
    entries = {}
    for source, fmt in zip(paths, formats, strict=True):
        relative = variants[fmt]
        target = _target(root, relative)
        after = source.read_text(encoding="utf-8")
        if (fmt == "html" and after != render_reference(doc.reference)) or (
            fmt == "json" and json.loads(after) != doc.reference
        ):
            raise click.ClickException("reference input changed since validation; render again")
        entries[relative] = {
            "before": target.read_text(encoding="utf-8") if target.exists() else None,
            "after": after,
        }
    journal = {
        "version": 1,
        "catalog_before": _digest((root / "catalog.json").read_text(encoding="utf-8")),
        "id": doc.id,
        "reference": doc.reference,
        "files": entries,
    }
    write_reference_file(root / JOURNAL, json.dumps(journal, ensure_ascii=False))
    return entries


def _target(root: Path, relative: str) -> Path:
    path = root / relative
    try:
        if Path(relative).is_absolute():
            raise ValueError
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        raise click.ClickException("reference transaction path escapes the library") from None
    return path


def recover_transaction(root: Path) -> bool:
    """Roll back before catalog commit; verify committed pair and regenerate index after."""
    path = root / JOURNAL
    if not path.exists():
        return False
    try:
        journal = json.loads(path.read_text(encoding="utf-8"))
        if journal["version"] != 1 or not isinstance(journal["files"], dict):
            raise ValueError("unsupported recovery journal")
        catalog_text = (root / "catalog.json").read_text(encoding="utf-8")
        committed = _digest(catalog_text) != journal["catalog_before"]
        raw = json.loads(catalog_text)
        if committed:
            doc = next(d for d in raw["documents"] if d["id"] == journal["id"])
            if doc.get("reference") != journal["reference"] or not set(journal["files"]) <= {
                f["path"] for f in doc["files"]
            }:
                raise ValueError("catalog changed unexpectedly; retain journal for manual review")
        # Inspect the entire pair before writing anything, including on repeated recovery.
        for relative, entry in journal["files"].items():
            target = _target(root, relative)
            current = target.read_text(encoding="utf-8") if target.exists() else None
            allowed = (entry["after"],) if committed else (entry["before"], entry["after"])
            if current not in allowed:
                raise ValueError(f"{relative} has hand edits; retain journal and reconcile")
        if not committed:
            for relative, entry in journal["files"].items():
                target = _target(root, relative)
                if entry["before"] is None:
                    target.unlink(missing_ok=True)
                    if target.parent.exists():
                        _sync_directory(target.parent)
                else:
                    write_reference_file(target, entry["before"])
            # New ingestion may leave an empty directory. Remove only if empty.
            for relative in journal["files"]:
                folder = _target(root, relative).parent
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
                    _sync_directory(folder.parent)
        from shelf.core.index import render_index
        from shelf.core.preview import build_snippets

        write_reference_file(
            root / "index.html",
            render_index(catalog_text, build_snippets(root, raw.get("documents", []))),
        )
        clear_transaction(root)
        return True
    except (OSError, ValueError, KeyError, TypeError, StopIteration) as exc:
        raise click.ClickException(f"cannot recover reference transaction: {exc}") from exc


def require_no_transaction(root: Path) -> None:
    if (root / JOURNAL).exists():
        raise click.ClickException("pending reference transaction; run 'shelf reference recover'")
