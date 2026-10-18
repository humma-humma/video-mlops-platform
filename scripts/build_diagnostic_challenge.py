"""Replay bounded faults through the real service task without Docker or a GPU."""

from contextlib import ExitStack, nullcontext
from datetime import timezone
from pathlib import Path
import hashlib
import time
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.diagnostic_workbench import write_json
from src.diagnostics import canonical, digest, finish_bundle, safe_attempts, safe_events, safe_timings
from src.service import tasks, telemetry
from src.service.db import Base
from src.service.deployments import VideoAdapter
from src.service.models import Job, JobAttempt, JobEvent
from src.service.storage import ArtifactStorageError, ArtifactStore


INPUT = b"isolated diagnostic fixture; no user video"
REVISION = "a" * 40
LINEAGE = {"code_hash": "b" * 64, "inference_config_hash": "c" * 64}
SCENARIOS = {
    "baseline": (0.02, 0.02, None),
    "storage_read_fault": (0.02, 0.02, "read"),
    "storage_write_fault": (0.02, 0.02, "write"),
    "dependency_inside_adapter": (0.02, 0.02, "adapter"),
    "preparation_delay": (0.25, 0.03, None),
    "download_delay": (0.03, 0.25, None),
    "mixed_delay": (0.25, 0.25, None),
}


class SimulatedVideoAdapter(VideoAdapter):
    def __init__(self, preparation_seconds: float, adapter_fault: bool):
        self.preparation_seconds = preparation_seconds
        self.adapter_fault = adapter_fault

    def run(self, input_path: Path, metadata: dict) -> dict:
        if self.adapter_fault:
            raise ArtifactStorageError("isolated adapter dependency fault")
        start = time.perf_counter()
        time.sleep(self.preparation_seconds)
        preparation = time.perf_counter() - start
        return {"schema_version": "1", "video_id": input_path.stem,
                "summary": "Isolated test output", "category": "Daily Life",
                "model_version": "simulated-video-adapter", "model_revision": REVISION,
                "lineage": LINEAGE,
                "timings": {"model_load": 0.0, "input_preparation": preparation,
                            "summary": 0.0, "category": 0.0,
                            "inference_total": time.perf_counter() - start}}


def utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def run_case(name: str, sessions, input_path: Path, scratch: Path) -> dict:
    preparation_seconds, download_seconds, fault = SCENARIOS[name]
    job_id = str(uuid4())
    with sessions() as db:
        db.add(Job(id=job_id, status="QUEUED", input_path=str(input_path),
                   deployment_id="video-summary-v1", generation=0, attempts=0))
        db.commit()
    structured_failures = []
    original_download = ArtifactStore.download_file

    def download(store, uri, destination):
        if fault == "read":
            raise ArtifactStorageError("isolated storage read fault")
        time.sleep(download_seconds)
        return original_download(store, uri, destination)

    def write_result(store, key, value):
        raise ArtifactStorageError("isolated storage write fault")

    def capture(event_name, **fields):
        if event_name == "worker_failure":
            structured_failures.append({"stage": fields.get("stage"),
                                        "error_code": fields.get("error_code")})

    adapter = SimulatedVideoAdapter(preparation_seconds, fault == "adapter")
    with ExitStack() as stack:
        stack.enter_context(patch.object(tasks, "SessionLocal", sessions))
        stack.enter_context(patch.object(tasks, "get_deployment", lambda _: adapter))
        stack.enter_context(patch.object(tasks, "TemporaryDirectory", lambda **_: nullcontext(str(scratch))))
        stack.enter_context(patch.object(tasks, "event", capture))
        stack.enter_context(patch.object(telemetry, "event", lambda *_args, **_kwargs: None))
        stack.enter_context(patch.object(tasks.settings, "use_fake_inference", False))
        stack.enter_context(patch.object(tasks.settings, "artifact_backend", "filesystem"))
        stack.enter_context(patch.object(tasks.settings, "artifact_root", str(scratch / "artifacts")))
        stack.enter_context(patch.object(tasks.settings, "worker_scratch_root", str(scratch)))
        stack.enter_context(patch.object(ArtifactStore, "download_file", download))
        if fault == "write":
            stack.enter_context(patch.object(ArtifactStore, "put_json", write_result))
        try:
            tasks.process_job.run(job_id, 0)
        except tasks.WorkerFailure:
            if fault is None:
                raise

    with sessions() as db:
        job = db.get(Job, job_id)
        attempts = db.scalars(select(JobAttempt).where(JobAttempt.job_id == job_id)).all()
        events = db.scalars(select(JobEvent).where(JobEvent.job_id == job_id)).all()
        result = ArtifactStore(root=scratch / "artifacts").get_json(job.result_path) if job.result_path else {}
        observations = {
            "status": job.status,
            "attempts": safe_attempts([{"number": a.number, "status": a.status,
                                        "error_code": a.error_code,
                                        "started_at": utc(a.started_at),
                                        "finished_at": utc(a.finished_at)} for a in attempts]),
            "events": safe_events([{"event": e.event, "generation": e.generation,
                                    "timestamp": utc(e.created_at)} for e in events]),
            "admission": None,
            "timings_seconds": safe_timings(result.get("timings")),
            "input_sha256": hashlib.sha256(INPUT).hexdigest(),
            "model_revision": REVISION,
            "deployment_id": "video-summary-v1",
            "lineage_hashes": LINEAGE,
            "failure_stage": structured_failures[0]["stage"] if structured_failures else None,
        }
    source = {"scenario": name, "observations": observations,
              "structured_failure": structured_failures}
    return finish_bundle("isolated_replay", {"report": digest(canonical(source))}, observations)


def main():
    output = Path("reports/diagnostics/challenge")
    scratch = Path("data/outputs/diagnostic-challenge-work")
    scratch.mkdir(parents=True, exist_ok=True)
    input_path = scratch / "input.mp4"
    input_path.write_bytes(INPUT)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    bundles = {}
    try:
        for name in SCENARIOS:
            bundles[name] = run_case(name, sessions, input_path, scratch)
            write_json(output / f"{name}.json", bundles[name])
    finally:
        engine.dispose()
    write_json(output / "injection_ledger.json", {
        "schema_version": "diagnostic-injection-ledger-v1",
        "harness_sha256": digest(Path(__file__).read_bytes()),
        "input_sha256": hashlib.sha256(INPUT).hexdigest(),
        "cases": {name: {"requested_preparation_seconds": spec[0],
                         "requested_download_seconds": spec[1],
                         "injected_fault": spec[2],
                         "bundle_sha256": bundles[name]["bundle_sha256"]}
                  for name, spec in SCENARIOS.items()},
        "scope": "Local SQLite/filesystem task replay; sleeps and faults are controlled injections, not GPU measurements."})
    print(f"Replayed {len(SCENARIOS)} isolated service-task cases in {output}")


if __name__ == "__main__":
    main()
