// Bottom bar: zoom level, live item count on the current page, and the auto-save state.

import { useStore, type SaveStatus } from '../store'

const SAVE_LABELS: Record<SaveStatus, string> = {
  idle: '',
  saving: 'Saving…',
  saved: 'Saved',
  error: 'Save failed',
}

export default function StatusBar() {
  const scale = useStore((state) => state.viewState.scale)
  const saveStatus = useStore((state) => state.saveStatus)
  const currentPageId = useStore((state) => state.currentPageId)
  // Deleted items remain in `items` until purged, so they are excluded from the count.
  const itemCount = useStore(
    (state) => state.items.filter((item) => !item.deleted_at).length,
  )

  if (!currentPageId) return <span>No page open</span>

  return (
    <>
      <span>{Math.round(scale * 100)}%</span>
      <span className="status-separator">·</span>
      <span>
        {itemCount} {itemCount === 1 ? 'item' : 'items'}
      </span>
      <span className={`status-save ${saveStatus}`}>{SAVE_LABELS[saveStatus]}</span>
    </>
  )
}
