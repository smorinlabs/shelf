"""Preview a reference without mutating a library."""

from pathlib import Path

import click

from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.reference import read_record, render_reference
from shelf.core.reference_transaction import recover_transaction


@click.group()
def reference():
    """Validate and render structured references."""


@reference.command("render")
@click.argument("record", type=click.Path(exists=True, dir_okay=False))
@click.argument("output", type=click.Path(dir_okay=False))
def render(record, output):
    """Render a versioned JSON RECORD to a standalone HTML OUTPUT."""
    if Path(record).resolve() == Path(output).resolve():
        raise click.UsageError("output must differ from the input record")
    Path(output).write_text(render_reference(read_record(record)), encoding="utf-8")
    click.echo(f"rendered {output}")


@reference.command("recover")
@click.pass_context
def recover(ctx):
    """Recover an interrupted reference update without overwriting hand edits."""
    root = get_library(ctx)
    with library_lock(root):
        changed = recover_transaction(root)
    click.echo("recovered reference transaction" if changed else "no pending reference transaction")
