# Connected Chrome demo review — 2026-10-17

The local preview at `http://127.0.0.1:8080/` was inspected in the connected
Chrome browser with the GPU Compose stack running. The initial desktop page
showed healthy database, queue and storage readiness. The newest persisted
real-model job (`abc40dcd-67b7-46c5-ab3a-fac5c8902e23`) loaded without a new
submission after the asset version changed. Its summary/category, stage
timings, submitted-to-succeeded event history, attempt record and pinned model,
source, prompt, taxonomy and inference-configuration lineage were visible.

The saved recovery job (`bd4908b7-be1f-4d39-b86a-59d54ebda05d`) also showed
the deadline-exceeded event, explicit retry and success, with one failed timeout
attempt followed by a successful second attempt. This is historical persisted
evidence; no worker was interrupted during the browser review.

The `/operations` page reached all four sources and displayed persisted job
counts, queue age, recent job history, process-local HTTP metrics and device-wide
RTX 2080 utilization, memory and temperature. The page states the limits of
those measurements. The desktop cards and job detail were visually inspected;
no overlapping controls or broken content were found.

At a 390 px viewport, the main page had no horizontal overflow. The long recent
job list initially pushed the selected result far down the page, so the list was
bounded to a 250 px scrolling region. The result remained accessible below it.
The browser's narrow operations screenshot was scaled incorrectly by the
connected capture tool, so that view was checked through DOM geometry and
content rather than accepted as visual proof. The viewport override was reset.

The preview initially displayed fresh HTML with a cached older `demo.js`, leaving
the detail panel empty despite the new auto-open behavior. Versioning the script
URL forced the new code to load; demo assets now return `Cache-Control: no-store`
for later local changes. That header was verified from a fresh preview on port
8081. After reload the latest job opened automatically.

Focused checks: nine preview-server Python tests, five main-page Node tests,
two operations Node tests and `git diff --check` passed. The broader local
service test attempt could not create its pytest temporary directories in this
session (`PermissionError`); the published GitHub Actions CPU and Compose jobs
passed separately. This browser pass did not submit a new video, measure GPU
capacity or record a walkthrough. The existing [GPU submission report](demo_shapes_probe.json)
and [delivery evidence](delivery_status.md) cover those separate claims.
