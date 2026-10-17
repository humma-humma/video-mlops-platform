import json
from pathlib import Path, PurePosixPath

from .config import settings


class ArtifactStorageError(RuntimeError):
    """Artifact dependency failed; safe to report without SDK credentials/details."""


class ArtifactStore:
    def __init__(self, root: str | None = None, *, s3_client=None):
        self.root = Path(root or settings.artifact_root)
        self.backend = "filesystem" if root is not None else settings.artifact_backend
        self.bucket = settings.s3_bucket
        self.client = s3_client
        if self.backend == "filesystem":
            self.root.mkdir(parents=True, exist_ok=True)
        elif self.client is None:
            import boto3
            from botocore.config import Config

            self.client = boto3.client(
                "s3", endpoint_url=settings.s3_endpoint_url,
                region_name=settings.s3_region,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
                config=Config(
                    s3={"addressing_style": "path"},
                    connect_timeout=3, read_timeout=10,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )

    def _request(self, operation: str, **kwargs):
        try:
            return getattr(self.client, operation)(**kwargs)
        except Exception as error:
            code = str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NoSuchBucket", "NotFound"}:
                raise FileNotFoundError("Artifact or bucket is missing") from error
            raise ArtifactStorageError("Artifact store request failed") from error

    def ensure_bucket(self) -> None:
        """Explicit bootstrap; ordinary object operations never create buckets."""
        if self.backend != "s3":
            return
        try:
            self._request("head_bucket", Bucket=self.bucket)
        except FileNotFoundError:
            options = {"Bucket": self.bucket}
            if settings.s3_region != "us-east-1":
                options["CreateBucketConfiguration"] = {"LocationConstraint": settings.s3_region}
            self._request("create_bucket", **options)

    def ready(self) -> bool:
        if self.backend == "filesystem":
            return self.root.is_dir()
        try:
            self._request("head_bucket", Bucket=self.bucket)
            return True
        except (ArtifactStorageError, FileNotFoundError):
            return False

    def _object_key(self, uri: str) -> str:
        prefix = f"s3://{self.bucket}/"
        if not uri.startswith(prefix) or not uri[len(prefix):]:
            raise ValueError("Artifact URI must reference the configured S3 bucket")
        return uri[len(prefix):]

    def put_bytes(self, key: str, value: bytes) -> str:
        if not key or "\\" in key or PurePosixPath(key).is_absolute() or ".." in PurePosixPath(key).parts:
            raise ValueError("Artifact key must be a relative object path")
        if self.backend == "s3":
            self._request("put_object", Bucket=self.bucket, Key=key, Body=value)
            return f"s3://{self.bucket}/{key}"
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return str(path)

    def put_json(self, key: str, value: dict) -> str:
        return self.put_bytes(key, (json.dumps(value, indent=2) + "\n").encode())

    def get_json(self, path: str) -> dict:
        return json.loads(self.get_bytes(path).decode("utf-8"))

    def get_bytes(self, uri: str) -> bytes:
        # Existing filesystem-backed job records remain readable during migration.
        if not uri.startswith("s3://"):
            return Path(uri).read_bytes()
        response = self._request("get_object", Bucket=self.bucket, Key=self._object_key(uri))
        body = response["Body"]
        try:
            return body.read()
        except Exception as error:
            raise ArtifactStorageError("Artifact download failed") from error
        finally:
            body.close()

    def exists(self, uri: str) -> bool:
        if not uri.startswith("s3://"):
            return Path(uri).is_file()
        try:
            self._request("head_object", Bucket=self.bucket, Key=self._object_key(uri))
            return True
        except FileNotFoundError:
            return False

    def download_file(self, uri: str, destination: Path) -> Path:
        """Materialize an artifact at a server-selected worker scratch path."""
        destination.write_bytes(self.get_bytes(uri))
        return destination


if __name__ == "__main__":
    import time

    store = ArtifactStore()
    for attempt in range(30):
        try:
            store.ensure_bucket()
            break
        except (ArtifactStorageError, FileNotFoundError):
            if attempt == 29:
                raise
            time.sleep(2)
