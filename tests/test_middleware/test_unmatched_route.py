from __future__ import annotations

from collections.abc import Callable

import pytest
from starlette.applications import Starlette

from routeflow.tracing import Trace
from routeflow.tracing.context import set_current_trace as real_set_current_trace


def test_unmatched_route_still_produces_a_trace(
    app_and_traces: tuple[Starlette, list[Trace]],
    do_request: Callable[..., object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 never runs a handler, so `app_and_traces`'s usual capture
    trick (appending from inside the route) can't observe it — spy on
    `set_current_trace` itself instead, at the exact point the
    middleware opens the trace, regardless of whether anything downstream
    ever runs.
    """
    app, _ = app_and_traces
    captured: list[Trace] = []

    def spy(trace: Trace | None):
        if trace is not None:
            captured.append(trace)
        return real_set_current_trace(trace)

    monkeypatch.setattr("routeflow.middleware.set_current_trace", spy)

    response = do_request(app, "GET", "/nope", raise_app_exceptions=False)

    assert response.status_code == 404
    (trace,) = captured
    assert trace.path == "/nope"
    assert trace.route_pattern is None
    # A 404 is a normal, handled response - not a RouteFlow-level error.
    assert trace.status == "ok"
    assert trace.duration is not None
