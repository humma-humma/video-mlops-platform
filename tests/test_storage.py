import io

import pytest

from src.service.config import settings
from src.service.storage import ArtifactStorageError, ArtifactStore


class S3Error(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.bucket_exists = False
        self.created = []
        self.failure = None

    def head_bucket(self, **kwargs):
        if self.failure:
            raise self.failure
        if not self.bucket_exists:
            raise S3Error("404")

    def create_bucket(self, **kwargs):
        self.created.append(kwargs)
        self.bucket_exists = True

    def put_object(self, *, Bucket, Key, Body):
        if self.failure:
            raise self.failure
        self.objects[Bucket, Key] = Body

    def head_object(self, *, Bucket, Key):
        if self.failure:
            raise self.failure
        if (Bucket, Key) not in self.objects:
            raise S3Error("404")

    def get_object(self, *, Bucket, Key):
        self.head_object(Bucket=Bucket, Key=Key)
        self.body = io.BytesIO(self.objects[Bucket, Key])
        return {"Body": self.body}


@pytest.fixture
def s3_store(monkeypatch):
    monkeypatch.setattr(settings, "artifact_backend", "s3")
    monkeypatch.setattr(settings, "s3_bucket", "test-artifacts")
    monkeypatch.setattr(settings, "s3_region", "us-east-1")
    client = FakeS3()
    return ArtifactStore(s3_client=client), client


def test_s3_bytes_and_json_round_trip(s3_store, tmp_path):
    store, client = s3_store
    uri = store.put_bytes("inputs/job/video #1?.mp4", b"video bytes")
    assert uri == "s3://test-artifacts/inputs/job/video #1?.mp4"
    assert store.exists(uri)
    path = store.download_file(uri, tmp_path / "video.mp4")
    assert path.read_bytes() == b"video bytes"
    assert client.body.closed
    result = {"summary": "A summary", "category": "Daily Life"}
    result_uri = store.put_json("results/job.json", result)
    assert store.get_json(result_uri) == result
    assert client.body.closed


def test_s3_missing_object_is_distinct_from_outage(s3_store):
    store, client = s3_store
    uri = "s3://test-artifacts/missing.mp4"
    assert not store.exists(uri)
    with pytest.raises(FileNotFoundError):
        store.get_bytes(uri)
    client.failure = S3Error("403")
    with pytest.raises(ArtifactStorageError):
        store.exists(uri)


def test_s3_connection_failure_is_not_a_missing_artifact(s3_store):
    store, client = s3_store
    client.failure = ConnectionError("private connection details")
    with pytest.raises(ArtifactStorageError, match="^Artifact store request failed$"):
        store.put_bytes("inputs/job.mp4", b"data")


@pytest.mark.parametrize("region", ["us-east-1", "eu-central-1"])
def test_bucket_bootstrap_only_creates_missing_bucket(s3_store, monkeypatch, region):
    store, client = s3_store
    monkeypatch.setattr(settings, "s3_region", region)
    store.ensure_bucket()
    store.ensure_bucket()
    expected = {"Bucket": "test-artifacts"}
    if region != "us-east-1":
        expected["CreateBucketConfiguration"] = {"LocationConstraint": region}
    assert client.created == [expected]


def test_bootstrap_does_not_treat_forbidden_as_missing(s3_store):
    store, client = s3_store
    client.failure = S3Error("403")
    with pytest.raises(ArtifactStorageError):
        store.ensure_bucket()
    assert client.created == []


def test_storage_readiness_requires_existing_accessible_bucket(s3_store):
    store, client = s3_store
    assert not store.ready()
    store.ensure_bucket()
    assert store.ready()
    client.failure = S3Error("403")
    assert not store.ready()


@pytest.mark.parametrize("key", ["", "../escape", "/absolute", "a/../../escape", "a\\escape"])
def test_invalid_object_keys_are_rejected(s3_store, key):
    store, client = s3_store
    with pytest.raises(ValueError):
        store.put_bytes(key, b"data")
    assert not client.objects


def test_foreign_bucket_uri_is_rejected(s3_store):
    store, _ = s3_store
    with pytest.raises(ValueError):
        store.get_json("s3://another-bucket/private.json")


def test_legacy_filesystem_result_remains_readable(s3_store, tmp_path):
    store, _ = s3_store
    legacy = tmp_path / "result.json"
    legacy.write_text('{"summary": "legacy"}', encoding="utf-8")
    assert store.get_json(str(legacy)) == {"summary": "legacy"}


def test_explicit_local_root_uses_filesystem(s3_store, tmp_path):
    store = ArtifactStore(root=str(tmp_path))
    uri = store.put_json("results/job.json", {"summary": "local"})
    assert not uri.startswith("s3://")
    assert store.exists(uri)
    assert store.get_json(uri) == {"summary": "local"}
