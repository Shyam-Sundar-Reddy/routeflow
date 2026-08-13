# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - Unreleased

First release. Everything needed to trace a FastAPI request and see it as
a live node graph, end to end.

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
