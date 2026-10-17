"""Shared static demo assets for the service and the local preview server."""
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ASSETS = Path(__file__).with_name("static")
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def install_demo(app):
    app.mount("/demo-assets", StaticFiles(directory=ASSETS), name="demo-assets")

    @app.get("/", include_in_schema=False)
    def demo_page():
        return FileResponse(ASSETS / "index.html", headers=SECURITY_HEADERS)

    @app.get("/operations", include_in_schema=False)
    def operations_page():
        return FileResponse(ASSETS / "operations.html", headers=SECURITY_HEADERS)
