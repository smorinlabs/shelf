"""shelf CLI entry point."""

from importlib.metadata import version

import click

from shelf.cli import docs as doc_cmds
from shelf.cli import taxonomy
from shelf.cli.library import init_cmd, migrate_cmd, path_cmd

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


def _stub(parent: click.Group, name: str, help_text: str) -> None:
    @parent.command(name, help=help_text)
    def _cmd() -> None:
        raise click.ClickException(f"'{name}' is not implemented yet")


doc = _group(cli, "doc", "Manage documents.")
doc_format = _group(doc, "format", "Manage a document's format variants.")
orphan = _group(cli, "orphan", "Manage uncataloged files.")
topic = _group(cli, "topic", "Manage topic buckets.")
kind = _group(cli, "kind", "Manage kinds.")

for _name, _help in [
    ("add", "Add a new document."),
    ("update", "Change a document's metadata."),
    ("move", "Relocate a document."),
    ("delete", "Delete a document."),
    ("adopt", "Register an existing in-library folder."),
]:
    _stub(doc, _name, _help)

for _name, _help in [
    ("add", "Add a format variant."),
    ("delete", "Remove a format variant."),
]:
    _stub(doc_format, _name, _help)

for _name, _help in [
    ("list", "List uncataloged files."),
    ("delete", "Delete an uncataloged file."),
]:
    _stub(orphan, _name, _help)

topic.add_command(taxonomy.topic_add)
topic.add_command(taxonomy.topic_list)
kind.add_command(taxonomy.kind_add)
kind.add_command(taxonomy.kind_list)
doc.add_command(doc_cmds.doc_list)
doc.add_command(doc_cmds.doc_list, "ls")
doc.add_command(doc_cmds.doc_view)

for _name, _help in [
    ("audit", "Run the library consistency check."),
    ("open", "Open the UI."),
    ("regen", "Regenerate index.html from the catalog."),
]:
    _stub(cli, _name, _help)

cli.add_command(init_cmd)
cli.add_command(migrate_cmd)
cli.add_command(path_cmd)
