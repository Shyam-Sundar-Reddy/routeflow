from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import quote

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

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


# ---- commands that talk to a running instance --------------------------
#
# There's no daemon and no config file - every command below that needs a
# running app takes an explicit --url pointing at it (the app's own base
# URL, e.g. http://127.0.0.1:8000), and derives the /__routeflow__ API
# path from that itself. Deliberately urllib, not a new HTTP-client
# dependency - routeflow's core dependencies are typer/rich/starlette
# only, and these commands are the one place a request actually needs to
# leave the process.

DEFAULT_URL = "http://127.0.0.1:8000"


def _api_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + "/__routeflow__/" + path.lstrip("/")


def _fetch_json(url: str) -> object:
    try:
        with urllib.request.urlopen(url, timeout=5.0) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Caught first, deliberately - HTTPError is a subclass of
        # URLError, so this branch would never run if URLError came
        # first (confirmed live: a real 404 was reported as "couldn't
        # reach", the wrong, more alarming message for "reached it fine,
        # got a 404 back").
        console.print(f"[red]{url} returned HTTP {exc.code}[/red]")
        raise typer.Exit(1) from exc
    except urllib.error.URLError as exc:
        console.print(
            f"[red]Couldn't reach {url}[/red]\n"
            "Is the app actually running, with RouteFlow installed "
            f"(RouteFlow(app)) and not disabled (ROUTEFLOW_ENABLED)? ({exc})"
        )
        raise typer.Exit(1) from exc


@app.command(name="open")
def open_flow_view(
    url: str = typer.Option(DEFAULT_URL, help="Base URL the app is running at."),
) -> None:
    """Open the flow view in your default browser."""
    flow_url = url.rstrip("/") + "/flow/"
    console.print(f"Opening {flow_url} ...")
    webbrowser.open(flow_url)


@app.command()
def traces(
    url: str = typer.Option(DEFAULT_URL, help="Base URL the app is running at."),
    route_pattern: str | None = typer.Option(
        None, "--route-pattern", help='Only this endpoint, e.g. "/orders/{id}".'
    ),
    limit: int = typer.Option(20, help="Show at most this many, most recent first."),
) -> None:
    """List recent traces from a running RouteFlow-instrumented app."""
    api = _api_url(url, "traces")
    if route_pattern:
        api += f"?route_pattern={quote(route_pattern)}"
    data = _fetch_json(api)

    if not data:
        console.print("No traces recorded yet.")
        return

    table = Table()
    table.add_column("Trace")
    table.add_column("Method")
    table.add_column("Path")
    table.add_column("Status")
    table.add_column("Duration", justify="right")

    for trace in data[:limit]:
        status = trace["status"]
        status_text = f"[red]{status}[/red]" if status == "error" else f"[green]{status}[/green]"
        duration = trace["duration_ms"]
        duration_text = "-" if duration is None else f"{round(duration)}ms"
        # escape(): trace["path"] is whatever the client actually
        # requested - a literal "[" in a query string or path segment
        # would otherwise be parsed as rich markup and silently vanish
        # from the output (confirmed - the exact bug caught below in
        # doctor()'s own uvicorn[standard] message, same root cause).
        table.add_row(
            trace["trace_id"][:8],
            trace["method"],
            escape(trace["path"]),
            status_text,
            duration_text,
        )

    console.print(table)
    if len(data) > limit:
        console.print(f"[dim]... and {len(data) - limit} more (--limit to see more)[/dim]")


@app.command()
def export(
    out: Path = typer.Option(  # noqa: B008 - idiomatic Typer, not a mutable default
        ..., "--out", help="File to write traces to, as JSON."
    ),
    url: str = typer.Option(DEFAULT_URL, help="Base URL the app is running at."),
    route_pattern: str | None = typer.Option(
        None, "--route-pattern", help='Only this endpoint, e.g. "/orders/{id}".'
    ),
) -> None:
    """Dump currently stored traces to a file.

    There's no persistence otherwise (see store.py's ring buffer) - once
    a trace ages out or the process restarts, it's gone. This is the only
    way to keep history past that.
    """
    api = _api_url(url, "traces")
    if route_pattern:
        api += f"?route_pattern={quote(route_pattern)}"
    data = _fetch_json(api)

    out.write_text(json.dumps(data, indent=2))
    console.print(f"Wrote {len(data)} trace(s) to {out}")


# ---- doctor: local environment checks, no running instance needed ------


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


@app.command()
def doctor() -> None:
    """Check your local environment for the gotchas RouteFlow users
    actually hit — not a server-side check, this doesn't need a running
    app.
    """
    table = Table(show_header=False)
    table.add_column("Check")
    table.add_column("Result")

    checks: list[tuple[str, bool | None, str]] = []

    py_ok = sys.version_info >= (3, 12)
    checks.append(
        (
            "Python version",
            py_ok,
            f"{sys.version_info.major}.{sys.version_info.minor} "
            f"({'ok' if py_ok else 'routeflow needs >=3.12'})",
        )
    )

    checks.append(("routeflow", True, __version__))

    starlette_ok = _has_module("starlette")
    checks.append(
        (
            "starlette",
            starlette_ok,
            "installed" if starlette_ok else "MISSING (routeflow can't run without it)",
        )
    )

    # The exact gotcha this project hit for real: uvicorn alone doesn't
    # include a WebSocket implementation, so the flow view's live updates
    # silently never connect - no error, just a "connecting..." indicator
    # that never resolves - unless websockets or wsproto is also present.
    ws_ok = _has_module("websockets") or _has_module("wsproto")
    checks.append(
        (
            "WebSocket support",
            ws_ok,
            "installed"
            if ws_ok
            else 'MISSING - live updates need `pip install "uvicorn[standard]"` '
            "or `pip install websockets`",
        )
    )

    uvicorn_present = _has_module("uvicorn")
    uvicorn_detail = (
        "installed"
        if uvicorn_present
        else "not installed (fine if you use a different ASGI server)"
    )
    checks.append(("uvicorn", None if not uvicorn_present else True, uvicorn_detail))

    enabled_value = os.environ.get("ROUTEFLOW_ENABLED")
    enabled_detail = (
        f"{enabled_value!r} in this shell"
        if enabled_value is not None
        else "unset (RouteFlow is on by default)"
    )
    checks.append(
        (
            "ROUTEFLOW_ENABLED",
            None,
            enabled_detail,
        )
    )

    any_failed = False
    for label, ok, detail in checks:
        if ok is True:
            mark = "[green]OK[/green]"
        elif ok is False:
            mark = "[red]FAIL[/red]"
            any_failed = True
        else:
            mark = "[yellow]INFO[/yellow]"
        # escape(): several detail strings above mention things like
        # uvicorn[standard] literally - unescaped, rich parses "[standard]"
        # as a markup tag and silently drops it from the output (confirmed
        # live: "uvicorn[standard]" rendered as just "uvicorn").
        table.add_row(f"{mark}  {label}", escape(detail))

    console.print(table)
    if any_failed:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
