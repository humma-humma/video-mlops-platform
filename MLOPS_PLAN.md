# MLOps Upgrade Plan

## Objective

Turn this video summarization benchmark into a reproducible MLOps project that demonstrates the full batch ML lifecycle: configurable experiments, tracked metrics and artifacts, data/output versioning, reliable orchestration, automated checks, and clear benchmark reporting.

The core target is a strong portfolio-ready implementation in roughly 8-12 focused working days. The larger 3-4 week methods are planned as end-of-project extensions if time remains.

## Portfolio Signal

The project should show that the pipeline is more than a one-off inference script. A prospective employer should be able to see:

- How to reproduce every reported result.
- Which data, config, model, and code version produced each run.
- How speed and quality trade off across optimization methods.
- How failures are handled and surfaced.
- How the pipeline can be tested and run consistently.

## Current Baseline

The repository already has a working batch inference path:

- `main.py` runs the end-to-end pipeline.
- `src/config.py` defines CLI configuration.
- `src/model_utils.py` loads the Hugging Face VLM pipeline.
- `src/inference_utils.py` builds prompts, runs inference, and writes outputs.
- `src/evaluation_utils.py` computes BERTScore and category metrics.
- `slurm_submissions/` contains benchmark variants for cache, compile, FlashAttention, and reduced frames.
- `data/outputs/` contains existing CSV and JSON benchmark artifacts.

Known gaps to address early:

- README says Python 3.11, while `pyproject.toml` requires Python 3.12.
- README run command omits required CLI arguments.
- Audio transcription fallback likely checks the wrong file path.
- Category outputs are not normalized before evaluation.
- Timing does not separately track video loading, transcription, inference, and evaluation.
- JSON min/max/std fields are currently placeholders in some paths.
- There are no tests or CI checks.

## Core Roadmap: 8-12 Days

### Phase 1: Stabilize The Existing Pipeline

Goal: make the current pipeline correct enough to build MLOps infrastructure around it.

Tasks:

- Fix category normalization before metric computation.
- Fix the audio fallback path so missing transcripts can be generated correctly.
- Align Python version documentation with project metadata.
- Replace the bare README command with complete runnable examples.
- Add a small sample-mode command using `--num-video-samples`.
- Add basic validation for required input folders and files.
- Split timing into meaningful stages: model load, transcript loading/generation, prompt creation, summary inference, category inference, evaluation, and total runtime.

Deliverables:

- Corrected pipeline behavior.
- Updated README usage section.
- Cleaner stats JSON with real timing fields.

### Phase 2: Config-Driven Experiments

Goal: replace long, fragile command lines with named experiment configs.

Tasks:

- Add `configs/` with YAML files for:
  - `baseline.yaml`
  - `cache.yaml`
  - `cache_compile.yaml`
  - `cache_flash.yaml`
  - `cache_compile_flash.yaml`
  - `max_frames_16.yaml`
  - `max_frames_8.yaml`
  - `max_frames_4.yaml`
- Add a config loader.
- Keep CLI overrides for quick experiments.
- Add a single command pattern such as:

```bash
uv run python -m src.pipeline.run --config configs/baseline.yaml
```

Deliverables:

- Reproducible experiment definitions.
- Cleaner Slurm script generation or simpler Slurm launch commands.

### Phase 3: MLflow Experiment Tracking

Goal: log each run as a tracked experiment with searchable metadata.

Tasks:

- Add MLflow dependency.
- Log run parameters:
  - model name
  - optimization flags
  - max frames
  - batch size
  - number of workers
  - sample count
  - config file path
- Log metrics:
  - total runtime
  - per-stage runtime
  - BERTScore precision, recall, F1
  - category accuracy
  - category weighted F1
  - processed video count
  - failed video count
- Log artifacts:
  - prediction CSV
  - stats JSON
  - config YAML
  - generated benchmark report

Deliverables:

- Local MLflow tracking.
- Run comparison across baseline and optimization variants.

### Phase 4: DVC Data And Pipeline Versioning

Goal: make datasets, generated outputs, and pipeline stages reproducible.

Tasks:

- Add DVC.
- Track external or local input data structure without committing large files to Git.
- Add `dvc.yaml` stages:
  - `prepare`
  - `infer`
  - `evaluate`
  - `report`
- Add `dvc metrics` outputs for key metrics.
- Add `dvc plots` or a generated markdown/CSV comparison table for benchmark runs.

Deliverables:

- Reproducible data and output lineage.
- `dvc repro` workflow for the core pipeline.

### Phase 5: Tests And CI

Goal: prove the project is maintainable, not just runnable.

Tasks:

- Add unit tests for:
  - config loading
  - prompt creation
  - category normalization
  - metrics alignment by `video_id`
  - stats JSON creation
  - transcript fallback behavior with mocks or small fixtures
- Add lightweight integration test for sample mode.
- Add formatting and linting.
- Add GitHub Actions workflow for:
  - install
  - lint
  - tests
  - smoke run on tiny fixtures

Deliverables:

- CI badge-ready test pipeline.
- Safer future refactors.

### Phase 6: Dockerized Reproducibility

Goal: make the runtime easier to recreate.

Tasks:

- Add Dockerfile for CPU/smoke mode.
- Add optional CUDA Dockerfile or documented GPU environment if feasible.
- Add `.dockerignore`.
- Add commands for running tests and sample inference in the container.

Deliverables:

- Reproducible local development path.
- Clear environment story for employers/reviewers.

### Phase 7: Benchmark Report

Goal: produce the artifact that communicates the project value.

Tasks:

- Generate `reports/benchmark.md`.
- Compare baseline vs optimization variants.
- Include:
  - total runtime
  - summary runtime
  - category runtime
  - BERTScore F1
  - category accuracy
  - category weighted F1
  - speedup over baseline
  - quality tradeoff notes
- Add a concise README section linking the report.

Deliverables:

- A polished result summary for interviews and portfolio review.

## Planned Methods If Time Remains: 3-4 Week Extensions

These sections are intentionally planned for the end. They are valuable, but the project should first have the core reproducible experiment system above.

### Method Extension 1: Prefect Batch Orchestration

Goal: turn the pipeline into a resumable, observable batch workflow.

Tasks:

- Add Prefect.
- Model each video as an independently tracked task.
- Add retries around transcript loading, video decoding, and inference.
- Persist per-video status.
- Support resuming failed or incomplete runs.
- Add a local Prefect deployment command.

Expected signal:

- Demonstrates production-style workflow orchestration.
- Shows task state, retries, failure handling, and resumability.

### Method Extension 2: Monitoring And Data Quality Reports

Goal: add lightweight monitoring without overbuilding online serving.

Tasks:

- Track input video duration distribution.
- Track missing transcript count.
- Track failed video count and failure reasons.
- Track summary length distribution.
- Track predicted category distribution.
- Compare category distribution against ground truth.
- Generate a data/quality report per run.

Expected signal:

- Shows awareness of operational ML failure modes.
- Makes quality degradation visible before relying on final metrics.

### Method Extension 3: Metric Regression Gates

Goal: prevent new changes from silently damaging benchmark quality.

Tasks:

- Define baseline thresholds for sample-mode tests.
- Add CI checks for:
  - category accuracy floor
  - BERTScore F1 floor
  - maximum failed videos
  - maximum runtime for tiny fixtures
- Add a script that compares a candidate run against a stored baseline metrics file.

Expected signal:

- Demonstrates ML-specific CI/CD rather than only generic unit testing.

### Method Extension 4: Dashboard Or Report App

Goal: make benchmark tradeoffs easy to inspect.

Tasks:

- Build a lightweight Streamlit or static HTML report.
- Plot latency vs BERTScore.
- Plot latency vs category accuracy.
- Show per-run config, metrics, and artifact links.
- Show examples of good and bad predictions.

Expected signal:

- Makes the project easier to understand in a short portfolio review.
- Communicates engineering results visually.

### Method Extension 5: Optional Batch Submission API

Goal: expose the batch workflow without pretending this is a low-latency serving system.

Tasks:

- Add FastAPI endpoint to submit a batch job.
- Add endpoint to query job status.
- Add endpoint to retrieve output artifacts.
- Keep GPU inference in the batch worker, not inside request handling.

Expected signal:

- Demonstrates service design while respecting the batch nature of video inference.

### Method Extension 6: Cloud Or Kubernetes Deployment

Goal: provide a deployment story only after the local MLOps system is solid.

Tasks:

- Package MLflow, Prefect, and the pipeline with Docker Compose.
- Optionally add Kubernetes manifests for the orchestrator and worker.
- Document GPU assumptions and storage requirements.

Expected signal:

- Strong infrastructure signal if completed cleanly.
- Should be skipped if it risks becoming a half-working demo.

## Suggested Final Project Structure

```text
configs/
  baseline.yaml
  cache_compile_flash.yaml
  max_frames_16.yaml
src/
  pipeline/
    run.py
    stages.py
    config_loader.py
  tracking/
    mlflow_utils.py
  reporting/
    benchmark_report.py
tests/
reports/
  benchmark.md
dvc.yaml
Dockerfile
.github/workflows/ci.yml
MLOPS_PLAN.md
```

## Definition Of Done

The core MLOps upgrade is done when a reviewer can:

1. Clone the repo.
2. Install dependencies.
3. Run tests.
4. Run a sample pipeline from a config.
5. Reproduce at least one benchmark result.
6. Open MLflow and compare runs.
7. Inspect DVC stages and metrics.
8. Read `reports/benchmark.md` and understand the speed/quality tradeoffs.

The optional 3-4 week extensions are done only if they are integrated into the same reproducible workflow rather than existing as disconnected demos.
