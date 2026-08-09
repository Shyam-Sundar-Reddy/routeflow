from __future__ import annotations

from typing import Protocol

from routeflow.middleware import RouteFlowMiddleware


class _SupportsAddMiddleware(Protocol):
    """What RouteFlow actually needs from "an app" — Starlette's and
    FastAPI's `add_middleware` signature. Structural typing here (rather
    than importing FastAPI/Starlette as a real dependency) keeps the
    library installable without pulling in a specific web framework.
    """

    def add_middleware(self, middleware_class: type, **options: object) -> None: ...


def RouteFlow(app: _SupportsAddMiddleware) -> _SupportsAddMiddleware:
    """Install RouteFlow on a FastAPI (or plain Starlette) app in one call:

        app = FastAPI()
        RouteFlow(app)

    For now this only wires up the request-tracing middleware. Once the
    local server exists (Phase 5) this same call will also mount it —
    the goal is that installing RouteFlow never needs more than this one
    line, regardless of how much lands behind it later.

    Returns `app` so this can be chained inline where that's convenient,
    e.g. `app = RouteFlow(FastAPI())`.
    """
    app.add_middleware(RouteFlowMiddleware)
    return app
