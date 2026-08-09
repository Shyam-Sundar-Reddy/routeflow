from __future__ import annotations

from collections.abc import Callable

import pytest
from starlette.applications import Starlette

from routeflow.tracing import Trace


def test_a_500_is_still_returned_to_the_client(
    app_and_traces: tuple[Starlette, list[Trace]],
    do_request: Callable[..., object],
) -> None:
    """RouteFlow must never change what the client sees — an unhandled
    exception still becomes a real 500, same as with no middleware at
    all. `raise_app_exceptions=False` here mirrors what a real ASGI
    server does with an unhandled exception.
    """
    app, traces = app_and_traces

    response = do_request(app, "GET", "/crash", raise_app_exceptions=False)

    assert response.status_code == 500
    (trace,) = traces
    assert trace.status == "error"
    assert trace.error is not None
    assert trace.error.type == "RuntimeError"
    assert trace.duration is not None


def test_the_exception_still_propagates_unchanged(
    app_and_traces: tuple[Starlette, list[Trace]],
    do_request: Callable[..., object],
) -> None:
    """The complementary case to the one above: with the transport
    configured to surface app exceptions (the default), the same
    RuntimeError must reach the caller — RouteFlow only observes, it
    never swallows a failure into a quiet 500 the caller can't see.
    """
    app, traces = app_and_traces

    with pytest.raises(RuntimeError, match="unhandled boom"):
        do_request(app, "GET", "/crash")

    (trace,) = traces
    assert trace.status == "error"
    assert trace.error.message == "unhandled boom"
