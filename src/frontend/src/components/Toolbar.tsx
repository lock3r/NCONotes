// Top bar: where you are (notebook › page) and prev/next navigation through the
// current notebook's pages. Creating and deleting live in the Sidebar, next to the lists.

import { useMemo } from 'react'
import { pageSequence, pageTitle, useStore } from '../store'

export default function Toolbar() {
  const notebooks = useStore((state) => state.notebooks)
  const pages = useStore((state) => state.pages)
  const currentNotebookId = useStore((state) => state.currentNotebookId)
  const currentPageId = useStore((state) => state.currentPageId)
  const selectPage = useStore((state) => state.selectPage)

  const notebook = notebooks.find((nb) => nb.id === currentNotebookId)
  const sequence = useMemo(
    () => pageSequence(notebooks, currentNotebookId, pages),
    [notebooks, currentNotebookId, pages],
  )

  const index = sequence.findIndex((page) => page.id === currentPageId)
  const current = index >= 0 ? sequence[index] : null

  function step(offset: number) {
    const target = sequence[index + offset]
    if (target) void selectPage(target.id)
  }

  return (
    <>
      <span className="toolbar-brand">NCONotes</span>
      <span className="toolbar-location">
        {notebook ? notebook.name : 'No notebook selected'}
        {current && <span className="toolbar-page"> › {pageTitle(current)}</span>}
      </span>
      <span className="toolbar-nav">
        <button title="Previous page" disabled={index <= 0} onClick={() => step(-1)}>
          ‹
        </button>
        <span className="toolbar-position">
          {index >= 0 ? `${index + 1} / ${sequence.length}` : '–'}
        </span>
        <button
          title="Next page"
          disabled={index < 0 || index >= sequence.length - 1}
          onClick={() => step(1)}
        >
          ›
        </button>
      </span>
    </>
  )
}
