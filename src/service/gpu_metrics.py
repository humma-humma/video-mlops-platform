"""Device-wide host telemetry; intentionally does not attribute usage to a job."""
import csv
import math
import subprocess
from datetime import datetime, timezone
from io import StringIO


def gpu_snapshot():
    snapshot = {"timestamp": datetime.now(timezone.utc).isoformat(),
                "scope": "device-wide; includes other applications", "devices": []}
    try:
        result = subprocess.run([
            "nvidia-smi", "--query-gpu=index,name,memory.total,memory.used,utilization.gpu,temperature.gpu",
            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5, check=True)
        for row in csv.reader(StringIO(result.stdout)):
            if len(row) != 6:
                raise ValueError("Unexpected GPU response")
            values = [float(value.strip()) for value in row[2:]]
            if not all(math.isfinite(value) and value >= 0 for value in values):
                raise ValueError("Invalid GPU measurement")
            snapshot["devices"].append(dict(zip(
                ("index", "name", "memory_total_mib", "memory_used_mib", "utilization_percent", "temperature_c"),
                [int(row[0]), row[1].strip(), *values])))
        snapshot["available"] = bool(snapshot["devices"])
    except (OSError, subprocess.SubprocessError, ValueError):
        snapshot.update(available=False, devices=[], reason="Host NVIDIA telemetry unavailable")
    return snapshot
