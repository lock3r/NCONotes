// Application state: notebook/page selection, canvas items, view state, undo/redo,
// and debounced auto-save.
//
// The store owns every mutation the canvas performs. Components read state and call
// actions; they never talk to api.ts directly, so save scheduling and error reporting
// stay in one place.
//
// `items` holds soft-deleted items too (those with deleted_at set) because the backend
// keeps them in the page JSON until the trash window expires. Use `visibleItems()` to
// get the drawable, z-ordered subset.

import { create } from 'zustand'
import * as api from './api'
import { ApiError } from './api'
import type { CanvasItem, ImageItem, Notebook, PageMeta, TextItem, ViewState } from './types'

const UNDO_LIMIT = 50
const ITEM_SAVE_DEBOUNCE_MS = 500
const VIEW_SAVE_DEBOUNCE_MS = 300
// Consecutive edits to the same item within this window merge into one undo step.
const EDIT_COALESCE_MS = 1000

const DEFAULT_TEXT_WIDTH = 240
const DEFAULT_TEXT_HEIGHT = 120

export const DEFAULT_VIEW_STATE: ViewState = { pan_x: 0, pan_y: 0, scale: 1 }

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

// Each variant carries enough state to be applied forwards or reversed.
export type UndoableOp =
  | { kind: 'create'; item: CanvasItem }
  | { kind: 'delete'; itemId: string; deletedAt: string }
  | { kind: 'move'; itemId: string; from: Point; to: Point }
  | { kind: 'resize'; itemId: string; from: Size; to: Size }
  | { kind: 'edit'; itemId: string; from: string; to: string; at: number }
  | { kind: 'replaceImage'; itemId: string; from: ImageSource; to: ImageSource }

// The image an ImageItem points at, plus the box sized to that image's aspect ratio.
export interface ImageSource {
  image_id: string
  width: number
  height: number
}

export interface Point {
  x: number
  y: number
}

export interface Size {
  width: number
  height: number
}

interface StoreState {
  notebooks: Notebook[]
  currentNotebookId: string | null
  currentPageId: string | null
  pages: PageMeta[]
  items: CanvasItem[]
  viewState: ViewState
  activeItemId: string | null
  undoStack: UndoableOp[]
  redoStack: UndoableOp[]
  activeError: string | null
  saveStatus: SaveStatus

  setError: (message: string) => void
  clearError: () => void

  loadNotebooks: () => Promise<void>
  createNotebook: (name: string) => Promise<void>
  deleteNotebook: (notebookId: string) => Promise<void>
  selectNotebook: (notebookId: string) => Promise<void>
  selectPage: (pageId: string) => Promise<void>
  createPage: (title: string) => Promise<void>
  deletePage: (pageId: string) => Promise<void>

  addTextItem: (x: number, y: number) => string
  addImageItem: (x: number, y: number, imageId: string, width: number, height: number) => string
  updateItem: (itemId: string, patch: Partial<TextItem> & Partial<ImageItem>) => void
  deleteItem: (itemId: string) => void
  bringToFront: (itemId: string) => void
  commitMove: (itemId: string, from: Point, to: Point) => void
  commitResize: (itemId: string, from: Size, to: Size) => void
  commitEdit: (itemId: string, from: string, to: string) => void
  commitReplaceImage: (itemId: string, to: ImageSource) => void

  setActiveItem: (itemId: string | null) => void
  setViewState: (patch: Partial<ViewState>) => void

  undo: () => void
  redo: () => void

  retrySave: () => Promise<void>
  visibleItems: () => CanvasItem[]
  nextZIndex: () => number
}

// --- Pure helpers ----------------------------------------------------------

function patchItem(
  items: CanvasItem[],
  itemId: string,
  patch: Partial<TextItem> & Partial<ImageItem>,
): CanvasItem[] {
  return items.map((item) => (item.id === itemId ? ({ ...item, ...patch } as CanvasItem) : item))
}

function describeSaveError(cause: unknown): string {
  const detail = cause instanceof ApiError ? cause.detail : String(cause)
  return `Save failed — changes may not be persisted (${detail})`
}

// --- Save scheduling -------------------------------------------------------
// A single timer serves both item and view-state changes: both write the whole page
// to the same endpoint, so two independent timers would only duplicate requests.
// When both are pending, the earlier deadline wins.

let saveTimer: ReturnType<typeof setTimeout> | null = null
let saveDeadline = 0

export const useStore = create<StoreState>()((set, get) => {
  async function flushSave(): Promise<void> {
    const { currentNotebookId, currentPageId, items, viewState } = get()
    if (!currentNotebookId || !currentPageId) return

    set({ saveStatus: 'saving' })
    try {
      await api.savePage(currentNotebookId, currentPageId, {
        id: currentPageId,
        view_state: viewState,
        items,
      })
      set({ saveStatus: 'saved' })
    } catch (cause) {
      set({ saveStatus: 'error', activeError: describeSaveError(cause) })
    }
  }

  function scheduleSave(delayMs: number): void {
    const deadline = Date.now() + delayMs
    if (saveTimer !== null) {
      if (saveDeadline <= deadline) return
      clearTimeout(saveTimer)
    }
    saveDeadline = deadline
    saveTimer = setTimeout(() => {
      saveTimer = null
      void flushSave()
    }, delayMs)
  }

  function cancelPendingSave(): void {
    if (saveTimer !== null) {
      clearTimeout(saveTimer)
      saveTimer = null
    }
  }

  function pushOp(op: UndoableOp): void {
    set((state) => ({
      undoStack: [...state.undoStack, op].slice(-UNDO_LIMIT),
      redoStack: [],
    }))
  }

  function reportError(cause: unknown): void {
    const detail = cause instanceof ApiError ? cause.detail : String(cause)
    set({ activeError: detail })
  }

  // Applies an op in the given direction. `forward` re-does it; otherwise it is reversed.
  function applyOp(op: UndoableOp, forward: boolean): void {
    set((state) => {
      switch (op.kind) {
        case 'create':
          return {
            items: forward
              ? [...state.items, op.item]
              : state.items.filter((item) => item.id !== op.item.id),
          }
        case 'delete':
          return {
            items: patchItem(state.items, op.itemId, {
              deleted_at: forward ? op.deletedAt : null,
            }),
          }
        case 'move':
          return { items: patchItem(state.items, op.itemId, forward ? op.to : op.from) }
        case 'resize':
          return { items: patchItem(state.items, op.itemId, forward ? op.to : op.from) }
        case 'edit':
          return {
            items: patchItem(state.items, op.itemId, { content: forward ? op.to : op.from }),
          }
        case 'replaceImage':
          return { items: patchItem(state.items, op.itemId, forward ? op.to : op.from) }
      }
    })
  }

  return {
    notebooks: [],
    currentNotebookId: null,
    currentPageId: null,
    pages: [],
    items: [],
    viewState: { ...DEFAULT_VIEW_STATE },
    activeItemId: null,
    undoStack: [],
    redoStack: [],
    activeError: null,
    saveStatus: 'idle',

    setError: (message) => set({ activeError: message }),
    clearError: () => set({ activeError: null }),

    // --- Notebooks and pages ---------------------------------------------

    loadNotebooks: async () => {
      try {
        set({ notebooks: await api.listNotebooks() })
      } catch (cause) {
        reportError(cause)
      }
    },

    createNotebook: async (name) => {
      try {
        const notebook = await api.createNotebook(name)
        set((state) => ({ notebooks: [...state.notebooks, notebook] }))
        await get().selectNotebook(notebook.id)
      } catch (cause) {
        reportError(cause)
      }
    },

    deleteNotebook: async (notebookId) => {
      try {
        await api.deleteNotebook(notebookId)
        set((state) => ({ notebooks: state.notebooks.filter((nb) => nb.id !== notebookId) }))
        if (get().currentNotebookId === notebookId) {
          cancelPendingSave()
          set({
            currentNotebookId: null,
            currentPageId: null,
            pages: [],
            items: [],
            activeItemId: null,
            undoStack: [],
            redoStack: [],
          })
        }
      } catch (cause) {
        reportError(cause)
      }
    },

    // Selecting a notebook opens its own canvas — pages[0], which the pages API hides.
    selectNotebook: async (notebookId) => {
      const notebook = get().notebooks.find((nb) => nb.id === notebookId)
      if (!notebook || notebook.pages.length === 0) {
        set({ activeError: `Notebook ${notebookId} has no canvas page` })
        return
      }
      try {
        const pages = await api.listPages(notebookId)
        set({ currentNotebookId: notebookId, pages })
        await get().selectPage(notebook.pages[0].id)
      } catch (cause) {
        reportError(cause)
      }
    },

    selectPage: async (pageId) => {
      const notebookId = get().currentNotebookId
      if (!notebookId) return
      // Any edits still pending belong to the page being left, not the one arriving.
      cancelPendingSave()
      try {
        const page = await api.loadPage(notebookId, pageId)
        set({
          currentPageId: page.id,
          items: page.items,
          viewState: page.view_state ?? { ...DEFAULT_VIEW_STATE },
          activeItemId: null,
          // Undo history is per-page.
          undoStack: [],
          redoStack: [],
          saveStatus: 'idle',
        })
      } catch (cause) {
        reportError(cause)
      }
    },

    createPage: async (title) => {
      const notebookId = get().currentNotebookId
      if (!notebookId) return
      try {
        const meta = await api.createPage(notebookId, title)
        set((state) => ({ pages: [...state.pages, meta] }))
        await get().selectPage(meta.id)
      } catch (cause) {
        reportError(cause)
      }
    },

    deletePage: async (pageId) => {
      const notebookId = get().currentNotebookId
      if (!notebookId) return
      try {
        await api.deletePage(notebookId, pageId)
        set((state) => ({ pages: state.pages.filter((page) => page.id !== pageId) }))
        if (get().currentPageId === pageId) {
          const notebook = get().notebooks.find((nb) => nb.id === notebookId)
          if (notebook) await get().selectPage(notebook.pages[0].id)
        }
      } catch (cause) {
        reportError(cause)
      }
    },

    // --- Canvas items -----------------------------------------------------

    addTextItem: (x, y) => {
      const item: TextItem = {
        type: 'text',
        id: crypto.randomUUID(),
        x,
        y,
        width: DEFAULT_TEXT_WIDTH,
        height: DEFAULT_TEXT_HEIGHT,
        z_index: get().nextZIndex(),
        content: '',
        deleted_at: null,
      }
      set((state) => ({ items: [...state.items, item] }))
      pushOp({ kind: 'create', item })
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
      return item.id
    },

    addImageItem: (x, y, imageId, width, height) => {
      const item: ImageItem = {
        type: 'image',
        id: crypto.randomUUID(),
        x,
        y,
        width,
        height,
        z_index: get().nextZIndex(),
        scale: 1,
        image_id: imageId,
        deleted_at: null,
      }
      set((state) => ({ items: [...state.items, item] }))
      pushOp({ kind: 'create', item })
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
      return item.id
    },

    // Applies a change without recording undo history — used for live drag/resize
    // feedback. The corresponding commit* action records the completed gesture.
    updateItem: (itemId, patch) => {
      set((state) => ({ items: patchItem(state.items, itemId, patch) }))
    },

    deleteItem: (itemId) => {
      const deletedAt = new Date().toISOString()
      set((state) => ({
        items: patchItem(state.items, itemId, { deleted_at: deletedAt }),
        activeItemId: state.activeItemId === itemId ? null : state.activeItemId,
      }))
      pushOp({ kind: 'delete', itemId, deletedAt })
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    bringToFront: (itemId) => {
      const item = get().items.find((candidate) => candidate.id === itemId)
      if (!item) return
      const top = get().nextZIndex() - 1
      if (item.z_index === top) return
      set((state) => ({ items: patchItem(state.items, itemId, { z_index: top + 1 }) }))
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    commitMove: (itemId, from, to) => {
      if (from.x === to.x && from.y === to.y) return
      set((state) => ({ items: patchItem(state.items, itemId, to) }))
      pushOp({ kind: 'move', itemId, from, to })
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    commitResize: (itemId, from, to) => {
      if (from.width === to.width && from.height === to.height) return
      set((state) => ({ items: patchItem(state.items, itemId, to) }))
      pushOp({ kind: 'resize', itemId, from, to })
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    commitEdit: (itemId, from, to) => {
      if (from === to) return
      set((state) => ({ items: patchItem(state.items, itemId, { content: to }) }))

      const now = Date.now()
      const top = get().undoStack[get().undoStack.length - 1]
      if (top?.kind === 'edit' && top.itemId === itemId && now - top.at < EDIT_COALESCE_MS) {
        // Extend the existing step so rapid typing undoes as one action.
        const merged: UndoableOp = { ...top, to, at: now }
        set((state) => ({ undoStack: [...state.undoStack.slice(0, -1), merged], redoStack: [] }))
      } else {
        pushOp({ kind: 'edit', itemId, from, to, at: now })
      }
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    commitReplaceImage: (itemId, to) => {
      const item = get().items.find((candidate) => candidate.id === itemId)
      if (!item || item.type !== 'image') return
      const from: ImageSource = {
        image_id: item.image_id,
        width: item.width,
        height: item.height,
      }
      set((state) => ({ items: patchItem(state.items, itemId, to) }))
      pushOp({ kind: 'replaceImage', itemId, from, to })
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    setActiveItem: (itemId) => set({ activeItemId: itemId }),

    setViewState: (patch) => {
      set((state) => ({ viewState: { ...state.viewState, ...patch } }))
      scheduleSave(VIEW_SAVE_DEBOUNCE_MS)
    },

    // --- Undo / redo ------------------------------------------------------

    undo: () => {
      const stack = get().undoStack
      if (stack.length === 0) return
      const op = stack[stack.length - 1]
      applyOp(op, false)
      set((state) => ({
        undoStack: state.undoStack.slice(0, -1),
        redoStack: [...state.redoStack, op],
      }))
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    redo: () => {
      const stack = get().redoStack
      if (stack.length === 0) return
      const op = stack[stack.length - 1]
      applyOp(op, true)
      set((state) => ({
        redoStack: state.redoStack.slice(0, -1),
        undoStack: [...state.undoStack, op].slice(-UNDO_LIMIT),
      }))
      scheduleSave(ITEM_SAVE_DEBOUNCE_MS)
    },

    // --- Derived / misc ---------------------------------------------------

    retrySave: flushSave,

    visibleItems: () =>
      get()
        .items.filter((item) => !item.deleted_at)
        .sort((a, b) => a.z_index - b.z_index),

    nextZIndex: () =>
      get().items.reduce((max, item) => Math.max(max, item.z_index), 0) + 1,
  }
})
