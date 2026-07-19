"""Atomic file writes and the library advisory lock (PRD §5)."""

import fcntl
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path

from shelf.core.errors import ConflictError

LOCK_FILENAME = ".shelf.lock"


def atomic_write_text(path: Path, text: str) -> None:
    """Write via temp file + os.replace; the replace is the commit point."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


@contextmanager
def library_lock(root: Path, timeout: float | None = None) -> Iterator[None]:
    """Exclusive advisory lock at <root>/.shelf.lock; ConflictError on timeout."""
    fh = open(root / LOCK_FILENAME, "a+")
    try:
        if timeout is None:
            fcntl.flock(fh, fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ConflictError("library is locked by another shelf process") from None
                    time.sleep(0.05)
        yield
    finally:
        fh.close()
