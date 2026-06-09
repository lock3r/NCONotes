# Phase 2 Implementation Report — Backend Server Startup

Date: 2026-06-09

## What was done

### 1. Relocated all Phase 1 scaffolding into `src/`

After Phase 1 committed `backend/`, `frontend/`, and `main.py` at the project root alongside the
existing `src/nconotes/` tree, Pino clarified a strong preference for everything inside `src/`.
All three were moved before any Phase 2 code was written:

```
backend/        →  src/backend/
frontend/       →  src/frontend/
main.py         →  src/main.py
```

`pyproject.toml` was updated to declare the new package locations:

```toml
[tool.poetry]
packages = [
    {include = "backend", from = "src"},
    {include = "main.py", from = "src"},
]

[tool.poetry.scripts]
nconotes = "main:main"
```

`poetry install` re-wires the editable install so `backend` and `main` are importable as
top-level modules without any `sys.path` manipulation.

### 2. Dependencies installed

`fastapi[standard]`, `uvicorn[standard]`, and `pywebview` were added via `poetry add`. The plan
placed this in Phase 8 but Phase 2 cannot be implemented or tested without them. This is the only
change to `pyproject.toml`'s `[project]` section — PySide6 is still listed (removal is Phase 8).

### 3. `src/backend/server.py`

FastAPI application with:

- `_TokenMiddleware`: Starlette `BaseHTTPMiddleware` subclass that rejects any `/api/*` request
  missing the correct `X-NCONotes-Token` header with a `401` JSON response. `/health` and static
  file requests pass through without a token.
- `GET /health` — returns `{"status": "ok"}`.
- Static file mount at `/` using `StaticFiles(html=True)`. Path resolution:
  - Packaged: `src/backend/static/` (build process copies `frontend/dist/` here)
  - Dev: `src/backend/../frontend/dist/` (i.e., `src/frontend/dist/`)
  - Mount is skipped silently if neither directory exists.
- `run(port, token)` — the function passed as `target` to `multiprocessing.Process`. Starts
  uvicorn on `127.0.0.1:{port}` with `log_level="warning"`.

### 4. `src/main.py`

Orchestrator with a `main()` function (called by the `nconotes` poetry script and by
`if __name__ == "__main__"`):

- `multiprocessing.set_start_method("spawn")` — consistent cross-platform behaviour.
- `find_free_port()` — binds a socket to port 0 and reads the assigned port.
- `generate_token()` — `secrets.token_urlsafe(32)`.
- Spawns `backend.server.run` as a daemon `multiprocessing.Process`.
- `_wait_for_backend()` — polls `GET /health` every 100ms; raises `RuntimeError` after 30s.
- Opens a pywebview window at `http://127.0.0.1:{port}`.
- Injects the token via `window.events.loaded` so it is set after every page load (including
  browser refresh).
- Terminates and joins the backend process in a `finally` block on window close.

### 5. Smoke tests

Verified with `fastapi.testclient.TestClient`:

- `GET /health` → 200 `{"status": "ok"}` (no token required)
- `GET /api/notebooks` (no token) → 401
- `GET /api/notebooks` (correct token) → 404 (route not yet implemented — middleware passed)

---

## Divergences from the plan

### 1. `src/` layout — backend, frontend, main all inside `src/`

The plan's target structure shows `backend/`, `frontend/`, and `main.py` at the project root.
Pino's preference (stated during Phase 2) is for everything to live inside `src/`. All three were
moved accordingly. `pyproject.toml` declares both `backend` and `main.py` from `src/` so they are
importable after `poetry install`.

### 2. Dependencies added in Phase 2, not Phase 8

The plan deferred `pyproject.toml` dependency updates to Phase 8 cleanup. In practice, `fastapi`,
`uvicorn`, and `pywebview` are required to implement and test Phase 2 code, so they were added now.
Phase 8 will still need to remove `pyside6`.

### 3. `main()` function wrapping

The plan describes `main.py` as a ~25-line script with top-level code under `if __name__ == "__main__"`.
The implementation wraps that body in a `main()` function so that the `nconotes` poetry console
script can reference it as `main:main`. The `if __name__ == "__main__": main()` guard is preserved
for direct `python src/main.py` invocation.

---

## Files created / modified

```
src/backend/server.py       (new)
src/main.py                 (new — relocated from root and expanded)
src/backend/                (relocated from root)
src/frontend/               (relocated from root)
pyproject.toml              (packages, scripts, new deps)
poetry.lock                 (updated)
```
