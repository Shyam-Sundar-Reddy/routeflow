# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.2] - Unreleased

### Fixed

- **The logo didn't render on PyPI.** The README's `<picture>` logo used
  paths relative to the repo (`docs/logo...svg`), which only resolve on
  GitHub — PyPI has no way to fetch a path relative to its own domain.
  Switched to absolute `raw.githubusercontent.com` URLs, verified to
  actually resolve (200) before publishing. Also confirmed directly from
  `readme_renderer`'s source: PyPI's Markdown sanitizer allows `<picture>`
  but strips `<source>`, so the dark-mode variant won't switch on PyPI
  specifically — it degrades to the light logo there, not to nothing.
  GitHub still gets full light/dark switching.
- This is also why the version bump: PyPI releases are immutable — the
  displayed README is fixed to whatever was uploaded with `0.3.1`, and
  can only be updated by publishing a new version, not edited in place.

### Added

- **PyPI license badge** next to the version badge — verified the
  underlying metadata (`license: 'MIT'`) is actually published correctly
  and the badge itself resolves before adding it.

## [0.3.1] - Released

### Added

- **`mask(*field_names, replacement="***")`** — builds a `redact=`
  callable for `@track`/`track_module`, e.g. `redact=mask("password",
  "token")`, replacing the few-line lambda most projects were
  reimplementing by hand. Still opt-in by exact field name, not by
  guessing which arguments "look sensitive" — same trust model as
  writing the lambda yourself, just less boilerplate.
- **`track_module(module, *, exclude=(), redact=None, capture_args=True)`**
  — bulk-applies `@track` to every function *defined in* a module, for
  onboarding an existing codebase without hand-adding `@track` everywhere.
  Deliberately not a global `auto_trace=True` switch (would capture
  arguments for functions nobody reviewed for sensitive data) — stays a
  scoped, reviewable call site instead. Skips classes, names merely
  imported into the module, and anything already `@track`-ed.
- **CLI**: `routeflow doctor` (checks the local env for the exact
  gotchas this project has actually hit — missing WebSocket support,
  Python version, `ROUTEFLOW_ENABLED` state), `routeflow traces --url`
  (list recent traces from a running instance without opening a
  browser), `routeflow export --url --out` (dump the ring buffer to a
  file before it rotates out — the only way to keep history past a
  restart), `routeflow open` (open the flow view in your default
  browser). No daemon, no config file — every command that talks to a
  running app takes an explicit `--url`.

### Fixed

- **`ROUTEFLOW_ENABLED=0` / `enabled=False` was not a true no-op for
  `@track`.** The middleware and both mounts correctly disabled, but
  `@track` is a separate mechanism and kept calling `open_span()`
  unconditionally — which raises with no active trace. Every
  `@track`-decorated endpoint returned an unhandled 500 the moment
  tracing was disabled, in exactly the "leave `@track` in your code,
  flip the env var off in production" scenario the flag exists to make
  safe. Reported with a full repro; fixed at the root: `span_scope`
  (what `@track` actually uses) is now a true no-op with no active
  trace, and `get_current_span()` returns a harmless placeholder
  instead of `None` so `get_current_span().log(...)` inside a
  `@track`-ed function (the same pattern this project's own examples
  use) doesn't crash either.
- **Error status was color-only** in the node graph and timeline strip —
  the red border/fill was the *only* signal a span had failed, with no
  text or icon fallback, not even on hover. Both now show an explicit
  "✕ error" alongside the color.
- Two bugs caught building the CLI commands above, both regression-tested:
  rich markup silently swallowing literal `[...]` in dynamic text (e.g.
  `uvicorn[standard]` rendered as `uvicorn`), and an exception-handling
  order bug where a real HTTP 404 was reported as "can't reach the
  server" (`HTTPError` is a subclass of `URLError`; the more general
  case was caught first).

### Documentation

- **The `/__routeflow__` API and `/flow` UI have no authentication** —
  previously only discoverable by reading `server.py`, now a stated
  caveat in both the README and `ARCHITECTURE.md`. It's the reason
  `redact=`/`mask()`/`capture_args=False` matter as much as they do —
  there's no auth gate standing behind them.

## [0.3.0] - Released

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
