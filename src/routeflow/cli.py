from __future__ import annotations

import typer
from rich.console import Console

from routeflow import __version__

app = typer.Typer(
    name="routeflow",
    help="Visualize the real-time execution path of FastAPI requests.",
    no_args_is_help=True,
)
console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"routeflow {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the routeflow version and exit.",
    ),
) -> None:
    """routeflow: execution-flow visualization for FastAPI apps."""


@app.command()
def about() -> None:
    """Print a short description of what routeflow does."""
    # Plain ASCII punctuation only, deliberately - a Windows console's
    # codepage (e.g. 437, the default) doesn't include the em-dash
    # rich/Python's stdout encoding writes by default, which renders as
    # mojibake ("?") instead of silently doing nothing. Confirmed by
    # inspecting the actual output bytes, not assumed.
    console.print(
        "routeflow tracks the real-time execution path of a FastAPI "
        "request - order, timing, logs, and errors - through a simple "
        "decorator, and renders it as an interactive node graph so you "
        "can see what happened instead of piecing it together from logs.\n\n"
        "Quickstart:\n"
        "  from routeflow import RouteFlow\n"
        "  RouteFlow(app)  # one line, wherever your FastAPI app is created\n\n"
        "Then open http://127.0.0.1:8000/flow/ (adjust host/port\n"
        "to match your server) while your app is running."
    )


if __name__ == "__main__":
    app()
