"use strict";
const el = id => document.getElementById(id);
let timer, busy = false, paused = false;
const history = [];
async function get(path, json = true) {
  const key = el("key").value.trim();
  const response = await fetch(path, {headers: key ? {"X-API-Key": key} : {}, cache: "no-store", signal: AbortSignal.timeout(10000)});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return json ? response.json() : response.text();
}
async function refresh() {
  if (busy) return;
  busy = true;
  const results = await Promise.allSettled([get("/health/ready"), get("/metrics", false), get("/api/v1/jobs?limit=12"), get("/local/gpu")]);
  for (const [index, id] of [[0,"health"], [1,"metrics"]]) {
    const r = results[index];
    el(id).textContent = r.status === "fulfilled" ? (typeof r.value === "string" ? r.value : JSON.stringify(r.value, null, 2)) : `Unavailable: ${r.reason.message}`;
  }
  el("counts").replaceChildren();
  if (results[1].status === "fulfilled") {
    for (const line of results[1].value.split("\n")) {
      if (/^video_jobs\{|^video_oldest_queued_job_seconds\s/.test(line)) {
        const card = document.createElement("span"); card.textContent = line; el("counts").append(card);
      }
    }
  }
  el("jobs").replaceChildren();
  if (results[2].status === "fulfilled") {
    const jobs = results[2].value.jobs || results[2].value;
    if (Array.isArray(jobs)) for (const job of jobs) {
      const row = document.createElement("tr");
      for (const value of [job.job_id || job.id, job.status, job.created_at]) {
        const cell = document.createElement("td"); cell.textContent = value ?? "—"; row.append(cell);
      }
      el("jobs").append(row);
    }
  } else {const row = document.createElement("tr"); const cell = document.createElement("td"); cell.textContent = `Unavailable: ${results[2].reason.message}`; row.append(cell); el("jobs").append(row);}
  const gpu = results[3];
  const device = gpu.status === "fulfilled" && gpu.value.available ? gpu.value.devices[0] : null;
  el("gpu").textContent = device ? `${device.name} · ${device.utilization_percent}% utilization · ${device.memory_used_mib}/${device.memory_total_mib} MiB · ${device.temperature_c} °C · ${gpu.value.timestamp}` : "Host GPU telemetry unavailable";
  history.push(device ? device.utilization_percent : null); if (history.length > 60) history.shift();
  el("chart").replaceChildren();
  let segment = [];
  function draw() { if (!segment.length) return; const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline"); line.setAttribute("points", segment.join(" ")); el("chart").append(line); segment = []; }
  history.forEach((value, i) => { if (value === null) draw(); else segment.push(`${i * 600 / 59},${120 - Math.max(0,Math.min(100,value)) * 1.2}`); }); draw();
  el("state").textContent = `${paused ? "Paused" : "Live · every 5 seconds"} · ${new Date().toLocaleTimeString()} · ${results.filter(r => r.status === "fulfilled").length}/4 sources reachable`;
  busy = false;
}
el("refresh").addEventListener("click", refresh);
el("pause").addEventListener("click", () => {paused = !paused; el("pause").textContent = paused ? "Resume" : "Pause"; clearInterval(timer); if (!paused) {refresh(); timer = setInterval(refresh, 5000);} else el("state").textContent = "Paused";});
refresh(); timer = setInterval(refresh, 5000);
