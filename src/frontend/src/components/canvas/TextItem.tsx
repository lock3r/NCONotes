// Display mode for a text note. The note's HTML is rendered read-only here; editing
// happens in the single shared Editor, which Canvas overlays on the active item.
//
// A single click anywhere in the note opens the editor, so reaching the text never
// requires aiming at the text itself.

import { useStore } from '../../store'
import type { TextItem as TextItemModel } from '../../types'
import ItemFrame from './ItemFrame'

interface Props {
  item: TextItemModel
}

export default function TextItem({ item }: Props) {
  const setActiveItem = useStore((state) => state.setActiveItem)
  const isActive = useStore((state) => state.activeItemId === item.id)

  return (
    <ItemFrame item={item} onBodyActivate={() => setActiveItem(item.id)}>
      {/* Hidden while the editor overlays this item, so the text is not drawn twice. */}
      {!isActive && (
        <div className="text-content" dangerouslySetInnerHTML={{ __html: item.content }} />
      )}
    </ItemFrame>
  )
}
