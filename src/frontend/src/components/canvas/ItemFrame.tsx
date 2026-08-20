// Positioning, drag, resize, z-ordering and delete chrome shared by every canvas item.
// TextItem and ImageItem supply only their body content.
//
// Pointer deltas are divided by the canvas scale so a gesture moves the item the same
// distance under the cursor at any zoom level.

import { useRef, useState, type ReactNode } from 'react'
import { useStore } from '../../store'
import type { CanvasItem } from '../../types'
import { MIN_ITEM_HEIGHT, MIN_ITEM_WIDTH } from './geometry'

interface DragState {
  pointerX: number
  pointerY: number
  originX: number
  originY: number
  lastX: number
  lastY: number
}

interface Props {
  item: CanvasItem
  children: ReactNode
  onBodyDoubleClick?: () => void
  onBodyDrop?: (event: React.DragEvent) => void
  bodyClassName?: string
}

export default function ItemFrame({
  item,
  children,
  onBodyDoubleClick,
  onBodyDrop,
  bodyClassName,
}: Props) {
  const scale = useStore((state) => state.viewState.scale)
  const updateItem = useStore((state) => state.updateItem)
  const commitMove = useStore((state) => state.commitMove)
  const commitResize = useStore((state) => state.commitResize)
  const deleteItem = useStore((state) => state.deleteItem)
  const bringToFront = useStore((state) => state.bringToFront)

  const [hovered, setHovered] = useState(false)
  const moveRef = useRef<DragState | null>(null)
  const resizeRef = useRef<DragState | null>(null)

  function beginGesture(
    ref: React.RefObject<DragState | null>,
    event: React.PointerEvent,
    originX: number,
    originY: number,
  ) {
    if (event.button !== 0) return
    // Keep the canvas from treating this as a pan or a new-note double click.
    event.stopPropagation()
    bringToFront(item.id)
    event.currentTarget.setPointerCapture(event.pointerId)
    ref.current = {
      pointerX: event.clientX,
      pointerY: event.clientY,
      originX,
      originY,
      lastX: originX,
      lastY: originY,
    }
  }

  function onMovePointerMove(event: React.PointerEvent) {
    const drag = moveRef.current
    if (!drag) return
    drag.lastX = drag.originX + (event.clientX - drag.pointerX) / scale
    drag.lastY = drag.originY + (event.clientY - drag.pointerY) / scale
    updateItem(item.id, { x: drag.lastX, y: drag.lastY })
  }

  function onMovePointerUp(event: React.PointerEvent) {
    const drag = moveRef.current
    if (!drag) return
    moveRef.current = null
    event.currentTarget.releasePointerCapture(event.pointerId)
    commitMove(
      item.id,
      { x: drag.originX, y: drag.originY },
      { x: drag.lastX, y: drag.lastY },
    )
  }

  function onResizePointerMove(event: React.PointerEvent) {
    const drag = resizeRef.current
    if (!drag) return
    drag.lastX = Math.max(MIN_ITEM_WIDTH, drag.originX + (event.clientX - drag.pointerX) / scale)
    drag.lastY = Math.max(MIN_ITEM_HEIGHT, drag.originY + (event.clientY - drag.pointerY) / scale)
    updateItem(item.id, { width: drag.lastX, height: drag.lastY })
  }

  function onResizePointerUp(event: React.PointerEvent) {
    const drag = resizeRef.current
    if (!drag) return
    resizeRef.current = null
    event.currentTarget.releasePointerCapture(event.pointerId)
    commitResize(
      item.id,
      { width: drag.originX, height: drag.originY },
      { width: drag.lastX, height: drag.lastY },
    )
  }

  return (
    <div
      className="item"
      style={{
        left: item.x,
        top: item.y,
        width: item.width,
        height: item.height,
        zIndex: item.z_index,
      }}
      onPointerDown={() => bringToFront(item.id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className="item-header"
        onPointerDown={(event) => beginGesture(moveRef, event, item.x, item.y)}
        onPointerMove={onMovePointerMove}
        onPointerUp={onMovePointerUp}
        onPointerCancel={onMovePointerUp}
      >
        {hovered && (
          <button
            className="item-delete"
            title="Delete"
            // The header owns pointer events for dragging; keep them off the button.
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => deleteItem(item.id)}
          >
            ×
          </button>
        )}
      </div>

      <div
        className={bodyClassName ? `item-body ${bodyClassName}` : 'item-body'}
        onDoubleClick={(event) => {
          if (!onBodyDoubleClick) return
          event.stopPropagation()
          onBodyDoubleClick()
        }}
        onDragOver={onBodyDrop ? (event) => event.preventDefault() : undefined}
        onDrop={onBodyDrop}
      >
        {children}
      </div>

      <div
        className="item-resize"
        onPointerDown={(event) => beginGesture(resizeRef, event, item.width, item.height)}
        onPointerMove={onResizePointerMove}
        onPointerUp={onResizePointerUp}
        onPointerCancel={onResizePointerUp}
      />
    </div>
  )
}
