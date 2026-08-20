# FastAPI application — HTTP server, token auth middleware, static file serving,
# and the run() entry point called by main.py in a subprocess.
#
# Static files are served from backend/static/ when packaged, or frontend/dist/
# during development. API routes are protected by X-NCONotes-Token; /health and
# static file requests pass through without a token.
#
# The token may also be presented as a session cookie. Browsers cannot attach custom
# headers to <img src> requests, so image URLs would otherwise be unreachable; the
# frontend exchanges its header token for the cookie once via POST /api/session.
# SameSite=strict keeps the cookie off cross-site requests, so a hostile page cannot
# use it to reach the API.

import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api import notebooks, pages, trash
from backend.storage.notebooks import purge_expired_trash

# Packaged path takes precedence; falls back to the dev build output.
_PACKAGED_STATIC = Path(__file__).parent / "static"
_DEV_STATIC = Path(__file__).parent.parent / "frontend" / "dist"


SESSION_COOKIE = "nconotes_session"


class _TokenMiddleware(BaseHTTPMiddleware):
    """Rejects /api/* requests that present neither the token header nor the session cookie."""

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    def _is_authorized(self, request: Request) -> bool:
        presented = request.headers.get("X-NCONotes-Token") or request.cookies.get(SESSION_COOKIE)
        if not presented:
            return False
        return secrets.compare_digest(presented, self._token)

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api") and not self._is_authorized(request):
            return JSONResponse(
                {"error": "unauthorized", "detail": "Missing or invalid token"},
                status_code=401,
            )
        return await call_next(request)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    purge_expired_trash()
    yield


def _build_app(token: str) -> FastAPI:
    app = FastAPI(lifespan=_lifespan)
    app.add_middleware(_TokenMiddleware, token=token)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/session", status_code=204)
    async def create_session():
        # Reaching this handler means the middleware already validated the header
        # token, so the cookie can be issued unconditionally.
        response = Response(status_code=204)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    app.include_router(notebooks.router, prefix="/api")
    app.include_router(pages.router, prefix="/api")
    app.include_router(trash.router, prefix="/api")

    static_dir = _PACKAGED_STATIC if _PACKAGED_STATIC.exists() else _DEV_STATIC
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def run(port: int, token: str) -> None:
    """Start the uvicorn server. Called as the target of a multiprocessing.Process."""
    app = _build_app(token)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
