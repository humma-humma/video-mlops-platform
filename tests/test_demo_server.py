from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

from fastapi.testclient import TestClient
import pytest

from scripts.demo_server import MAX_UPLOAD, create_app


@pytest.fixture
def preview():
    received = []
    class Upstream(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append((self.command, self.path, dict(self.headers), b""))
            if self.path == "/health/ready":
                self.send_response(503)
                self.send_header("Retry-After", "5")
            else:
                self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "test", "path": self.path}).encode())

        def do_POST(self):
            data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            received.append((self.command, self.path, dict(self.headers), data))
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"job_id":"test-job","status":"QUEUED"}')

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Upstream) as upstream:
        thread = Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with TestClient(create_app(f"http://127.0.0.1:{upstream.server_port}"), base_url="http://localhost") as client:
            yield client, received
        upstream.shutdown()
        thread.join()


def test_preview_serves_local_assets_with_restrictive_policy(preview):
    client, received = preview
    response = client.get("/")
    assert response.status_code == 200
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/demo-assets/demo.js").status_code == 200
    assert client.get("/demo-assets/demo.css").status_code == 200
    assert client.get("/operations").status_code == 200
    assert client.get("/demo-assets/operations.js").status_code == 200
    assert not received


def test_proxy_preserves_upload_auth_idempotency_and_query(preview):
    client, received = preview
    response = client.post("/api/v1/jobs", content=b"fixture", headers={
        "Content-Type": "video/mp4", "X-API-Key": "test-only-key", "Idempotency-Key": "unique",
        "Origin": "http://localhost"})
    assert response.status_code == 202
    assert received[0][3] == b"fixture"
    assert received[0][2]["X-Api-Key"] == "test-only-key"
    assert received[0][2]["Idempotency-Key"] == "unique"
    assert client.get("/api/v1/jobs?limit=12").json()["path"] == "/api/v1/jobs?limit=12"


def test_upstream_failures_keep_status_and_retry_hint(preview):
    client, _ = preview
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"


def test_gpu_route_checks_upstream_access_before_collecting(monkeypatch):
    from scripts import demo_server
    collected = []
    monkeypatch.setattr(demo_server, "gpu_snapshot", lambda: collected.append(True) or {"available": True})
    class Denied(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.headers.get("X-API-Key") == "allowed" else 401)
            self.end_headers()
        def log_message(self, *args):
            pass
    with ThreadingHTTPServer(("127.0.0.1", 0), Denied) as upstream:
        thread = Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        with TestClient(create_app(f"http://127.0.0.1:{upstream.server_port}"), base_url="http://localhost") as client:
            assert client.get("/local/gpu").status_code == 401
            assert not collected
            assert client.get("/local/gpu", headers={"X-API-Key": "allowed"}).json()["available"]
            assert collected == [True]
        upstream.shutdown()
        thread.join()


def test_proxy_refuses_cross_origin_oversize_and_unlisted_routes(preview):
    client, received = preview
    assert client.post("/api/v1/jobs", headers={"Origin": "https://outside.example"}).status_code == 403
    assert client.post("/api/v1/jobs", headers={"Content-Length": str(MAX_UPLOAD + 1)}).status_code == 413
    assert client.post("/metrics").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/", headers={"Host": "outside.example"}).status_code == 400
    assert not received


@pytest.mark.parametrize("upstream", ["https://example.com", "http://192.168.1.5:8000",
                                      "http://user:secret@localhost", "http://localhost/api"])
def test_nonlocal_or_credential_bearing_upstream_is_refused(upstream):
    with pytest.raises(ValueError, match="loopback"):
        create_app(upstream)
