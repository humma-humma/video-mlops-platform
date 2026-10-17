from types import SimpleNamespace
import subprocess

import pytest

from src.service.gpu_metrics import gpu_snapshot


def test_device_metrics_have_explicit_scope_and_units(monkeypatch):
    def run(command, **kwargs):
        assert command[0] == "nvidia-smi"
        assert kwargs["timeout"] == 5
        return SimpleNamespace(stdout="0, RTX 2080, 8192, 4000, 43, 82\n")
    monkeypatch.setattr(subprocess, "run", run)
    snapshot = gpu_snapshot()
    assert snapshot["available"]
    assert "other applications" in snapshot["scope"]
    assert snapshot["devices"][0]["memory_used_mib"] == 4000


@pytest.mark.parametrize("output", ["0, GPU, N/A, 3, 4, 5", "0, GPU, 8192, nan, 0, 32", "invalid"])
def test_unavailable_or_invalid_measurements_are_not_reported_as_zero(monkeypatch, output):
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: SimpleNamespace(stdout=output))
    assert gpu_snapshot()["available"] is False


def test_missing_nvidia_command_is_nonfatal(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(subprocess, "run", missing)
    assert gpu_snapshot()["devices"] == []
