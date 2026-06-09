# Phase 3 Implementation Report — Storage and API

Date: 2026-06-09

## What was done

### 1. `src/backend/storage/models.py` — Pydantic data models

All models match the plan exactly:

- `TextItem` — `type: Literal["text"]`, id, x, y, width, height, z_index, content (HTML), deleted_at
- `ImageItem` — `type: Literal["image"]`, id, x, y, width, height, z_index, scale, image_id, deleted_at
- `CanvasItem` — `Annotated[Union[TextItem, ImageItem], Field(discriminator="type")]`; Pydantic dispatches on the `type` field when deserializing
- `ViewState` — pan_x, pan_y, scale (all float, defaulting to 0/0/1)
- `PageMeta` — id (UUID), title
- `Page` — id, view_state, items; plus trash-only fields: deleted_at, notebook_id, title
- `Notebook` — id (UUID), name, pages, plus trash-only deleted_at
- `TrashItem` — id, name, type (notebook/page/note), deleted_at, notebook_id, page_id

Trash-only fields are stored on `Page` and `Notebook` directly rather than in separate model variants. They are `None` in normal operation and only populated when an item is moved to trash.

### 2. `src/backend/storage/notebooks.py` — storage layer

Storage root: `~/MyNotebooks/` by default. Overridable via `NCONOTES_STORAGE_ROOT` environment variable (used by tests).

Key implementation notes:

- `create_notebook(name)`: generates UUID for notebook and page_0, creates `{root}/{id}/pages/` and `images/` directories, writes both `notebook.json` and `pages/{page0_id}.json`. Page_0 has `title=""` to signal it's the notebook canvas, not a user page.
- `delete_notebook` / `delete_page`: write `deleted_at` (and `notebook_id`, `title` for pages) into the JSON before moving to `.trash/`. This preserves metadata needed by `list_trash()` without a separate index file.
- `list_trash()`: three independent scans — (1) subdirectories of `.trash/` for deleted notebooks, (2) `.trash/pages/*.json` for deleted pages, (3) all active `pages/*.json` for items with `deleted_at` (soft-deleted notes). The three scans are all independent; no early return short-circuits them.
- `purge_trash_item(note)`: parses TipTap HTML for embedded `<img src="/api/notebooks/{id}/images/{image_id}">` URLs and deletes the referenced `.png` files.
- `purge_expired_trash()`: called on application startup via FastAPI lifespan; removes items with `deleted_at` older than 60 days.
- `NotFoundError` and `StorageError` are the two public exception types; API routers map these to 404 and 500 respectively.

### 3. `src/backend/api/notebooks.py`, `pages.py`, `trash.py` — FastAPI routers

All routes from the plan implemented:

```
GET    /api/notebooks
POST   /api/notebooks                             201
DELETE /api/notebooks/{notebook_id}               204

GET    /api/notebooks/{notebook_id}/pages
POST   /api/notebooks/{notebook_id}/pages         201
DELETE /api/notebooks/{notebook_id}/pages/{page_id}  204
GET    /api/notebooks/{notebook_id}/pages/{page_id}
PUT    /api/notebooks/{notebook_id}/pages/{page_id}  204

POST   /api/notebooks/{notebook_id}/images        201  (multipart)
GET    /api/notebooks/{notebook_id}/images/{image_id}

GET    /api/trash
POST   /api/trash/{item_id}/restore?type=…        204
DELETE /api/trash/{item_id}?type=…                204
```

Error responses are `{"error": "<label>", "detail": "<message>"}` as specified.

### 4. `src/backend/server.py` — wired routers and startup purge

Added FastAPI `lifespan` context manager that calls `purge_expired_trash()` on startup. Routers included with `prefix="/api"`. The token middleware and static file serving are unchanged.

### 5. Tests

60 tests in `tests/test_storage.py` and `tests/test_api.py`, all passing. All storage tests use a per-test temporary directory via `NCONOTES_STORAGE_ROOT`. API tests use `TestClient(_build_app(token))` against the real storage layer — no mocks.

One warning present: `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` This is a version mismatch between the installed `fastapi[standard]` and `httpx` packages, not a test failure. Not addressed here as it does not affect correctness.

---

## Divergences from the plan

### 1. Trash-only fields on Page and Notebook models

The plan does not specify how `deleted_at`, `notebook_id`, and `title` are stored when items move to trash. Rather than creating separate `TrashedPage` / `TrashedNotebook` model variants, these fields were added as `Optional` fields to the existing `Page` and `Notebook` models (always `None` in normal operation). This avoids a separate model hierarchy while keeping the JSON self-describing.

### 2. `type` query parameter on trash restore/purge endpoints

The plan shows:
```
POST /api/trash/{item_id}/restore
DELETE /api/trash/{item_id}
```

Without specifying how the item type (notebook/page/note) is communicated. The storage layer's `restore_trash_item` and `purge_trash_item` require the type. A `?type=notebook|page|note` query parameter was added to both endpoints. The client always has this information from `list_trash()`.

### 3. `save_page` does not update notebook.json

The plan's storage spec says `save_page` "also updates notebook.json if view_state changed." `ViewState` is stored inside the page JSON, not in `notebook.json`, so there is nothing to update in notebook.json on a page save. The comment in the plan spec appears to be stale. `save_page` only writes the page JSON.

### 4. `httpx` dev dependency installed via poetry (not in plan)

`pytest` and `httpx` were added as dev dependencies (`poetry add --group dev pytest httpx`) to support the test suite. `httpx` was already present as a transitive dependency of `fastapi[standard]`; the explicit `poetry add` was a no-op for it, only `pytest` was newly installed.

---

## Files created / modified

```
src/backend/storage/models.py     (new)
src/backend/storage/notebooks.py  (new)
src/backend/api/notebooks.py      (new)
src/backend/api/pages.py          (new)
src/backend/api/trash.py          (new)
src/backend/server.py             (modified — routers, lifespan)
tests/test_storage.py             (new)
tests/test_api.py                 (new)
pyproject.toml                    (dev dependency: pytest)
poetry.lock                       (updated)
```
