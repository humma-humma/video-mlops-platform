from pathlib import Path

from src.lineage import canonical_hash, sha256_file, verify_manifest


def test_canonical_hash_is_order_independent_and_content_sensitive():
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})


def test_manifest_detects_corruption_missing_files_and_path_escape(tmp_path):
    truth = tmp_path / "truth.csv"
    truth.write_text("original")
    entry = {"path": "truth.csv", "bytes": truth.stat().st_size, "sha256": sha256_file(truth)}
    manifest = {"ground_truth": entry, "records": []}
    assert verify_manifest(manifest, tmp_path) == []
    truth.write_text("modified")
    assert verify_manifest(manifest, tmp_path) == ["checksum mismatch: truth.csv"]
    truth.unlink()
    assert verify_manifest(manifest, tmp_path) == ["missing: truth.csv"]
    manifest["ground_truth"]["path"] = "../outside.csv"
    assert verify_manifest(manifest, tmp_path) == ["outside dataset root: ../outside.csv"]
