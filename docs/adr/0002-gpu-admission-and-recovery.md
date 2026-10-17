# ADR 0002: bound GPU backlog and expose the actual recovery policy

Status: accepted for local demo, 2026-10-17.

## Context and decision

One worker process and one 8 GiB GPU cannot serve an unbounded queue. Keep
worker concurrency at one and admit at most two outstanding jobs by default:
one may run while one waits. Count PENDING, QUEUED and RUNNING rows in
PostgreSQL under a transaction-scoped advisory lock. Use that same lock for
new submissions, explicit retries and automatic dependency retries. Return
HTTP 429 with `Retry-After` when full. Existing idempotency keys still replay
the accepted job even while capacity is full.

The dispatcher remains independent of the GPU worker. After a hard kill, it
marks an expired RUNNING attempt FAILED at the configured task deadline plus
an allowance. Timeout is not automatically retried; the client/operator may
retry if the attempt budget and cause permit it. A new generation fences late
completions from replacing the recovered result.

## Alternatives and consequences

- The process-local request-rate limit protects HTTP traffic, but cannot bound
  queued GPU work across API replicas or a burst below its per-minute threshold.
- Broker queue length is not the source of truth because durable jobs can await
  publication or be republished. Counting database state covers those cases.
- Raising worker concurrency to absorb load risks memory contention and OOM on
  this device. The measured small burst supports a backlog bound, not a larger
  throughput claim.
- Automatically replaying every interrupted job would hide OOM, invalid output
  and timeout causes, and could repeat expensive work. Explicit timeout retry
  makes the observed behavior reviewable.

The admission lock is PostgreSQL-specific. SQLite unit tests exercise response
contracts; the [live burst](../../reports/admission_demo.json) exercises the
deployed database. Storage upload currently precedes the atomic admission
transaction, so a rejected race can leave an orphaned input object. The
[controlled kill](../../reports/recovery_demo.json) observed about five minutes
before timeout under shortened 180/240-second demo limits, then one successful
explicit retry. It does not establish exactly-once execution or high availability.
