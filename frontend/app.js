const apiStatus = document.querySelector("#api-status");
const datasetSelect = document.querySelector("#dataset-select");
const questionForm = document.querySelector("#question-form");
const questionInput = document.querySelector("#question");
const analyzeButton = document.querySelector("#analyze-button");
const pageError = document.querySelector("#page-error");
const offlineMessage = document.querySelector("#offline-message");
const answerCard = document.querySelector("#answer-card");
const profileContent = document.querySelector("#profile-content");
const insightsContent = document.querySelector("#insights-content");
const permissionsContent = document.querySelector("#permissions-content");
const auditContent = document.querySelector("#audit-content");
const evaluationContent = document.querySelector("#evaluation-content");
const settingsContent = document.querySelector("#settings-content");
const importResult = document.querySelector("#import-result");

let busy = false;

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function formatValue(value) {
  if (value === null || value === undefined) return "NOT RUN";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function showError(message) { pageError.textContent = message; pageError.hidden = !message; }

function setStages(state) {
  document.querySelectorAll("#stage-list li").forEach((item) => {
    item.classList.remove("done", "active");
    const label = item.querySelector("strong");
    if (state === "running") { item.classList.add("active"); label.textContent = "Running"; }
    else if (state === "done") { item.classList.add("done"); label.textContent = "Complete"; }
    else { label.textContent = "Waiting"; }
  });
}

async function request(path, options = {}) {
  const response = await fetch(path, { headers: { Accept: "application/json" }, ...options });
  let payload = {};
  try { payload = await response.json(); } catch (_) { payload = {}; }
  if (!response.ok) {
    const error = payload.error || {};
    const exception = new Error(error.message || "Request could not be completed.");
    exception.code = error.code;
    throw exception;
  }
  return payload;
}

async function checkApi() {
  try {
    const payload = await request("/api/v1/health");
    apiStatus.innerHTML = '<span class="status-dot"></span>API online';
    apiStatus.className = "status-chip";
    document.querySelector("#model-status")?.replaceChildren();
    return payload;
  } catch (_) {
    apiStatus.innerHTML = '<span class="status-dot"></span>API unavailable';
    apiStatus.className = "status-chip status-muted";
    return null;
  }
}

async function loadDatasets() {
  const payload = await request("/api/v1/datasets");
  const datasets = payload.datasets || [];
  datasetSelect.replaceChildren();
  if (!datasets.length) {
    const option = new Option("No permitted datasets", ""); option.disabled = true; option.selected = true; datasetSelect.add(option); return;
  }
  datasets.forEach((dataset) => { const id = typeof dataset === "string" ? dataset : dataset.dataset_id; datasetSelect.add(new Option(id, id)); });
  document.querySelector("#dataset-metric").textContent = datasetSelect.value;
  await loadProfile();
}

function renderTable(columns, rows) {
  if (!columns?.length || !rows?.length) return '<p class="empty">No rows returned.</p>';
  return `<div class="table-wrap"><table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function getNumericChartData(columns, rows) {
  if (!Array.isArray(columns) || !Array.isArray(rows) || !rows.length) return null;
  const numericIndex = columns.findIndex((_, index) => {
    const values = rows.map((row) => Number(row?.[index])).filter((value) => Number.isFinite(value));
    return values.length >= Math.max(2, Math.ceil(rows.length / 2));
  });
  if (numericIndex < 0) return null;
  const labelIndex = columns.findIndex((_, index) => index !== numericIndex && rows.some((row) => {
    const value = row?.[index];
    return value !== null && value !== undefined && value !== "" && !Number.isFinite(Number(value));
  }));
  const valueIndex = numericIndex;
  const items = rows.map((row) => ({
    label: row?.[labelIndex >= 0 ? labelIndex : 0] ?? `Row ${rows.indexOf(row) + 1}`,
    value: Number(row?.[valueIndex]),
  })).filter((item) => Number.isFinite(item.value)).slice(0, 12);
  return items.length ? { label: columns[labelIndex >= 0 ? labelIndex : 0], value: columns[valueIndex], items } : null;
}

function renderResultChart(summary) {
  if (summary?.truncated) return "";
  const data = getNumericChartData(summary?.columns, summary?.rows);
  if (!data) return "";
  const max = Math.max(...data.items.map((item) => Math.abs(item.value)), 1);
  const bars = data.items.map((item) => `<div class="bar" style="--height:${Math.max(8, Math.round((Math.abs(item.value) / max) * 100))}%"><span>${escapeHtml(String(item.label))}</span></div>`).join("");
  const rows = data.items.map((item) => `<tr><td>${escapeHtml(item.label)}</td><td>${escapeHtml(formatValue(item.value))}</td></tr>`).join("");
  return `<section class="chart-box result-chart" aria-labelledby="result-chart-title"><span class="section-kicker">VISUAL SUMMARY</span><h4 id="result-chart-title">${escapeHtml(data.value)} by ${escapeHtml(data.label)}</h4><div class="bar-chart" role="img" aria-label="Bar chart of ${escapeHtml(data.value)} by ${escapeHtml(data.label)}">${bars}</div><p class="chart-summary">Highest visible value: <strong>${escapeHtml(formatValue(Math.max(...data.items.map((item) => item.value))))}</strong>. The table below is the accessible data alternative.</p><div class="table-wrap"><table><thead><tr><th>${escapeHtml(data.label)}</th><th>${escapeHtml(data.value)}</th></tr></thead><tbody>${rows}</tbody></table></div></section>`;
}

function renderProfile(profile) {
  const entries = Object.entries(profile || {});
  if (!entries.length) { profileContent.innerHTML = '<p class="empty">No permitted profile is available.</p>'; return; }
  profileContent.innerHTML = entries.map(([tableName, table]) => {
    const columns = Object.entries(table.columns || {});
    const rows = columns.map(([name, column]) => {
      const range = column.numeric_range || column.date_range || {};
      const rangeText = range.min != null || range.max != null ? `${escapeHtml(range.min ?? "-")} → ${escapeHtml(range.max ?? "-")}` : "-";
      const warnings = (column.warnings || []).join(", ") || "-";
      const markerCount = Object.values(column.missing_marker_counts || {}).reduce((sum, value) => sum + Number(value || 0), 0);
      return `<tr><td>${escapeHtml(name)}</td><td>${escapeHtml(column.inferred_type || "unknown")}</td><td>${escapeHtml(column.null_count)} / ${escapeHtml(column.blank_count)} / ${markerCount}</td><td>${rangeText}</td><td>${escapeHtml(warnings)}</td></tr>`;
    }).join("");
    return `<article class="profile-card"><h3>${escapeHtml(tableName)}</h3><p class="empty">${escapeHtml(table.row_count)} rows · ${escapeHtml(table.column_count)} columns · ${escapeHtml(table.duplicate_like_rows)} duplicate-like rows</p><div class="table-wrap"><table><thead><tr><th>Column</th><th>Type</th><th>NULL / blank / markers</th><th>Range</th><th>Warnings</th></tr></thead><tbody>${rows}</tbody></table></div></article>`;
  }).join("");
}

async function loadProfile() {
  const dataset = datasetSelect.value;
  if (!dataset) { profileContent.innerHTML = '<p class="empty">Select a dataset to view its profile.</p>'; return; }
  try { const payload = await request(`/api/v1/datasets/${encodeURIComponent(dataset)}/profile`); renderProfile(payload.profile); }
  catch (error) { profileContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`; }
}

function renderResult(payload, evidence) {
  answerCard.hidden = false;
  document.querySelector("#outcome-status").textContent = payload.status || "UNKNOWN";
  document.querySelector("#answer-text").textContent = payload.answer || "No answer was returned.";
  document.querySelector("#run-id").textContent = payload.run_id ? `Run: ${payload.run_id}` : "No run ID";
  document.querySelector("#evidence-id").textContent = payload.evidence_id ? `Evidence: ${payload.evidence_id}` : "";
  const warningList = document.querySelector("#warnings"); warningList.replaceChildren(...(payload.warnings || []).map((warning) => { const item = document.createElement("li"); item.textContent = warning; return item; }));
  const summary = payload.result_summary || {};
  document.querySelector("#result-tab").innerHTML = summary.columns ? renderResultChart(summary) + renderTable(summary.columns, summary.rows || []) + (summary.truncated ? '<div class="alert alert-warning">Showing a truncated result. Totals must not be inferred.</div>' : "") : `<pre>${escapeHtml(JSON.stringify(summary, null, 2))}</pre>`;
  document.querySelector("#checks-tab").innerHTML = `<pre>${escapeHtml(JSON.stringify(evidence?.checks || [], null, 2))}</pre>`;
  document.querySelector("#evidence-tab").innerHTML = `<pre>${escapeHtml(JSON.stringify(evidence || payload, null, 2))}</pre>`;
}

async function analyze(event) {
  event.preventDefault(); if (busy || !datasetSelect.value) return;
  const question = questionInput.value.trim(); if (!question) return;
  busy = true; analyzeButton.disabled = true; analyzeButton.innerHTML = "<span>Analyzing…</span>"; showError(""); offlineMessage.hidden = true; setStages("running");
  try {
    const payload = await request("/api/v1/analyze", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify({ dataset_id: datasetSelect.value, question, mode: "question_answering" }) });
    let evidence = null; if (payload.run_id) { try { evidence = await request(`/api/v1/runs/${encodeURIComponent(payload.run_id)}/evidence`); } catch (_) {} }
    setStages("done"); renderResult(payload, evidence);
  } catch (error) { setStages("waiting"); if (error.code === "MODEL_UNAVAILABLE" || /model.*unavailable/i.test(error.message)) offlineMessage.hidden = false; showError(error.message); }
  finally { busy = false; analyzeButton.disabled = false; analyzeButton.innerHTML = "<span>Analyze</span><span aria-hidden=\"true\">→</span>"; }
}

function renderInsights(payload) {
  const hotspots = payload.missingness_hotspots || [];
  const tableSummary = payload.table_summary || [];
  const bars = hotspots.slice(0, 8).map((item) => `<div class="bar" style="--height:${Math.max(8, Math.min(100, item.missing_percent || 0))}%"><span>${escapeHtml(item.column)}</span></div>`).join("");
  const totalRows = tableSummary.reduce((sum, item) => sum + Number(item.rows || 0), 0);
  let cursor = 0;
  const palette = ["#8E9867", "#E1937D", "#8D6959", "#9fb8b1", "#c8b69b", "#6f8f96"];
  const segments = tableSummary.map((item, index) => {
    const share = totalRows ? (Number(item.rows || 0) / totalRows) * 100 : 0;
    const start = cursor; cursor += share;
    return `${palette[index % palette.length]} ${start.toFixed(2)}% ${cursor.toFixed(2)}%`;
  }).join(", ");
  const legend = tableSummary.map((item, index) => `<div class="legend-item"><span class="legend-swatch" style="background:${palette[index % palette.length]}"></span><span>${escapeHtml(item.table)}</span><strong>${escapeHtml(item.rows)} rows</strong></div>`).join("");
  const hotspotRows = hotspots.slice(0, 8).map((item) => `<tr><td>${escapeHtml(item.table)}.${escapeHtml(item.column)}</td><td>${escapeHtml(item.missing_count)}</td><td>${escapeHtml(Number(item.missing_percent || 0).toFixed(1))}%</td></tr>`).join("");
  insightsContent.innerHTML = `<article class="insight-card"><span class="section-kicker">MISSINGNESS HOTSPOTS</span><h3>Where quality needs attention</h3><div class="chart-box"><div class="bar-chart" role="img" aria-label="Bar chart of missingness percentage by column">${bars || '<p class="empty">No missingness hotspots detected.</p>'}</div><div class="table-wrap"><table><thead><tr><th>Column</th><th>Missing</th><th>Rate</th></tr></thead><tbody>${hotspotRows || '<tr><td colspan="3">No missingness hotspots detected.</td></tr>'}</tbody></table></div></div><p class="empty">Observed profile signals only. Investigate changes; no causal conclusion is made.</p></article><article class="insight-card"><span class="section-kicker">DATASET COVERAGE</span><h3>Tables in this workspace</h3><div class="donut" role="img" aria-label="Donut chart of rows by table" style="background:conic-gradient(${segments || "#d9d2ca 0 100%"})"></div><div class="chart-legend">${legend || '<p class="empty">No table rows available.</p>'}</div><p class="chart-summary">${escapeHtml(totalRows)} total rows across ${escapeHtml(tableSummary.length)} permitted tables.</p></article><article class="insight-card"><span class="section-kicker">INTERPRETATION</span><h3>Evidence-first by design</h3><p>Insights are deterministic summaries from the permitted profile. Every analytical answer should link back to its evidence and checks.</p><div class="alert alert-warning">${escapeHtml((payload.warnings || [])[0] || "Observed data only")}</div></article>`;
}

async function loadInsights() { try { renderInsights(await request(`/api/v1/datasets/${encodeURIComponent(datasetSelect.value)}/insights`)); } catch (error) { insightsContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`; } }

async function loadPermissions() {
  try { const payload = await request(`/api/v1/permissions?dataset_id=${encodeURIComponent(datasetSelect.value || "demo")}`); permissionsContent.innerHTML = `<article class="permissions-card"><span class="section-kicker">ROLE BADGE</span><h3>${escapeHtml(payload.role || "Unknown")}</h3><p>${escapeHtml(payload.notice || "Role is resolved by the backend.")}</p><div class="insight-stat"><span>Policy action</span><strong>${escapeHtml(payload.action)}</strong></div><div class="insight-stat"><span>Reason</span><strong>${escapeHtml(payload.reason_code)}</strong></div><h3>Permitted tables</h3><ul>${(payload.allowed_tables || []).map((table) => `<li>${escapeHtml(table)}</li>`).join("")}</ul></article><article class="permissions-card"><span class="section-kicker">ACCESS BOUNDARY</span><h3>What this role can see</h3><p>Protected columns are filtered before model context and checked again before execution. A UI control cannot grant access.</p><div class="alert alert-warning">Approval is simulated in this prototype.</div></article>`; } catch (error) { permissionsContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`; }
}

async function loadAudit() { try { const payload = await request("/api/v1/audit?limit=50"); const events = payload.events || []; auditContent.innerHTML = events.length ? `<table><thead><tr><th>Event</th><th>Run</th><th>Status</th><th>Time</th></tr></thead><tbody>${events.map((event) => `<tr><td>${escapeHtml(event.event_type)}</td><td>${escapeHtml(event.run_id || "-")}</td><td>${escapeHtml(event.payload?.status || "-")}</td><td>${escapeHtml(event.created_at)}</td></tr>`).join("")}</tbody></table>` : '<p class="empty">No audit events yet.</p>'; } catch (error) { auditContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`; } }

function renderEvaluation(payload) {
  const metrics = payload.metrics || {};
  const metricCards = Object.entries(metrics).map(([key, value]) => `<div class="metric-card"><span class="metric-label">${escapeHtml(key.replaceAll("_", " "))}</span><strong>${escapeHtml(formatValue(value))}</strong><small>Measured output only</small></div>`).join("");
  evaluationContent.innerHTML = `<div class="metric-strip">${metricCards}</div><article class="evaluation-card"><span class="section-kicker">ABLATION</span><h3>Configuration ladder</h3><div class="table-wrap"><table><thead><tr><th>Configuration</th><th>Execution accuracy</th><th>Valid SQL</th><th>Median latency</th><th>P95 latency</th></tr></thead><tbody>${(payload.ablation || []).map((row) => `<tr><td>${escapeHtml(row.configuration)}</td><td>${escapeHtml(formatValue(row.execution_accuracy))}</td><td>${escapeHtml(formatValue(row.valid_sql_rate))}</td><td>${escapeHtml(formatValue(row.median_latency_ms))}</td><td>${escapeHtml(formatValue(row.p95_latency_ms))}</td></tr>`).join("")}</tbody></table></div><div class="alert alert-warning">Only measured numbers are shown. Current evaluation status: ${escapeHtml(payload.status || "TBD / NOT RUN")}.</div></article>`;
}
async function loadEvaluation() { try { renderEvaluation(await request("/api/v1/evaluation")); } catch (error) { evaluationContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`; } }

async function loadSettings() { try { const payload = await request("/api/v1/settings"); settingsContent.innerHTML = `<article class="settings-card"><span class="section-kicker">MODEL</span><h3>${escapeHtml(payload.model.name)}</h3><p>Status: ${escapeHtml(payload.model.status)}</p><p>Endpoint: ${escapeHtml(payload.model.base_url)}</p></article><article class="settings-card"><span class="section-kicker">LIMITS</span><h3>Read-only guardrails</h3><ul>${Object.entries(payload.limits || {}).map(([key, value]) => `<li><strong>${escapeHtml(key.replaceAll("_", " "))}:</strong> ${escapeHtml(value)}</li>`).join("")}</ul></article><article class="settings-card"><span class="section-kicker">RETENTION</span><h3>Local metadata</h3><p>${escapeHtml(payload.retention)}</p></article>`; } catch (error) { settingsContent.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`; } }

async function importDataset(event) {
  event.preventDefault(); const file = document.querySelector("#import-file").files[0]; if (!file) { importResult.innerHTML = '<p class="empty">Choose a CSV or XLSX file first.</p>'; return; }
  const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ""; bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  try { const payload = await request("/api/v1/datasets/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: file.name, content_base64: btoa(binary) }) }); importResult.innerHTML = `<span class="section-kicker">IMPORTED</span><h3>${escapeHtml(payload.dataset_id)}</h3><p>SHA-256: <code>${escapeHtml(payload.source_sha256)}</code></p><pre>${escapeHtml(JSON.stringify(payload.summary, null, 2))}</pre>`; await loadDatasets(); } catch (error) { importResult.innerHTML = `<div class="alert alert-error">${escapeHtml(error.message)}</div>`; }
}

async function openView(view) {
  document.querySelectorAll(".view").forEach((item) => { item.hidden = true; });
  document.querySelector(`#${view}-view`).hidden = false;
  if (view === "profile") await loadProfile(); if (view === "insights") await loadInsights(); if (view === "permissions") await loadPermissions(); if (view === "audit") await loadAudit(); if (view === "evaluation") await loadEvaluation(); if (view === "settings") await loadSettings();
}

document.querySelectorAll(".nav-button").forEach((button) => button.addEventListener("click", async () => { document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active")); button.classList.add("active"); await openView(button.dataset.view); }));
document.querySelectorAll(".example-button").forEach((button) => button.addEventListener("click", () => { questionInput.value = button.textContent; questionInput.focus(); }));
document.querySelectorAll(".tab-button").forEach((button) => button.addEventListener("click", () => { document.querySelectorAll(".tab-button").forEach((item) => { item.classList.remove("active"); item.setAttribute("aria-selected", "false"); }); document.querySelectorAll(".tab-panel").forEach((panel) => { panel.hidden = true; }); button.classList.add("active"); button.setAttribute("aria-selected", "true"); document.querySelector(`#${button.dataset.tab}`).hidden = false; }));
datasetSelect.addEventListener("change", async () => { document.querySelector("#dataset-metric").textContent = datasetSelect.value; await loadProfile(); });
document.querySelector("#refresh-profile").addEventListener("click", loadProfile); document.querySelector("#refresh-insights").addEventListener("click", loadInsights); document.querySelector("#refresh-audit").addEventListener("click", loadAudit); document.querySelector("#refresh-evaluation").addEventListener("click", loadEvaluation); document.querySelector("#import-form").addEventListener("submit", importDataset); questionForm.addEventListener("submit", analyze);

setStages("waiting"); checkApi().then(() => loadDatasets()).catch((error) => showError(error.message));
