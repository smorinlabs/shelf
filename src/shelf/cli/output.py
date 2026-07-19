"""Result-output option tier: -o/--output with --json shorthand (R4.1/R4.2)."""

import click


def output_options(fn):
    fn = click.option("--json", "json_", is_flag=True, help="Shorthand for -o json.")(fn)
    fn = click.option(
        "-o",
        "--output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format.",
    )(fn)
    return fn


def resolve_format(output: str, json_: bool) -> str:
    return "json" if json_ else output
