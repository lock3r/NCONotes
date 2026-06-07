# PySide6 → FastAPI + React Migration

## Goal
Replace the PySide6 desktop app with a Python/FastAPI backend + React/TypeScript frontend,
glued together by pywebview for desktop use. The frontend must also work in a plain browser
by pointing it at localhost:{port}.

NOTE: this should not restrict a possible future usage in which we eventually ship this as a web service or whatever.
YAGNI: we don't add authentication now but we plan for it.

## Decisions made
- Keep backend, frontend and desktop glue separated so that in future we could spin a web service based on this
- HARD ARCHITECTURAL BOUNDARY between the components. Everything speaks via REST (no WebSockets for now — may revisit if real-time collaboration is ever needed)
- Canvas: CSS transforms (no library), single world div with absolutely-positioned items
- Rich text: TipTap
- Bundler: Vite
- Desktop wrapper: pywebview
- State management: Zustand (avoids prop drilling across the Sidebar/Canvas/Toolbar sibling tree)
- Auth: random token generated at startup, injected by pywebview as `window.NCONOTES_TOKEN`. Browser-dev mode points directly at localhost:{port}; a future web deployment will use a real auth system
- Port: ask OS for a free port (accept theoretical race condition — fine for desktop)
- File format: clean break, no migration needed
- Notebooks and pages are identified by UUID internally; the user-visible name is stored in metadata
- Undo/redo: command pattern in the Zustand store (typed operations, each with do/undo); TipTap handles its own undo inside the editor
- Deletion is always soft: notebooks and pages move to `.trash/`; individual notes get a `deleted_at` field inside the page JSON. All are recoverable for 60 days
- Z-ordering: clicking or creating a note brings it to the front (highest z-index). Overlapping is allowed; the topmost note always wins clicks
- Images can be added to the canvas via paste (Ctrl+V) or drag-and-drop from the filesystem

---

## Target project structure

```
NCONotes/
  main.py                        ← entry point
  backend/
    __init__.py
    server.py                    ← FastAPI app + run(port, token) entry point
    api/
      __init__.py
      notebooks.py               ← /api/notebooks routes
      pages.py                   ← /api/pages routes
      trash.py                   ← /api/trash routes
    storage/
      __init__.py
      notebooks.py               ← file I/O
      models.py                  ← data models (Pydantic)
  frontend/
    index.html
    package.json
    vite.config.ts
    tsconfig.json
    src/
      main.tsx                   ← React root
      api.ts                     ← typed fetch wrappers
      store.ts                   ← Zustand store (app state)
      components/
        App.tsx                  ← root layout (toolbar + sidebar + canvas + statusbar)
        ErrorBanner.tsx          ← global error notification
        Toolbar.tsx
        Sidebar.tsx
        StatusBar.tsx
        canvas/
          Canvas.tsx             ← world div, pan/zoom, event routing
          TextItem.tsx           ← text note card (display mode)
          ImageItem.tsx          ← standalone image card
          Editor.tsx             ← single shared TipTap instance
```

---

## Phase 1: Project scaffolding

1. Create `backend/` package with empty `__init__.py` files
2. Create `frontend/` with Vite + React + TypeScript template
   - `npm create vite@latest frontend -- --template react-ts`
   - Install: `tiptap`, `@tiptap/react`, `@tiptap/starter-kit`, `zustand`
3. Create `main.py` (stub — just prints "hello")
4. Verify the frontend builds: `cd frontend && npm run build`

## Phase 2: Backend — server startup

Two separate OS processes, coordinated by `main.py` at startup.
Uses `multiprocessing` with the `spawn` start method for identical behavior across platforms.

**Process 1 — backend** (spawned via `multiprocessing`):
- `backend/server.py` exposes a `run(port: int, token: str)` function
- `main.py` calls `multiprocessing.Process(target=run, args=(port, token))`
- `run()` starts uvicorn with the FastAPI app
- FastAPI app has token-checking middleware (rejects requests missing the correct
  `X-NCONotes-Token` header, except static file routes and `/health`)
- Serves `frontend/dist/` as static files at `/`
- Knows nothing about windows or pywebview

**Process 2 — desktop** (pywebview, runs in `main.py`):
- Opens a pywebview window at `http://localhost:{port}`
- Injects token as JS global: `window.NCONOTES_TOKEN = "{token}"`
- Knows nothing about storage or HTTP routing
- On window close: terminates the backend process

**`main.py` (orchestrator, ~25 lines)**:
- Sets multiprocessing start method to `spawn`
- `find_free_port()`: bind socket to port 0, read assigned port, close socket, return it
- `generate_token()`: `secrets.token_urlsafe(32)`
- Spawns backend process passing `port` and `token` directly as arguments
- Polls `GET /health` until backend is ready — raises `RuntimeError` after 30 seconds
- Opens pywebview window, blocks until window is closed
- Terminates backend process on exit

**Web deployment**: skip `main.py`, run backend directly with a proper auth system.

## Phase 3: Backend — storage and API

### Data models (`backend/storage/models.py`, Pydantic)

Two distinct canvas item types, matching the current implementation:

- `TextItem`: id, x, y, width, height, z_index, content (HTML string from TipTap), deleted_at (optional ISO timestamp)
- `ImageItem`: id, x, y, width, height, z_index, scale, image_id, deleted_at (optional ISO timestamp)
- `ViewState`: pan_x, pan_y, scale (persisted per page so the user resumes where they left off)
- `PageMeta`: id, title
- `Page`: id, view_state: ViewState, items: list[TextItem | ImageItem]
- `Notebook`: id, name, pages: list[PageMeta]

Items with `deleted_at` set are excluded from the canvas display but remain in the page JSON until the 60-day window expires, at which point they are stripped from the file on startup.

The `type` discriminator field (`"text"` / `"image"`) is stored in JSON and used by Pydantic to
deserialize the correct model. This matches the current `TextBoxData`/`ImageData` pattern.

### Notebook canvas (page_0)

Every notebook has a mandatory first page (`pages[0]`) that represents the notebook's own canvas.
It is created automatically when the notebook is created and is never shown in the page list UI.
Selecting the notebook in the sidebar loads this page. This matches the current `page_0` behavior.

### File layout on disk (`~/MyNotebooks/`)

```
{notebook_uuid}/
  notebook.json          ← {id, name, pages: [{id, title}]}
  pages/
    {page_uuid}.json     ← {id, view_state, items: [...]} — items include type discriminator
  images/
    {image_uuid}.png     ← images referenced by ImageItems and embedded in TipTap HTML
.trash/
  {notebook_uuid}/       ← deleted notebook folders moved here intact
    notebook.json        ← has an added "deleted_at" ISO timestamp field
  pages/
    {page_uuid}.json     ← deleted page files moved here; include "notebook_id" and "deleted_at"
```

Trash items older than 60 days are permanently purged on application startup.

### Image pipeline

Two flows, both triggered by paste (Ctrl+V) or drag-and-drop:

1. **Drop/paste on empty canvas**: creates a standalone `ImageItem` at the drop/paste position.
   The image bytes are uploaded via `POST /api/notebooks/{id}/images`, which returns `image_id`.
   The `ImageItem` stores that `image_id`. The image is served at `/api/notebooks/{id}/images/{image_id}`.

2. **Paste inside TipTap editor**: TipTap fires `onImagePaste(blob)`.
   The blob is uploaded via the same endpoint. The returned URL (`/api/notebooks/{id}/images/{image_id}`)
   is inserted as `<img src="{url}">` in the TipTap HTML. The HTML content is stored in `TextItem.content`.

Both flows use the same image upload endpoint. Images are always stored as `{uuid}.png` under `images/`.

### Image orphan cleanup

When a `TextItem` is deleted, its TipTap HTML may contain `<img src="...">` references whose
backing files are never explicitly removed. Similarly, if a `TextItem`'s content is edited and
an image is removed from the HTML, the file remains on disk.

Cleanup strategy: on startup (after trash purge), scan all non-deleted page JSONs in a notebook,
collect every `image_id` referenced (both from `ImageItem` fields and from `src` URLs in TipTap HTML),
and delete any `images/{uuid}.png` file not in that set. This runs per-notebook, lazily.

### Storage layer (`backend/storage/notebooks.py`)

```python
list_notebooks() → list[Notebook]
create_notebook(name: str) → Notebook               # generates UUID, creates page_0
delete_notebook(notebook_id: str) → None            # moves folder to .trash/
load_page(notebook_id, page_id) → Page
save_page(notebook_id, page_id, page: Page) → None  # also updates notebook.json if view_state changed
create_page(notebook_id, title: str) → PageMeta     # generates UUID, appends to notebook.json
delete_page(notebook_id, page_id) → None            # moves page file to .trash/pages/
save_image(notebook_id, image_data: bytes) → str    # returns image_id (uuid)
load_image(notebook_id, image_id) → bytes
list_trash() → list[TrashItem]                      # TrashItem: id, name, type (notebook|page|note), deleted_at, notebook_id, page_id
restore_trash_item(item_id: str, item_type: str) → None
purge_trash_item(item_id: str, item_type: str) → None  # permanent delete
purge_expired_trash() → None                        # called on startup; removes items > 60 days old
purge_orphaned_images() → None                      # called on startup after trash purge
```

### REST API

```
GET  /health                                         → 200 OK

GET  /api/notebooks                                  → list[Notebook]
POST /api/notebooks                                  → body: {name: str} → Notebook
DELETE /api/notebooks/{notebook_id}                  → soft delete (moves to trash)

GET  /api/notebooks/{notebook_id}/pages              → list[PageMeta]
POST /api/notebooks/{notebook_id}/pages              → body: {title: str} → PageMeta
DELETE /api/notebooks/{notebook_id}/pages/{page_id} → soft delete (moves to trash)
GET  /api/notebooks/{notebook_id}/pages/{page_id}   → Page
PUT  /api/notebooks/{notebook_id}/pages/{page_id}   → body: Page → 204 No Content

POST /api/notebooks/{notebook_id}/images             → multipart upload → {image_id, url}
GET  /api/notebooks/{notebook_id}/images/{image_id} → image file (PNG)

GET  /api/trash                                      → list[TrashItem]
POST /api/trash/{item_id}/restore                    → restore item
DELETE /api/trash/{item_id}                          → permanent delete
```

### Error response format

All errors return JSON `{"error": "<short label>", "detail": "<human-readable message>"}`.

HTTP status codes:
- `404` — notebook or page not found
- `422` — invalid request body (FastAPI default)
- `500` — unexpected server error (detail is generic; internal exception is logged server-side only)

## Phase 4: Frontend — layout shell

Build the static layout with no functionality:
- `App.tsx`: flexbox column — Toolbar (top, fixed height), middle row, StatusBar (bottom, fixed height)
- Middle row: Sidebar (fixed width) + Canvas area (fills remaining space)
- `ErrorBanner.tsx`: fixed overlay at the top, hidden by default, shown when the store has an active error
- All components render placeholder content
- Verify it looks right in the browser

## Phase 5: Frontend — canvas and notes

`Canvas.tsx`:
- Outer div: fills available space, `overflow: hidden`, captures mouse/wheel events
- Inner "world" div: `position: relative`, `transform: translate({panX}px, {panY}px) scale({scale})`
  (translate applied before scale so pan is in screen space, not world space)
- Pan: middle-mouse drag or space+drag updates panX/panY state
- Zoom: Ctrl+wheel updates scale
- Y-clamp: panY is clamped to `<= 0` so the top of the world stays at or above the viewport top
- On pan/zoom end: persists ViewState to backend (debounced — don't save on every pixel)
- Double-click on empty canvas: creates a TextItem at that world position, opens editor on it
- Ctrl+V on canvas (no active editor) or file drop on canvas: if clipboard/drop contains an image, creates ImageItem at that position
- Renders `<TextItem>` and `<ImageItem>` for each non-deleted item, sorted by `z_index` ascending (highest z_index renders last = on top)
- Clicking any item sets its `z_index` to `max(all z_indices) + 1` (brings to front)

`TextItem.tsx`:
- `position: absolute`, `left: item.x`, `top: item.y`, `width: item.width`, `height: item.height`
- Top bar (drag handle): mousedown starts drag, mousemove updates position, mouseup commits and triggers auto-save
- Body: renders `item.content` as innerHTML (display mode)
- Double-click body: fires `onActivate(itemId)` — Canvas attaches the shared Editor
- Resize: bottom-right handle updates width/height on mouseup, triggers auto-save
- Delete button (visible on hover/select): sets `deleted_at` on the item, triggers auto-save

`ImageItem.tsx`:
- Same positioning, drag/resize, and z-ordering behavior as TextItem
- Renders `<img src="{imageUrl}">` where `imageUrl` is `/api/notebooks/{id}/images/{image_id}`
- Delete button: sets `deleted_at` on the item, triggers auto-save
- Accepts drop events (image file dropped directly onto an existing ImageItem replaces its content)

`Editor.tsx`:
- Single TipTap editor instance, rendered once, hidden when inactive
- When activated for an item: positioned to overlay that item's body, loaded with item's content
- On deactivate (click outside, Escape, tab away): saves content back to item, hides, triggers auto-save
- Handles paste: text pastes into editor normally; image paste fires `onImagePaste(blob)`

## Phase 6: Frontend — API client and state

`api.ts`:
- All fetch calls go through a single `apiFetch(path, options)` wrapper that:
  - Adds `X-NCONotes-Token: window.NCONOTES_TOKEN` to every request
  - On non-2xx response: throws `ApiError` with `{error, detail}` parsed from the response body
- Typed functions: `listNotebooks()`, `createNotebook(name)`, `deleteNotebook(id)`,
  `listPages(notebookId)`, `createPage(notebookId, title)`, `deletePage(notebookId, pageId)`,
  `loadPage(notebookId, pageId)`, `savePage(notebookId, pageId, page)`,
  `uploadImage(notebookId, blob)`, `listTrash()`, `restoreTrashItem(id)`, `purgeTrashItem(id)`

`store.ts` (Zustand):
```ts
{
  notebooks: Notebook[]
  currentNotebookId: string | null
  currentPageId: string | null
  items: (TextItem | ImageItem)[]
  viewState: ViewState
  undoStack: UndoableOp[]         // capped at ~50 entries
  redoStack: UndoableOp[]
  activeError: string | null      // displayed by ErrorBanner
  setError(message: string): void // called by any component on ApiError
  clearError(): void
  undo(): void
  redo(): void
  // ... actions: loadNotebooks, selectNotebook, selectPage, updateItem, deleteItem, etc.
}
```

**Undo/redo design:**
- `UndoableOp` is a typed discriminated union: `CreateItem | DeleteItem | MoveItem | ResizeItem | EditContent`
- Each variant stores enough state to reverse the operation (e.g. `MoveItem` stores `{itemId, oldPos, newPos}`)
- Every user action pushes an op onto `undoStack` and clears `redoStack`
- `undo()` pops from `undoStack`, applies the inverse, pushes onto `redoStack`, triggers auto-save
- `redo()` pops from `redoStack`, re-applies, pushes onto `undoStack`, triggers auto-save
- TipTap content edits are coalesced: rapid typing merges into one `EditContent` op (same item, within 1s)
- Undo/redo scope is per-page — switching pages clears both stacks
- Keyboard: Ctrl+Z / Ctrl+Shift+Z (or Ctrl+Y); when TipTap is active, TipTap handles its own Ctrl+Z

Auto-save behavior:
- Any change to items (move, resize, content edit, create, delete) triggers a debounced `savePage()` call (500ms debounce)
- Any change to ViewState (pan, zoom) triggers a debounced `savePage()` call (300ms debounce)
- There is no manual save button — the UI reflects real state at all times
- On `ApiError` during save: `setError("Save failed — changes may not be persisted")` with a retry option

## Phase 7: Wire up Toolbar and Sidebar

Toolbar:
- Notebook name display (current notebook)
- Page tabs or prev/next navigation
- "New Notebook" and "New Page" buttons

Sidebar:
- List of notebooks (click to navigate)
- List of pages in selected notebook (click to navigate)
- "New Notebook" / "New Page" buttons (also in Toolbar — pick one location, avoid duplication)
- Trash section: link to a trash view showing deleted items with restore/purge actions

StatusBar:
- Current zoom level
- Item count on current page
- Auto-save indicator ("Saved" / "Saving..." / "Save failed")

ErrorBanner:
- Fixed overlay, red background, shown when `store.activeError` is set
- Shows error message and a "Dismiss" button (calls `clearError()`)
- For save errors: also shows a "Retry" button

## Phase 8: Cleanup

- Delete all PySide6 code (`src/nconotes/`)
- Update `pyproject.toml` / `requirements.txt`: remove PySide6, add FastAPI, uvicorn, pywebview
- Update README

---

## Packaging targets (.deb, Flatpak)

Goal: self-contained app, only external dependency is the platform webview engine
(WebKitGTK on Linux, WebView2 on Windows, WKWebView on macOS).

**What this means for the code:**
- Frontend is always pre-built to static files. No Node.js at runtime, ever.
  `npm run build` is a build-time step, not a runtime step.
- The path to `frontend/dist/` must be resolved relative to `backend/server.py`
  using `Path(__file__).parent / "static"` (or similar). Never hardcoded.
  The build process copies the built frontend into that location.
- All Python dependencies must be bundleable (FastAPI, uvicorn, pywebview, pydantic
  are all compatible with standard Python bundling tools).

**Flatpak notes:**
- Use `org.gnome.Platform` runtime which includes WebKitGTK
- Bundle Python + pip deps inside the flatpak
- pywebview's WebKitGTK backend works in the flatpak sandbox

**These are future concerns — YAGNI applies. But the static path resolution must be
correct from the start to avoid a painful retrofit later.**

---

## Key constraints to keep in mind

- One TipTap editor instance total — activated per item, never multiple editors live
- World Y is clamped: panY <= 0 always
- Canvas transform order: `translate(panX, panY) scale(scale)` — translate before scale
- Token required on every API call (`X-NCONotes-Token` header)
- Backend is stateless per request — page is fully loaded and fully saved each time
- No explicit save — all changes auto-save (debounced)
- Errors are always shown to the user via ErrorBanner; nothing fails silently
- Deletion is always soft: notebooks/pages move to `.trash/`; notes get `deleted_at` in the page JSON
- Trash items older than 60 days are purged on startup; orphaned images are cleaned up in the same pass
- Health poll in main.py raises RuntimeError after 30 seconds if backend doesn't respond
- Notebooks and pages are identified internally by UUID; user-visible names are metadata
- Z-ordering: items are rendered by `z_index` ascending; any click/create sets `z_index` to current max+1
- Undo/redo scope is per-page; stacks are cleared on page switch; TipTap owns its own undo when active
- Images enter the canvas via paste (Ctrl+V) or drag-and-drop from the filesystem
