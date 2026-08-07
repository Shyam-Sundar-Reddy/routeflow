from __future__ import annotations

from collections.abc import Iterator

import pytest

from routeflow.tracing import Trace
from routeflow.tracing.context import reset_current_trace, set_current_trace


@pytest.fixture
def trace() -> Iterator[Trace]:
    """An active trace, set as current for the test and reset after.

    Most tracing APIs (open_span, span_scope, ...) require an active trace
    to attach to — this fixture gives tests one without each having to
    wire up the context plumbing by hand, and guarantees it's cleaned up
    even if the test fails, so state can't leak into the next test.
    """
    t = Trace(method="POST", path="/orders")
    token = set_current_trace(t)
    yield t
    reset_current_trace(token)
