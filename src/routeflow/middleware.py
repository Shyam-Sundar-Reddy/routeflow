from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from routeflow.tracing import Trace
from routeflow.tracing.context import reset_current_trace, set_current_trace

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class RouteFlowMiddleware:
    """The request boundary: opens a trace when a request comes in and
    closes it when the response is done, no matter what happens in
    between.

    Deliberately pure ASGI rather than Starlette's `BaseHTTPMiddleware` —
    that convenience class buffers responses in ways that break streaming
    responses and can interfere with `BackgroundTasks` (see
    ARCHITECTURE.md). Wrapping `scope`/`receive`/`send` directly avoids
    that, at the cost of a bit more boilerplate here.

    Route pattern capture, trace closing/duration, and error handling land
    in the following commits — this only opens the trace so far. The
    `scope["type"] != "http"` check is a minimal stand-in for now: ASGI
    also delivers "lifespan" (startup/shutdown) and "websocket" scopes,
    neither of which has a `method`/`path` to build a trace from. Explicit
    handling and tests for that land in its own commit.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        trace = Trace(method=scope["method"], path=scope["path"])
        token = set_current_trace(trace)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_trace(token)
