from __future__ import annotations

from collections.abc import Callable

from starlette.applications import Starlette

from routeflow.tracing import Trace


def test_parameterized_paths_group_under_one_pattern(
    app_and_traces: tuple[Starlette, list[Trace]],
    do_request: Callable[..., object],
) -> None:
    app, traces = app_and_traces

    do_request(app, "GET", "/orders/42")
    do_request(app, "GET", "/orders/99")

    assert len(traces) == 2
    assert traces[0].path == "/orders/42"
    assert traces[1].path == "/orders/99"
    # Different literal paths, same pattern — this is what lets the flow
    # view bucket both under one endpoint instead of one per order id.
    assert traces[0].route_pattern == traces[1].route_pattern == "/orders/{id}"
