from __future__ import annotations

from starlette.websockets import WebSocket

from routeflow.tracing import Trace


class LiveBroadcaster:
    """Tracks connected flow-view WebSocket clients and pushes each
    finished trace to all of them as it lands.

    Nothing stops a developer from having the flow view open in more than
    one tab — hence a *set* of clients, not a single connection — and
    each finished trace goes to all of them, not just the first.
    """

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    def add(self, websocket: WebSocket) -> None:
        self._clients.add(websocket)

    def remove(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def broadcast_trace(self, trace: Trace) -> None:
        """Push one finished trace to every currently connected client.

        A stale connection (tab closed, network dropped) can make
        `send_json` raise before `_live`'s own receive loop has noticed
        the disconnect — that must not stop the remaining clients from
        getting this trace, so each send is isolated and a client that
        fails is dropped from the registry immediately rather than
        waiting for its own disconnect handling to catch up.
        """
        payload = trace.to_dict()
        for websocket in list(self._clients):
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001 - one dead socket must not skip the rest
                self._clients.discard(websocket)
