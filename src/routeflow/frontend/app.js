// RouteFlow flow view — vanilla JS, no build step, no framework. This
// is served as a static file directly from the package, so it has to
// run as-is in a browser with no bundling.

// The page is served at ".../<mount>/app/" — the REST/WS API lives one
// level up, at ".../<mount>/". Computed from the current URL rather than
// hardcoded, so this keeps working regardless of what mount path a given
// app was installed at.
const API_BASE = window.location.pathname.replace(/app\/?$/, "");

async function fetchJSON(path) {
  const response = await fetch(API_BASE + path);
  if (!response.ok) {
    throw new Error(`${path} -> ${response.status}`);
  }
  return response.json();
}

// The one route pattern currently selected in the sidebar, if any — the
// trace list and (in a later commit) the node graph both key off this.
let selectedRoutePattern = null;

function renderEndpointList(endpoints) {
  const container = document.getElementById("endpoint-list");
  container.innerHTML = "";

  if (endpoints.length === 0) {
    const empty = document.createElement("p");
    empty.className = "placeholder";
    empty.textContent = "No requests seen yet.";
    container.appendChild(empty);
    return;
  }

  for (const endpoint of endpoints) {
    const row = document.createElement("div");
    row.className = "endpoint";
    row.dataset.routePattern = endpoint.route_pattern;
    if (endpoint.route_pattern === selectedRoutePattern) {
      row.classList.add("selected");
    }
    row.addEventListener("click", () => selectEndpoint(endpoint.route_pattern));

    const top = document.createElement("div");
    top.className = "endpoint-top";

    const method = document.createElement("span");
    method.className = `method ${endpoint.method.toLowerCase()}`;
    method.textContent = endpoint.method;

    const path = document.createElement("span");
    path.className = "endpoint-path";
    path.textContent = endpoint.route_pattern;

    top.append(method, path);

    const stats = document.createElement("div");
    stats.className = "endpoint-stats";
    stats.innerHTML = `
      <span>${endpoint.request_count} reqs</span>
      <span>p95 ${
        endpoint.p95_duration_ms === null
          ? "—"
          : Math.round(endpoint.p95_duration_ms) + "ms"
      }</span>
      ${
        endpoint.error_count > 0
          ? `<span class="err-rate">${Math.round(endpoint.error_rate * 100)}% err</span>`
          : ""
      }
    `;

    row.append(top, stats);
    container.appendChild(row);
  }
}

function selectEndpoint(routePattern) {
  selectedRoutePattern = routePattern;

  // Reflect the selection in the already-rendered rows rather than
  // re-fetching /endpoints — the list of endpoints hasn't changed, only
  // which one is selected.
  for (const row of document.querySelectorAll(".endpoint")) {
    row.classList.toggle("selected", row.dataset.routePattern === routePattern);
  }

  document.getElementById("trace-list-heading").textContent =
    `Recent traces · ${routePattern}`;
  document.getElementById("trace-list-section").hidden = false;

  loadTraces(routePattern);
}

function renderTraceList(traces) {
  const container = document.getElementById("trace-list");
  container.innerHTML = "";

  if (traces.length === 0) {
    const empty = document.createElement("p");
    empty.className = "placeholder";
    empty.textContent = "No traces for this endpoint yet.";
    container.appendChild(empty);
    return;
  }

  for (const trace of traces) {
    const row = document.createElement("div");
    row.className = "trace";
    row.dataset.traceId = trace.trace_id;
    if (trace.trace_id === selectedTraceId) {
      row.classList.add("selected");
    }
    row.addEventListener("click", () => selectTrace(trace.trace_id));

    const status = document.createElement("span");
    status.className = `status-chip ${trace.status}`;
    status.textContent = trace.status.toUpperCase();

    const id = document.createElement("span");
    id.className = "trace-id";
    // Short id for scanability in a list — the full id is still on
    // trace.trace_id for whatever reads it next (the detail panel, in a
    // later commit).
    id.textContent = `#${trace.trace_id.slice(0, 8)}`;

    const meta = document.createElement("span");
    meta.className = "trace-meta";
    meta.textContent =
      trace.duration_ms === null ? "—" : `${Math.round(trace.duration_ms)}ms`;

    row.append(status, id, meta);
    container.appendChild(row);
  }
}

async function loadTraces(routePattern) {
  const container = document.getElementById("trace-list");
  container.innerHTML = "";
  const loading = document.createElement("p");
  loading.className = "placeholder";
  loading.textContent = "Loading traces…";
  container.appendChild(loading);

  try {
    const traces = await fetchJSON(
      `traces?route_pattern=${encodeURIComponent(routePattern)}`
    );
    // The user may have clicked a different endpoint while this request
    // was in flight — don't let a slow, stale response clobber a newer
    // selection's traces.
    if (routePattern !== selectedRoutePattern) return;
    renderTraceList(traces);
  } catch (err) {
    if (routePattern !== selectedRoutePattern) return;
    container.innerHTML = "";
    const message = document.createElement("p");
    message.className = "placeholder";
    message.textContent = "Couldn't load traces.";
    container.appendChild(message);
    console.error("routeflow: failed to load traces", err);
  }
}

// The one trace currently shown in the graph, if any.
let selectedTraceId = null;

// Layout constants for the node graph — one screen-pixel size, shared by
// both the DOM node divs and the SVG edges connecting them, so the two
// stay aligned without either side re-deriving the other's geometry.
const NODE_W = 170;
const NODE_H = 56;
const COL_GAP = 24;
const ROW_GAP = 48;
const MARGIN = 20;

/**
 * Positions each span as a (x, y, width, height) box: depth (via
 * parent_id) becomes the row, spans within a depth are laid out
 * left-to-right in the order they appear (already call order — see
 * Trace.to_dict). Not a full tidy-tree layout (children aren't centered
 * under their specific parent), but every edge is still drawn correctly
 * regardless, so the tree structure itself is always accurate even when
 * the geometry is just "good enough" for now.
 */
function layoutSpans(spans) {
  const byId = new Map(spans.map((span) => [span.span_id, span]));
  const depthOf = new Map();

  function depthOfSpan(span) {
    if (depthOf.has(span.span_id)) return depthOf.get(span.span_id);
    const parent = span.parent_id ? byId.get(span.parent_id) : null;
    const depth = parent ? depthOfSpan(parent) + 1 : 0;
    depthOf.set(span.span_id, depth);
    return depth;
  }

  const rows = [];
  for (const span of spans) {
    const depth = depthOfSpan(span);
    if (!rows[depth]) rows[depth] = [];
    rows[depth].push(span);
  }

  const positions = new Map();
  let maxCols = 0;
  rows.forEach((row, rowIndex) => {
    maxCols = Math.max(maxCols, row.length);
    row.forEach((span, colIndex) => {
      positions.set(span.span_id, {
        span,
        x: MARGIN + colIndex * (NODE_W + COL_GAP),
        y: MARGIN + rowIndex * (NODE_H + ROW_GAP),
      });
    });
  });

  const width = MARGIN * 2 + maxCols * NODE_W + Math.max(0, maxCols - 1) * COL_GAP;
  const height =
    MARGIN * 2 + rows.length * NODE_H + Math.max(0, rows.length - 1) * ROW_GAP;
  return { positions, width, height };
}

// The trace currently rendered in the graph — the detail panel reads
// span.start_time offsets against `currentTrace.started_at`, so it needs
// the trace, not just the one span that was clicked.
let currentTrace = null;
let selectedSpanId = null;

function renderGraph(trace) {
  currentTrace = trace;
  selectedSpanId = null;
  document.getElementById("detail").hidden = true;

  document.getElementById("canvas-placeholder").hidden = true;
  document.getElementById("canvas-scroll").hidden = false;
  const graph = document.getElementById("graph");
  graph.innerHTML = "";

  if (trace.spans.length === 0) {
    graph.style.width = "";
    graph.style.height = "";
    const empty = document.createElement("p");
    empty.className = "placeholder";
    empty.textContent = "No @track-ed calls recorded for this request.";
    graph.appendChild(empty);
    return;
  }

  const { positions, width, height } = layoutSpans(trace.spans);
  graph.style.width = `${width}px`;
  graph.style.height = `${height}px`;

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));

  for (const { span, x, y } of positions.values()) {
    const parentPos = span.parent_id ? positions.get(span.parent_id) : null;
    if (!parentPos) continue;
    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("x1", String(parentPos.x + NODE_W / 2));
    line.setAttribute("y1", String(parentPos.y + NODE_H));
    line.setAttribute("x2", String(x + NODE_W / 2));
    line.setAttribute("y2", String(y));
    line.setAttribute("stroke", "currentColor");
    line.setAttribute("stroke-opacity", "0.4");
    svg.appendChild(line);
  }
  graph.appendChild(svg);

  for (const { span, x, y } of positions.values()) {
    const node = document.createElement("div");
    node.className = `node ${span.status === "error" ? "error" : "ok"}`;
    node.dataset.spanId = span.span_id;
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    node.style.width = `${NODE_W}px`;
    node.style.height = `${NODE_H}px`;
    node.addEventListener("click", () => selectSpan(span));

    const bar = document.createElement("span");
    bar.className = "bar";

    const inner = document.createElement("div");
    inner.className = "inner";
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = span.name;
    const sub = document.createElement("div");
    sub.className = "sub";
    sub.textContent =
      span.duration_ms === null ? "running…" : `${Math.round(span.duration_ms)}ms`;
    inner.append(name, sub);

    node.append(bar, inner);
    graph.appendChild(node);
  }
}

function selectSpan(span) {
  selectedSpanId = span.span_id;
  for (const node of document.querySelectorAll(".node")) {
    node.classList.toggle("selected", node.dataset.spanId === span.span_id);
  }
  renderDetail(span);
}

function renderDetail(span) {
  document.getElementById("detail").hidden = false;
  document.getElementById("detail-name").textContent = span.name;

  const parent = span.parent_id
    ? currentTrace.spans.find((s) => s.span_id === span.parent_id)
    : null;
  // Offsets relative to the trace's own start (not span.start_time raw —
  // that's a perf_counter reading, meaningless without this subtraction;
  // see Trace.to_dict's docstring on the Python side).
  const startedAtMs = Math.round(
    (span.start_time - currentTrace.started_at) * 1000
  );

  const metrics = document.getElementById("detail-metrics");
  metrics.innerHTML = "";
  const rows = [
    ["Status", span.status === "error" ? "✕ error" : "ok"],
    ["Started at", `${startedAtMs}ms`],
    ["Duration", span.duration_ms === null ? "—" : `${Math.round(span.duration_ms)}ms`],
    ["Parent span", parent ? parent.name : "— (root)"],
  ];
  for (const [label, value] of rows) {
    const row = document.createElement("div");
    row.className = "metric-row";
    const labelEl = document.createElement("span");
    labelEl.textContent = label;
    const valueEl = document.createElement("span");
    valueEl.textContent = value;
    row.append(labelEl, valueEl);
    metrics.appendChild(row);
  }

  const argsContainer = document.getElementById("detail-args");
  argsContainer.innerHTML = "";
  const argEntries = Object.entries(span.args);
  if (argEntries.length === 0) {
    const none = document.createElement("p");
    none.className = "placeholder";
    none.textContent = "None captured.";
    argsContainer.appendChild(none);
  } else {
    for (const [name, value] of argEntries) {
      const row = document.createElement("div");
      row.className = "arg-row";
      const nameEl = document.createElement("span");
      nameEl.className = "arg-name";
      nameEl.textContent = `${name}=`;
      const valueEl = document.createElement("span");
      valueEl.textContent = value;
      row.append(nameEl, valueEl);
      argsContainer.appendChild(row);
    }
  }

  const logsContainer = document.getElementById("detail-logs");
  logsContainer.innerHTML = "";
  if (span.logs.length === 0) {
    const none = document.createElement("p");
    none.className = "placeholder";
    none.textContent = "No log lines captured.";
    logsContainer.appendChild(none);
  } else {
    for (const log of span.logs) {
      const offsetMs = Math.round((log.timestamp - span.start_time) * 1000);
      const row = document.createElement("div");
      row.className = "log-line";
      const t = document.createElement("span");
      t.className = "t";
      t.textContent = `+${offsetMs}ms`;
      const msg = document.createElement("span");
      msg.textContent = log.message;
      row.append(t, msg);
      logsContainer.appendChild(row);
    }
  }

  const errorSection = document.getElementById("detail-error-section");
  if (span.error === null) {
    errorSection.hidden = true;
  } else {
    errorSection.hidden = false;
    const errorBox = document.getElementById("detail-error");
    errorBox.innerHTML = "";
    const type = document.createElement("div");
    type.className = "type";
    type.textContent = span.error.type;
    const msg = document.createElement("div");
    msg.className = "msg";
    msg.textContent = span.error.message;
    const tb = document.createElement("div");
    tb.className = "trace";
    tb.textContent = span.error.traceback;
    errorBox.append(type, msg, tb);
  }
}

function selectTrace(traceId) {
  selectedTraceId = traceId;

  for (const row of document.querySelectorAll(".trace")) {
    row.classList.toggle("selected", row.dataset.traceId === traceId);
  }

  loadTraceDetail(traceId);
}

async function loadTraceDetail(traceId) {
  const graph = document.getElementById("graph");
  document.getElementById("canvas-placeholder").hidden = true;
  document.getElementById("canvas-scroll").hidden = false;
  graph.innerHTML = "";
  const loading = document.createElement("p");
  loading.className = "placeholder";
  loading.textContent = "Loading trace…";
  graph.appendChild(loading);

  try {
    const trace = await fetchJSON(`traces/${encodeURIComponent(traceId)}`);
    if (traceId !== selectedTraceId) return; // superseded by a newer click
    renderGraph(trace);
  } catch (err) {
    if (traceId !== selectedTraceId) return;
    graph.innerHTML = "";
    const message = document.createElement("p");
    message.className = "placeholder";
    message.textContent = "Couldn't load this trace.";
    graph.appendChild(message);
    console.error("routeflow: failed to load trace", err);
  }
}

async function loadEndpoints() {
  try {
    const endpoints = await fetchJSON("endpoints");
    renderEndpointList(endpoints);
  } catch (err) {
    const container = document.getElementById("endpoint-list");
    container.innerHTML = "";
    const message = document.createElement("p");
    message.className = "placeholder";
    message.textContent = "Couldn't load endpoints.";
    container.appendChild(message);
    console.error("routeflow: failed to load endpoints", err);
  }
}

/**
 * Opens the WebSocket the server pushes a finished trace's full JSON
 * over as it lands (see LiveBroadcaster.broadcast_trace). The payload
 * itself isn't consumed here — its arrival is just the signal to
 * re-fetch: that keeps the endpoint sidebar's counts/p95/error-rate and
 * whatever trace list is currently open both trivially correct, rather
 * than hand-patching two different pieces of derived state from one raw
 * trace. Reconnect-on-drop and a visible "disconnected" state are their
 * own later commit — this is deliberately just the happy path.
 */
function connectLiveSocket() {
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${wsProtocol}//${window.location.host}${API_BASE}live`);

  socket.addEventListener("message", () => {
    loadEndpoints();
    if (selectedRoutePattern) {
      loadTraces(selectedRoutePattern);
    }
  });

  socket.addEventListener("error", (err) => {
    console.error("routeflow: live socket error", err);
  });

  return socket;
}

loadEndpoints();
connectLiveSocket();
