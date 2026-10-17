"""Track inference bundles; registry creation always recomputes the gate."""
import math
import re

from src.experiments import GatePolicy, evaluate_gate


def track_candidate(candidate: dict, baseline: dict, policy: GatePolicy, *, tracking_uri: str,
                    registry_name: str | None = None, image_digest: str | None = None,
                    mlflow_module=None) -> dict:
    gate = evaluate_gate(candidate, baseline, policy)
    if registry_name:
        if not gate["passed"]:
            raise ValueError("A failed candidate cannot be registered")
        if not image_digest or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_digest):
            raise ValueError("Registration requires an immutable container image digest")
    if mlflow_module is None:
        import mlflow as mlflow_module
    mlflow = mlflow_module
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("video-inference-bundles")
    with mlflow.start_run(run_name=candidate.get("name", "candidate")) as run:
        mlflow.set_tags({"bundle_type": "inference", "gate_passed": str(gate["passed"]).lower(),
                         "candidate_hash": gate["candidate_hash"], "baseline_hash": gate["baseline_hash"],
                         "policy_hash": gate["policy_hash"]})
        mlflow.log_params({key: str(value) for key, value in candidate.get("resolved_config", {}).items()})
        mlflow.log_metrics({key: value for key, value in candidate.get("metrics", {}).items()
                            if not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)})
        for name, value in {"report": candidate, "baseline": baseline, "policy": policy.model_dump(), "gate": gate,
                            "bundle": {"lineage": candidate["lineage"], "image_digest": image_digest,
                                       "config": candidate.get("resolved_config", {})}}.items():
            mlflow.log_dict(value, f"bundle/{name}.json")
        run_id = run.info.run_id
    result = {"run_id": run_id, "gate": gate}
    if registry_name:
        client = mlflow.MlflowClient(tracking_uri=tracking_uri)
        try:
            client.create_registered_model(registry_name)
        except mlflow.exceptions.MlflowException as error:
            if error.error_code != "RESOURCE_ALREADY_EXISTS":
                raise
        registered = client.create_model_version(name=registry_name, source=f"runs:/{run_id}/bundle", run_id=run_id,
            tags={"candidate_hash": gate["candidate_hash"], "policy_hash": gate["policy_hash"], "image_digest": image_digest},
            description="Gated inference bundle metadata; weights remain at the pinned Hugging Face revision.")
        result["registry_version"] = registered.version
    return result
