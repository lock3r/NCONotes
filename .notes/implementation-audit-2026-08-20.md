# NCONotes implementation audit

Date: 2026-08-20  
Scope: current working tree, including uncommitted frontend changes  
Reviewer perspective: first working implementation / pre-production desktop application

## Executive summary

NCONotes has a good small-application shape: the UI, HTTP API, storage layer, and desktop launcher are separated; the code is readable; API errors have a consistent envelope; dependencies are locked; and the existing backend tests cover the main happy paths and trash lifecycle. This is a credible prototype, not a badly designed project.

It is not yet safe to trust with important notes. The main reason is data integrity, not internet exposure. Navigating away from a page cancels its pending autosave instead of flushing it, so ordinary navigation can discard recent edits. Whole-page saves have neither serialization nor revision checks, so overlapping requests can complete out of order and silently restore older content. JSON writes are in-place and multi-file operations are not transactional, so interruption or disk failure can corrupt or partially apply changes.

The primary security boundary—random bearer token plus loopback binding—is directionally sound, but it is undermined by three issues: user-controlled identifiers are used as path components without validation or containment checks; stored HTML is inserted into the DOM without sanitization; and the bearer token is exposed to page JavaScript. Image uploads and model values are also effectively unbounded. These issues matter even for a local desktop app because a malicious/corrupt notebook, future import feature, compromised dependency, or another local process can cross boundaries that the design currently assumes are safe.

Overall assessment: **appropriate as an early prototype; not ready for valuable or untrusted data**.

### Priority snapshot

| Priority | Finding | Consequence |
|---|---|---|
| P0 | Pending autosaves are discarded during navigation | Routine silent data loss |
| P0 | Filesystem paths accept unvalidated identifiers | Authenticated path traversal / files outside the notebook tree may be read, overwritten, moved, or deleted |
| P0 | Stored HTML is rendered unsanitized while the token is readable by JavaScript | Persistent script/content injection and compromise of the local API boundary |
| P1 | Whole-page saves can race and have no revision control | Older state can overwrite newer state |
| P1 | JSON writes and multi-file mutations are non-atomic | Corruption and inconsistent notebook/trash state after interruption or I/O failure |
| P1 | Uploads and request models have no practical limits | Memory/disk exhaustion, pathological rendering, malformed state |
| P1 | No backup, recovery, or corruption visibility | One damaged JSON file can make content silently disappear from listings |
| P2 | Desktop port allocation has a bind race | Startup failure or connection to the wrong local process |

## Audit method and limitations

I inspected all application source, project configuration, lockfiles, and backend tests; traced UI-to-API-to-filesystem flows; reviewed the current Git diff so findings apply to the user's working tree; ran compilation/lint/build checks; and attempted the Python suite.

Checks performed:

- `npm run build`: passed. Vite warned that the main minified chunk is 638.37 kB (199.20 kB gzip).
- `npm run lint`: passed.
- `python -m compileall -q src tests`: passed.
- `poetry check --lock`: lock consistency passed, with deprecation warnings for the license table and Poetry script declaration.
- `python -m pytest -q`: did not finish or emit progress after several minutes on the Windows-mounted workspace; manually interrupted. This is **not** a test pass. Investigate collection/hanging behavior with verbose output and per-test timeouts.
- Dependency vulnerability audit: not established. The attempted offline npm audit was run from the repository root and could not find the frontend lockfile. A proper online audit was intentionally not substituted because this review stayed within standard sandboxed tools.

This was a source/configuration audit, not a penetration test, fuzz test, accessibility session with assistive technology, packaged-binary inspection, or multi-platform runtime test.

## System and trust-boundary overview

The desktop parent chooses a loopback port and a random token, starts FastAPI in a child process, opens that origin in pywebview, and injects the token into `window.NCONOTES_TOKEN`. API calls attach it as a header. The frontend exchanges it for an HttpOnly SameSite cookie so normal `<img>` requests can retrieve stored images. Storage is JSON and PNG files beneath `~/MyNotebooks` (or `NCONOTES_STORAGE_ROOT`).

The design currently trusts:

1. all JavaScript executing in the webview;
2. every saved note's HTML;
3. all identifier strings reaching authenticated API routes;
4. one application instance and effectively serialized writes;
5. local disk writes and multi-file moves completing fully;
6. uploaded files being reasonable images of reasonable size.

Items 2–6 are not enforced in code.

## Detailed findings

### F-01 — P0 — Navigation drops pending edits

Evidence: `selectPage()` calls `cancelPendingSave()` and then loads the new page (`src/frontend/src/store.ts:314-330`). The timer merely gets cleared (`store.ts:197-201`); it is not flushed. Notebook/page creation and selection all route through this method. Deleting the selected notebook also cancels the timer (`store.ts:282-295`).

An edit is normally scheduled 500 ms later (`store.ts:448-462`). If the user types and immediately selects another page, the edit exists only in memory and is discarded when the loaded page replaces `items`. This is an ordinary interaction, so severity is critical even though the loss window is short.

Recommendation:

- Give each page a save queue. Before navigation, await the current page's queued save using an immutable snapshot tied to that notebook/page.
- Disable or indicate navigation while the flush is failing; never silently proceed after a failed flush without an explicit user choice.
- Flush on window lifecycle events as a last line of defense, but do not rely on unload HTTP requests.
- Add an automated test: edit, navigate within the debounce interval, navigate back, assert persistence.

### F-02 — P0 — Identifier path traversal and missing path confinement

Evidence: `_notebook_dir`, `_page_json`, trashed notebook/page helpers, and image loading concatenate route-controlled strings directly into `Path` objects (`src/backend/storage/notebooks.py:56-90`). Route parameters are plain `str`; models also use unrestricted `str` IDs. No UUID parse, resolved-path containment check, or canonical ownership check exists.

Examples of dangerous shapes include notebook IDs containing `..` and page/image IDs containing slashes or traversal segments. Depending on route decoding and the particular endpoint, an authenticated caller can address paths outside the intended notebook directory. File operations include reads, writes, `shutil.move`, `unlink`, and `shutil.rmtree`, substantially increasing impact.

The random token reduces who can call the API, but it is not a substitute for filesystem safety. The frontend token is obtainable by injected page JavaScript (F-03), and local desktop data must remain confined even after authentication.

Recommendation:

- Represent IDs as UUIDs at the FastAPI/Pydantic boundary (`UUID` types), convert to canonical strings internally, and reject all non-UUIDs with 422.
- Add a reusable `safe_join(root, components...)` that resolves candidate and root and verifies `candidate.is_relative_to(root.resolve())` before every file operation.
- Validate that a loaded object's internal `id` matches the path ID and that a page belongs to the notebook metadata before allowing load/save/delete.
- Add adversarial tests for encoded traversal, separators, absolute paths, mismatched body/path IDs, and symlink escapes. Consider refusing symlinks anywhere in the storage tree.

### F-03 — P0 — Stored HTML injection defeats the API security boundary

Evidence: text content is stored as unrestricted HTML (`models.py:17-27`) and rendered via `dangerouslySetInnerHTML` (`src/frontend/src/components/canvas/TextItem.tsx:20-24`). The editor loads stored HTML directly (`Editor.tsx:67-75`). No sanitizer or Content Security Policy is configured. Meanwhile the bearer token is deliberately exposed as `window.NCONOTES_TOKEN` (`src/main.py:58-62`, `src/frontend/src/api.ts:32-40`).

React does not sanitize `dangerouslySetInnerHTML`. Browser behavior may prevent some script tags inserted this way from executing, but event-handler attributes, dangerous URLs, resource loads, DOM clobbering, editor parsing quirks, and future renderer changes make raw untrusted HTML an unacceptable boundary. Any execution can read the injected token and make authenticated API calls. Future document import—already on the roadmap—would make this much easier to trigger.

Recommendation:

- Prefer storing TipTap/ProseMirror JSON and render only a strict extension schema.
- If HTML remains, sanitize at ingestion and again before rendering using a maintained allowlist sanitizer; allow only the tags/attributes/protocols the editor generates. Strip event attributes, scripts, embedded documents, styles unless explicitly needed, and non-local image URLs.
- Add a restrictive CSP from the backend, ideally with `default-src 'self'`, no objects/frames, controlled image sources, and no inline script. Verify Vite's production output under that policy.
- Avoid making the long-lived bearer token readable to page JavaScript. Bootstrap a session through a narrow native bridge or one-time exchange, then erase the bootstrap secret. Keep authorization and CSRF protections separate.
- Add stored-XSS regression fixtures covering event attributes, SVG, `javascript:` URLs, malformed markup, and pasted rich content.

### F-04 — P1 — Saves can complete out of order and overwrite newer state

Evidence: `flushSave()` snapshots current state, sends an unconditional full-page PUT, and sets global status after completion (`store.ts:167-181`). `scheduleSave()` clears its timer before calling `flushSave()` (`store.ts:191-194`), so edits made while a request is in flight can schedule another request. Nothing serializes the two or verifies a revision. The backend overwrites the entire JSON file (`notebooks.py:226-230`).

If request A contains older content, request B contains newer content, and B finishes first, A can finish last and restore the older page. The global `saveStatus` can also say `saved` for the wrong page or after a newer save has failed.

Recommendation:

- Serialize saves per page and coalesce queued state behind the current request.
- Add a monotonically increasing revision or ETag. PUT should require the last observed revision and return 409 on conflict.
- Associate save status/error with `{notebookId, pageId, revision}` rather than one global flag.
- Test delayed/reordered responses, edits during a save, navigation during a save, retries, and two app instances.

### F-05 — P1 — Storage writes and multi-file operations are crash-unsafe

Evidence: `_write_json` calls `Path.write_text` directly (`notebooks.py:106-111`). Creation writes notebook metadata then page data (`:168-180`); page creation writes page data then rewrites notebook metadata (`:233-245`); deletion annotates/moves the page then rewrites notebook metadata (`:249-271`); restore moves the page then appends metadata (`:438-463`). Similar windows exist for notebooks. There is no lock, temporary file, atomic replace, fsync, journal, or rollback.

Power loss, process termination, full disk, antivirus interference, or a second instance can leave truncated JSON, orphan pages, metadata referencing missing files, or active and trashed state disagreeing.

Recommendation:

- Write JSON to a temporary file in the same directory, flush/fsync as appropriate, then `os.replace` atomically. Preserve the prior version until replacement succeeds.
- Add a storage-wide lock or enforce one running application instance. Add finer locks only if future concurrency requires them.
- For compound operations, use a tiny transaction journal/state machine or redesign the on-disk representation so a single atomic rename is the commit point.
- Add startup reconciliation that detects and reports orphaned/missing/malformed files and offers recovery; never silently skip them.

### F-06 — P1 — Upload and model inputs are unbounded and weakly validated

Evidence: `UploadFile` is fully read into memory and saved without size, media-type, signature, dimension, or decompression checks (`src/backend/api/pages.py:70-80`). Files are always named and served as PNG even if the bytes are another format (`notebooks.py:278-298`, pages API image response). Names, titles, HTML, item counts, coordinates, dimensions, scales, z-indexes, timestamps, and IDs have no bounds (`models.py:17-87`).

Consequences include memory/disk exhaustion, enormous page JSON, UI hangs, invalid geometry, misleading MIME handling, and persistence of nonsensical timestamps. A pasted image upload can also become orphaned if the subsequent page save fails.

Recommendation:

- Stream uploads with a hard byte limit; validate decoded image type and dimensions; re-encode to a supported safe format; reject animated/oversized/decompression-bomb inputs.
- Configure request-body limits at the server boundary and explicit Pydantic constraints for string lengths, item count, finite numbers, positive dimensions, scale range, z-index range, UUIDs, and timezone-aware timestamps.
- Track image references and garbage-collect unreferenced uploads safely. Do not delete an image still referenced by another item/page.

### F-07 — P1 — Image deletion ignores shared references

Evidence: purging an item or page directly deletes each referenced image (`notebooks.py:118-140`, `:483-507`) without checking whether another note/page references the same image ID. TipTap HTML extraction uses a regex and trusts any notebook segment. Undoing an image replacement also retains uploaded files indefinitely.

If image URLs are copied between notes/pages within a notebook, purging one can break another. Conversely, abandoned replacements/uploads leak disk space.

Recommendation: make images content-addressed or maintain reference accounting. Before physical deletion, scan/index all live and trashed references in the notebook. Treat HTML regex parsing as insufficient; derive references from structured editor data.

### F-08 — P1 — Corruption is hidden rather than surfaced

Evidence: notebook and trash scans broadly catch `Exception` and `pass` (`notebooks.py:147-165`, `:305-371`, `:406-415`, and note lookup later in the file). A malformed file therefore disappears from the UI. Automatic purge also swallows every exception. Error messages can include full local paths and exception details returned through the API.

Silent omission is dangerous for a notes app because users can interpret “not listed” as “deleted” and then create conflicting content. It also makes support diagnosis difficult.

Recommendation: log structured errors to a rotating local log; show a non-destructive “storage needs attention” state; quarantine nothing automatically; provide a diagnostic/export command. Return stable user-safe API details while retaining technical details in logs.

### F-09 — P2 — Free-port selection has a TOCTOU race

Evidence: the launcher binds port zero, closes the socket, then later starts uvicorn on that port (`src/main.py:19-23`, `:45-51`). Another process can claim it between those actions. `/health` is unauthenticated, so `_wait_for_backend` could accept an unrelated service that happens to respond successfully (`:30-39`). The webview would then open that process while the token injection still occurs on load.

Recommendation: let the server bind port zero and communicate the actual bound port back to the parent, or pass an already-bound socket to uvicorn. Authenticate readiness with an unguessable path/value or verify the child remains alive and response identity matches.

### F-10 — P2 — Cookie and browser-origin defenses need hardening

Positive: the session cookie is HttpOnly and SameSite Strict, and the server binds only to `127.0.0.1`.

Gaps: the cookie has no explicit `Secure` flag (HTTP loopback complicates this), no explicit lifetime, and no host-prefix semantics. SameSite is not the same as same-origin; localhost ports share site semantics in modern browsers. Middleware accepts the cookie for every API method (`server.py:42-54`) and there is no Origin/Host validation or CSRF token. CORS absence limits hostile JavaScript from reading responses, but should not be treated as complete request-forgery protection. Host-header/DNS-rebinding assumptions are not documented or tested.

Recommendation: validate `Host` against the exact loopback host/port, reject state-changing cookie-authenticated requests whose `Origin` is not the application origin, use a CSRF token or header-only auth for mutations, and test pywebview behavior. Set security headers (`CSP`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, frame restrictions).

### F-11 — P2 — API consistency and ownership invariants are incomplete

- `save_page` does not ensure the JSON body's `id` equals the route `page_id`; it writes arbitrary body IDs into that file.
- Loading/saving a page checks file existence but not membership in `notebook.json`.
- The notebook canvas is represented by positional convention (`pages[0]` plus empty title), a fragile implicit invariant used by backend and frontend.
- Page deletion can target the canvas if its UUID is known; the API/storage layer does not enforce the comment that it cannot be deleted.
- Duplicate item IDs are accepted; trash restore/purge searches can affect the first matching note across the entire store.
- Trash endpoints accept `type` as a free string instead of a literal/enum, turning a client validation error into a storage error.

Recommendation: enforce ownership and identity server-side, model page kind explicitly (`kind: canvas|page`), make item IDs unique within an enforced scope, and use typed API parameters.

### F-12 — P2 — Startup and shutdown can lose data or obscure failures

The backend child is daemonized and always terminated forcefully (`main.py:50`, `:64-66`). There is no graceful shutdown handshake or frontend “all changes persisted” check. If the backend exits early, readiness polling waits up to 30 seconds without checking the child's exit code. `multiprocessing.set_start_method("spawn")` can raise if an embedding environment already chose a method.

Recommendation: request graceful backend shutdown, wait with a bounded timeout, then terminate only as fallback; prevent window close until the save queue is drained or the user accepts the risk; monitor child liveness during startup/runtime; use an explicit multiprocessing context.

### F-13 — P2 — Accessibility and keyboard operation are incomplete

The sidebar uses clickable `div`/`li` rows rather than semantic buttons/links, so notebook/page selection is not naturally keyboard accessible. Delete buttons are hidden with `visibility` until hover, which is poor for touch and keyboard discoverability. Icon-only controls rely on `title` rather than robust accessible names; the trash modal lacks dialog semantics, focus trapping, initial focus, Escape handling, and focus restoration. Error/status changes are not announced through live regions. Canvas operations are primarily pointer-driven.

Recommendation: use semantic controls, visible focus styles, `aria-label`, `role="dialog"`/`aria-modal`, focus management, live status regions, and keyboard equivalents for core actions. Run axe plus manual keyboard/screen-reader checks.

### F-14 — P2 — Testing misses the riskiest behavior

The existing backend tests are valuable and use real temporary storage. However, there are no frontend unit/component/end-to-end tests, no autosave race/navigation tests, no security/adversarial path tests, no malformed/corrupt storage tests, no interrupted-write tests, no upload limit/type tests, and no multi-instance tests. The current suite's unexplained hang also reduces confidence in repeatability.

Recommendation:

- Add Vitest for store state machines and React Testing Library for navigation/modal behavior.
- Add Playwright against the real backend for create/edit/save/reload/trash workflows.
- Use pytest parametrization/Hypothesis for IDs, model limits, malformed JSON, and filesystem failures.
- Add timeouts and CI on Windows plus Linux, since pywebview and mounted-filesystem behavior are platform-sensitive.

### F-15 — P3 — Performance will degrade with notebook size

- Each edit serializes and rewrites the full page JSON.
- Trash listing scans and parses every active page and every trashed item at startup/open.
- Note lookup for restore/purge scans all notebooks/pages.
- `visibleItems()` sorts in place after `filter`, which is safe, but canvas rendering remains O(items log items) and all visible React nodes render together.
- The initial JS bundle is 638.37 kB minified; TipTap is a likely major contributor.
- Images are read completely into backend memory and returned as a complete `Response`; no streaming, caching headers, thumbnails, or deduplication exist.

This is acceptable at prototype scale but should be measured with realistic notebooks. Introduce indexing/metadata, incremental persistence, lazy editor loading, image thumbnails/caching, and canvas culling only when profiling establishes thresholds.

### F-16 — P3 — Packaging and operational readiness are incomplete

- README says the packaged app serves a pre-built frontend, but no reproducible packaging configuration or CI artifact flow is present.
- The source selection silently falls back between backend static and frontend dist directories.
- No application data version/schema migration, backup/export command, diagnostics location, telemetry policy, or support bundle exists.
- No dependency-update/vulnerability workflow is documented.
- Python metadata emits deprecation warnings: use an SPDX license expression and `[project.scripts]`.
- The repository contains a `NCONotes/` virtual-environment-looking directory; keep environments and generated artifacts out of source control/workspaces.

Recommendation: define a deterministic build/package pipeline, schema version and migration policy, backup/export/restore flow, CI checks, supported OS matrix, log/data locations, and release signing/update strategy.

## Architecture and design assessment

### What is good

- Clear separation among desktop orchestration, HTTP/API concerns, storage, application state, and UI components.
- A single frontend store centralizes mutations and save scheduling instead of scattering persistence across components.
- Pydantic discriminated unions give canvas items an understandable model.
- UUID generation and a cryptographically strong startup token use appropriate standard-library primitives.
- Loopback binding and constant-time token comparison are correct defense-in-depth choices.
- HttpOnly/SameSite cookie use shows awareness of image-request constraints.
- Trash instead of immediate deletion is the right product default.
- Backend errors use a consistent JSON shape, and frontend errors have a typed wrapper.
- Existing tests isolate storage under a temporary root and cover much of the basic contract.
- Source is unusually well-commented for a first web implementation.

### What should change structurally

Do not replace this with microservices or a heavy database server. The current single-process backend is appropriate. The important structural improvement is to make persistence a first-class subsystem with explicit invariants:

1. canonical typed IDs and path confinement;
2. atomic writes and a single-writer lock;
3. page revisions and serialized save queues;
4. schema versioning and recovery diagnostics;
5. structured rich-text content and managed image references.

SQLite is worth considering because it supplies atomic transactions, constraints, indexing, migrations, and crash recovery in one local file. It is not mandatory: carefully implemented atomic JSON plus journaling can work, but it will recreate a meaningful subset of database behavior. If plain files are a core product requirement, document that decision and build the missing guarantees deliberately.

The frontend store is currently both domain state and asynchronous workflow engine. As saves, navigation, conflicts, uploads, and recovery grow, separate a `PageRepository`/save coordinator from Zustand state. Use a small explicit state machine per page (`clean`, `dirty`, `saving(rev)`, `dirty-while-saving`, `failed`) rather than a global four-value status.

## Recommended remediation roadmap

### Before trusting real notes

1. Fix navigation/save data loss and serialize saves.
2. Validate all identifiers as UUIDs and enforce resolved-path confinement.
3. Sanitize or replace HTML storage; add CSP; remove JavaScript access to the persistent API secret.
4. Make single-file writes atomic and prevent concurrent app instances.
5. Add strict upload/request limits and image validation.
6. Add regression tests for all five areas and get the full suite reliably completing.

### Next hardening milestone

1. Add revisions/conflict handling and compound-operation recovery.
2. Add backups/export/import validation and visible corruption diagnostics.
3. Correct shared-image lifecycle and garbage collection.
4. Harden Origin/Host/CSRF behavior and add security headers.
5. Add frontend/E2E/accessibility test coverage and CI on supported platforms.

### Before distributing to other users

1. Reproducible signed packaging and dependency scanning/updating.
2. Schema migration policy and rollback-tested releases.
3. Realistic scale/performance benchmarks.
4. Manual accessibility and platform-native webview testing.
5. Threat model and security reporting/update process.

## Suggested acceptance criteria for the next release

- Switching pages immediately after an edit never loses the edit, including under injected latency and save failure.
- Reordered HTTP responses cannot overwrite a newer revision.
- Every route ID rejects non-canonical UUIDs; tests prove paths cannot escape storage even through encoding or symlinks.
- Malicious stored/pasted HTML fixtures cannot execute code, load disallowed resources, or obtain an API credential.
- Oversized, mislabeled, corrupt, and decompression-bomb images are rejected without excessive memory/disk usage.
- Killing the process during any write leaves either the old valid state or new valid state, never truncated JSON.
- Corrupted/orphaned files produce a visible diagnostic and remain recoverable.
- A second app instance cannot concurrently mutate the same store.
- Backend, frontend, E2E, lint, build, dependency, and accessibility checks run unattended in CI.

## Final judgment

The implementation demonstrates good instincts and a maintainable starting layout. The main mistake is common in first desktop-web hybrids: treating “localhost + token” and “plain JSON” as simpler boundaries than they really are. Keep the overall architecture, but harden the seams. In particular, solve persistence correctness before adding search/import/tagging features; those features will multiply the amount and variety of data flowing through the currently unsafe boundaries.
