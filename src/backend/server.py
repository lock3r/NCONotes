# FastAPI application — HTTP server, token auth middleware, static file serving,
# and the run() entry point called by main.py in a subprocess.
#
# Static files are served from backend/static/ when packaged, or frontend/dist/
# during development. API routes are protected by X-NCONotes-Token; /health and
# static file requests pass through without a token.

from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

# Packaged path takes precedence; falls back to the dev build output.
_PACKAGED_STATIC = Path(__file__).parent / "static"
_DEV_STATIC = Path(__file__).parent.parent / "frontend" / "dist"


class _TokenMiddleware(BaseHTTPMiddleware):
    """Rejects /api/* requests that do not carry the correct token header."""

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api"):
            if request.headers.get("X-NCONotes-Token") != self._token:
                return JSONResponse(
                    {"error": "unauthorized", "detail": "Missing or invalid token"},
                    status_code=401,
                )
        return await call_next(request)


def _build_app(token: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(_TokenMiddleware, token=token)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    static_dir = _PACKAGED_STATIC if _PACKAGED_STATIC.exists() else _DEV_STATIC
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def run(port: int, token: str) -> None:
    """Start the uvicorn server. Called as the target of a multiprocessing.Process."""
    app = _build_app(token)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
