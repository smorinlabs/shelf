"""Install shelf's agent skills for Claude Code and Codex/Cursor (P22).

Modeled on `baml agent install`: the skills ship inside the package, so a copy always
matches the CLI version. Shelf adds a user scope, a dev mode that places symlinks into
a checkout, and a guard against replacing any placement shelf did not install.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import click

import shelf

SKILL_NAMES = ("shelf", "shelf-reference")
FOLDERS = ((".claude/skills", "Claude Code"), (".agents/skills", "Codex / Cursor"))
STAMP = ".shelf-agent.json"
BACKUP_DIR = "shelf-old_skills"
PLUGIN_ID = "shelf@shelf"
CHECKOUT_SKILLS = Path("plugins") / "shelf" / "skills"


def cli_version() -> str:
    return version("shelf")


def bundled_dir() -> Path:
    return Path(shelf.__file__).resolve().parent / "agent_skills"


# --- scope roots -------------------------------------------------------------


def _git_toplevel(cwd: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return Path(out.stdout.strip()).resolve()


def scope_root(scope: str, cwd: Path | None = None) -> Path:
    """Directory under which `.claude/skills` and `.agents/skills` live for *scope*."""
    home = Path.home().resolve()
    if scope == "user":
        return home
    cwd = (cwd or Path.cwd()).resolve()
    top = _git_toplevel(cwd)
    if top is None:
        raise click.UsageError(f"--scope project needs a Git repository; none contains {cwd}")
    if top != cwd and top not in cwd.parents:
        raise click.UsageError(
            f"the Git repository root {top} does not contain {cwd} (check GIT_DIR / GIT_WORK_TREE)"
        )
    if top == home or top in home.parents:
        raise click.UsageError(
            f"the Git repository root {top} is the home directory or above it; use --scope user"
        )
    return top


# --- sources -----------------------------------------------------------------


def _valid_skills_dir(skills: Path) -> bool:
    for name in SKILL_NAMES:
        md = skills / name / "SKILL.md"
        if not md.is_file() or f"\nname: {name}\n" not in "\n" + md.read_text(encoding="utf-8"):
            return False
    return True


def dev_source(source: str | None) -> Path:
    """The `plugins/shelf/skills` folder of the checkout dev-mode links point into."""
    if source is not None:
        skills = Path(source).expanduser().resolve() / CHECKOUT_SKILLS
        if not _valid_skills_dir(skills):
            raise click.UsageError(
                f"{source} is not a shelf checkout: {CHECKOUT_SKILLS}/<skill>/SKILL.md "
                f"is missing for {', '.join(SKILL_NAMES)}"
            )
        return skills
    skills = Path(shelf.__file__).resolve().parents[2] / CHECKOUT_SKILLS
    if not _valid_skills_dir(skills):
        raise click.UsageError(
            "this shelf is not running from a checkout; pass --source <shelf checkout>"
        )
    return skills


# --- inspection --------------------------------------------------------------


@dataclass
class Placement:
    root: Path
    folder: str
    label: str
    skill: str

    @property
    def skills_dir(self) -> Path:
        return self.root / self.folder

    @property
    def dest(self) -> Path:
        return self.skills_dir / self.skill


def placements(root: Path) -> list[Placement]:
    return [Placement(root, f, label, s) for f, label in FOLDERS for s in SKILL_NAMES]


def _read_stamp(path: Path) -> dict | None:
    try:
        data = json.loads((path / STAMP).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _is_dev_link(dest: Path) -> bool:
    """A symlink into some checkout's `plugins/shelf/skills/<skill>`."""
    target = Path(os.path.realpath(dest))
    return (
        dest.is_symlink()
        and target.name == dest.name
        and target.parent.parts[-len(CHECKOUT_SKILLS.parts) :] == CHECKOUT_SKILLS.parts
        and (target / "SKILL.md").is_file()
    )


def inspect(dest: Path) -> dict:
    """Classify *dest*: missing, copy (stamped by shelf), dev-link, link, or foreign."""
    if dest.is_symlink():
        kind = "dev-link" if _is_dev_link(dest) else "link"
        return {"kind": kind, "target": os.readlink(dest), "version": None}
    if not dest.exists():
        return {"kind": "missing", "target": None, "version": None}
    stamp = _read_stamp(dest) if dest.is_dir() else None
    if stamp is not None and stamp.get("mode") == "copy":
        return {"kind": "copy", "target": None, "version": stamp.get("version")}
    return {"kind": "foreign", "target": None, "version": None}


def _version_key(text: str | None) -> tuple:
    try:
        return tuple(int(part) for part in str(text).split("."))
    except ValueError:
        return ()


def is_stale(info: dict) -> bool:
    return info["kind"] == "copy" and _version_key(info["version"]) < _version_key(cli_version())


def plugin_enabled(root: Path) -> bool:
    try:
        data = json.loads((root / ".claude" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    plugins = data.get("enabledPlugins") if isinstance(data, dict) else None
    return isinstance(plugins, dict) and plugins.get(PLUGIN_ID) is True


def _files(path: Path) -> dict:
    return {
        str(p.relative_to(path)): p.read_bytes()
        for p in sorted(path.rglob("*"))
        if p.is_file() and p.name != STAMP
    }


# --- placing -----------------------------------------------------------------


def _remove(path: Path) -> None:
    """Remove *path*; a symlink is unlinked, never followed."""
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _move_into_place(src: Path, dest: Path) -> None:
    os.replace(src, dest)


def _backup_slot(p: Placement) -> Path:
    """The one-placement backup slot; refuses a symlinked backup folder."""
    folder = p.skills_dir / BACKUP_DIR
    if folder.is_symlink():
        raise click.ClickException(
            f"{folder} is a symlink; shelf will not move or delete files through it. "
            "Replace it with a plain folder and re-run."
        )
    return folder / p.skill


def _swap(p: Placement, build) -> None:
    """Build the new placement beside *p.dest*, back up the old one, then swap it in."""
    tmp_parent = p.skills_dir / f".shelf-agent-tmp-{os.getpid()}"
    _remove(tmp_parent)
    tmp_parent.mkdir(parents=True)
    staged = tmp_parent / p.skill
    backup = _backup_slot(p)
    backed_up = False
    try:
        build(staged)
        if p.dest.is_symlink() or p.dest.exists():
            _remove(backup)
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(p.dest, backup)
            backed_up = True
        try:
            _move_into_place(staged, p.dest)
        except BaseException:
            if backed_up and not (p.dest.is_symlink() or p.dest.exists()):
                os.replace(backup, p.dest)
            raise
    finally:
        _remove(tmp_parent)


def _build_copy(staged: Path, skill: str) -> None:
    shutil.copytree(bundled_dir() / skill, staged)
    stamp = {"mode": "copy", "version": cli_version()}
    (staged / STAMP).write_text(json.dumps(stamp) + "\n", encoding="utf-8")


def _link_text(p: Placement, target: Path, relative: bool) -> str:
    return os.path.relpath(target, p.skills_dir) if relative else str(target)


# --- install / uninstall -----------------------------------------------------


@dataclass
class Outcome:
    placement: Placement
    verb: str  # created | updated | unchanged | replaced | removed | skipped
    reason: str = ""

    @property
    def skipped(self) -> bool:
        return self.verb == "skipped"


def install(
    root: Path,
    *,
    dev: Path | None,
    relative_links: bool,
    force: bool,
    dry_run: bool,
) -> list[Outcome]:
    results = []
    has_plugin = plugin_enabled(root)
    for p in placements(root):
        info = inspect(p.dest)
        kind = info["kind"]
        target = dev / p.skill if dev is not None else None
        text = _link_text(p, target, relative_links) if target is not None else None
        verb, reason = _decide(p, info, target, text, has_plugin, force)
        if verb in ("created", "updated", "replaced") and not dry_run:
            if target is not None:
                _swap(p, lambda staged, text=text: staged.symlink_to(text))
            else:
                _swap(p, lambda staged, skill=p.skill: _build_copy(staged, skill))
        if verb == "replaced" and kind == "missing":
            verb = "created"
        results.append(Outcome(p, verb, reason))
    return results


def _decide(
    p: Placement,
    info: dict,
    target: Path | None,
    text: str | None,
    has_plugin: bool,
    force: bool,
):
    kind = info["kind"]
    guard = None
    if has_plugin and p.folder == ".claude/skills":
        guard = f"the {PLUGIN_ID} plugin is enabled here, so the skill would load twice"
    elif target is not None:  # dev mode
        if kind == "missing":
            return "created", ""
        if kind in ("dev-link", "link") and Path(os.path.realpath(p.dest)) == target.resolve():
            if info["target"] == text:
                return "unchanged", "dev link"
            return "updated", f"link rewritten to {text}"
        guard = {
            "copy": "a copy is installed here; switching to a dev link",
            "dev-link": f"linked to another checkout ({info['target']})",
            "link": f"linked elsewhere ({info['target']})",
            "foreign": "a copy not installed by shelf",
        }[kind]
    else:  # copy mode
        if kind == "missing":
            return "created", ""
        if kind == "copy":
            same = _files(p.dest) == _files(bundled_dir() / p.skill)
            if same and info["version"] == cli_version():
                return "unchanged", ""
            return "updated", ""
        guard = {
            "dev-link": "a dev link is installed here; switching to a copy",
            "link": f"linked elsewhere ({info['target']})",
            "foreign": "a copy not installed by shelf",
        }[kind]
    if force:
        return "replaced", guard
    return "skipped", guard


def uninstall(root: Path, *, force: bool, dry_run: bool) -> list[Outcome]:
    results = []
    for p in placements(root):
        info = inspect(p.dest)
        kind = info["kind"]
        if kind == "missing":
            continue
        if kind in ("copy", "dev-link"):
            if not dry_run:
                _remove(p.dest)
            results.append(Outcome(p, "removed"))
            continue
        reason = (
            f"linked elsewhere ({info['target']})"
            if kind == "link"
            else "a copy not installed by shelf"
        )
        if not force:
            results.append(Outcome(p, "skipped", reason))
            continue
        if not dry_run:
            backup = _backup_slot(p)
            _remove(backup)
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(p.dest, backup)
        results.append(Outcome(p, "removed", f"{reason}; kept in {BACKUP_DIR}/"))
    return results


def status_rows(root: Path, scope: str) -> list[dict]:
    rows = []
    for p in placements(root):
        info = inspect(p.dest)
        rows.append(
            {
                "scope": scope,
                "folder": p.folder,
                "skill": p.skill,
                "path": str(p.dest),
                **info,
                "stale": is_stale(info),
            }
        )
    return rows
