"""Exit-code-bearing exceptions (cli-design-standard §6, PRD §5 conformance note)."""

import click


class NotFoundError(click.ClickException):
    """The requested resource does not exist — exit 3."""

    exit_code = 3


class ConflictError(click.ClickException):
    """Conflict / precondition failed — exit 5."""

    exit_code = 5


class SchemaTooOldError(ConflictError):
    """Catalog schema older than current; mutation refused until `shelf migrate`."""
