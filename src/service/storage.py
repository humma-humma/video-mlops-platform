import json
from pathlib import Path

from .config import settings


class ArtifactStore:
    def __init__(self, root: str | None = None):
        self.root = Path(root or settings.artifact_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put_bytes(self, key: str, value: bytes) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return str(path)

    def put_json(self, key: str, value: dict) -> str:
        return self.put_bytes(key, (json.dumps(value, indent=2) + "\n").encode())

    def get_json(self, path: str) -> dict:
        return json.loads(Path(path).read_text(encoding="utf-8"))
