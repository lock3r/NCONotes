# Storage layer for NCONotes — all file I/O for notebooks, pages, images, and trash.
#
# Default storage root: ~/MyNotebooks/
# Override for testing: set NCONOTES_STORAGE_ROOT environment variable.
#
# Layout on disk:
#   {root}/
#     {notebook_id}/
#       notebook.json          — Notebook model (id, name, pages list)
#       pages/
#         {page_id}.json       — Page model (id, view_state, items)
#       images/
#         {image_id}.png
#     .trash/
#       {notebook_id}/         — Deleted notebook moved here intact; notebook.json gains deleted_at
#         notebook.json
#         pages/
#         images/
#       pages/
#         {page_id}.json       — Deleted page moved here; gains deleted_at, notebook_id, title

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.storage.models import (
    CanvasItem,
    ImageItem,
    Notebook,
    Page,
    PageMeta,
    TextItem,
    TrashItem,
    ViewState,
)


class NotFoundError(Exception):
    pass


class StorageError(Exception):
    pass


# ---------------------------------------------------------------------------
# Storage root
# ---------------------------------------------------------------------------

def _storage_root() -> Path:
    root = os.environ.get("NCONOTES_STORAGE_ROOT")
    return Path(root) if root else Path.home() / "MyNotebooks"


def _trash_root() -> Path:
    return _storage_root() / ".trash"


def _notebook_dir(notebook_id: str) -> Path:
    return _storage_root() / notebook_id


def _pages_dir(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "pages"


def _images_dir(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "images"


def _notebook_json(notebook_id: str) -> Path:
    return _notebook_dir(notebook_id) / "notebook.json"


def _page_json(notebook_id: str, page_id: str) -> Path:
    return _pages_dir(notebook_id) / f"{page_id}.json"


def _trashed_notebook_json(notebook_id: str) -> Path:
    return _trash_root() / notebook_id / "notebook.json"


def _trashed_page_json(page_id: str) -> Path:
    return _trash_root() / "pages" / f"{page_id}.json"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise NotFoundError(f"File not found: {path}")
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Failed to read {path}: {exc}") from exc


def _write_json(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        raise StorageError(f"Failed to write {path}: {exc}") from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _img_ids_from_html(html: str) -> list[str]:
    """Extract image UUIDs from /api/notebooks/{id}/images/{image_id} URLs in TipTap HTML."""
    pattern = r"/api/notebooks/[^/]+/images/([0-9a-f-]{36})"
    return re.findall(pattern, html)


def _delete_image_file(notebook_id: str, image_id: str) -> None:
    """Delete an image file, silently ignoring missing files."""
    img_path = _images_dir(notebook_id) / f"{image_id}.png"
    try:
        img_path.unlink()
    except FileNotFoundError:
        pass


def _purge_items_images(notebook_id: str, items: list[CanvasItem]) -> None:
    """Delete all image files referenced by a list of canvas items."""
    for item in items:
        if isinstance(item, ImageItem):
            _delete_image_file(notebook_id, item.image_id)
        elif isinstance(item, TextItem) and item.content:
            for img_id in _img_ids_from_html(item.content):
                _delete_image_file(notebook_id, img_id)


# ---------------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------------

def list_notebooks() -> list[Notebook]:
    root = _storage_root()
    if not root.exists():
        return []
    notebooks = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        nb_json = entry / "notebook.json"
        if not nb_json.exists():
            continue
        try:
            nb = Notebook.model_validate(_read_json(nb_json))
            # Notebooks in the main tree never have deleted_at, but guard anyway.
            if nb.deleted_at is None:
                notebooks.append(nb)
        except Exception:
            pass  # Skip corrupted notebook entries rather than crashing on startup.
    return notebooks


def create_notebook(name: str) -> Notebook:
    nb_id = str(uuid.uuid4())
    page0_id = str(uuid.uuid4())
    # page_0 is the notebook's own canvas; title is empty to signal it's not a user page.
    page0_meta = PageMeta(id=page0_id, title="")
    notebook = Notebook(id=nb_id, name=name, pages=[page0_meta])

    _pages_dir(nb_id).mkdir(parents=True, exist_ok=True)
    _images_dir(nb_id).mkdir(parents=True, exist_ok=True)

    page0 = Page(id=page0_id)
    _write_json(_notebook_json(nb_id), notebook.model_dump())
    _write_json(_page_json(nb_id, page0_id), page0.model_dump())

    return notebook


def delete_notebook(notebook_id: str) -> None:
    nb_json = _notebook_json(notebook_id)
    if not nb_json.exists():
        raise NotFoundError(f"Notebook not found: {notebook_id}")

    nb = Notebook.model_validate(_read_json(nb_json))
    nb.deleted_at = _now_iso()
    _write_json(nb_json, nb.model_dump())

    dest = _trash_root() / notebook_id
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(_notebook_dir(notebook_id)), str(dest))
    except OSError as exc:
        raise StorageError(f"Failed to move notebook to trash: {exc}") from exc


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def load_page(notebook_id: str, page_id: str) -> Page:
    data = _read_json(_page_json(notebook_id, page_id))
    return Page.model_validate(data)


def save_page(notebook_id: str, page_id: str, page: Page) -> None:
    path = _page_json(notebook_id, page_id)
    if not path.exists():
        raise NotFoundError(f"Page not found: {page_id} in notebook {notebook_id}")
    _write_json(path, page.model_dump())


def create_page(notebook_id: str, title: str) -> PageMeta:
    nb_json = _notebook_json(notebook_id)
    if not nb_json.exists():
        raise NotFoundError(f"Notebook not found: {notebook_id}")

    meta = PageMeta(title=title)
    page = Page(id=meta.id)
    _write_json(_page_json(notebook_id, meta.id), page.model_dump())

    nb = Notebook.model_validate(_read_json(nb_json))
    nb.pages.append(meta)
    _write_json(nb_json, nb.model_dump())

    return meta


def delete_page(notebook_id: str, page_id: str) -> None:
    page_path = _page_json(notebook_id, page_id)
    if not page_path.exists():
        raise NotFoundError(f"Page not found: {page_id} in notebook {notebook_id}")

    nb_json = _notebook_json(notebook_id)
    nb = Notebook.model_validate(_read_json(nb_json))

    # Find the title before removing from notebook.json.
    title = next((p.title for p in nb.pages if p.id == page_id), "")

    page = Page.model_validate(_read_json(page_path))
    page.deleted_at = _now_iso()
    page.notebook_id = notebook_id
    page.title = title

    trash_pages = _trash_root() / "pages"
    trash_pages.mkdir(parents=True, exist_ok=True)
    _write_json(page_path, page.model_dump())
    shutil.move(str(page_path), str(trash_pages / f"{page_id}.json"))

    nb.pages = [p for p in nb.pages if p.id != page_id]
    _write_json(nb_json, nb.model_dump())


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def save_image(notebook_id: str, image_data: bytes) -> str:
    images_dir = _images_dir(notebook_id)
    if not images_dir.exists():
        raise NotFoundError(f"Notebook not found: {notebook_id}")

    image_id = str(uuid.uuid4())
    try:
        (images_dir / f"{image_id}.png").write_bytes(image_data)
    except OSError as exc:
        raise StorageError(f"Failed to save image: {exc}") from exc
    return image_id


def load_image(notebook_id: str, image_id: str) -> bytes:
    path = _images_dir(notebook_id) / f"{image_id}.png"
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise NotFoundError(f"Image not found: {image_id}")
    except OSError as exc:
        raise StorageError(f"Failed to read image: {exc}") from exc


# ---------------------------------------------------------------------------
# Trash
# ---------------------------------------------------------------------------

def list_trash() -> list[TrashItem]:
    trash = _trash_root()
    items: list[TrashItem] = []

    # Deleted notebooks: each subdirectory under .trash/ (except pages/).
    if trash.exists():
        for entry in trash.iterdir():
            if not entry.is_dir() or entry.name == "pages":
                continue
            nb_json = entry / "notebook.json"
            if not nb_json.exists():
                continue
            try:
                nb = Notebook.model_validate(json.loads(nb_json.read_text(encoding="utf-8")))
                if nb.deleted_at:
                    items.append(TrashItem(
                        id=nb.id,
                        name=nb.name,
                        type="notebook",
                        deleted_at=nb.deleted_at,
                    ))
            except Exception:
                pass

    # Deleted pages: .trash/pages/*.json
    pages_dir = trash / "pages"
    if pages_dir.exists():
        for page_file in pages_dir.glob("*.json"):
            try:
                page = Page.model_validate(json.loads(page_file.read_text(encoding="utf-8")))
                if page.deleted_at:
                    items.append(TrashItem(
                        id=page.id,
                        name=page.title or page.id,
                        type="page",
                        deleted_at=page.deleted_at,
                        notebook_id=page.notebook_id,
                    ))
            except Exception:
                pass

    # Deleted notes: items with deleted_at inside active page files.
    # This scan is independent of the trash directory.
    root = _storage_root()
    if root.exists():
        for nb_dir in root.iterdir():
            if not nb_dir.is_dir() or nb_dir.name.startswith("."):
                continue
            pages_path = nb_dir / "pages"
            if not pages_path.exists():
                continue
            for page_file in pages_path.glob("*.json"):
                try:
                    page = Page.model_validate(json.loads(page_file.read_text(encoding="utf-8")))
                    for item in page.items:
                        if item.deleted_at:
                            name = _note_display_name(item)
                            items.append(TrashItem(
                                id=item.id,
                                name=name,
                                type="note",
                                deleted_at=item.deleted_at,
                                notebook_id=nb_dir.name,
                                page_id=page.id,
                            ))
                except Exception:
                    pass

    return items


def _note_display_name(item: CanvasItem) -> str:
    if isinstance(item, TextItem):
        # Strip HTML tags for a readable preview.
        text = re.sub(r"<[^>]+>", "", item.content or "")
        return text[:60].strip() or "(empty note)"
    return "Image"


def restore_trash_item(item_id: str, item_type: str) -> None:
    if item_type == "notebook":
        _restore_notebook(item_id)
    elif item_type == "page":
        _restore_page(item_id)
    elif item_type == "note":
        _restore_note(item_id)
    else:
        raise StorageError(f"Unknown trash item type: {item_type}")


def purge_trash_item(item_id: str, item_type: str) -> None:
    if item_type == "notebook":
        _purge_notebook(item_id)
    elif item_type == "page":
        _purge_page(item_id)
    elif item_type == "note":
        _purge_note(item_id)
    else:
        raise StorageError(f"Unknown trash item type: {item_type}")


def purge_expired_trash() -> None:
    """Remove trash items older than 60 days. Called on application startup."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=60)
    for item in list_trash():
        try:
            deleted = datetime.fromisoformat(item.deleted_at)
            if deleted < cutoff:
                purge_trash_item(item.id, item.type)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Trash — internal restore/purge helpers
# ---------------------------------------------------------------------------

def _restore_notebook(notebook_id: str) -> None:
    src = _trash_root() / notebook_id
    if not src.exists():
        raise NotFoundError(f"Trashed notebook not found: {notebook_id}")

    nb_json = src / "notebook.json"
    nb = Notebook.model_validate(_read_json(nb_json))
    nb.deleted_at = None
    _write_json(nb_json, nb.model_dump())

    dest = _notebook_dir(notebook_id)
    if dest.exists():
        raise StorageError(f"Cannot restore notebook {notebook_id}: directory already exists in storage root")
    shutil.move(str(src), str(dest))


def _restore_page(page_id: str) -> None:
    src = _trashed_page_json(page_id)
    if not src.exists():
        raise NotFoundError(f"Trashed page not found: {page_id}")

    page = Page.model_validate(_read_json(src))
    notebook_id = page.notebook_id
    if not notebook_id:
        raise StorageError(f"Trashed page {page_id} has no notebook_id — cannot restore")

    nb_json = _notebook_json(notebook_id)
    if not nb_json.exists():
        raise NotFoundError(f"Parent notebook {notebook_id} not found — cannot restore page")

    title = page.title or ""
    page.deleted_at = None
    page.notebook_id = None
    page.title = None

    dest = _page_json(notebook_id, page_id)
    _write_json(src, page.model_dump())
    shutil.move(str(src), str(dest))

    nb = Notebook.model_validate(_read_json(nb_json))
    nb.pages.append(PageMeta(id=page_id, title=title))
    _write_json(nb_json, nb.model_dump())


def _restore_note(note_id: str) -> None:
    note_id_str, notebook_id, page_id = _find_note_in_trash(note_id)
    page = Page.model_validate(_read_json(_page_json(notebook_id, page_id)))
    for item in page.items:
        if item.id == note_id:
            item.deleted_at = None
            break
    _write_json(_page_json(notebook_id, page_id), page.model_dump())


def _purge_notebook(notebook_id: str) -> None:
    src = _trash_root() / notebook_id
    if not src.exists():
        raise NotFoundError(f"Trashed notebook not found: {notebook_id}")
    shutil.rmtree(src)


def _purge_page(page_id: str) -> None:
    src = _trashed_page_json(page_id)
    if not src.exists():
        raise NotFoundError(f"Trashed page not found: {page_id}")

    page = Page.model_validate(_read_json(src))
    # Delete any image files referenced by this page (best-effort).
    if page.notebook_id:
        _purge_items_images(page.notebook_id, page.items)

    src.unlink()


def _purge_note(note_id: str) -> None:
    _, notebook_id, page_id = _find_note_in_trash(note_id)
    page = Page.model_validate(_read_json(_page_json(notebook_id, page_id)))

    to_purge = [item for item in page.items if item.id == note_id]
    _purge_items_images(notebook_id, to_purge)

    page.items = [item for item in page.items if item.id != note_id]
    _write_json(_page_json(notebook_id, page_id), page.model_dump())


def _find_note_in_trash(note_id: str) -> tuple[str, str, str]:
    """Return (note_id, notebook_id, page_id) by scanning active pages for a soft-deleted note."""
    root = _storage_root()
    if not root.exists():
        raise NotFoundError(f"Note not found in trash: {note_id}")

    for nb_dir in root.iterdir():
        if not nb_dir.is_dir() or nb_dir.name.startswith("."):
            continue
        pages_path = nb_dir / "pages"
        if not pages_path.exists():
            continue
        for page_file in pages_path.glob("*.json"):
            try:
                page = Page.model_validate(json.loads(page_file.read_text(encoding="utf-8")))
                for item in page.items:
                    if item.id == note_id and item.deleted_at:
                        return note_id, nb_dir.name, page.id
            except Exception:
                pass

    raise NotFoundError(f"Note not found in trash: {note_id}")
