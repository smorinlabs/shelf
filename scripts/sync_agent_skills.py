#!/usr/bin/env python3
"""Keep the packaged skill copy generated from its master (P23).

Master:    plugins/shelf/skills/      edit skills here (the marketplace installs it)
Generated: src/shelf/agent_skills/    rebuilt from the master (`shelf agent install` copies it)

    sync_agent_skills.py            rebuild the copy from the master in the working tree
    sync_agent_skills.py --check    exit 1 if the copy differs from the master; write nothing
    sync_agent_skills.py --staged   pre-commit hook: rebuild the copy from the *staged* master
                                    and stage it; fail if only the copy was edited

One physical copy is not possible: uv_build cannot package a symlinked folder, and
Codex installs a plugin whose skills folder is a symlink without its skills.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MASTER = "plugins/shelf/skills"
COPY = "src/shelf/agent_skills"
MARKER = "GENERATED.md"
MARKER_TEXT = f"""# Generated — do not edit

This folder is generated from the master copy in `{MASTER}/`.
Edit the skills there; the pre-commit hook (`lefthook.yml`) or
`just sync-agent-skills` rebuilds this copy. The package ships it so that
`shelf agent install` installs skills that match the CLI version.
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout


def _root() -> Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(out.stdout.strip()) if out.returncode == 0 else Path.cwd()


def _tree(folder: Path) -> dict[str, bytes]:
    if not folder.is_dir():
        return {}
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.relative_to(folder).as_posix() != MARKER
    }


def _rebuild(root: Path, master: Path) -> None:
    copy = root / COPY
    shutil.rmtree(copy, ignore_errors=True)
    shutil.copytree(master, copy)
    (copy / MARKER).write_text(MARKER_TEXT, encoding="utf-8")


def _export_index(root: Path, folder: str, dest: Path) -> Path:
    """Write the staged (index) version of *folder* under *dest*; return its path."""
    files = [f for f in _git(root, "ls-files", "-z", "--", folder).split("\0") if f]
    if files:
        subprocess.run(
            ["git", "-C", str(root), "checkout-index", f"--prefix={dest}/", "--", *files],
            check=True,
            capture_output=True,
        )
    return dest / folder


def _staged(root: Path) -> int:
    changed = _git(root, "diff", "--cached", "--name-only", "--", MASTER, COPY).split()
    master_changed = any(f.startswith(MASTER + "/") for f in changed)
    copy_changed = any(f.startswith(COPY + "/") for f in changed)
    if not (master_changed or copy_changed):
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        master = _export_index(root, MASTER, Path(tmp) / "index")
        if not master_changed:
            staged_copy = _export_index(root, COPY, Path(tmp) / "copy")
            if _tree(staged_copy) == _tree(master):
                return 0
            print(
                f"error: {COPY}/ is generated; this commit edits it without changing the "
                f"master. Make the edit in {MASTER}/ instead (the hook then regenerates "
                f"{COPY}/), or run `just sync-agent-skills` to discard the copy's edit.",
                file=sys.stderr,
            )
            return 1
        _rebuild(root, master)
    _git(root, "add", "-A", "--", COPY)
    print(f"synced {COPY}/ from the staged {MASTER}/", file=sys.stderr)
    return 0


def main(argv: list[str]) -> int:
    root = _root()
    if "--staged" in argv:
        return _staged(root)
    if "--check" in argv:
        if _tree(root / COPY) == _tree(root / MASTER):
            return 0
        print(
            f"error: {COPY}/ differs from its master {MASTER}/: run `just sync-agent-skills`",
            file=sys.stderr,
        )
        return 1
    _rebuild(root, root / MASTER)
    print(f"rebuilt {COPY}/ from {MASTER}/", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
