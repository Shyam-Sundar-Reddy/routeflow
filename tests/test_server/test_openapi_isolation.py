from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from starlette.routing import Mount

from routeflow.integration import FLOW_UI_PATH, MOUNT_PATH


def test_routeflow_routes_are_absent_from_the_openapi_schema(app: FastAPI) -> None:
    schema = app.openapi()

    paths = list(schema["paths"])
    assert paths == ["/orders/{id}", "/crash"]
    assert not any(MOUNT_PATH in path for path in paths)
    assert not any(FLOW_UI_PATH in path for path in paths)


def test_docs_still_renders(
    app: FastAPI, do_request: Callable[..., object]
) -> None:
    response = do_request(app, "GET", "/docs")

    assert response.status_code == 200


def test_mounts_are_genuinely_present_despite_being_invisible_to_the_schema(
    app: FastAPI,
) -> None:
    """The isolation from the two tests above isn't because either mount
    silently failed — confirms both `Mount`s are really on `app.routes`
    (the REST/WS API and the separately-mounted /flow UI), and their own
    routes really respond (covered by test_rest_endpoints.py and
    test_flow_view_smoke.py), it's just excluded from what
    `app.openapi()` walks.
    """
    mounts = [route for route in app.routes if isinstance(route, Mount)]
    mount_paths = {mount.path for mount in mounts}
    assert MOUNT_PATH in mount_paths
    assert FLOW_UI_PATH in mount_paths
