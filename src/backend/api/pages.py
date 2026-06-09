# REST endpoints for page CRUD and image upload/serve operations.
# All routes are mounted under /api by server.py.

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from backend.storage import notebooks as storage
from backend.storage.models import Page, PageMeta

router = APIRouter()


def _error(status: int, error: str, detail: str) -> JSONResponse:
    return JSONResponse({"error": error, "detail": detail}, status_code=status)


class CreatePageBody(BaseModel):
    title: str


@router.get("/notebooks/{notebook_id}/pages", response_model=list[PageMeta])
async def list_pages(notebook_id: str):
    try:
        nb_list = storage.list_notebooks()
        nb = next((n for n in nb_list if n.id == notebook_id), None)
        if nb is None:
            return _error(404, "not_found", f"Notebook not found: {notebook_id}")
        return nb.pages
    except storage.StorageError as exc:
        return _error(500, "storage_error", str(exc))


@router.post("/notebooks/{notebook_id}/pages", response_model=PageMeta, status_code=201)
async def create_page(notebook_id: str, body: CreatePageBody):
    try:
        return storage.create_page(notebook_id, body.title)
    except storage.NotFoundError as exc:
        return _error(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return _error(500, "storage_error", str(exc))


@router.delete("/notebooks/{notebook_id}/pages/{page_id}", status_code=204)
async def delete_page(notebook_id: str, page_id: str):
    try:
        storage.delete_page(notebook_id, page_id)
    except storage.NotFoundError as exc:
        return _error(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return _error(500, "storage_error", str(exc))


@router.get("/notebooks/{notebook_id}/pages/{page_id}", response_model=Page)
async def load_page(notebook_id: str, page_id: str):
    try:
        return storage.load_page(notebook_id, page_id)
    except storage.NotFoundError as exc:
        return _error(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return _error(500, "storage_error", str(exc))


@router.put("/notebooks/{notebook_id}/pages/{page_id}", status_code=204)
async def save_page(notebook_id: str, page_id: str, page: Page):
    try:
        storage.save_page(notebook_id, page_id, page)
    except storage.NotFoundError as exc:
        return _error(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return _error(500, "storage_error", str(exc))


@router.post("/notebooks/{notebook_id}/images", status_code=201)
async def upload_image(notebook_id: str, file: UploadFile):
    try:
        data = await file.read()
        image_id = storage.save_image(notebook_id, data)
        url = f"/api/notebooks/{notebook_id}/images/{image_id}"
        return {"image_id": image_id, "url": url}
    except storage.NotFoundError as exc:
        return _error(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return _error(500, "storage_error", str(exc))


@router.get("/notebooks/{notebook_id}/images/{image_id}")
async def get_image(notebook_id: str, image_id: str):
    try:
        data = storage.load_image(notebook_id, image_id)
        return Response(content=data, media_type="image/png")
    except storage.NotFoundError as exc:
        return _error(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return _error(500, "storage_error", str(exc))
