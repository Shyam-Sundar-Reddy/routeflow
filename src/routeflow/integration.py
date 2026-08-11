from __future__ import annotations

from typing import Protocol

from routeflow.middleware import RouteFlowMiddleware
from routeflow.server import build_server_app
from routeflow.store import TraceStore

# Deliberately unlikely to collide with a real app's own routes, and
# obviously "not part of your API" to anyone who spots it in a request
# log — same idea as Django's /__debug__/.
MOUNT_PATH = "/__routeflow__"


class _SupportsRouteFlow(Protocol):
    """What RouteFlow actually needs from "an app" — Starlette's and
    FastAPI's `add_middleware`/`mount` signatures. Structural typing here
    (rather than importing FastAPI/Starlette as a real dependency) keeps
    the library installable without pulling in a specific web framework.
    """

    def add_middleware(self, middleware_class: type, **options: object) -> None: ...
    def mount(self, path: str, app: object, name: str | None = None) -> None: ...


def RouteFlow(app: _SupportsRouteFlow) -> _SupportsRouteFlow:
    """Install RouteFlow on a FastAPI (or plain Starlette) app in one call:

        app = FastAPI()
        RouteFlow(app)

    Wires up the request-tracing middleware and the same `TraceStore` it
    writes to, then mounts the small standalone server that reads from
    that store at `/__routeflow__` — `app.mount`, not `include_router`,
    so RouteFlow's own routes get an isolated OpenAPI schema and never
    show up in the host app's own `/docs`.

    Returns `app` so this can be chained inline where that's convenient,
    e.g. `app = RouteFlow(FastAPI())`.
    """
    store = TraceStore()
    app.add_middleware(RouteFlowMiddleware, store=store, exclude_prefix=MOUNT_PATH)
    app.mount(MOUNT_PATH, build_server_app(store))
    return app
