"""Frozen challenge, review proposal and pinned delivery inputs stay consistent."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_text_model_artifact import verify


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "src/service/model_artifacts/text_topic_v1.json"


def test_frozen_cpu_challenge_matches_unchanged_rules_and_labels():
    folder = ROOT / "reports/diagnostics/input-confounder-live"
    protocol = json.loads((folder / "protocol.json").read_text())
    cases = json.loads((folder / "cases.json").read_text())
    assert protocol["rules_sha256"] == hashlib.sha256((ROOT / "src/diagnostics.py").read_bytes()).hexdigest()
    assert {case["id"]: case["expected"] for case in cases["cases"]} == {
        name: spec["expected_diagnosis"] for name, spec in protocol["cases"].items()}
    assert {case["split"] for case in cases["cases"]} == {"held_out"}


def test_proposed_gate_rejects_missing_model_without_changing_deployed_dockerfile():
    digest = hashlib.sha256(MODEL.read_bytes()).hexdigest()
    assert verify(MODEL, digest) == digest
    with pytest.raises(FileNotFoundError):
        verify(MODEL.with_name("absent-replay-model.json"), digest)
    proposal = json.loads((ROOT / "reports/diagnostics/proposals/model_artifact_build_gate.json").read_text())
    replay = json.loads((ROOT / "reports/diagnostics/proposals/model_artifact_replay.json").read_text())
    assert proposal["status"] == "human_review_required"
    assert replay["scenarios"]["healthy_artifact"]["candidate_gate"]["accepted"] is True
    assert replay["scenarios"]["missing_artifact"]["candidate_gate"]["accepted"] is False
    assert "verify_text_model_artifact" not in (ROOT / "Dockerfile").read_text()


def test_pinned_service_packages_are_in_cpu_test_snapshot():
    def names(path):
        return {line.split("==", 1)[0] for line in path.read_text().splitlines()
                if line and not line.startswith("#")}

    service = names(ROOT / "requirements-service.lock.txt")
    test = names(ROOT / "requirements-service-test.lock.txt")
    assert service <= test
    assert {"celery", "boto3", "fastapi", "psycopg", "sqlalchemy", "uvicorn"} <= service
    assert {"pytest", "httpx", "pandas", "scikit-learn"} <= test
    assert "pip" not in test
