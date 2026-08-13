from __future__ import annotations

from collections.abc import Callable

from starlette.applications import Starlette

from routeflow.tracing import Trace


def test_trace_opens_and_closes_around_a_request(
    app_and_traces: tuple[Starlette, list[Trace]],
    do_request: Callable[..., object],
) -> None:
    app, traces = app_and_traces

    response = do_request(app, "GET", "/orders/42")

    assert response.status_code == 200
    (trace,) = traces
    assert trace.method == "GET"
    assert trace.path == "/orders/42"
    assert trace.status == "ok"
    assert trace.duration is not None
    assert trace.duration >= 0


def test_a_tracked_call_inside_the_handler_lands_on_the_same_trace(
    app_and_traces: tuple[Starlette, list[Trace]],
    do_request: Callable[..., object],
) -> None:
    """Confirms the middleware's trace and the decorator's spans are
    actually the same trace, not two independent things that happen to
    both exist during the request.
    """
    app, traces = app_and_traces

    do_request(app, "GET", "/orders/42")

    (trace,) = traces
    (span,) = trace.spans.values()
    assert span.name == "validate_order"
    assert span.status == "ok"
