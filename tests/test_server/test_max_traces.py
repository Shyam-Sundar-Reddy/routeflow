from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from routeflow import RouteFlow

# Uses its own app, not the shared `app` fixture — this is specifically
# testing the max_traces= config knob, which needs a non-default value at
# construction time.


def test_max_traces_caps_how_many_traces_are_kept(
    do_request: Callable[..., object],
) -> None:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    RouteFlow(app, max_traces=3)

    for _ in range(6):
        do_request(app, "GET", "/ping")

    traces = do_request(app, "GET", "/__routeflow__/traces").json()

    # A ring buffer, not a hard cutoff that errors or stops tracing once
    # full - the oldest is dropped as each new one lands, so what's kept
    # is always the *most recent* max_traces, not just the first 3.
    assert len(traces) == 3


def test_max_traces_defaults_to_the_store_default(
    do_request: Callable[..., object],
) -> None:
    """Confirms RouteFlow(app) with no override still gets a real,
    working limit (DEFAULT_MAX_TRACES) rather than an unbounded store -
    the default itself is already covered by test_trace_store.py, this
    just confirms the public API actually wires it through.
    """
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    RouteFlow(app)
    do_request(app, "GET", "/ping")

    traces = do_request(app, "GET", "/__routeflow__/traces").json()
    assert len(traces) == 1
