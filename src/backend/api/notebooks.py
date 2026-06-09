# REST endpoints for notebook CRUD operations.
# All routes are mounted under /api by server.py.

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.errors import error_response
from backend.storage import notebooks as storage
from backend.storage.models import Notebook

router = APIRouter()


class CreateNotebookBody(BaseModel):
    name: str


@router.get("/notebooks", response_model=list[Notebook])
async def list_notebooks():
    return storage.list_notebooks()


@router.post("/notebooks", response_model=Notebook, status_code=201)
async def create_notebook(body: CreateNotebookBody):
    try:
        return storage.create_notebook(body.name)
    except storage.StorageError as exc:
        return error_response(500, "storage_error", str(exc))


@router.delete("/notebooks/{notebook_id}", status_code=204)
async def delete_notebook(notebook_id: str):
    try:
        storage.delete_notebook(notebook_id)
    except storage.NotFoundError as exc:
        return error_response(404, "not_found", str(exc))
    except storage.StorageError as exc:
        return error_response(500, "storage_error", str(exc))
