"""shelf CLI entry point."""

from importlib.metadata import version

import click

from shelf.cli import docs as doc_cmds
from shelf.cli import taxonomy
from shelf.cli.audit_cmd import audit_cmd
from shelf.cli.doc_add import doc_add
from shelf.cli.doc_adopt import doc_adopt
from shelf.cli.doc_delete import doc_delete, orphan_delete, orphan_list
from shelf.cli.doc_move import doc_move
from shelf.cli.doc_update import doc_update
from shelf.cli.doc_variants import format_add, format_delete
from shelf.cli.library import init_cmd, migrate_cmd, path_cmd, regen_cmd
from shelf.cli.open_cmd import open_cmd

_VERSION = version("shelf")


@click.group(
    "shelf",
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option(_VERSION, "-V", "--version", prog_name="shelf", message="shelf %(version)s")
@click.option(
    "--library", "library_", type=click.Path(), default=None, help="Library path override."
)
@click.option(
    "--config", "config_", type=click.Path(), default=None, help="Config file overriding discovery."
)
@click.option("-v", "--verbose", count=True, help="Increase diagnostic detail (repeatable).")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-essential output.")
@click.option("--debug", is_flag=True, help="Maximum diagnostics.")
@click.option("--no-input", is_flag=True, help="Never prompt; fail if input would be required.")
@click.pass_context
def cli(ctx, library_, config_, verbose, quiet, debug, no_input):
    """Shelf — a private documentation library."""
    ctx.ensure_object(dict)
    ctx.obj.update(
        library=library_,
        config=config_,
        verbose=verbose,
        quiet=quiet,
        debug=debug,
        no_input=no_input,
    )
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)


def _group(parent: click.Group, name: str, help_text: str) -> click.Group:
    @parent.group(name, invoke_without_command=True, help=help_text)
    @click.pass_context
    def grp(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help(), err=True)
            ctx.exit(2)

    return grp


doc = _group(cli, "doc", "Manage documents.")
doc_format = _group(doc, "format", "Manage a document's format variants.")
orphan = _group(cli, "orphan", "Manage uncataloged files.")
topic = _group(cli, "topic", "Manage topic buckets.")
kind = _group(cli, "kind", "Manage kinds.")

topic.add_command(taxonomy.topic_add)
topic.add_command(taxonomy.topic_list)
kind.add_command(taxonomy.kind_add)
kind.add_command(taxonomy.kind_list)
doc.add_command(doc_cmds.doc_list)
doc.add_command(doc_cmds.doc_list, "ls")
doc.add_command(doc_cmds.doc_view)
doc.add_command(doc_add)
doc.add_command(doc_adopt)
doc.add_command(doc_delete)
doc.add_command(doc_delete, "rm")
doc.add_command(doc_move)
doc.add_command(doc_update)
doc_format.add_command(format_add)
doc_format.add_command(format_delete)
orphan.add_command(orphan_list)
orphan.add_command(orphan_delete)

cli.add_command(open_cmd)

cli.add_command(audit_cmd)
cli.add_command(init_cmd)
cli.add_command(migrate_cmd)
cli.add_command(path_cmd)
cli.add_command(regen_cmd)
