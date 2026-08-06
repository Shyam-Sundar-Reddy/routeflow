from typer.testing import CliRunner

from routeflow import __version__
from routeflow.cli import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_about() -> None:
    result = runner.invoke(app, ["about"])
    assert result.exit_code == 0
    assert "routeflow" in result.stdout
