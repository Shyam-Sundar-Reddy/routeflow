from __future__ import annotations

import json
from unittest import mock

import pytest
from typer.testing import CliRunner

from routeflow.cli import app, open_flow_view

runner = CliRunner()


class _FakeResponse:
    """A minimal stand-in for what `urlopen(...)` returns, used as its
    own context manager - avoids needing a real running server (uvicorn
    isn't even a project dependency) just to test the CLI's own URL
    construction, error handling, and output formatting.
    """

    def __init__(self, payload: object) -> None:
        self._data = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> bool:
        return False


SAMPLE_TRACES = [
    {
        "trace_id": "82c482b70e5949fa8af24927275ac1dc",
        "method": "POST",
        "path": "/checkout",
        "route_pattern": "/checkout",
        "status": "error",
        "duration_ms": 168.9,
        "spans": [{"name": "charge"}],
    },
    {
        "trace_id": "f986cf76aaaa4444bbbb222233334444",
        "method": "GET",
        "path": "/health",
        "route_pattern": "/health",
        "status": "ok",
        "duration_ms": 10.2,
        "spans": [],
    },
]


def test_traces_renders_a_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _FakeResponse(SAMPLE_TRACES)
    )

    result = runner.invoke(app, ["traces", "--url", "http://127.0.0.1:8400"])

    assert result.exit_code == 0
    assert "82c482b7" in result.stdout
    assert "/checkout" in result.stdout
    assert "/health" in result.stdout


def test_traces_with_no_traces_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _FakeResponse([]))

    result = runner.invoke(app, ["traces", "--url", "http://127.0.0.1:8400"])

    assert result.exit_code == 0
    assert "No traces recorded yet" in result.stdout


def test_traces_escapes_rich_markup_in_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: a literal "[" in trace["path"] (a query string, a
    path segment) used to be parsed as rich markup and silently vanish
    from the output - confirmed live before this test existed.
    """
    traced = [{**SAMPLE_TRACES[0], "path": "/items[1]"}]
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _FakeResponse(traced)
    )

    result = runner.invoke(app, ["traces", "--url", "http://127.0.0.1:8400"])

    assert "/items[1]" in result.stdout


def test_traces_unreachable_server_gives_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    def _raise(*args: object, **kwargs: object) -> None:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", _raise)

    result = runner.invoke(app, ["traces", "--url", "http://127.0.0.1:9999"])

    assert result.exit_code == 1
    assert "Couldn't reach" in result.stdout


def test_traces_http_error_gives_a_different_message_than_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTPError is a subclass of URLError - regression test for a real
    ordering bug: catching URLError first meant a genuine 404 was
    reported as "couldn't reach", the wrong, more alarming message for
    "reached it fine, got an error status back".
    """
    import urllib.error

    def _raise(*args: object, **kwargs: object) -> None:
        raise urllib.error.HTTPError("http://x", 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _raise)

    result = runner.invoke(app, ["traces", "--url", "http://127.0.0.1:8400"])

    assert result.exit_code == 1
    assert "HTTP 404" in result.stdout
    assert "Couldn't reach" not in result.stdout


def test_export_writes_full_trace_data_to_a_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _FakeResponse(SAMPLE_TRACES)
    )
    out_file = tmp_path / "traces.json"  # type: ignore[operator]

    result = runner.invoke(
        app, ["export", "--url", "http://127.0.0.1:8400", "--out", str(out_file)]
    )

    assert result.exit_code == 0
    written = json.loads(out_file.read_text())
    assert len(written) == 2
    assert written[0]["spans"] == [{"name": "charge"}]  # full data, not a summary


def test_open_opens_the_flow_view_url() -> None:
    with mock.patch("webbrowser.open") as mock_open:
        open_flow_view(url="http://127.0.0.1:8400")

    mock_open.assert_called_once_with("http://127.0.0.1:8400/flow/")


def test_doctor_reports_missing_websocket_support(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("routeflow.cli._has_module", lambda name: False)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "FAIL" in result.stdout
    # Regression test: "uvicorn[standard]" used to render as "uvicorn" -
    # rich parsed the literal "[standard]" as a markup tag and dropped it.
    assert "uvicorn[standard]" in result.stdout


def test_doctor_passes_when_everything_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("routeflow.cli._has_module", lambda name: True)

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "FAIL" not in result.stdout
