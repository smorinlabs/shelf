"""P02-TS02 — atomic writes and the library lock."""

import os
import threading

import click
import pytest

from shelf.core.atomic import atomic_write_text, library_lock
from shelf.core.errors import ConflictError, NotFoundError


def test_atomic_write_creates_file(tmp_path):
    target = tmp_path / "catalog.json"
    atomic_write_text(target, "hello")
    assert target.read_text() == "hello"
    assert list(tmp_path.iterdir()) == [target]  # no temp residue


def test_atomic_write_failure_leaves_original(tmp_path, monkeypatch):
    target = tmp_path / "catalog.json"
    target.write_text("original")

    def boom(src, dst):
        raise OSError("injected")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="injected"):
        atomic_write_text(target, "new")
    assert target.read_text() == "original"
    assert list(tmp_path.iterdir()) == [target]  # temp cleaned up


def test_lock_serializes(tmp_path):
    attempted = threading.Event()
    acquired = threading.Event()
    failures: list[BaseException] = []

    def worker():
        try:
            attempted.set()
            with library_lock(tmp_path):
                acquired.set()
        except BaseException as exc:
            failures.append(exc)

    with library_lock(tmp_path):
        t = threading.Thread(target=worker)
        t.start()
        assert attempted.wait(2)
        assert not acquired.wait(0.3)  # still blocked while we hold the lock
    t.join(timeout=2)
    assert not t.is_alive()
    assert acquired.is_set()
    assert not failures


def test_lock_timeout_raises_conflict(tmp_path):
    with library_lock(tmp_path):
        with pytest.raises(ConflictError):
            with library_lock(tmp_path, timeout=0.2):
                pass


def test_exit_codes():
    assert NotFoundError("x").exit_code == 3
    assert ConflictError("x").exit_code == 5
    assert issubclass(NotFoundError, click.ClickException)
