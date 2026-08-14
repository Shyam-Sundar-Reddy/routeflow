from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from routeflow.live import LiveBroadcaster
from routeflow.store import TraceStore

# The flow view's HTML/CSS/JS, shipped inside the package itself — no
# separate frontend build/install step for a dev-only tool that's meant
# to be "add one line, it just works."
FRONTEND_DIR = Path(__file__).parent / "frontend"


def _list_traces(store: TraceStore):
    async def handler(request: Request) -> JSONResponse:
        route_pattern = request.query_params.get("route_pattern")
        traces = store.list_traces(route_pattern=route_pattern)
        return JSONResponse([trace.to_dict() for trace in traces])

    return handler


def _get_trace(store: TraceStore):
    async def handler(request: Request) -> JSONResponse:
        trace_id = request.path_params["trace_id"]
        trace = store.get(trace_id)
        if trace is None:
            return JSONResponse({"detail": "trace not found"}, status_code=404)
        return JSONResponse(trace.to_dict())

    return handler


def _list_endpoints(store: TraceStore):
    async def handler(request: Request) -> JSONResponse:
        stats = store.endpoint_stats()
        return JSONResponse([s.to_dict() for s in stats])

    return handler


def _live(broadcaster: LiveBroadcaster):
    async def handler(websocket: WebSocket) -> None:
        """Held open for as long as a flow-view tab is watching, and
        registered with `broadcaster` so a finished trace elsewhere in
        the app (see `RouteFlowMiddleware`'s `on_trace` hook) reaches it.
        """
        await websocket.accept()
        broadcaster.add(websocket)
        try:
            while True:
                # Nothing meaningful expected from the client — this is
                # purely what keeps the coroutine (and thus the
                # connection) alive between server-initiated pushes.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass  # a closed tab is a normal event here, not an error
        finally:
            # Runs on a clean disconnect and on any other exit alike, so
            # a client can never linger in the registry after its
            # connection is actually gone.
            broadcaster.remove(websocket)

    return handler


def build_server_app(store: TraceStore, broadcaster: LiveBroadcaster) -> Starlette:
    """The small standalone app RouteFlow mounts onto the user's own
    FastAPI/Starlette app — serves stored traces over REST and live
    updates over WebSocket.

    Deliberately a separate Starlette app rather than routes merged into
    the host's own router: mounting it (`app.mount(...)`) gives it an
    isolated OpenAPI schema for free — the host's `/docs` never learns
    these routes exist. Kept under the collision-safe `/__routeflow__`
    prefix (see integration.py's MOUNT_PATH) - the flow-view UI itself
    is a *separate* mount, at bare `/flow`, so it isn't built here (see
    integration.py).
    """
    return Starlette(
        routes=[
            Route("/traces", _list_traces(store)),
            Route("/traces/{trace_id}", _get_trace(store)),
            Route("/endpoints", _list_endpoints(store)),
            WebSocketRoute("/live", _live(broadcaster)),
        ]
    )
