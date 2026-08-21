// Infinite canvas: pan/zoom viewport, item rendering, and event routing.
//
// The viewport is a clipping div; inside it a single "world" div carries the transform
// translate(pan) scale(zoom) — translate first, so pan is measured in screen pixels and
// stays constant as the zoom changes. Items are absolutely positioned in world
// coordinates and inherit that transform.

import { useCallback, useEffect, useMemo, useRef } from 'react'
import * as api from '../../api'
import { ApiError } from '../../api'
import { useStore } from '../../store'
import Editor from './Editor'
import ImageItem from './ImageItem'
import TextItem from './TextItem'
import './canvas.css'
import {
  clampPanY,
  clampScale,
  imageFileFrom,
  pointerInElement,
  readImageSize,
  screenToWorld,
} from './geometry'

interface PanState {
  pointerX: number
  pointerY: number
  originPanX: number
  originPanY: number
}

export default function Canvas() {
  const viewportRef = useRef<HTMLDivElement>(null)
  const panRef = useRef<PanState | null>(null)
  const spaceHeldRef = useRef(false)

  const notebookId = useStore((state) => state.currentNotebookId)
  const pageId = useStore((state) => state.currentPageId)
  const items = useStore((state) => state.items)
  const viewState = useStore((state) => state.viewState)
  const setViewState = useStore((state) => state.setViewState)
  const addTextItem = useStore((state) => state.addTextItem)
  const addImageItem = useStore((state) => state.addImageItem)
  const setActiveItem = useStore((state) => state.setActiveItem)
  const setError = useStore((state) => state.setError)

  // Deleted items stay in `items` until purged; draw only the live ones.
  //
  // Stacking is the z-index style on each item, never the DOM order: reordering a node
  // between pointerdown and pointerup makes the browser drop the click, and raising an
  // item to the front is exactly what a press on it does.
  const visible = useMemo(() => items.filter((item) => !item.deleted_at), [items])

  const toWorld = useCallback(
    (event: { clientX: number; clientY: number }) => {
      const viewport = viewportRef.current
      if (!viewport) return { x: 0, y: 0 }
      return screenToWorld(pointerInElement(event, viewport), useStore.getState().viewState)
    },
    [],
  )

  const placeImage = useCallback(
    async (file: File, worldX: number, worldY: number) => {
      const currentNotebook = useStore.getState().currentNotebookId
      if (!currentNotebook) return
      try {
        const [uploaded, size] = await Promise.all([
          api.uploadImage(currentNotebook, file),
          readImageSize(file),
        ])
        addImageItem(worldX, worldY, uploaded.image_id, size.width, size.height)
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.detail : String(cause))
      }
    },
    [addImageItem, setError],
  )

  // Wheel handling is registered natively because React's synthetic wheel listener is
  // passive, and zooming must preventDefault to suppress the browser's own page zoom.
  useEffect(() => {
    const viewport = viewportRef.current
    if (!viewport) return

    function onWheel(event: WheelEvent) {
      event.preventDefault()
      const view = useStore.getState().viewState

      if (event.ctrlKey) {
        const cursor = pointerInElement(event, viewport!)
        const scale = clampScale(view.scale * Math.exp(-event.deltaY * 0.0015))
        const factor = scale / view.scale
        // Keep the world point under the cursor pinned while the scale changes.
        setViewState({
          scale,
          pan_x: cursor.x - (cursor.x - view.pan_x) * factor,
          pan_y: clampPanY(cursor.y - (cursor.y - view.pan_y) * factor),
        })
        return
      }

      if (event.shiftKey) {
        setViewState({ pan_x: view.pan_x - event.deltaY })
        return
      }
      setViewState({
        pan_x: view.pan_x - event.deltaX,
        pan_y: clampPanY(view.pan_y - event.deltaY),
      })
    }

    viewport.addEventListener('wheel', onWheel, { passive: false })
    return () => viewport.removeEventListener('wheel', onWheel)
  }, [setViewState])

  // Space enables drag-panning with the left button, as an alternative to middle-drag.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.code === 'Space' && !isTypingTarget(event.target)) {
        spaceHeldRef.current = true
      }
    }
    function onKeyUp(event: KeyboardEvent) {
      if (event.code === 'Space') spaceHeldRef.current = false
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [])

  // Undo/redo shortcuts. While an editor is active TipTap owns Ctrl+Z for its own text.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (!event.ctrlKey && !event.metaKey) return
      const key = event.key.toLowerCase()
      if (key !== 'z' && key !== 'y') return
      if (useStore.getState().activeItemId) return

      event.preventDefault()
      const redo = key === 'y' || event.shiftKey
      if (redo) useStore.getState().redo()
      else useStore.getState().undo()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  // Pasting an image onto the canvas drops it at the viewport centre; while an editor
  // is active the paste belongs to TipTap instead.
  useEffect(() => {
    function onPaste(event: ClipboardEvent) {
      if (useStore.getState().activeItemId) return
      const file = imageFileFrom(event.clipboardData)
      const viewport = viewportRef.current
      if (!file || !viewport) return
      event.preventDefault()
      const rect = viewport.getBoundingClientRect()
      const centre = screenToWorld(
        { x: rect.width / 2, y: rect.height / 2 },
        useStore.getState().viewState,
      )
      void placeImage(file, centre.x, centre.y)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [placeImage])

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    const panning = event.button === 1 || (event.button === 0 && spaceHeldRef.current)
    if (!panning) {
      // A plain click on empty canvas dismisses the editor.
      if (event.button === 0) setActiveItem(null)
      return
    }
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    panRef.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      originPanX: viewState.pan_x,
      originPanY: viewState.pan_y,
    }
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const pan = panRef.current
    if (!pan) return
    setViewState({
      pan_x: pan.originPanX + (event.clientX - pan.pointerX),
      pan_y: clampPanY(pan.originPanY + (event.clientY - pan.pointerY)),
    })
  }

  function onPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (!panRef.current) return
    panRef.current = null
    event.currentTarget.releasePointerCapture(event.pointerId)
  }

  function onDoubleClick(event: React.MouseEvent<HTMLDivElement>) {
    const world = toWorld(event)
    setActiveItem(addTextItem(world.x, world.y))
  }

  function onDrop(event: React.DragEvent<HTMLDivElement>) {
    const file = imageFileFrom(event.dataTransfer)
    if (!file) return
    event.preventDefault()
    const world = toWorld(event)
    void placeImage(file, world.x, world.y)
  }

  if (!notebookId || !pageId) {
    return <div className="canvas-empty">No page selected</div>
  }

  return (
    <div
      ref={viewportRef}
      className="canvas-viewport"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onDoubleClick={onDoubleClick}
      onDragOver={(event) => event.preventDefault()}
      onDrop={onDrop}
    >
      <div
        className="canvas-world"
        style={{
          transform: `translate(${viewState.pan_x}px, ${viewState.pan_y}px) scale(${viewState.scale})`,
        }}
      >
        {visible.map((item) =>
          item.type === 'text' ? (
            <TextItem key={item.id} item={item} />
          ) : (
            <ImageItem key={item.id} item={item} />
          ),
        )}
        <Editor />
      </div>
    </div>
  )
}

// Space must still type a space inside the editor rather than arming pan mode.
function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  return target.isContentEditable || target.tagName === 'INPUT' || target.tagName === 'TEXTAREA'
}
