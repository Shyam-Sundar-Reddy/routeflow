# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - Unreleased

### Added

- **`RouteFlow(app, max_traces=...)`** — configure how many finished
  traces stay in the in-memory ring buffer (default 500, unchanged).
- Flow view UI moved from `/__routeflow__/flow` to bare **`/flow`**,
  directly on the host app — matching FastAPI's own `/docs`/`/redoc`,
  a real trade-off made deliberately (see `integration.py`'s
  `FLOW_UI_PATH`). The REST/WebSocket API stays under the
  collision-safe `/__routeflow__` prefix, unchanged.
- Node graph: hover tooltips for truncated names, a depth badge per
  node, `+Xms` gap-time labels on every edge, click-to-highlight the
  full ancestor path back to root (dims everything unrelated), a close
  button on the detail panel, fit-to-width auto-scaling so wide fan-outs
  (e.g. `asyncio.gather` branches) no longer sit off-canvas with no
  scroll hint, and a legend strip explaining the above.
- `examples/production_demo.py` — a layered async example
  (service/repository/gateway/client), concurrent `asyncio.gather`
  fan-out, argument redaction, a deterministic and a flaky failure path.

### Fixed

- **Node graph layout** — children were positioned by flat append order
  within a depth row, not under their actual parent; a wide fan-out
  could jog an edge sideways by hundreds of pixels. Now a proper
  bottom-up tree layout (verified against a real trace: worst case went
  from 970px to a clean, non-overlapping fan-out).
- **Timeline strip row overlap** — two spans at the same depth but
  running concurrently (any `asyncio.gather` pair) shared one row and
  their bars visually overlapped, misrepresenting "ran together" as
  "one longer call." Now packed per-depth like a calendar view, so
  concurrent spans get their own row.

## [0.2.0] - Released

First real release. Everything needed to trace a FastAPI request and see
it as a live node graph, end to end.

> **Note:** `0.1.0` exists on PyPI but is a stale artifact of the initial
> project scaffold, published before any of the functionality below was
> built — PyPI never allows reusing a version number once published, so
> this release starts at `0.2.0` instead. Don't install `0.1.0`.

### Added

- **Tracing core** — `Span`/`Trace` data model, `ContextVar`-based context
  propagation correct under concurrent async requests, JSON serialization.
- **`@track` decorator** — instruments both sync and async functions,
  nests spans automatically via call order, captures arguments with a
  redaction hook, records exceptions without altering control flow.
- **`RouteFlowMiddleware`** — pure-ASGI request boundary; opens/closes a
  trace per request, captures the matched route pattern, records unhandled
  exceptions, excludes RouteFlow's own routes from self-tracing.
- **`TraceStore`** — thread-safe, bounded in-memory ring buffer with
  per-endpoint aggregate stats (request count, error rate, p95 latency).
- **Local server** — REST endpoints (`GET /traces`, `GET /traces/{id}`,
  `GET /endpoints`) and a `WS /live` feed, mounted with an isolated OpenAPI
  schema so it never appears in the host app's own `/docs`.
- **Flow view** — a node-graph UI (vanilla HTML/CSS/JS, no build step)
  showing call order, timing, logs, and errors for any traced request,
  updating live via WebSocket, with light/dark theming and a Docs/Flow tab
  bar next to Swagger.
- **`RouteFlow(app)`** — the one-line install. On by default; disable via
  `ROUTEFLOW_ENABLED=0` or `enabled=False` without touching other code.
- **CLI** — `routeflow --version`, `routeflow about`.

### Known limitations

- Generator/async-generator functions decorated with `@track` don't get
  accurate timing yet (warns at decoration time rather than failing).
- Context doesn't propagate across `asyncio.create_task()` /
  `BackgroundTasks` — a fire-and-forget task's own `@track`ed calls won't
  automatically attribute back to the request that started it.
- In-memory only, dev-focused — no persistence across restarts, and it's
  meant to run locally, not as a production observability backend.
