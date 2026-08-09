from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from routeflow.tracing import Trace
from routeflow.tracing.context import reset_current_trace, set_current_trace

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _route_pattern(scope: Scope) -> str | None:
    """The route pattern the request matched, e.g. `/orders/{id}` — not
    the literal path (`/orders/123`), so traces group by endpoint instead
    of scattering one bucket per id.

    Starlette's router doesn't hand back the matched `Route` object
    directly on `scope` — it writes `scope["endpoint"]` (the handler) and
    `scope["router"]` (the `Router` instance) while handling the request,
    *before* the endpoint runs. So by the time our `await self.app(...)`
    returns (or raises), both are already there if a route matched, and
    the route itself is recovered by searching the router for the route
    whose `.endpoint` is that handler. `None` if nothing matched (a 404)
    or the app underneath isn't Starlette/FastAPI-based.

    (Checked against the installed Starlette version directly rather than
    assumed — `scope["route"]`, which older docs/examples reference, does
    not exist here.)
    """
    endpoint = scope.get("endpoint")
    router = scope.get("router")
    if endpoint is None or router is None:
        return None
    for route in getattr(router, "routes", []):
        if getattr(route, "endpoint", None) is endpoint:
            return getattr(route, "path", None)
    return None


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
            # Read from `finally`, not just the success path — routing
            # happens before the endpoint runs, so the pattern is known
            # even when the endpoint itself raised.
            trace.route_pattern = _route_pattern(scope)
            # Closes the trace: records ended_at (so trace.duration is no
            # longer None) and derives overall status - "error" if any
            # span errored, "ok" otherwise. Must also run on the
            # exception path, same reasoning as the route pattern above:
            # a failed request still has a real duration worth recording.
            trace.finish()
            reset_current_trace(token)
            # No storage yet (Phase 4) - the finished trace is only
            # reachable here for now, via `trace` itself.
