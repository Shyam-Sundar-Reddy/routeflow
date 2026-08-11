from __future__ import annotations

import os
from typing import Protocol

from routeflow.live import LiveBroadcaster
from routeflow.middleware import RouteFlowMiddleware
from routeflow.server import build_server_app
from routeflow.store import TraceStore

# Deliberately unlikely to collide with a real app's own routes, and
# obviously "not part of your API" to anyone who spots it in a request
# log — same idea as Django's /__debug__/.
MOUNT_PATH = "/__routeflow__"

_ENV_VAR = "ROUTEFLOW_ENABLED"
_FALSY = {"0", "false", "no", "off"}


class _SupportsRouteFlow(Protocol):
    """What RouteFlow actually needs from "an app" — Starlette's and
    FastAPI's `add_middleware`/`mount` signatures. Structural typing here
    (rather than importing FastAPI/Starlette as a real dependency) keeps
    the library installable without pulling in a specific web framework.
    """

    def add_middleware(self, middleware_class: type, **options: object) -> None: ...
    def mount(self, path: str, app: object, name: str | None = None) -> None: ...


def RouteFlow(
    app: _SupportsRouteFlow, *, enabled: bool | None = None
) -> _SupportsRouteFlow:
    """Install RouteFlow on a FastAPI (or plain Starlette) app in one call:

        app = FastAPI()
        RouteFlow(app)

    On by default — this is a dev tool, and "add one line, it just
    works" is the whole point. But traces can include captured function
    arguments and full stack traces, so this must never stay on
    silently if the same code ships to production. The escape hatch:
    `ROUTEFLOW_ENABLED=0` (also accepts "false"/"no"/"off") in the
    environment disables it without touching code — set that in
    production and leave `RouteFlow(app)` in place safely. `enabled=`
    overrides the environment either way, for a caller that wants to
    decide in code instead (e.g. `enabled=settings.debug`).

    When disabled, this is a true no-op: no middleware installed, no
    route mounted, `app` handed back completely untouched.

    Wires up the request-tracing middleware, the `TraceStore` it writes
    to, and a `LiveBroadcaster` it notifies as each trace finishes, then
    mounts the small standalone server that reads from that store (and
    pushes over that broadcaster) at `/__routeflow__` — `app.mount`, not
    `include_router`, so RouteFlow's own routes get an isolated OpenAPI
    schema and never show up in the host app's own `/docs`.

    Returns `app` so this can be chained inline where that's convenient,
    e.g. `app = RouteFlow(FastAPI())`.
    """
    if enabled is None:
        env_value = os.environ.get(_ENV_VAR)
        enabled = env_value is None or env_value.strip().lower() not in _FALSY
    if not enabled:
        return app

    store = TraceStore()
    broadcaster = LiveBroadcaster()
    app.add_middleware(
        RouteFlowMiddleware,
        store=store,
        exclude_prefix=MOUNT_PATH,
        on_trace=broadcaster.broadcast_trace,
    )
    # Verified against a real FastAPI app, not just assumed from how
    # `mount` is described: the mounted sub-app genuinely works (its
    # routes respond) but is absent from `app.openapi()`'s generated
    # schema and from `/docs` — FastAPI's schema generation only walks
    # `APIRoute`s it owns directly, so a `Mount`ed sub-application (this
    # one's a plain Starlette app, see server.py) is invisible to it
    # without any extra effort here.
    app.mount(MOUNT_PATH, build_server_app(store, broadcaster))
    return app
