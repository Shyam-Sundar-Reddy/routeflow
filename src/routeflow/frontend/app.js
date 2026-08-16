// RouteFlow flow view — vanilla JS, no build step, no framework. This
// is served as a static file directly from the package, so it has to
// run as-is in a browser with no bundling.

// This page is served at ".../flow/" — bare, directly on the host app's
// own root (see integration.py's FLOW_UI_PATH), the same way FastAPI
// serves /docs. HOST_ROOT is just "wherever this page's own mount point
// is, minus 'flow/'" - derived from the current URL, not assumed, so a
// host app that's itself served behind a path prefix (a reverse proxy,
// say) still gets a correct Docs link below.
const HOST_ROOT = window.location.pathname.replace(/flow\/?$/, "");

// Unlike the UI, the REST/WS API is *not* nested under FLOW_UI_PATH — it
// lives at its own, separately-mounted, collision-safe prefix (see
// integration.py's MOUNT_PATH). Can't be derived from this page's own
// URL the way it used to be when both were nested together, so this is
// HOST_ROOT plus that fixed, known prefix.
const API_BASE = `${HOST_ROOT}__routeflow__/`;

document.getElementById("docs-tab").href = HOST_ROOT + "docs";

// "system" (follow the OS, the default) / "light" / "dark" — cycled by
// the topbar button, persisted so a reload doesn't lose the choice.
// Applying it as [data-theme] on <html> is what the CSS's
// :root[data-theme="..."] blocks key off; "system" means *no* attribute
// at all, letting the plain prefers-color-scheme block take over.
const THEME_STORAGE_KEY = "routeflow-theme";
const THEME_CYCLE = ["system", "light", "dark"];
const THEME_LABEL = { system: "◐", light: "☀", dark: "☾" };

function applyTheme(theme) {
  if (theme === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
  document.getElementById("theme-toggle").textContent = THEME_LABEL[theme];
}

function initTheme() {
  const stored = localStorage.getItem(THEME_STORAGE_KEY);
  applyTheme(THEME_CYCLE.includes(stored) ? stored : "system");

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = localStorage.getItem(THEME_STORAGE_KEY) || "system";
    const next = THEME_CYCLE[(THEME_CYCLE.indexOf(current) + 1) % THEME_CYCLE.length];
    localStorage.setItem(THEME_STORAGE_KEY, next);
    applyTheme(next);
  });
}

initTheme();

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
// Below this, text stops being readable - past this point a wide trace is
// left to scroll horizontally instead of shrinking further.
const MIN_FIT_SCALE = 0.5;

/**
 * Depth of each span via its parent_id chain (root spans are depth 0) —
 * shared by the node graph's row layout and the timeline strip's row
 * layout below, so "which row is this span in" is answered the same way
 * in both places rather than two implementations drifting apart.
 */
function computeDepths(spans) {
  const byId = new Map(spans.map((span) => [span.span_id, span]));
  const depthOf = new Map();

  function depthOfSpan(span) {
    if (depthOf.has(span.span_id)) return depthOf.get(span.span_id);
    const parent = span.parent_id ? byId.get(span.parent_id) : null;
    const depth = parent ? depthOfSpan(parent) + 1 : 0;
    depthOf.set(span.span_id, depth);
    return depth;
  }

  for (const span of spans) depthOfSpan(span);
  return depthOf;
}

/**
 * Positions each span as a (x, y, width, height) box: depth becomes the
 * row; within a row, x comes from a bottom-up tree layout, not append
 * order — a leaf gets the next free horizontal slot (left to right, call
 * order), and a parent's slot is the average of its own children's, so a
 * node always sits above the midpoint of its actual subtree rather than
 * wherever it happened to appear in a flat per-depth list.
 *
 * This matters once a trace has more than one branch at the same depth
 * (any @track call under asyncio.gather, or just several sibling calls) —
 * the previous append-order layout put a child wherever its position in
 * a flat row landed, with no relation to where its real parent was drawn,
 * which produced edges jogging sideways by hundreds of pixels to reach
 * their own child. Verified against a real trace from
 * examples/production_demo.py before this fix (worst case: a single edge
 * had to jog 970px sideways) and after (structurally guaranteed not to
 * happen: leaf slots are strictly increasing in call order, and every
 * parent's slot is bounded within its own children's slot range, so
 * sibling subtrees can never overlap or cross).
 */
function layoutSpans(spans) {
  const depthOf = computeDepths(spans);
  const byId = new Map(spans.map((span) => [span.span_id, span]));
  const childrenOf = (parentId) =>
    spans.filter((span) => span.parent_id === parentId);

  let nextSlot = 0;
  const slotOf = new Map();
  function assignSlot(span) {
    if (slotOf.has(span.span_id)) return slotOf.get(span.span_id);
    const kids = childrenOf(span.span_id);
    const slot =
      kids.length === 0
        ? nextSlot++
        : kids.reduce((sum, kid) => sum + assignSlot(kid), 0) / kids.length;
    slotOf.set(span.span_id, slot);
    return slot;
  }
  // Normally exactly one root (parent_id === null); more than one shows
  // up if the route handler itself isn't @track-ed and calls several
  // tracked functions directly — each gets its own slot range in the
  // same left-to-right sweep, same as siblings under a real parent.
  for (const span of spans) {
    if (span.parent_id === null || !byId.has(span.parent_id)) assignSlot(span);
  }

  const positions = new Map();
  for (const span of spans) {
    positions.set(span.span_id, {
      span,
      x: MARGIN + slotOf.get(span.span_id) * (NODE_W + COL_GAP),
      y: MARGIN + depthOf.get(span.span_id) * (NODE_H + ROW_GAP),
    });
  }

  const maxX = Math.max(...[...positions.values()].map((p) => p.x));
  const maxRow = Math.max(...[...depthOf.values()]);
  const width = maxX + NODE_W + MARGIN;
  const height = MARGIN * 2 + (maxRow + 1) * NODE_H + maxRow * ROW_GAP;
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
  document.getElementById("canvas-body").hidden = false;
  const graph = document.getElementById("graph");
  const graphViewport = document.getElementById("graph-viewport");
  graph.innerHTML = "";
  graph.style.transform = "";

  renderTimeline(trace);

  if (trace.spans.length === 0) {
    graph.style.width = "";
    graph.style.height = "";
    graphViewport.style.width = "";
    graphViewport.style.height = "";
    const empty = document.createElement("p");
    empty.className = "placeholder";
    empty.textContent = "No @track-ed calls recorded for this request.";
    graph.appendChild(empty);
    return;
  }

  const { positions, width, height } = layoutSpans(trace.spans);
  const depthOf = computeDepths(trace.spans);
  graph.style.width = `${width}px`;
  graph.style.height = `${height}px`;

  // Fit-to-width: a wide fan-out (several branches at the same depth,
  // easy to get from asyncio.gather) can be wider than the canvas ever
  // is, which used to mean entire branches sat off-screen with no visual
  // hint they existed - just a scrollbar to stumble onto by accident.
  // Scaling the whole graph down to fit is the same "zoom to fit" any
  // graph/diagram tool defaults to; .graph-viewport is sized to the
  // *scaled* dimensions so .canvas-scroll's own overflow calculation
  // agrees with what's actually visible, instead of reserving scroll
  // space for the pre-scale size.
  //
  // The available width has to come from .canvas-scroll itself, not
  // .graph-viewport - .graph-viewport's own size is what this code is
  // about to set, and .graph (its child) already has an explicit huge
  // width from the layout above, so measuring either of those here would
  // just read back a stale or content-driven number instead of the
  // actual viewport space, min 0 to survive an unmeasurable/detached DOM.
  const canvasScroll = document.getElementById("canvas-scroll");
  const scrollStyle = getComputedStyle(canvasScroll);
  const availableWidth = Math.max(
    0,
    canvasScroll.clientWidth -
      parseFloat(scrollStyle.paddingLeft) -
      parseFloat(scrollStyle.paddingRight)
  );
  const rawScale = availableWidth > 0 ? availableWidth / width : 1;
  const scale = Math.min(1, Math.max(MIN_FIT_SCALE, rawScale));
  graph.style.transform = scale !== 1 ? `scale(${scale})` : "";
  graphViewport.style.width = `${width * scale}px`;
  graphViewport.style.height = `${height * scale}px`;

  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));

  for (const { span, x, y } of positions.values()) {
    const parentPos = span.parent_id ? positions.get(span.parent_id) : null;
    if (!parentPos) continue;

    // A gentle S-curve reads as "a call" rather than a ruled line, and
    // keeps many edges converging on one root from visually knotting up
    // at that single point the way straight lines do.
    const x1 = parentPos.x + NODE_W / 2, y1 = parentPos.y + NODE_H;
    const x2 = x + NODE_W / 2, y2 = y;
    const midY = (y1 + y2) / 2;
    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", `M${x1},${y1} C${x1},${midY} ${x2},${midY} ${x2},${y2}`);
    path.setAttribute("class", "edge");
    path.dataset.child = span.span_id;
    path.dataset.parent = span.parent_id;
    svg.appendChild(path);

    // Gap = how long after the parent *started* this child started -
    // same number the mockups showed, now on the real thing. Concurrent
    // branches (asyncio.gather) read as near-identical gaps at a glance.
    const parentSpan = positions.get(span.parent_id).span;
    const gapMs = Math.round((span.start_time - parentSpan.start_time) * 1000);
    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("x", String((x1 + x2) / 2 + 6));
    label.setAttribute("y", String(midY + 3));
    label.setAttribute("class", "edge-label");
    label.dataset.child = span.span_id;
    label.dataset.parent = span.parent_id;
    label.textContent = `+${gapMs}ms`;
    svg.appendChild(label);
  }
  graph.appendChild(svg);

  for (const { span, x, y } of positions.values()) {
    const node = document.createElement("div");
    node.className = `node ${span.status === "error" ? "error" : "ok"}`;
    node.dataset.spanId = span.span_id;
    node.dataset.parentId = span.parent_id ?? "";
    node.style.left = `${x}px`;
    node.style.top = `${y}px`;
    node.style.width = `${NODE_W}px`;
    node.style.height = `${NODE_H}px`;
    // Native tooltip: a name truncated by the node's fixed width (ellipsis,
    // see .node .name) is still readable on hover instead of only guessable.
    node.title = span.name;
    node.addEventListener("click", () => selectSpan(span));

    const bar = document.createElement("span");
    bar.className = "bar";

    const depth = depthOf.get(span.span_id);
    const depthBadge = document.createElement("span");
    depthBadge.className = "depth-badge";
    depthBadge.textContent = String(depth);
    depthBadge.title = `Depth ${depth}`;

    const inner = document.createElement("div");
    inner.className = "inner";
    const name = document.createElement("div");
    name.className = "name";
    name.textContent = span.name;
    const sub = document.createElement("div");
    sub.className = "sub";
    // Error state must never be color-only (the red border/bar alone
    // fails for anyone who can't distinguish red from the ok-blue at a
    // glance) - "✕ error" here matches the wording already used in the
    // detail panel's own Status row.
    sub.textContent =
      span.duration_ms === null
        ? "running…"
        : span.status === "error"
          ? `✕ error · ${Math.round(span.duration_ms)}ms`
          : `${Math.round(span.duration_ms)}ms`;
    inner.append(name, sub);

    node.append(bar, depthBadge, inner);
    graph.appendChild(node);
  }

  // Clicking empty canvas (not a node) clears the selection - the same
  // "click away to deselect" a click-to-highlight interaction needs, since
  // nothing here uses an expand/collapse control to get back to neutral.
  graph.addEventListener("click", (event) => {
    if (event.target === graph || event.target === svg) clearSelection();
  });
}

// Fixed "virtual" width for the timeline's SVG viewBox — real pixel
// width is whatever the browser lays the SVG out at (CSS: width: 100%),
// scaling this coordinate space to fit. Avoids needing to measure the
// container's actual pixel width in JS just to compute a scale factor.
const TIMELINE_VIRTUAL_WIDTH = 1000;
const TIMELINE_ROW_H = 18;
const TIMELINE_ROW_GAP = 6;
const TIMELINE_MARGIN = 8;
// Extra height at the top reserved for the 0ms/100ms/... axis labels -
// without this the strip showed relative bar proportions but no actual
// timing, which is most of what a "timeline" is for.
const TIMELINE_AXIS_H = 16;
const TIMELINE_TICK_COUNT = 5;

/**
 * Row assignment for the timeline: depth alone isn't enough. Two spans
 * at the same depth are usually sequential siblings and can safely share
 * a row — but asyncio.gather makes it just as normal for two same-depth
 * spans to run at the *same time*, and sharing a row then means their
 * bars visually overlap, silently misrepresenting "these ran together"
 * as "this is one longer call" (confirmed against a real trace: every
 * gather pair - inventory/pricing, their own DB children, email/sms -
 * produced exactly this collision).
 *
 * Fix: pack each depth's own spans independently, greedily, into the
 * fewest sub-rows such that nothing sharing a sub-row overlaps in time
 * (the same algorithm a calendar view uses for overlapping meetings).
 * Sequential siblings still end up sharing one row, same as before;
 * only spans that are genuinely concurrent get split into their own.
 * Returns each span's *global* row index (depths stack in order) and
 * the total row count.
 */
function packTimelineRows(spans, depthOf) {
  const maxDepth = Math.max(...depthOf.values());
  const rowOf = new Map();
  let rowCursor = 0;

  for (let depth = 0; depth <= maxDepth; depth++) {
    const atDepth = spans
      .filter((s) => depthOf.get(s.span_id) === depth)
      .sort((a, b) => a.start_time - b.start_time);

    const subRowEnds = []; // last end time (ms, trace-relative) per sub-row
    for (const span of atDepth) {
      const start = span.start_time;
      const end = start + (span.duration_ms ?? 0) / 1000;
      let subRow = subRowEnds.findIndex((endTime) => endTime <= start);
      if (subRow === -1) {
        subRow = subRowEnds.length;
        subRowEnds.push(end);
      } else {
        subRowEnds[subRow] = end;
      }
      rowOf.set(span.span_id, rowCursor + subRow);
    }
    rowCursor += Math.max(1, subRowEnds.length);
  }

  return { rowOf, rowCount: rowCursor };
}

/**
 * The flamegraph-style strip: every span as a horizontal bar positioned
 * by when it ran and how long it took, relative to the trace's own
 * start — literally the same (offset, duration) pair the detail panel
 * shows as text, drawn as geometry instead. Synced to whatever trace
 * `renderGraph` just rendered, and clicking a bar drives the exact same
 * `selectSpan` the node graph does, so either view can be the one the
 * user actually clicks.
 */
function renderTimeline(trace) {
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.getElementById("timeline-svg");
  svg.innerHTML = "";

  if (trace.spans.length === 0 || trace.duration_ms === null) {
    return;
  }

  const depthOf = computeDepths(trace.spans);
  const { rowOf, rowCount } = packTimelineRows(trace.spans, depthOf);
  const height = TIMELINE_AXIS_H + TIMELINE_MARGIN * 2 + rowCount * TIMELINE_ROW_H +
    Math.max(0, rowCount - 1) * TIMELINE_ROW_GAP;

  svg.setAttribute("viewBox", `0 0 ${TIMELINE_VIRTUAL_WIDTH} ${height}`);
  // Real pixel height, not stretched to a fixed box - a trace needing
  // more rows (packTimelineRows) actually gets a taller strip instead of
  // every row just getting proportionally thinner. .strip-scroll's own
  // max-height + overflow-y is the ceiling for a genuinely deep trace.
  svg.style.height = `${height}px`;

  // A span can outlast the trace's own recorded duration by a hair (the
  // trace closes as soon as the response is ready, spans close as their
  // calls return) - guard against a negative/zero denominator rather
  // than let a bar's width go negative or divide by zero.
  const totalMs = Math.max(trace.duration_ms, 1);
  const usableWidth = TIMELINE_VIRTUAL_WIDTH - TIMELINE_MARGIN * 2;
  const pxPerMs = usableWidth / totalMs;

  for (let i = 0; i < TIMELINE_TICK_COUNT; i++) {
    const frac = i / (TIMELINE_TICK_COUNT - 1);
    const tickX = TIMELINE_MARGIN + frac * usableWidth;
    const line = document.createElementNS(svgNS, "line");
    line.setAttribute("class", "timeline-gridline");
    line.setAttribute("x1", String(tickX));
    line.setAttribute("x2", String(tickX));
    line.setAttribute("y1", String(TIMELINE_AXIS_H));
    line.setAttribute("y2", String(height));
    svg.appendChild(line);

    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("class", "timeline-axis-label");
    label.setAttribute("x", String(tickX));
    label.setAttribute("y", String(TIMELINE_AXIS_H - 4));
    label.setAttribute("text-anchor", i === TIMELINE_TICK_COUNT - 1 ? "end" : "start");
    label.textContent = `${Math.round(frac * totalMs)}ms`;
    svg.appendChild(label);
  }

  for (const span of trace.spans) {
    const offsetMs = (span.start_time - trace.started_at) * 1000;
    const durationMs = span.duration_ms ?? 0;
    const row = rowOf.get(span.span_id);

    const rect = document.createElementNS(svgNS, "rect");
    rect.setAttribute("class", `timeline-bar ${span.status === "error" ? "error" : "ok"}`);
    rect.dataset.spanId = span.span_id;
    rect.setAttribute("x", String(TIMELINE_MARGIN + offsetMs * pxPerMs));
    rect.setAttribute(
      "y",
      String(TIMELINE_AXIS_H + TIMELINE_MARGIN + row * (TIMELINE_ROW_H + TIMELINE_ROW_GAP))
    );
    // A floor on width - an instant (0ms) call would otherwise render as
    // a zero-width, unclickable, invisible rect.
    rect.setAttribute("width", String(Math.max(durationMs * pxPerMs, 3)));
    rect.setAttribute("height", String(TIMELINE_ROW_H));
    rect.setAttribute("rx", "2");
    rect.addEventListener("click", () => selectSpan(span));

    // Same reasoning as the node graph's .sub text - the bar's color is
    // the only other signal for error status, and that must never be
    // the sole cue, not even one only visible on hover.
    const title = document.createElementNS(svgNS, "title");
    title.textContent =
      span.status === "error"
        ? `${span.name} — ✕ error · ${Math.round(durationMs)}ms`
        : `${span.name} — ${Math.round(durationMs)}ms`;
    rect.appendChild(title);

    svg.appendChild(rect);
  }
}

// A span's own ancestor chain, root first isn't needed here - order
// doesn't matter, only membership does (which nodes/edges sit on the
// path back to the root, for highlighting).
function ancestorChain(span) {
  const byId = new Map(currentTrace.spans.map((s) => [s.span_id, s]));
  const chain = [];
  let cur = span;
  while (cur) {
    chain.push(cur.span_id);
    cur = cur.parent_id ? byId.get(cur.parent_id) : null;
  }
  return chain;
}

function selectSpan(span) {
  selectedSpanId = span.span_id;
  const chain = new Set(ancestorChain(span));

  for (const el of document.querySelectorAll(".node, .timeline-bar")) {
    const onPath = chain.has(el.dataset.spanId);
    el.classList.toggle("selected", el.dataset.spanId === span.span_id);
    el.classList.toggle("highlighted", onPath && el.dataset.spanId !== span.span_id);
    el.classList.toggle("dimmed", !onPath);
  }
  for (const el of document.querySelectorAll(".edge, .edge-label")) {
    const onPath = chain.has(el.dataset.child) && chain.has(el.dataset.parent);
    el.classList.toggle("highlighted", onPath);
    el.classList.toggle("dimmed", !onPath);
  }
  renderDetail(span);
}

function clearSelection() {
  selectedSpanId = null;
  for (const el of document.querySelectorAll(".node, .timeline-bar, .edge, .edge-label")) {
    el.classList.remove("selected", "highlighted", "dimmed");
  }
  document.getElementById("detail").hidden = true;
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
    ["Depth", String(computeDepths(currentTrace.spans).get(span.span_id))],
    ["Started at", `${startedAtMs}ms`],
    ["Duration", span.duration_ms === null ? "—" : `${Math.round(span.duration_ms)}ms`],
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

  // Parent span as a jump-to-it link when there is one, rather than
  // inert text - the relationship it names should be one click away, not
  // just something you visually hunt for back in the graph.
  const parentRow = document.createElement("div");
  parentRow.className = "metric-row";
  const parentLabel = document.createElement("span");
  parentLabel.textContent = "Parent span";
  const parentValue = document.createElement("span");
  if (parent) {
    const link = document.createElement("button");
    link.type = "button";
    link.className = "parent-link";
    link.textContent = parent.name;
    link.addEventListener("click", () => selectSpan(parent));
    parentValue.appendChild(link);
  } else {
    parentValue.textContent = "— (root)";
  }
  parentRow.append(parentLabel, parentValue);
  metrics.appendChild(parentRow);

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
  document.getElementById("canvas-body").hidden = false;
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
const RECONNECT_DELAY_MS = 2000;

function setLiveStatus(status) {
  const indicator = document.getElementById("live-indicator");
  indicator.classList.remove("connecting", "connected", "disconnected");
  indicator.classList.add(status);
  indicator.textContent =
    status === "connected"
      ? "● live"
      : status === "disconnected"
        ? "○ disconnected — retrying…"
        : "connecting…";
}

function connectLiveSocket() {
  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${wsProtocol}//${window.location.host}${API_BASE}live`);

  socket.addEventListener("open", () => setLiveStatus("connected"));

  socket.addEventListener("message", () => {
    loadEndpoints();
    if (selectedRoutePattern) {
      loadTraces(selectedRoutePattern);
    }
  });

  socket.addEventListener("error", (err) => {
    console.error("routeflow: live socket error", err);
  });

  socket.addEventListener("close", () => {
    setLiveStatus("disconnected");
    // The dev server restarting (--reload, a crash, a manual stop) is
    // the routine case here, not a rare edge - retry rather than leaving
    // the tab permanently stuck the moment the server bounces once.
    setTimeout(connectLiveSocket, RECONNECT_DELAY_MS);
  });

  return socket;
}

document.getElementById("detail-close").addEventListener("click", clearSelection);

loadEndpoints();
connectLiveSocket();
