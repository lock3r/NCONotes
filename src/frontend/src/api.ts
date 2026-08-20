// Typed fetch wrappers for the NCONotes REST API.
//
// Every request carries the auth token. In the packaged app pywebview injects it as
// window.NCONOTES_TOKEN; under the Vite dev server the token is unknown to the browser
// and the dev proxy attaches it instead (see vite.config.ts), so the header is simply
// omitted when no token is present.
//
// Non-2xx responses are thrown as ApiError carrying the backend's {error, detail}.

import type { Notebook, Page, PageMeta, TrashItem, TrashItemType, UploadedImage } from './types'

declare global {
  interface Window {
    NCONOTES_TOKEN?: string
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly error: string
  readonly detail: string

  constructor(status: number, error: string, detail: string) {
    super(detail || error)
    this.name = 'ApiError'
    this.status = status
    this.error = error
    this.detail = detail
  }
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = window.NCONOTES_TOKEN
  if (token) headers.set('X-NCONotes-Token', token)

  let res: Response
  try {
    res = await fetch(`/api${path}`, { ...options, headers })
  } catch (cause) {
    throw new ApiError(0, 'network_error', (cause as Error).message)
  }

  if (!res.ok) {
    let error = 'http_error'
    let detail = `Request failed with status ${res.status}`
    try {
      const body = await res.json()
      if (typeof body?.error === 'string') error = body.error
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      // Response body was not the expected JSON envelope; keep the defaults.
    }
    throw new ApiError(res.status, error, detail)
  }

  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

function jsonBody(body: unknown): RequestInit {
  return {
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
  }
}

// --- Session ---------------------------------------------------------------

// Exchanges the header token for a session cookie. Browsers cannot attach custom
// headers to <img src> requests, so without the cookie every image URL would 401.
// Only needed where a token is present: under the dev proxy the token is attached
// server-side and image requests are already authorized.
export function createSession(): Promise<void> {
  return apiFetch<void>('/session', { method: 'POST' })
}

export function hasInjectedToken(): boolean {
  return typeof window.NCONOTES_TOKEN === 'string' && window.NCONOTES_TOKEN.length > 0
}

// --- Notebooks -------------------------------------------------------------

export function listNotebooks(): Promise<Notebook[]> {
  return apiFetch<Notebook[]>('/notebooks')
}

export function createNotebook(name: string): Promise<Notebook> {
  return apiFetch<Notebook>('/notebooks', { method: 'POST', ...jsonBody({ name }) })
}

export function deleteNotebook(notebookId: string): Promise<void> {
  return apiFetch<void>(`/notebooks/${notebookId}`, { method: 'DELETE' })
}

// --- Pages -----------------------------------------------------------------

export function listPages(notebookId: string): Promise<PageMeta[]> {
  return apiFetch<PageMeta[]>(`/notebooks/${notebookId}/pages`)
}

export function createPage(notebookId: string, title: string): Promise<PageMeta> {
  return apiFetch<PageMeta>(`/notebooks/${notebookId}/pages`, {
    method: 'POST',
    ...jsonBody({ title }),
  })
}

export function deletePage(notebookId: string, pageId: string): Promise<void> {
  return apiFetch<void>(`/notebooks/${notebookId}/pages/${pageId}`, { method: 'DELETE' })
}

export function loadPage(notebookId: string, pageId: string): Promise<Page> {
  return apiFetch<Page>(`/notebooks/${notebookId}/pages/${pageId}`)
}

export function savePage(notebookId: string, pageId: string, page: Page): Promise<void> {
  return apiFetch<void>(`/notebooks/${notebookId}/pages/${pageId}`, {
    method: 'PUT',
    ...jsonBody(page),
  })
}

// --- Images ----------------------------------------------------------------

export function uploadImage(notebookId: string, blob: Blob): Promise<UploadedImage> {
  const form = new FormData()
  // Field name must be "file" to match the UploadFile parameter on the backend.
  form.append('file', blob, 'image.png')
  // Content-Type is deliberately unset so the browser adds the multipart boundary.
  return apiFetch<UploadedImage>(`/notebooks/${notebookId}/images`, {
    method: 'POST',
    body: form,
  })
}

export function imageUrl(notebookId: string, imageId: string): string {
  return `/api/notebooks/${notebookId}/images/${imageId}`
}

// --- Trash -----------------------------------------------------------------

export function listTrash(): Promise<TrashItem[]> {
  return apiFetch<TrashItem[]>('/trash')
}

export function restoreTrashItem(itemId: string, type: TrashItemType): Promise<void> {
  return apiFetch<void>(`/trash/${itemId}/restore?type=${type}`, { method: 'POST' })
}

export function purgeTrashItem(itemId: string, type: TrashItemType): Promise<void> {
  return apiFetch<void>(`/trash/${itemId}?type=${type}`, { method: 'DELETE' })
}
