"""Content-addressed lineage without importing a GPU or tracking SDK."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def source_lineage() -> dict:
    names = ["src/config.py", "src/pipeline.py", "src/inference_utils.py", "src/decoding.py", "src/model_utils.py",
             "src/category_utils.py", "src/taxonomy.py", "src/service/inference.py",
             "src/lineage.py", "src/experiments.py", "src/evaluation_utils.py"]
    files = {name: sha256_file(ROOT / name) for name in names}
    return {"source_files": files, "code_hash": canonical_hash(files),
            "prompt_version": "video-prompts-v1", "prompt_hash": files["src/inference_utils.py"],
            "taxonomy_hash": files["src/taxonomy.py"]}


def verify_manifest(manifest: dict, dataset_root: Path) -> list[str]:
    """Return every integrity error; refuse manifest paths outside the dataset."""
    root = dataset_root.resolve()
    errors = []
    entries = [manifest["ground_truth"]]
    for record in manifest["records"]:
        entries.extend(record.get(key) for key in ("video", "transcript") if record.get(key))
    seen = set()
    for item in entries:
        relative = item["path"]
        if relative in seen:
            continue
        seen.add(relative)
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            errors.append(f"outside dataset root: {relative}")
        elif not path.is_file():
            errors.append(f"missing: {relative}")
        elif path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            errors.append(f"checksum mismatch: {relative}")
    return errors
