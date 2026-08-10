from __future__ import annotations

from collections.abc import Callable

import pytest

from routeflow.tracing import Trace


def _make_trace(
    method: str = "GET",
    path: str = "/orders/1",
    route_pattern: str | None = "/orders/{id}",
    status: str = "ok",
    duration_ms: float | None = 10.0,
) -> Trace:
    """A finished-looking Trace without going through the middleware —
    store tests care about storage behavior, not how a trace gets built.
    """
    trace = Trace(method=method, path=path, route_pattern=route_pattern)
    trace.status = status
    if duration_ms is not None:
        trace.ended_at = trace.started_at + duration_ms / 1000
    return trace


@pytest.fixture
def make_trace() -> Callable[..., Trace]:
    """Exposed as a fixture (not a plain import) so test modules don't
    need `tests` to be an importable package — same convention as
    `do_request` in tests/test_middleware/conftest.py.
    """
    return _make_trace
