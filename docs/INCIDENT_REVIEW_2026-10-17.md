# Controlled GPU worker interruption — 2026-10-17

The [recorded run](../reports/recovery_demo.json) submitted one real 500M GPU
job, observed RUNNING, then killed its Compose worker with SIGKILL at
08:48:46.39 UTC. The worker restarted at 08:48:47.12, but the database job
remained RUNNING. At 08:53:54.80 the dispatcher marked attempt 1 FAILED with
`timeout` under the temporary 180/240-second soft/hard limits plus its
reconciliation allowance. The API requested an explicit retry at 08:53:56.51;
attempt 2 succeeded at 08:54:23.21 and stored a result with the pinned 500M
model revision. The script restored the normal 840/900-second limits at
08:54:36.13. PostgreSQL retained both attempts and correlated events.

This is the observed recovery policy: a hard kill can leave a job RUNNING for
several minutes and a timeout requires an operator/client retry. Restarting a
worker did not itself resume that attempt. Generation fencing and atomic claims
protect the final result from late deliveries, but this run does not prove
exactly-once execution or every failure mode. For triage, inspect
`/api/v1/jobs/{id}`, `/attempts`, `/events`, dispatcher logs, and worker logs;
then retry only if the error and remaining attempt budget permit it.
