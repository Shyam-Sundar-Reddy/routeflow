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

loadEndpoints();
