from __future__ import annotations

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

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

    Skeleton only for now — a pure passthrough. Trace open/close, route
    pattern capture, and error handling land in the following commits.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self.app(scope, receive, send)
