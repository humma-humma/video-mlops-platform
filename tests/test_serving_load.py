from urllib.error import HTTPError

import pytest

from scripts import serving_load as load


def test_summary_keeps_failures_out_of_success_percentiles_but_in_denominator():
    rows = [{"outcome": "SUCCEEDED", "completion_observed_seconds": 2},
            {"outcome": "SUCCEEDED", "completion_observed_seconds": 4},
            {"outcome": "FAILED", "completion_observed_seconds": 100},
            {"outcome": "TIMEOUT"}, {"outcome": "CLIENT_ERROR"}]
    metrics = load.summarize(rows, 30)
    assert metrics["attempted"] == 5
    assert metrics["succeeded"] == 2
    assert metrics["failed"] == metrics["timeouts"] == metrics["client_errors"] == 1
    assert metrics["successful_jobs_per_minute"] == 4
    assert metrics["successful_completion_observed_seconds"] == {"count": 2, "p50": 3, "p95": 3.9}
    assert metrics["successful_initial_queue_seconds"]["p95"] is None


def test_job_records_queue_evidence_and_keeps_generation_content_out(monkeypatch):
    def request(url, **kwargs):
        if kwargs.get("data"):
            assert kwargs["headers"]["Idempotency-Key"]
            return 202, {"job_id": "job"}
        if url.endswith("/attempts"):
            return 200, [{"started_at": "2026-10-10T12:00:03Z"}]
        return 200, {"status": "SUCCEEDED", "created_at": "2026-10-10T12:00:00Z",
                     "result": {"model_version": "real", "timings": {"model_load": 0},
                                "summary": "private content", "category": "News"}}
    monkeypatch.setattr(load, "request_json", request)
    journal = []
    row = load.measure_job("http://local", b"video", "multipart", 30, 1, journal.append)
    assert row["outcome"] == "SUCCEEDED"
    assert row["initial_queue_seconds"] == 3
    assert "private content" not in str(journal)
    assert [e["event"] for e in journal] == ["accepted", "finished"]
    assert journal[0]["outcome"] == "ACCEPTED"


def test_poll_error_preserves_accepted_job_and_redacts_error_body(monkeypatch):
    def request(url, **kwargs):
        if kwargs.get("data"):
            return 202, {"job_id": "still-running"}
        raise HTTPError(url, 503, "secret response detail", {}, None)
    monkeypatch.setattr(load, "request_json", request)
    journal = []
    row = load.measure_job("http://local", b"video", "multipart", 30, 1, journal.append)
    assert row["job_id"] == "still-running"
    assert row["outcome"] == "CLIENT_ERROR"
    assert row["http_status"] == 503
    assert "secret response detail" not in str(journal)


def test_timeout_preserves_job_id_without_claiming_server_failure(monkeypatch):
    times = iter([0, 0, 2, 2])
    monkeypatch.setattr(load.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(load, "request_json", lambda *a, **k: (202, {"job_id": "slow"}))
    row = load.measure_job("http://local", b"video", "multipart", 1, 1, lambda _: None)
    assert row["outcome"] == "TIMEOUT"
    assert row["job_id"] == "slow"


@pytest.mark.parametrize("args", [["--jobs", "0"], ["--jobs", "2", "--concurrency", "3"],
                                  ["--timeout", "0"], ["--base-url", "https://user:password@example.com"]])
def test_invalid_or_credential_bearing_configuration_is_refused(args):
    with pytest.raises(SystemExit):
        load.main(["--video", "not-read.mp4", *args])
