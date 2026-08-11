from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from starlette.routing import Mount

from routeflow.integration import MOUNT_PATH


def test_routeflow_routes_are_absent_from_the_openapi_schema(app: FastAPI) -> None:
    schema = app.openapi()

    paths = list(schema["paths"])
    assert paths == ["/orders/{id}", "/crash"]
    assert not any(MOUNT_PATH in path for path in paths)


def test_docs_still_renders(
    app: FastAPI, do_request: Callable[..., object]
) -> None:
    response = do_request(app, "GET", "/docs")

    assert response.status_code == 200


def test_mount_is_genuinely_present_despite_being_invisible_to_the_schema(
    app: FastAPI,
) -> None:
    """The isolation from the two tests above isn't because the mount
    silently failed — confirms the `Mount` is really on `app.routes`,
    and its own routes really respond (covered by test_rest_endpoints.py),
    it's just excluded from what `app.openapi()` walks.
    """
    mounts = [route for route in app.routes if isinstance(route, Mount)]
    assert any(mount.path == MOUNT_PATH for mount in mounts)
