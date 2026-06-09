# REST endpoints for trash listing, restore, and permanent purge.
# All routes are mounted under /api by server.py.

from fastapi import APIRouter, Query

from backend.api.errors import error_response
from backend.storage import notebooks as storage
from backend.storage.models import TrashItem

router = APIRouter()


@router.get("/trash", response_model=list[TrashItem])
async def list_trash():
    try:
        return storage.list_trash()
    except storage.StorageError as exc:
        return error_response(500, "storage_error", str(exc))


@router.post("/trash/{item_id}/restore", status_code=204)
async def restore_trash_item(
    item_id: str,
    type: str = Query(..., description="Item type: notebook, page, or note"),
):
    try:
        storage.restore_trash_item(item_id, type)
    except storage.NotFoundError as exc:
        return error_response(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return error_response(500, "storage_error", str(exc))


@router.delete("/trash/{item_id}", status_code=204)
async def purge_trash_item(
    item_id: str,
    type: str = Query(..., description="Item type: notebook, page, or note"),
):
    try:
        storage.purge_trash_item(item_id, type)
    except storage.NotFoundError as exc:
        return error_response(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return error_response(500, "storage_error", str(exc))
