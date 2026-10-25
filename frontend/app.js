const apiStatus = document.querySelector("#api-status");
const datasetSelect = document.querySelector("#dataset-select");
const questionForm = document.querySelector("#question-form");
const questionInput = document.querySelector("#question");
const analyzeButton = document.querySelector("#analyze-button");
const pageError = document.querySelector("#page-error");
const offlineMessage = document.querySelector("#offline-message");
const answerCard = document.querySelector("#answer-card");
const profileContent = document.querySelector("#profile-content");
const auditContent = document.querySelector("#audit-content");
const dashboardContent = document.querySelector("#dashboard-content");

let busy = false;

const DATASET_LABELS = {
  demo: "Demo sales",
  crm_demo: "Mock CRM (read-only)",
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function displayColumn(value) {
  return String(value ?? "")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "Not available";
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 }).format(value);
  }
  return String(value);
}

function renderSummary(summary) {
  const columns = summary.columns || [];
  const rows = summary.rows || [];
  if (!rows.length) return '<p class="empty">No rows matched the current filters.</p>';
  const headers = columns.map((column) => `<th>${escapeHtml(displayColumn(column))}</th>`).join("");
  const body = rows.map((row) => `<tr>${columns.map((_, index) =>
    `<td>${escapeHtml(displayValue(row[index]))}</td>`).join("")}</tr>`).join("");
  const truncated = summary.truncated ? " · Preview is truncated" : "";
  return `<p class="result-meta">Showing ${rows.length.toLocaleString("en-IN")} of ` +
    `${Number(summary.row_count || rows.length).toLocaleString("en-IN")} result(s)${truncated}.</p>` +
    `<div class="table-wrap"><table class="result-table"><thead><tr>${headers}</tr></thead>` +
    `<tbody>${body}</tbody></table></div>`;
}

function renderChecks(checks) {
  if (!checks?.length) return '<p class="empty">No validation checks were recorded.</p>';
  return `<div class="table-wrap"><table class="result-table"><thead><tr>` +
    `<th>Status</th><th>Check</th><th>Details</th></tr></thead><tbody>` +
    checks.map((check) => `<tr><td><span class="status-pill status-${escapeHtml(String(check.status || "").toLowerCase())}">` +
      `${escapeHtml(check.status || "-")}</span></td><td>${escapeHtml(check.code || "-")}</td>` +
      `<td>${escapeHtml(check.detail || "-")}</td></tr>`).join("") +
    `</tbody></table></div>`;
}

function formatInsightValue(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 }).format(value);
  }
  return String(value ?? "Not available");
}

function renderBarChart(chart) {
  const max = Math.max(...(chart.values || []), 1);
  const bars = (chart.labels || []).map((label, index) => {
    const value = Number(chart.values?.[index] || 0);
    const width = Math.max(2, (value / max) * 100);
    return `<div class="chart-row"><div class="chart-label">${escapeHtml(label)}</div>` +
      `<div class="chart-track"><div class="chart-bar" style="width:${width}%"></div></div>` +
      `<strong class="chart-value">${escapeHtml(formatInsightValue(value))}</strong></div>`;
  }).join("");
  return `<article class="chart-card"><h3>${escapeHtml(chart.title)}</h3>` +
    `<p class="chart-detail">${escapeHtml(chart.detail || "")}</p><div class="bar-chart">${bars}</div></article>`;
}

function renderDashboard(payload) {
  if (!payload || !payload.charts) {
    dashboardContent.innerHTML = '<p class="empty">Visual insights are not available for this dataset.</p>';
    return;
  }
  const periods = payload.periods || {};
  const kpis = (payload.kpis || []).map((kpi) =>
    `<article class="kpi-card ${kpi.tone === "warning" ? "kpi-warning" : ""}">` +
    `<p>${escapeHtml(kpi.label)}</p><strong>${escapeHtml(formatInsightValue(kpi.value))}</strong>` +
    `<span>${escapeHtml(kpi.detail || "")}</span></article>`).join("");
  const insights = (payload.insights || []).map((insight) =>
    `<article class="insight-card insight-${escapeHtml(insight.severity || "info")}">` +
    `<strong>${escapeHtml(insight.title)}</strong><p>${escapeHtml(insight.detail)}</p></article>`).join("");
  const quality = payload.data_quality || {};
  const qualityRows = [
    ["Duplicate email groups", quality.duplicate_email_groups],
    ["Missing amount values", quality.missing_amounts],
    ["Comma-formatted amounts", quality.comma_formatted_amounts],
    ["Blank close dates", quality.blank_close_dates],
    ["Stage/status mismatches", quality.stage_status_mismatches],
  ].map(([label, value]) => `<li><span>${escapeHtml(label)}</span><strong>${escapeHtml(formatInsightValue(value))}</strong></li>`).join("");
  dashboardContent.innerHTML =
    `<div class="dashboard-period"><strong>${escapeHtml(periods.current || "Current year")}</strong>` +
    ` compared with <strong>${escapeHtml(periods.previous || "Previous year")}</strong>` +
    `${periods.comparable ? " · like-for-like records available" : " · no comparable prior period"}</div>` +
    `<div class="kpi-grid">${kpis}</div>` +
    `<section class="insights-panel"><div class="section-heading compact"><h3>Key insights</h3>` +
    `<span class="badge badge-role">Observed data only</span></div>${insights || '<p class="empty">No additional insights.</p>'}</section>` +
    `<div class="chart-grid">${(payload.charts || []).map(renderBarChart).join("")}</div>` +
    `<section class="quality-panel"><h3>Data quality watchlist</h3><ul class="quality-list">${qualityRows}</ul>` +
    `<p class="empty">Money totals remain blocked until the dirty amount field is normalized.</p></section>`;
}

function showError(message) {
  pageError.textContent = message;
  pageError.hidden = !message;
}

function setStages(state) {
  document.querySelectorAll("#stage-list li").forEach((item) => {
    item.classList.remove("done", "active");
    const label = item.querySelector("strong");
    if (state === "running") {
      item.classList.add("active");
      label.textContent = "Running";
    } else if (state === "done") {
      item.classList.add("done");
      label.textContent = "Complete";
    } else {
      label.textContent = "Waiting";
    }
  });
}

async function request(path, options = {}) {
  const response = await fetch(path, { headers: { "Accept": "application/json" }, ...options });
  let payload = {};
  try { payload = await response.json(); } catch (_) { payload = {}; }
  if (!response.ok) {
    const error = payload.error || {};
    const exception = new Error(error.message || "Request could not be completed.");
    exception.code = error.code;
    exception.payload = payload;
    throw exception;
  }
  return payload;
}

async function checkApi() {
  try {
    await request("/api/v1/health");
    apiStatus.textContent = "API online";
    apiStatus.className = "badge badge-role";
  } catch (_) {
    apiStatus.textContent = "API unavailable";
    apiStatus.className = "badge badge-muted";
  }
}

async function loadDatasets() {
  const payload = await request("/api/v1/datasets");
  const datasets = payload.datasets || [];
  datasetSelect.replaceChildren();
  if (!datasets.length) {
    const option = new Option("No permitted datasets", "");
    option.disabled = true;
    option.selected = true;
    datasetSelect.add(option);
    return;
  }
  datasets.forEach((dataset) => {
    const id = typeof dataset === "string" ? dataset : dataset.dataset_id;
    datasetSelect.add(new Option(DATASET_LABELS[id] || id, id));
  });
  await loadProfile();
  await loadDashboard();
}

async function loadDashboard() {
  const dataset = datasetSelect.value;
  if (!dataset) {
    dashboardContent.innerHTML = '<p class="empty">Select a dataset to load visual insights.</p>';
    return;
  }
  try {
    const payload = await request(`/api/v1/datasets/${encodeURIComponent(dataset)}/dashboard`);
    renderDashboard(payload);
  } catch (error) {
    dashboardContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

function renderProfile(profile) {
  const entries = Object.entries(profile || {});
  if (!entries.length) {
    profileContent.innerHTML = '<p class="empty">No permitted profile is available.</p>';
    return;
  }
  profileContent.innerHTML = entries.map(([tableName, table]) => {
    const columns = Object.entries(table.columns || {});
    const rows = columns.map(([name, column]) => {
      const range = column.numeric_range || column.date_range || {};
      const rangeText = range.min != null || range.max != null
        ? `${escapeHtml(range.min ?? "-")} → ${escapeHtml(range.max ?? "-")}` : "-";
      const warnings = (column.warnings || []).join(", ") || "-";
      return `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(column.inferred_type || "unknown")}</td>` +
        `<td>${escapeHtml(column.null_count)} / ${escapeHtml(column.blank_count)}</td>` +
        `<td>${rangeText}</td><td>${escapeHtml(warnings)}</td></tr>`;
    }).join("");
    return `<article class="profile-card"><h3>${escapeHtml(tableName)}</h3>` +
      `<p class="empty">${escapeHtml(table.row_count)} rows · ${escapeHtml(table.column_count)} columns · ` +
      `${escapeHtml(table.duplicate_like_rows)} duplicate-like rows</p>` +
      `<div class="table-wrap"><table><thead><tr><th>Column</th><th>Type</th><th>NULL / blank</th><th>Range</th><th>Warnings</th></tr></thead>` +
      `<tbody>${rows}</tbody></table></div></article>`;
  }).join("");
}

async function loadProfile() {
  const dataset = datasetSelect.value;
  if (!dataset) {
    profileContent.innerHTML = '<p class="empty">Select a dataset to view its profile.</p>';
    return;
  }
  try {
    const payload = await request(`/api/v1/datasets/${encodeURIComponent(dataset)}/profile`);
    renderProfile(payload.profile);
  } catch (error) {
    profileContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

function renderResult(payload, evidence) {
  answerCard.hidden = false;
  document.querySelector("#outcome-status").textContent = payload.status || "UNKNOWN";
  document.querySelector("#answer-text").textContent = payload.answer || "No answer was returned.";
  document.querySelector("#run-id").textContent = payload.run_id ? `Run: ${payload.run_id}` : "No run ID";
  document.querySelector("#evidence-id").textContent = payload.evidence_id ? `Evidence: ${payload.evidence_id}` : "";
  const warningList = document.querySelector("#warnings");
  warningList.replaceChildren(...(payload.warnings || []).map((warning) => {
    const item = document.createElement("li");
    item.textContent = warning;
    return item;
  }));
  const summary = payload.result_summary || {};
  document.querySelector("#result-tab").innerHTML = renderSummary(summary);
  document.querySelector("#checks-tab").innerHTML = renderChecks(evidence?.checks || []);
  document.querySelector("#evidence-tab").innerHTML = `<pre>${escapeHtml(JSON.stringify(evidence || payload, null, 2))}</pre>`;
}

async function analyze(event) {
  event.preventDefault();
  if (busy || !datasetSelect.value) return;
  const question = questionInput.value.trim();
  if (!question) return;
  busy = true;
  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analyzing…";
  showError("");
  offlineMessage.hidden = true;
  setStages("running");
  try {
    const payload = await request("/api/v1/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify({ dataset_id: datasetSelect.value, question, mode: "question_answering" }),
    });
    let evidence = null;
    if (payload.run_id) {
      try { evidence = await request(`/api/v1/runs/${encodeURIComponent(payload.run_id)}/evidence`); } catch (_) { /* evidence is optional */ }
    }
    setStages("done");
    renderResult(payload, evidence);
  } catch (error) {
    setStages("waiting");
    if (error.code === "MODEL_UNAVAILABLE" || /model.*unavailable/i.test(error.message)) offlineMessage.hidden = false;
    showError(error.message);
  } finally {
    busy = false;
    analyzeButton.disabled = false;
    analyzeButton.textContent = "Analyze";
  }
}

async function loadAudit() {
  try {
    const payload = await request("/api/v1/audit?limit=50");
    const events = payload.events || [];
    if (!events.length) {
      auditContent.innerHTML = '<p class="empty">No audit events yet.</p>';
      return;
    }
    auditContent.innerHTML = `<table><thead><tr><th>Event</th><th>Run</th><th>Status</th><th>Time</th></tr></thead><tbody>` +
      events.map((event) => `<tr><td>${escapeHtml(event.event_type)}</td><td>${escapeHtml(event.run_id || "-")}</td>` +
        `<td>${escapeHtml(event.payload?.status || "-")}</td><td>${escapeHtml(event.created_at)}</td></tr>`).join("") +
      "</tbody></table>";
  } catch (error) {
    auditContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", async () => {
    document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    document.querySelectorAll(".view").forEach((view) => { view.hidden = true; });
    document.querySelector(`#${button.dataset.view}-view`).hidden = false;
    if (button.dataset.view === "profile") await loadProfile();
    if (button.dataset.view === "dashboard") await loadDashboard();
    if (button.dataset.view === "audit") await loadAudit();
  });
});

document.querySelectorAll(".example-button").forEach((button) => {
  button.addEventListener("click", () => { questionInput.value = button.textContent; questionInput.focus(); });
});
document.querySelectorAll(".tab-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-button").forEach((item) => {
      item.classList.remove("active");
      item.setAttribute("aria-selected", "false");
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => { panel.hidden = true; });
    button.classList.add("active");
    button.setAttribute("aria-selected", "true");
    document.querySelector(`#${button.dataset.tab}`).hidden = false;
  });
});

datasetSelect.addEventListener("change", loadProfile);
datasetSelect.addEventListener("change", loadDashboard);
document.querySelector("#refresh-profile").addEventListener("click", loadProfile);
document.querySelector("#refresh-dashboard").addEventListener("click", loadDashboard);
document.querySelector("#refresh-audit").addEventListener("click", loadAudit);
questionForm.addEventListener("submit", analyze);

setStages("waiting");
checkApi().then(() => loadDatasets()).catch((error) => showError(error.message));
