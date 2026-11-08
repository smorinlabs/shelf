"""shelf audit (PRD §11.6)."""

import json
from dataclasses import asdict

import click

from shelf.cli.agent_cmd import stale_note
from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import resolve_target, scope_option
from shelf.core.audit import run_audit


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
