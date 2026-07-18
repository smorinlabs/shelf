"""shelf CLI entry point."""

from importlib.metadata import version

import click

_VERSION = version("shelf")


@click.group("shelf", invoke_without_command=True)
@click.version_option(_VERSION, "-V", "--version", prog_name="shelf", message="shelf %(version)s")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Shelf — a private documentation library."""
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
    ("list", "Filter and query documents."),
    ("view", "Print one document in full."),
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

for _name, _help in [
    ("add", "Add a topic."),
    ("list", "List topics."),
]:
    _stub(topic, _name, _help)

for _name, _help in [
    ("add", "Add a kind."),
    ("list", "List kinds."),
]:
    _stub(kind, _name, _help)

for _name, _help in [
    ("init", "Create, adopt, and register a library."),
    ("audit", "Run the library consistency check."),
    ("open", "Open the UI."),
    ("path", "Print resolved locations."),
    ("regen", "Regenerate index.html from the catalog."),
    ("migrate", "Migrate the catalog to the current schema version."),
]:
    _stub(cli, _name, _help)
