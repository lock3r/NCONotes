# Data models for NCONotes canvas items, pages, notebooks, and trash.
# Pydantic models are used for JSON serialization/deserialization throughout
# the storage layer and API responses.

from __future__ import annotations

import uuid
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


class TextItem(BaseModel):
    # Canvas item containing TipTap-generated HTML.
    type: Literal["text"] = "text"
    id: str = Field(default_factory=_new_id)
    x: float
    y: float
    width: float
    height: float
    z_index: int
    content: str = ""
    deleted_at: str | None = None


class ImageItem(BaseModel):
    # Canvas item referencing an image stored under the notebook's images/ directory.
    type: Literal["image"] = "image"
    id: str = Field(default_factory=_new_id)
    x: float
    y: float
    width: float
    height: float
    z_index: int
    scale: float = 1.0
    image_id: str
    deleted_at: str | None = None


# Discriminated union used by Page.items — Pydantic dispatches on the "type" field.
CanvasItem = Annotated[Union[TextItem, ImageItem], Field(discriminator="type")]


class ViewState(BaseModel):
    # Persisted per-page so the user resumes exactly where they left off.
    pan_x: float = 0.0
    pan_y: float = 0.0
    scale: float = 1.0


class PageMeta(BaseModel):
    # Lightweight page descriptor stored in notebook.json.
    id: str = Field(default_factory=_new_id)
    title: str


class Page(BaseModel):
    # Full page content loaded from / saved to pages/{id}.json.
    # deleted_at, notebook_id, and title are only set when the page is in the trash.
    id: str
    view_state: ViewState = Field(default_factory=ViewState)
    items: list[CanvasItem] = Field(default_factory=list)
    deleted_at: str | None = None
    notebook_id: str | None = None
    title: str | None = None


class Notebook(BaseModel):
    id: str = Field(default_factory=_new_id)
    name: str
    pages: list[PageMeta] = Field(default_factory=list)
    # deleted_at is only set when the notebook is in the trash.
    deleted_at: str | None = None


class TrashItem(BaseModel):
    id: str
    name: str
    type: Literal["notebook", "page", "note"]
    deleted_at: str
    # notebook_id and page_id locate the containing notebook/page for page and note items.
    notebook_id: str | None = None
    page_id: str | None = None
