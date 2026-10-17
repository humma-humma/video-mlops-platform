"""Serve the demo on loopback while forwarding only known local API routes."""
import argparse
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request as UpstreamRequest, build_opener

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.service.demo_ui import install_demo
from src.service.gpu_metrics import gpu_snapshot

MAX_UPLOAD = 64 * 1024 * 1024
MAX_RESPONSE = 5 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def allowed_route(method, path):
    if method == "GET" and path in {"health/ready", "health/live", "metrics", "api/v1/jobs"}:
        return True
    if method == "POST" and path == "api/v1/jobs":
        return True
    match = re.fullmatch(r"api/v1/jobs/[0-9a-f-]{36}(?:/(result|attempts|events|cancel|retry))?", path, re.I)
    return bool(match and ((method == "GET" and match[1] in {None, "result", "attempts", "events"}) or
                          (method == "POST" and match[1] in {"cancel", "retry"})))


def create_app(upstream="http://127.0.0.1:8000"):
    parsed = urlsplit(upstream)
    if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise ValueError("Demo upstream must be a loopback HTTP origin without credentials")
    app = FastAPI(title="Local Video-MLOps Demo", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    install_demo(app)
    opener = build_opener(ProxyHandler({}), NoRedirect)

    def forward(path, method, body, headers):
        request = UpstreamRequest(upstream.rstrip("/") + "/" + path,
                                  data=body if method == "POST" else None, headers=headers, method=method)
        try:
            response = opener.open(request, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            payload = response.read(MAX_RESPONSE + 1)
            if len(payload) > MAX_RESPONSE:
                raise ValueError("Upstream response exceeds demo limit")
            returned = {"Content-Type": response.headers.get("Content-Type", "application/json"),
                        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
            for name in ("Retry-After", "traceparent"):
                if response.headers.get(name):
                    returned[name] = response.headers[name]
            return Response(payload, status_code=response.status, headers=returned)

    @app.get("/local/gpu")
    async def host_gpu(request: Request):
        headers = {"x-api-key": request.headers["x-api-key"]} if "x-api-key" in request.headers else {}
        try:
            access = await run_in_threadpool(forward, "api/v1/jobs?limit=1", "GET", b"", headers)
            if access.status_code != 200:
                return access
            return JSONResponse(await run_in_threadpool(gpu_snapshot), headers={"Cache-Control": "no-store"})
        except (URLError, TimeoutError, OSError, ValueError):
            return JSONResponse({"detail": "Local API unavailable"}, status_code=502)

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def proxy(path: str, request: Request):
        if not allowed_route(request.method, path):
            return JSONResponse({"detail": "Route not available in local demo"}, status_code=404)
        if request.method == "POST":
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin submissions are not allowed"}, status_code=403)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > MAX_UPLOAD):
            return JSONResponse({"detail": "Local demo upload limit is 64 MiB"}, status_code=413)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_UPLOAD:
                return JSONResponse({"detail": "Local demo upload limit is 64 MiB"}, status_code=413)
        headers = {name: request.headers[name] for name in
                   ("content-type", "x-api-key", "idempotency-key", "traceparent") if name in request.headers}
        target = path + ("?" + request.url.query if request.url.query else "")
        try:
            return await run_in_threadpool(forward, target, request.method, bytes(body), headers)
        except (URLError, TimeoutError, OSError, ValueError):
            return JSONResponse({"detail": "Local API unavailable; check the service and retry Refresh"}, status_code=502)

    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port must be between 1 and 65535")
    uvicorn.run(create_app(args.api_url), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
