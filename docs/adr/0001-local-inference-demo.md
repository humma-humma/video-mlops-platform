# ADR 0001: demonstrate inference infrastructure on the existing GPU

Status: accepted project direction, 2026-10-10.

## Context and decision

The project demonstrates ML infrastructure and system-design skills using an
existing video model. The owner chose the no-additional-cloud-spend route.
Operate the local Docker/GPU stack and expose a small loopback-only UI. Defer
AWS provisioning and keep cloud deployment explicitly unverified.

Use the existing FastAPI, PostgreSQL, Celery/Valkey and S3-compatible storage
boundaries. PostgreSQL owns job state, attempts and the committed result URI;
the broker coordinates execution. An undispatched database job can be
redispatched. Object storage holds videos, transcripts and per-attempt result
artifacts. Avoid placing large media in job rows or task messages.

The GPU worker keeps a model instance warm. Default single-worker concurrency
and prefetch 1 bound contention on the available device. Client concurrency
creates queueing, not additional GPU capacity. Measure batching and alternative
concurrency before changing those settings.

The UI is served by FastAPI after image rebuild. A temporary local preview
forwards only known routes to the existing API because this agent cannot
access Docker's engine. This adds no model server, alternate job database or
second execution path. The preview is not a production gateway.

## Alternatives and consequences

- Running inference inside a synchronous HTTP request simplifies the first
  example but ties client lifetime to expensive, variable-duration execution.
  Durable asynchronous jobs support reconnecting, queueing and inspection.
- Keeping authoritative status only in the broker couples result availability
  to transient coordination state. Database state makes recovery inspectable,
  at the cost of explicit dispatch/reconciliation logic.
- A permanently hosted cloud GPU makes the demo independently available but
  adds idle and supporting-service costs. Local execution requires the PC to
  be on; recorded evidence will provide an honest offline fallback.
- Kubernetes and distributed training are deferred. Neither is required to
  demonstrate the measured single-host serving design; neither is claimed.

## Guarantees and limits to defend

Database claims and generation checks suppress duplicate/stale state commits.
This is **not exactly-once GPU execution** or an atomic transaction across
database, broker and object storage. Crashes can leave orphan objects; cleanup
remains unfinished. The dispatcher rechecks durable queued jobs, while expired
running attempts become failed and require policy-appropriate recovery/retry.
Do not promise immediate transparent recovery from every worker loss.

Single-host storage and GPU failure domains remain. The API key is a demo
access control, not per-tenant identity or authorization. Current telemetry
provides logs, counters, trace correlation and a read-only host GPU dashboard;
durable metric storage, alerting and complete exported spans remain open. The
architecture is defensible because these
boundaries and missing guarantees are visible rather than implied away.
