"""`shelf agent install | status | uninstall` (alias `shelf skill`) — P22."""

import json
from pathlib import Path

import click

from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import interactive, project_scope
from shelf.core import agent

SCOPE = click.Choice(["user", "project"])
DRY_VERBS = {
    "created": "would create",
    "updated": "would update",
    "replaced": "would replace",
    "removed": "would remove",
    "skipped": "would skip",
}


def _tilde(path: Path) -> str:
    home = Path.home().resolve()
    return "~/" + str(path.relative_to(home)) if path.is_relative_to(home) else str(path)


def _report(heading: str, outcomes: list[agent.Outcome], dry_run: bool) -> None:
    click.echo(heading)
    current = None
    for o in outcomes:
        p = o.placement
        if p.folder != current:
            current = p.folder
            click.echo(f"  {p.label} ({_tilde(p.skills_dir)})")
        verb = DRY_VERBS.get(o.verb, o.verb) if dry_run else o.verb
        if o.verb == "skipped":
            line = f"{verb}: {o.reason} (use --force)"
        elif o.verb == "unchanged" and o.reason:
            line = f"unchanged ({o.reason})"
        elif o.reason:
            line = f"{verb}: {o.reason}"
        else:
            line = verb
        click.echo(f"    {p.skill:<17} {line}")


def _run_guarded(fn):
    try:
        return fn()
    except OSError as exc:
        raise click.ClickException(f"could not update the skill folders: {exc}") from exc


PROJECT_HINT = "shelf agent install --scope project"


def _choose_scope(ctx: click.Context) -> tuple[str, bool]:
    """User scope unless the user picks project for a repo with a project shelf.

    Returns (scope, hint): *hint* means print the project-scope command afterwards.
    The question is a choice, not consent, so nothing answers it but a person.
    """
    proj = project_scope(ctx)
    if proj is None:
        return "user", False
    if not interactive(ctx):
        return "user", True
    question = (
        f"This repo has a project shelf ({proj.root}). Install the skills at project "
        "scope, so they are committed for everyone?"
    )
    return ("project" if click.confirm(question, default=False) else "user"), False


@click.command("install")
@click.option(
    "--scope",
    type=SCOPE,
    default=None,
    help="Where to install (default: user; in a repo with a project shelf, asks).",
)
@click.option("--dev", is_flag=True, help="Install symlinks into a shelf checkout, not copies.")
@click.option(
    "--source",
    type=click.Path(file_okay=False),
    default=None,
    help="Shelf checkout for --dev (default: the checkout this shelf runs from).",
)
@click.option("-f", "--force", is_flag=True, help="Replace placements shelf did not install.")
@click.option("--dry-run", is_flag=True, help="Show what would change; write nothing.")
@click.pass_context
def install_cmd(ctx, scope, dev, source, force, dry_run):
    """Install the shelf skills for Claude Code and Codex/Cursor.

    \b
    Examples:
      shelf agent install
      shelf agent install --scope project
      shelf agent install --dev --source ~/c/shelf
    """
    if source is not None and not dev:
        raise click.UsageError("--source requires --dev")
    hint = False
    if scope is None:
        scope, hint = _choose_scope(ctx)
    root = agent.scope_root(scope)
    skills = agent.dev_source(source) if dev else None
    relative = False
    if skills is not None and scope == "project":
        if not skills.resolve().is_relative_to(root):
            raise click.UsageError(
                "a project-scope dev install links into the repo, so the checkout must be "
                f"inside {root}; a link to {skills.parents[2]} would only work on this machine"
            )
        relative = True
    outcomes = _run_guarded(
        lambda: agent.install(
            root, dev=skills, relative_links=relative, force=force, dry_run=dry_run
        )
    )
    mode = f"dev → {_tilde(skills.parents[2])}" if skills is not None else "copy"
    action = "Would install" if dry_run else "Installed"
    _report(
        f"{action} shelf agent skills (scope: {scope}, mode: {mode}, v{agent.cli_version()})",
        outcomes,
        dry_run,
    )
    if not dry_run and any(o.verb in ("created", "updated", "replaced") for o in outcomes):
        click.echo("Restart any running agent session to pick up changes.")
    if hint:
        click.echo(f"Installed at user scope. This repo has a project shelf: {PROJECT_HINT}")
    if any(o.skipped for o in outcomes):
        raise SystemExit(1)


@click.command("status")
@click.option(
    "--scope", type=click.Choice(["user", "project", "all"]), default="all", show_default=True
)
@output_options
@click.pass_context
def status_cmd(ctx, scope, output, json_):
    """List installed shelf skills, their kind, and whether copies are stale."""
    rows = []
    for name in ("user", "project") if scope == "all" else (scope,):
        try:
            root = agent.scope_root(name)
        except click.UsageError:
            if scope != "all":
                raise
            continue
        rows.extend(agent.status_rows(root, name))
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps(rows, indent=2))
        return
    for r in rows:
        detail = r["target"] or (f"v{r['version']}" if r["version"] else "")
        fix = "shelf agent install" + (" --scope project" if r["scope"] == "project" else "")
        stale = f" (stale: {fix})" if r["stale"] else ""
        click.echo(f"{r['scope']}\t{r['folder']}\t{r['skill']}\t{r['kind']}\t{detail}{stale}")
    has_project_skills = any(r["scope"] == "project" and r["kind"] != "missing" for r in rows)
    if scope != "user" and project_scope(ctx) is not None and not has_project_skills:
        click.echo(f"This repo has a project shelf but no project-scope skills: {PROJECT_HINT}")


@click.command("uninstall")
@click.option("--scope", type=SCOPE, default="user", show_default=True)
@click.option("-f", "--force", is_flag=True, help="Also remove placements shelf did not install.")
@click.option("--dry-run", is_flag=True, help="Show what would be removed; remove nothing.")
def uninstall_cmd(scope, force, dry_run):
    """Remove the shelf skills that shelf installed."""
    root = agent.scope_root(scope)
    outcomes = _run_guarded(lambda: agent.uninstall(root, force=force, dry_run=dry_run))
    action = "Would uninstall" if dry_run else "Uninstalled"
    _report(f"{action} shelf agent skills (scope: {scope})", outcomes, dry_run)
    if any(o.skipped for o in outcomes):
        raise SystemExit(1)


def stale_note() -> str | None:
    """One-line note when a user-scope copy is older than this CLI, else None."""
    rows = agent.status_rows(Path.home().resolve(), "user")
    stale = sorted({r["version"] or "unknown" for r in rows if r["stale"]})
    if not stale:
        return None
    known = [v for v in stale if v != "unknown"]
    installed = f"is v{known[0]}" if known else "has no recorded version"
    cli = agent.cli_version()
    return f"note: installed shelf skill {installed}, CLI is v{cli}: shelf agent install"
