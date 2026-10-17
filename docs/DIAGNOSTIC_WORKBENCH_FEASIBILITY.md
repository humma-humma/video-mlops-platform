# Diagnostic Workbench: Feasibility, ROI and ETA

- **Date:** 2026-10-12
- **Status:** analysis of the deferred concept in [PORTFOLIO_REFERENCE.md §10](PORTFOLIO_REFERENCE.md#10-future-product-idea-restricted-access-inference-diagnostics); does not change the current plan
- **Live copy:** [Claude doc](https://claude.ai/code/artifact/cccc26ca-2931-4fef-a22e-65299d8c1131)

**2026-10-18 implementation update:** a first [offline pilot](DIAGNOSTIC_WORKBENCH.md)
now exports bounded evidence from recorded reports and existing service jobs,
and evaluates simple deterministic rules. The timeline and market estimates below
were made before that implementation; the eight report-derived pilot cases are
not independent diagnosis-quality evidence.

## Verdict

Build it as a narrow portfolio piece, not as a product, and only after demo phases A–E are complete. Generic AI incident diagnosis is crowded and well funded. The open angle is GPU-inference-specific diagnosis backed by an honest evaluation harness: injected ground truth, held-out variants, and measured citation accuracy and abstention.

The minimum credible version is stages F1 (evidence bundles) and F2 (diagnostic cases). It takes roughly 10–12 weeks including the demo, at about 15–20 focused hours per week. F3 and F4 are worth adding only if the F2 results are interesting. F5 is blocked until an authorized external environment exists.

## Is the problem real?

Yes. Current agents diagnose incidents poorly, and the main reason is missing or misread evidence, not weak reasoning. That supports the workbench design, which puts the evidence bundle and a deterministic baseline first and treats the LLM as optional.

- **Low agent accuracy.** On [ORCA-bench](https://www.alphaxiv.org/abs/2607.28545), the best frontier agents found the root cause in 25.3% of medium tasks and 10.0% of hard ones. The weakest model invented a root cause in 40% of reports.
- **Evidence failures dominate.** On OpenRCA, baseline agents scored 3.9–12.5%. The most common failures were misread data and incomplete exploration, across all five models, and prompt engineering did not fix them ([arXiv 2602.09937](https://www.arxiv.org/abs/2602.09937)).
- **Prepared context helps.** One June 2026 test found all three frontier models it tried named the root cause when given the same prepared context ([Mezmo market map](https://www.mezmo.com/learn/the-2026-ai-sre-market-map-agents-harnesses-and-the-data-layer)).
- **Generic tools miss GPU-inference causes.** Standard APM shows a request was slow, but not whether queue pressure, KV-cache preemption, prefill or decode caused it ([Dash0](https://www.dash0.com/blog/observing-vllm-with-opentelemetry-and-dash0)). [InferLens](https://github.com/rabrooks/inferlens) targets this gap but is pre-alpha.
- **Read-only access needs layers.** Practitioner guidance says a read-only tool label is not a security boundary. Enforce it in the tool and the data source, and give the agent its own revocable identity ([Permit.io](https://www.permit.io/blog/read-only-trust-level-ai-ops-agents)). That matches the access boundary in the reference doc.

## Market and ROI

The return is high as portfolio evidence and low as a product. The value comes from rigorous evaluation, not from yet another incident chat agent.

| Lens | ROI | Why |
| --- | --- | --- |
| As a product | Low | Resolve AI is reportedly valued at $1–1.5B, Traversal has raised about $48–53M, Cleric is also in the space, and AWS, Microsoft, Google, Datadog, Grafana and PagerDuty all sell AI SRE tools ([Mezmo](https://www.mezmo.com/learn/best-ai-sre-tools-00035), [Traversal profile](https://startupintros.com/orgs/traversal)). Funding figures conflict across secondary sources. |
| GPU-inference niche | Medium | [Caladrius](https://www.ai-infra-summit.com/press-releases/caladrius-emerges-from-stealth-to-deliver-full-loop-gpu-infrastructure-observability-and-remediation) and [Nscale](https://www.nscale.com/blog/the-gpu-fleet-that-fixes-itself) target GPU hardware faults. [GPUAlert](https://arxiv.org/abs/2607.01409) classifies training failures with regex rules. Diagnosing inference-service problems (queueing, decoder changes, memory pressure, release regressions) is less covered, though vLLM tooling vendors are moving in. |
| As portfolio evidence | High | The [OpenAI Inference Runtime productivity role](https://startup.jobs/software-engineer-productivity-inference-runtime-openai-8030327) lists deploy gates, regression detection, flaky-failure noise and triage automation. The [Anthropic Inference Systems role](https://scoutify.com/companies/anthropic/jobs/1121998/) asks which signals reliably catch real regressions versus noise. A workbench that measures its own diagnosis quality demonstrates exactly that. |

The main hiring-signal risk: a generic "AI SRE agent" demo is now common and reads as a me-too project. What sets this apart is the measurement discipline.

## Feasibility on the current setup

The current stack already supplies roughly 40–50% of the raw material for F1 and F2 (an estimate). What's missing is incident variety and a way to score diagnoses.

**Already in place:**

- Durable job, attempt and event history in PostgreSQL, with generation fencing.
- Lineage: model revision, configuration and image identity.
- Per-attempt result artifacts in MinIO.
- The read-only `/operations` page and host GPU telemetry collector.
- GPU profiling scripts and the bounded HTTP load runner.
- Planned incidents that map directly to F2: worker interruption (Phase B) and overload (Phase C).

**Constraints:**

| Constraint | Effect |
| --- | --- |
| One RTX 2080 (8 GiB), single host | Fine for F1–F3. Rules out multi-node, NCCL or distributed-tracing claims. |
| GPU shared with other work (a nerfstudio container was running on 2026-10-12) | Contaminates measurements unless recorded. It can also serve as a labelled "noisy neighbour" incident. |
| One workload | Limited incident variety. Hard cases need injected variants: decoder swap, frame count, memory cap, queue depth, storage faults. |
| No production access | Matches the design: offline bundles are the first integration. F5 is unlikely without an employer or cluster. |
| No paid LLM required | Matches the design: deterministic analysis first. An optional F4 agent costs little. |

**Main technical risk:** incidents that are too easy. If one rule always finds the cause, the results prove nothing. Build confounders into each case, such as a decoder change combined with GPU contention.

## ETA

The minimum credible version (demo plus F1 and F2) takes about 10–12 weeks; F3 and F4 add another 4–5. These are estimates assuming about 15–20 focused hours per week; actual availability is unknown.

| Stage | Scope | Estimate | Running total |
| --- | --- | --- | --- |
| Demo A–E (prerequisite) | Rebuild, recovery, load, release, reviewer pack ([§7](PORTFOLIO_REFERENCE.md#7-immediate-implementation-plan-finish-the-local-demo)) | 4–6 weeks | 4–6 weeks |
| F1 Evidence bundles | Schema, exporter, redaction, hashes, missing-evidence markers, offline import | 1.5–2 weeks | — |
| F2 Diagnostic cases | 4 incident types × ~3 variants, deterministic timelines and comparisons, scoring harness | 3–4 weeks | **10–12 weeks** |
| Kill check | Stop if deterministic rules solve over 90% of cases or cases are trivial; publish findings | — | — |
| F3 Proposals + replay | Config diff, isolated baseline comparison | 2 weeks | — |
| F4 Agent tool layer | Typed read-only tools, audit log, adversarial-log tests, agent vs. baseline eval | 2–3 weeks | **14–17 weeks** |
| F5 External adapter | Real inference or SLURM integration | Not scheduled | Blocked on authorized access |

## Recommendation

Finish Phase A, then Phase B, and shape the demo work so it feeds the workbench later.

1. **Don't start the workbench yet.** The reference doc's own promotion criteria require a complete demo first, and the demo provides the incidents.
2. **Make Phases B and C produce workbench inputs:**
   - Emit incident timelines as structured JSON, an early F1 bundle schema.
   - Label every injected cause so each incident has known ground truth.
   - Record GPU contention rather than only avoiding it.
3. **Frame the workbench as an evaluation harness** for diagnosing GPU inference incidents. Use deterministic analysis as the baseline and an optional agent as the challenger. Report cause accuracy, citation accuracy and abstention.
4. **Kill criterion:** after F2, stop if deterministic rules solve more than 90% of cases or the cases are trivial. Publish the findings as the result and skip F4.

## Sources

These come from web search results on 2026-10-12. The pages were not opened individually, so treat figures such as funding amounts as unverified. Several research items are non-peer-reviewed preprints.

- Market: [Mezmo 2026 AI SRE market map](https://www.mezmo.com/learn/the-2026-ai-sre-market-map-agents-harnesses-and-the-data-layer) · [Mezmo AI SRE tools](https://www.mezmo.com/learn/best-ai-sre-tools-00035) · [Ivinco AI SRE in 2026](https://www.ivinco.com/blog/ai-sre) · [Traversal profile](https://startupintros.com/orgs/traversal) · [DigyAI on AI SRE failures](https://digyai.com/insights/ai-sre-agents-incident-response/) · [Anyshift top 10](https://www.anyshift.io/blog/top-10-ai-sre-tools-2026-comparison) · [Gravity funding tracker Q3 2026](https://gravity.fast/blog/ai-agent-funding-tracker-q3-2026/)
- Benchmarks: [ORCA-bench](https://www.alphaxiv.org/abs/2607.28545) · [OpenRCA failure analysis](https://www.arxiv.org/abs/2602.09937) · [Structured multi-agent RCA](https://www.alphaxiv.org/abs/2607.13548.md) · [Cloud-OpsBench](https://arxiv.org/pdf/2603.00468)
- GPU and inference observability: [Dash0 on vLLM](https://www.dash0.com/blog/observing-vllm-with-opentelemetry-and-dash0) · [InferLens](https://github.com/rabrooks/inferlens) · [SREcon26 slides](https://www.usenix.org/system/files/sre26amer_slides_munaf.pdf) · [Elastic ES|QL debugging](https://www.elastic.co/observability-labs/blog/esql-llm-opentelemetry-debugging) · [Collective Communication for 100k+ GPUs](https://arxiv.org/pdf/2510.20171) · [GPUAlert](https://arxiv.org/abs/2607.01409) · [Nscale](https://www.nscale.com/blog/the-gpu-fleet-that-fixes-itself) · [Caladrius](https://www.ai-infra-summit.com/press-releases/caladrius-emerges-from-stealth-to-deliver-full-loop-gpu-infrastructure-observability-and-remediation)
- Access control and bundles: [Permit.io read-only trust](https://www.permit.io/blog/read-only-trust-level-ai-ops-agents) · [Chronosphere MCP](https://toolradar.com/tools/chronosphere-mcp) · [Troubleshoot framework](https://github.com/mesosphere/troubleshoot) · [Infrahub Collect](https://docs.infrahub.app/backup/collect) · [Apollo router support tool](https://www.apollographql.com/blog/troubleshoot-faster-with-the-graphos-router-support-tool)
- Roles: [OpenAI Productivity, Inference Runtime](https://startup.jobs/software-engineer-productivity-inference-runtime-openai-8030327) · [Anthropic Performance Engineer, Inference Systems](https://scoutify.com/companies/anthropic/jobs/1121998/) · [SREcon25 quality gates talk](https://www.usenix.org/conference/srecon25emea/presentation/birkner)
- Internal: [PORTFOLIO_REFERENCE.md](PORTFOLIO_REFERENCE.md) (Sections 7 and 10) and the local Docker container state on 2026-10-12.
