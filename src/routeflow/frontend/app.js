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
