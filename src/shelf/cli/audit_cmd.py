"""shelf audit (PRD §11.6)."""

import json
from dataclasses import asdict

import click

from shelf.cli.agent_cmd import stale_note
from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import Target, resolve_target, same_library, scope_option, scope_target
from shelf.core.audit import Finding, run_audit
from shelf.core.catalog import load_catalog


def _cross_scope(ctx: click.Context, target: Target) -> list[Finding]:
    """Check 6: a document id in both the project and user libraries (e.g. an
    interrupted 'doc move --to-scope')."""
    other_scope = "user" if target.scope == "project" else "project"
    try:
        other = scope_target(ctx, other_scope)
        if same_library(target, other):
            return []
        here = {d.id for d in load_catalog(target.root).documents}
        there = {d.id for d in load_catalog(other.root).documents}
    except (click.ClickException, OSError, ValueError, KeyError, TypeError):
        return []  # no other scope, or an unreadable catalog the other checks report
    return [
        Finding(
            6,
            "cross-scope-duplicate",
            f"{doc_id} is in both the project and user libraries",
            f"keep one copy: 'shelf doc delete {doc_id} --scope {other_scope}' "
            f"or '--scope {target.scope}'",
        )
        for doc_id in sorted(here & there)
    ]


@click.command("audit")
@click.option(
    "--pre-commit",
    "pre_commit",
    is_flag=True,
    help="Skip the dirty-git check (for use as a pre-commit hook).",
)
@output_options
@scope_option()
@click.pass_context
def audit_cmd(ctx, pre_commit, output, json_):
    """Run the library consistency check."""
    target = resolve_target(ctx)
    findings = run_audit(target.root, target.config_path, pre_commit=pre_commit)
    findings += _cross_scope(ctx, target)
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            click.echo("library is consistent")
        for f in findings:
            click.echo(f"check {f.check} [{f.code}]: {f.detail}")
            click.echo(f"  fix: {f.remediation}")
    note = None if ctx.obj.get("quiet") else stale_note()
    if note:
        click.echo(note, err=True)
    if findings:
        ctx.exit(1)
