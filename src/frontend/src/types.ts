// TypeScript mirrors of the Pydantic models in backend/storage/models.py.
// Field names are snake_case because they cross the wire exactly as the backend
// serializes them.

export interface TextItem {
  type: 'text'
  id: string
  x: number
  y: number
  width: number
  height: number
  z_index: number
  content: string
  deleted_at: string | null
}

export interface ImageItem {
  type: 'image'
  id: string
  x: number
  y: number
  width: number
  height: number
  z_index: number
  scale: number
  image_id: string
  deleted_at: string | null
}

// Discriminated on `type`, matching the backend's CanvasItem union.
export type CanvasItem = TextItem | ImageItem

export interface ViewState {
  pan_x: number
  pan_y: number
  scale: number
}

export interface PageMeta {
  id: string
  title: string
}

export interface Page {
  id: string
  view_state: ViewState
  items: CanvasItem[]
}

export interface Notebook {
  id: string
  name: string
  // pages[0] is the notebook's own canvas and is absent from the pages API.
  pages: PageMeta[]
}

export type TrashItemType = 'notebook' | 'page' | 'note'

export interface TrashItem {
  id: string
  name: string
  type: TrashItemType
  deleted_at: string
  notebook_id: string | null
  page_id: string | null
}

export interface UploadedImage {
  image_id: string
  url: string
}
