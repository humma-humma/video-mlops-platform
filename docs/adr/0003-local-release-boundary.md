# ADR 0003: separate operational rollback from model promotion

Status: accepted and exercised locally, 2026-10-17.

## Context and decision

The service can exercise deployment safety before it has a quality-qualified
500M model candidate. Treat these as different decisions. The evaluation gate
compares measured reports with a pinned baseline and explicit policy. Its
[provisional rejection](../../reports/local_demo_gate.json) uses 2.2B research
experiments and cannot authorize deployment of the 500M serving workload.

The operational exercise snapshots the current API, dispatcher and worker
image IDs, builds a candidate that exposes an observable release identity,
checks a real request and stored result, then restores the prior image IDs.
The schema is unchanged across this pair; no downgrade or volume deletion is
part of rollback. Reports will retain image IDs, job IDs, result hashes and
lineage. Local tags ease switching, while image IDs identify content. The
[execution report](../../reports/release_demo_20261017105931.json) and its
candidate/rollback probes record the completed sequence.

## Alternatives and consequences

- Relaxing thresholds until a candidate passes would make the gate poor
  evidence. A recorded rejection and an open promotion task are more honest.
- Reverting database migrations during image rollback risks deleting attempts,
  events and result references. A compatible additive schema avoids that risk.
- A cloud registry and automated canary would add cost and new failure domains
  before the single-host sequence is proven. This demo uses local Docker
  images; remote CI, registry promotion and signed delivery remain open.

The working tree is currently uncommitted. The release report must mark that
fact; local image IDs and runtime lineage are useful evidence but are not a
substitute for a clean commit and executed remote CI.
