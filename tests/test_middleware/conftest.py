from __future__ import annotations

import asyncio
from collections.abc import Iterator

import httpx
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from routeflow import RouteFlow
from routeflow.tracing import Trace, track
from routeflow.tracing.context import get_current_trace


@track
async def validate_order(order_id: str) -> None:
    """A tracked call inside the route, so tests can check that spans
    opened during the request end up on the same trace the middleware
    closes — not just that the trace itself opens and closes.
    """
    if order_id == "boom":
        raise ValueError(f"invalid order {order_id!r}")


@pytest.fixture
def app_and_traces() -> Iterator[tuple[Starlette, list[Trace]]]:
    """A small real Starlette app, wired up with RouteFlow exactly the
    way a user would, plus a list every handler appends its
    `get_current_trace()` to — the only place these tests can observe a
    trace, since there's no store yet (Phase 4).

    A fresh app and list per test — nothing here is shared/module-level,
    so tests can't leak trace state into each other.
    """
    traces: list[Trace] = []

    async def get_order(request):
        order_id = request.path_params["id"]
        await validate_order(order_id)
        traces.append(get_current_trace())
        return JSONResponse({"id": order_id})

    async def crash(request):
        traces.append(get_current_trace())
        raise RuntimeError("unhandled boom")

    app = Starlette(
        routes=[
            Route("/orders/{id}", get_order),
            Route("/crash", crash),
        ]
    )
    RouteFlow(app)
    yield app, traces


def _do_request(
    app: Starlette, method: str, path: str, *, raise_app_exceptions: bool = True
) -> httpx.Response:
    """Run one request through `app` via a real ASGI transport, returning
    the response. Wraps `asyncio.run()` so test bodies stay plain `def`
    functions — consistent with the rest of the suite, no pytest-asyncio
    dependency needed.

    `raise_app_exceptions=False` mirrors what a real ASGI server does:
    an unhandled exception becomes a 500 response instead of propagating
    to the caller — use that when a test wants to see the response, and
    the default (True) when a test wants to see the exception itself.
    """

    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=app, raise_app_exceptions=raise_app_exceptions
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.request(method, path)

    return asyncio.run(call())


@pytest.fixture
def do_request():
    """Exposed as a fixture (not a plain import) so test modules don't
    need `tests` to be an importable package — pytest wires this up via
    normal fixture discovery instead.
    """
    return _do_request
