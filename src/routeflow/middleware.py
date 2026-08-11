from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from routeflow.store import TraceStore
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

    ASGI also delivers "lifespan" (startup/shutdown) and "websocket"
    scopes to an app — neither has a `method` the way an HTTP scope does
    (lifespan has no `path` either), so both are passed straight through
    untouched rather than treated as a traceable request.
    """

    def __init__(
        self,
        app: ASGIApp,
        store: TraceStore | None = None,
        exclude_prefix: str | None = None,
        on_trace: Callable[[Trace], Awaitable[None]] | None = None,
    ) -> None:
        self.app = app
        # Deliberately just "an async callable that takes a Trace" rather
        # than importing LiveBroadcaster/WebSocket here — the middleware
        # has no business knowing traces get pushed over a websocket at
        # all, only that something may want to know when one finishes.
        # `RouteFlow(app)` passes `LiveBroadcaster.broadcast_trace`.
        self.on_trace = on_trace
        # Defaults to a private store so the middleware is still usable
        # on its own (as most of the existing test suite does) without
        # every caller needing to wire one up. RouteFlow(app) always
        # passes the same store it mounts the server onto, so traces
        # recorded here are actually reachable from outside the process.
        self.store = store if store is not None else TraceStore()
        # This middleware wraps the *entire* app, including whatever
        # RouteFlow itself mounts onto it (see integration.py) — without
        # this, a browser polling GET /__routeflow__/traces would trace
        # itself, piling up as a bogus "unmatched" endpoint (confirmed:
        # this was actually happening before `exclude_prefix` existed).
        # `RouteFlow(app)` passes its own mount path here; direct use of
        # the middleware without mounting anything leaves it unset.
        self.exclude_prefix = exclude_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or (
            self.exclude_prefix is not None
            and scope["path"].startswith(self.exclude_prefix)
        ):
            await self.app(scope, receive, send)
            return

        trace = Trace(method=scope["method"], path=scope["path"])
        token = set_current_trace(trace)
        try:
            await self.app(scope, receive, send)
        except BaseException as exc:
            # Only reached for exceptions that escape *everything* below
            # us, including FastAPI's own exception handlers (an
            # HTTPException or a registered handler resolves to a normal
            # response and never gets here — this is genuinely unhandled
            # failure). Record it on the trace itself, since it may not
            # have happened inside any @track-ed span at all, then
            # re-raise unchanged: RouteFlow only observes.
            trace.record_error(exc)
            raise
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
            self.store.add(trace)
            if self.on_trace is not None:
                await self.on_trace(trace)
