// Standalone image on the canvas. Dropping another image file onto it replaces the
// picture in place, keeping the item's position and z-order.

import * as api from '../../api'
import { ApiError } from '../../api'
import { useStore } from '../../store'
import type { ImageItem as ImageItemModel } from '../../types'
import ItemFrame from './ItemFrame'
import { imageFileFrom, readImageSize } from './geometry'

interface Props {
  item: ImageItemModel
}

export default function ImageItem({ item }: Props) {
  const notebookId = useStore((state) => state.currentNotebookId)
  const commitReplaceImage = useStore((state) => state.commitReplaceImage)
  const setError = useStore((state) => state.setError)

  async function replaceFromDrop(event: React.DragEvent) {
    const file = imageFileFrom(event.dataTransfer)
    if (!file || !notebookId) return
    event.preventDefault()
    event.stopPropagation()
    try {
      const [uploaded, size] = await Promise.all([
        api.uploadImage(notebookId, file),
        readImageSize(file),
      ])
      commitReplaceImage(item.id, { image_id: uploaded.image_id, ...size })
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.detail : String(cause))
    }
  }

  return (
    <ItemFrame item={item} onBodyDrop={(event) => void replaceFromDrop(event)} bodyClassName="image-body">
      {notebookId && (
        <img
          className="item-image"
          src={api.imageUrl(notebookId, item.image_id)}
          alt=""
          // Native image dragging would hijack the pointer gestures.
          draggable={false}
        />
      )}
    </ItemFrame>
  )
}
