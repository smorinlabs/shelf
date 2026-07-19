"""shelf audit (PRD §11.6)."""

import json
from dataclasses import asdict

import click

from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import active_config_path, get_library
from shelf.core.audit import run_audit
from shelf.core.paths import default_library_path


@click.command("audit")
@click.option(
    "--pre-commit",
    "pre_commit",
    is_flag=True,
    help="Skip the dirty-git check (for use as a pre-commit hook).",
)
@output_options
@click.pass_context
def audit_cmd(ctx, pre_commit, output, json_):
    """Run the library consistency check."""
    config_path = active_config_path(ctx)
    try:
        root = get_library(ctx)
    except click.ClickException:
        root = default_library_path()
    findings = run_audit(root, config_path, pre_commit=pre_commit)
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            click.echo("library is consistent")
        for f in findings:
            click.echo(f"check {f.check} [{f.code}]: {f.detail}")
            click.echo(f"  fix: {f.remediation}")
    if findings:
        ctx.exit(1)
