// Modal listing deleted notebooks, pages and notes, with restore and permanent delete.
//
// Deletion elsewhere in the app is always soft, so this is the only place where data
// leaves the disk for good.

import { useEffect } from 'react'
import { useStore } from '../store'
import type { TrashItem } from '../types'

const TYPE_LABELS: Record<TrashItem['type'], string> = {
  notebook: 'Notebook',
  page: 'Page',
  note: 'Note',
}

function formatDeletedAt(iso: string): string {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleString()
}

interface Props {
  onClose: () => void
}

export default function TrashPanel({ onClose }: Props) {
  const trash = useStore((state) => state.trash)
  const loadTrash = useStore((state) => state.loadTrash)
  const restoreFromTrash = useStore((state) => state.restoreFromTrash)
  const purgeFromTrash = useStore((state) => state.purgeFromTrash)

  useEffect(() => {
    void loadTrash()
  }, [loadTrash])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <span>Trash</span>
          <button onClick={onClose}>Close</button>
        </div>

        {trash.length === 0 ? (
          <p className="modal-empty">Trash is empty.</p>
        ) : (
          <ul className="trash-list">
            {trash.map((entry) => (
              <li key={`${entry.type}:${entry.id}`} className="trash-row">
                <span className="trash-type">{TYPE_LABELS[entry.type]}</span>
                <span className="trash-name">{entry.name}</span>
                <span className="trash-date">{formatDeletedAt(entry.deleted_at)}</span>
                <button onClick={() => void restoreFromTrash(entry.id, entry.type)}>
                  Restore
                </button>
                <button
                  className="danger"
                  onClick={() => void purgeFromTrash(entry.id, entry.type)}
                >
                  Delete forever
                </button>
              </li>
            ))}
          </ul>
        )}
        <p className="modal-note">Items are purged automatically 60 days after deletion.</p>
      </div>
    </div>
  )
}
