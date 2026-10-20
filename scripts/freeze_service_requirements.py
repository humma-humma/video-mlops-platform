"""Snapshot the tested Python 3.12 service environment for review."""

from collections import deque
from importlib.metadata import distribution, distributions
from pathlib import Path
import sys

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
ROOTS = ("celery[redis]", "boto3", "alembic", "fastapi", "psycopg[binary]",
         "pydantic-settings", "python-multipart", "sqlalchemy", "uvicorn[standard]")


def service_packages():
    queue = deque(Requirement(name) for name in ROOTS)
    seen = set()
    pinned = {}
    environment = default_environment()
    while queue:
        requirement = queue.popleft()
        name = canonicalize_name(requirement.name)
        extras = frozenset(requirement.extras)
        if (name, extras) in seen:
            continue
        seen.add((name, extras))
        package = distribution(name)
        pinned[name] = package.version
        for raw in package.requires or ():
            child = Requirement(raw)
            if child.marker is None or any(child.marker.evaluate({**environment, "extra": extra})
                                           for extra in ("", *extras)):
                queue.append(child)
    return pinned


def main():
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError("Freeze the service from a tested Python 3.12 environment")
    service = service_packages()
    all_packages = {canonicalize_name(dist.metadata["Name"]): dist.version for dist in distributions()
                    if canonicalize_name(dist.metadata["Name"]) not in {"pip", "setuptools", "wheel"}}
    header = "# Recorded Python 3.12 dependency snapshot; see docs/REPRODUCIBILITY.md.\n"
    for name, packages in (("requirements-service.lock.txt", service),
                           ("requirements-service-test.lock.txt", all_packages)):
        lines = [f"{package}=={version}" for package, version in sorted(packages.items())]
        with (ROOT / name).open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(header + "\n".join(lines) + "\n")
        print(f"Wrote {name}: {len(lines)} pinned distributions")


if __name__ == "__main__":
    main()
