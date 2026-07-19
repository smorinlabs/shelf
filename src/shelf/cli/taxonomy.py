"""topic/kind add and list (PRD §11.9) — governed growth's explicit steps."""

import json

import click

from shelf.cli.output import output_options, resolve_format
from shelf.cli.runtime import get_library
from shelf.core.atomic import library_lock
from shelf.core.catalog import commit_library, load_catalog
from shelf.core.errors import ConflictError


def _add(ctx: click.Context, list_name: str, name: str) -> None:
    root = get_library(ctx)
    with library_lock(root):
        catalog = load_catalog(root, for_write=True)
        items = getattr(catalog, list_name)
        label = list_name[:-1]  # "topics" -> "topic"
        if name in items:
            raise ConflictError(f"{label} '{name}' already exists")
        items.append(name)
        commit_library(root, catalog)
    click.echo(f"added {list_name[:-1]} '{name}'")


def _list(ctx: click.Context, list_name: str, output: str, json_: bool) -> None:
    catalog = load_catalog(get_library(ctx))
    items = sorted(getattr(catalog, list_name))
    if resolve_format(output, json_) == "json":
        click.echo(json.dumps(items, indent=2))
    else:
        for item in items:
            click.echo(item)


@click.command("add")
@click.argument("name")
@click.pass_context
def topic_add(ctx, name):
    """Add a topic bucket."""
    _add(ctx, "topics", name)


@click.command("list")
@output_options
@click.pass_context
def topic_list(ctx, output, json_):
    """List topic buckets."""
    _list(ctx, "topics", output, json_)


@click.command("add")
@click.argument("name")
@click.pass_context
def kind_add(ctx, name):
    """Add a kind."""
    _add(ctx, "kinds", name)


@click.command("list")
@output_options
@click.pass_context
def kind_list(ctx, output, json_):
    """List kinds."""
    _list(ctx, "kinds", output, json_)
