from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from routeflow.middleware import RouteFlowMiddleware
from routeflow.tracing.context import get_current_trace

# ASGI events fed/collected by hand here, no Starlette app needed — this
# is testing that RouteFlowMiddleware leaves non-"http" scopes alone,
# which is a property of the middleware itself, not of any framework
# built on top of it.


def _queue_receive(events: list[dict]) -> Callable[[], Awaitable[dict]]:
    events_iter = iter(events)

    async def receive() -> dict:
        return next(events_iter)

    return receive


def test_lifespan_scope_passes_through_untouched() -> None:
    """A lifespan scope has no method/path — RouteFlowMiddleware must
    never try to build a Trace from one, just hand it straight to the
    wrapped app.
    """
    sent: list[dict] = []

    async def inner_app(scope: dict, receive, send) -> None:
        assert scope["type"] == "lifespan"
        message = await receive()
        assert message["type"] == "lifespan.startup"
        await send({"type": "lifespan.startup.complete"})

    middleware = RouteFlowMiddleware(inner_app)
    receive = _queue_receive([{"type": "lifespan.startup"}])

    async def send(message: dict) -> None:
        sent.append(message)

    asyncio.run(middleware({"type": "lifespan"}, receive, send))

    assert sent == [{"type": "lifespan.startup.complete"}]
    assert get_current_trace() is None  # nothing left behind


def test_websocket_scope_passes_through_untouched() -> None:
    """A websocket scope has a path but no method — must also be left
    alone rather than crashing on a missing scope["method"].
    """
    sent: list[dict] = []

    async def inner_app(scope: dict, receive, send) -> None:
        assert scope["type"] == "websocket"
        await send({"type": "websocket.accept"})

    middleware = RouteFlowMiddleware(inner_app)
    receive = _queue_receive([{"type": "websocket.connect"}])

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {"type": "websocket", "path": "/live"}
    asyncio.run(middleware(scope, receive, send))

    assert sent == [{"type": "websocket.accept"}]
    assert get_current_trace() is None
