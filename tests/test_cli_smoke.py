"""P01-TS01 — CLI smoke tests."""

from importlib.metadata import version as pkg_version

from click.testing import CliRunner

from shelf.cli.main import cli


def test_version_exits_zero():
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"shelf {pkg_version('shelf')}"


def test_dash_v_capital_alias():
    result = CliRunner().invoke(cli, ["-V"])
    assert result.exit_code == 0
    assert result.output.strip() == f"shelf {pkg_version('shelf')}"


def test_help_exits_zero():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Usage: shelf" in result.output
