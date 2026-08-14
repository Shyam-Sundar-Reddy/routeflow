from __future__ import annotations

import os
from typing import Protocol

from starlette.staticfiles import StaticFiles

from routeflow.live import LiveBroadcaster
from routeflow.middleware import RouteFlowMiddleware
from routeflow.server import FRONTEND_DIR, build_server_app
from routeflow.store import DEFAULT_MAX_TRACES, TraceStore

# Deliberately unlikely to collide with a real app's own routes, and
# obviously "not part of your API" to anyone who spots it in a request
# log — same idea as Django's /__debug__/. The REST/WebSocket API lives
# here; the flow-view UI is a separate mount, see FLOW_UI_PATH below.
MOUNT_PATH = "/__routeflow__"

# The flow view itself sits at a short, bare path directly on the host
# app - matching FastAPI's own /docs, /redoc - rather than nested under
# MOUNT_PATH, so it's a URL worth remembering. Real trade-off, made
# deliberately: unlike MOUNT_PATH, this is a plausible name a host app
# could already be using for its own route, so it's a small, genuine
# collision risk - the same one FastAPI itself accepts with /docs (and
# lets you override via docs_url=).
FLOW_UI_PATH = "/flow"

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
    app: _SupportsRouteFlow,
    *,
    enabled: bool | None = None,
    max_traces: int = DEFAULT_MAX_TRACES,
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

    Every request is traced — there's no sampling (trace 1 in N, or X%)
    yet, only this: `max_traces` caps how many *finished* traces stay in
    memory at once (default 500). It's a ring buffer, not a hard cutoff -
    once full, the oldest trace is dropped as each new one lands, so the
    flow view always shows the most recent activity rather than erroring
    out or silently growing without bound on a long-running dev server.

    Wires up the request-tracing middleware, the `TraceStore` it writes
    to, and a `LiveBroadcaster` it notifies as each trace finishes, then
    mounts two things — `app.mount`, not `include_router`, so both get
    an isolated OpenAPI schema and never show up in the host app's own
    `/docs`:

    - the REST/WebSocket API at `/__routeflow__` (`MOUNT_PATH`)
    - the flow-view UI at `/flow` (`FLOW_UI_PATH`), a short URL worth
      remembering, matching FastAPI's own `/docs`/`/redoc`

    Returns `app` so this can be chained inline where that's convenient,
    e.g. `app = RouteFlow(FastAPI())`.
    """
    if enabled is None:
        env_value = os.environ.get(_ENV_VAR)
        enabled = env_value is None or env_value.strip().lower() not in _FALSY
    if not enabled:
        return app

    store = TraceStore(maxlen=max_traces)
    broadcaster = LiveBroadcaster()
    app.add_middleware(
        RouteFlowMiddleware,
        store=store,
        exclude_prefixes=(MOUNT_PATH, FLOW_UI_PATH),
        on_trace=broadcaster.broadcast_trace,
    )
    # Verified against a real FastAPI app, not just assumed from how
    # `mount` is described: both mounted sub-apps genuinely work (their
    # routes respond) but are absent from `app.openapi()`'s generated
    # schema and from `/docs` — FastAPI's schema generation only walks
    # `APIRoute`s it owns directly, so a `Mount`ed sub-application (this
    # one's a plain Starlette app, see server.py) is invisible to it
    # without any extra effort here.
    app.mount(MOUNT_PATH, build_server_app(store, broadcaster))
    # html=True serves index.html for /flow and /flow/ alike.
    app.mount(FLOW_UI_PATH, StaticFiles(directory=FRONTEND_DIR, html=True))
    return app
