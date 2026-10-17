"use strict";
const $ = id => document.getElementById(id);
let selected = null, result = null, timer = null, busy = false, revision = 0;
const terminal = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);
async function request(path, options = {}, text = false) {
  const headers = new Headers(options.headers || {});
  if ($("api-key").value) headers.set("X-API-Key", $("api-key").value);
  const response = await fetch(path, {...options, headers, signal: AbortSignal.timeout(30000)});
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try { const data = await response.json(); detail = typeof data.detail === "string" ? data.detail : detail; } catch (_) {}
    throw new Error(detail);
  }
  return text ? response.text() : response.json();
}
function message(error) { $("message").textContent = error instanceof Error ? error.message : error; }
async function health() {
  try {
    const data = await request("/health/ready");
    $("health").textContent = data.status === "ok" ? "Service ready" : "Service degraded";
    $("dependencies").textContent = `Database: ${data.database} · Queue: ${data.queue} · Storage: ${data.storage}`;
  } catch (error) { $("health").textContent = "Service unavailable or authentication required"; $("dependencies").textContent = error.message; }
}
async function jobs() {
  const data = await request("/api/v1/jobs?limit=12&deployment_id=video-summary-v1");
  $("jobs").replaceChildren();
  for (const job of data) {
    const button = document.createElement("button"); button.type = "button";
    button.textContent = job.status; if (job.job_id === selected) button.className = "current";
    const id = document.createElement("span"); id.textContent = job.job_id; button.append(id);
    button.addEventListener("click", () => selectJob(job.job_id)); $("jobs").append(button);
  }
  if (!data.length) $("jobs").textContent = "No jobs yet.";
  else if (!selected) selectJob(data[0].job_id);
}
function clearDetail() {
  result = null; $("result").hidden = true; $("job-error").textContent = "";
  $("timings").replaceChildren(); $("events").replaceChildren();
  $("attempts").textContent = "Loading…"; $("lineage").textContent = "Available after a successful result.";
  $("cancel").disabled = true; $("retry").disabled = true;
}
async function detail(id, token) {
  const [job, events, attempts] = await Promise.all([
    request(`/api/v1/jobs/${id}`), request(`/api/v1/jobs/${id}/events`), request(`/api/v1/jobs/${id}/attempts`)
  ]);
  if (token !== revision) return;
  clearDetail(); $("job-status").textContent = job.status; $("job-error").textContent = job.error || "";
  $("cancel").disabled = !["PENDING", "QUEUED"].includes(job.status);
  $("retry").disabled = job.status !== "FAILED";
  $("attempts").textContent = JSON.stringify(attempts, null, 2);
  for (const event of events) {
    const li = document.createElement("li"); li.textContent = `${event.event} · ${new Date(event.timestamp).toLocaleString()}${event.trace_id ? ` · trace ${event.trace_id}` : ""}`;
    $("events").append(li);
  }
  if (job.result) {
    result = job.result; $("result").hidden = false;
    $("summary").textContent = result.summary || ""; $("category").textContent = result.category || "";
    $("result-mode").textContent = result.model_version === "fake" ? "SIMULATED · fake worker" : "Model inference";
    $("lineage").textContent = JSON.stringify({model: result.model_version, revision: result.model_revision, instance: result.model_instance_id, lineage: result.lineage}, null, 2);
    for (const [stage, seconds] of Object.entries(result.timings || {})) {
      const tr = document.createElement("tr"), name = document.createElement("td"), value = document.createElement("td");
      name.textContent = stage; value.textContent = typeof seconds === "number" ? seconds.toFixed(3) : String(seconds);
      tr.append(name, value); $("timings").append(tr);
    }
  }
  return job.status;
}
async function poll(id, token) {
  try {
    const status = await detail(id, token);
    if (token !== revision) return;
    await jobs();
    if (!terminal.has(status)) timer = setTimeout(() => poll(id, token), 2500);
  } catch (error) { if (token === revision) message(`Refresh stopped: ${error.message}. Use Refresh to reconnect.`); }
}
function selectJob(id) {
  if (!/^[0-9a-f-]{36}$/i.test(id)) { message("Enter a valid job UUID."); return; }
  clearTimeout(timer); revision++; selected = id; clearDetail();
  $("selected-id").textContent = id; $("job-status").textContent = "Loading…"; $("job-id").value = id;
  message(""); poll(id, revision);
}
$("submit-form").addEventListener("submit", async event => {
  event.preventDefault(); if (busy) return;
  const file = $("video").files[0]; if (!file) return;
  if (file.size > 64 * 1024 * 1024) { message("Choose a video no larger than 64 MiB for this demo."); return; }
  busy = true; $("submit").disabled = true; message("Uploading and validating video…");
  const body = new FormData(); body.append("video", file);
  if ($("transcript").value) body.append("transcript", $("transcript").value);
  try {
    const job = await request("/api/v1/jobs", {method: "POST", body, headers: {"Idempotency-Key": crypto.randomUUID()}});
    selectJob(job.job_id);
  } catch (error) { message(`Submission could not be confirmed: ${error.message}. Check Recent jobs before submitting again.`); }
  finally { busy = false; $("submit").disabled = false; }
});
$("open-job").addEventListener("click", () => selectJob($("job-id").value.trim()));
$("refresh").addEventListener("click", () => { health(); jobs().catch(message); if (selected) selectJob(selected); });
for (const action of ["cancel", "retry"]) $(action).addEventListener("click", async () => {
  const id = selected; if (!id) return; $(action).disabled = true;
  try { await request(`/api/v1/jobs/${id}/${action}`, {method: "POST"}); if (selected === id) selectJob(id); }
  catch (error) { if (selected === id) selectJob(id); message(error); }
});
$("download").addEventListener("click", () => {
  if (!result) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: "application/json"}));
  const link = document.createElement("a"); link.href = url; link.download = `${selected}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("load-metrics").addEventListener("click", async () => {
  try { $("metrics").textContent = await request("/metrics", {}, true); } catch (error) { $("metrics").textContent = error.message; }
});
window.addEventListener("pagehide", () => { clearTimeout(timer); revision++; });
health(); jobs().catch(message);
