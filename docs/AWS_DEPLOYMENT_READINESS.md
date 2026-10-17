# AWS demo deployment readiness

Status on 2026-10-10: preparation started; no cloud deployment performed.
The owner subsequently chose the local route with no additional cloud spend.
Provisioning is deferred; the inputs below are needed only if cloud work resumes.
Governing scope: [PORTFOLIO_DIRECTION.md](PORTFOLIO_DIRECTION.md).

## Inputs still required

- AWS account/profile or SSO setup and target region.
- Maximum spend for a bounded deployment/demo session and expiry time.
- GPU quota and instance availability in that region.
- Whether the demo needs a public authenticated endpoint or private reviewer
  access. Default during preparation is private access.

The local environment currently has no `aws` or `terraform` executable; Docker
engine access is denied to this session. HTTP access to the existing local API
works. These findings are in
[deployment_environment_check.json](../reports/deployment_environment_check.json).
No cloud identity or permissions have been verified; absence of the CLI does
not imply absence of an account or credentials.

## Proposed deployment boundary

Retain the existing AWS mapping as the starting design: CPU API on ECS,
GPU worker on ECS/EC2 capacity, PostgreSQL job metadata, private Valkey,
S3 artifacts, ECR images, role-based AWS access and managed secret injection.
The final temporary-demo topology must fit the agreed budget. In particular,
price the fixed costs of a load balancer, database and CPU capacity alongside
the GPU. A consolidated temporary deployment may be justified, but its failure
domain must be explicit. Neither topology is approved or deployed yet.

Do not copy local MinIO/PostgreSQL demo passwords into cloud configuration.
Only the authenticated application entry point may be reviewer-accessible;
database, broker and telemetry administration stay private. Decide TLS/access
before enabling a public endpoint. Use instance/task roles for S3 and ECR,
with restricted resource access rather than embedding static keys in images.

## Execution gate and evidence

Before paid provisioning, produce a concrete resource inventory with region,
instance type/count, storage, networking, estimated session cost, idle costs,
tags and deletion commands. Establish budget notifications and an explicit
expiry/teardown procedure. A billing alert is not a hard spending cap.

Then execute and retain evidence for:

1. Read-only identity, IAM capabilities, GPU quota and regional availability.
2. Versioned CPU/GPU image builds and registry push; exact model snapshot/cache
   delivery and dependency verification; secrets and role configuration.
3. Manual deployment, schema migration and authenticated readiness checks.
4. Real inference, durable result retrieval and controlled recovery.
5. Logs/metrics, resource inventory and actual elapsed infrastructure lifetime.
6. Teardown, followed by a check for remaining compute, volumes, snapshots,
   endpoints, load balancers and retained storage/registry costs.

Codify the verified manual deployment as IaC and test recreation/teardown.
Do not treat generated templates or a successful local Compose run as cloud
acceptance. Never delete unowned resources to simplify teardown.
