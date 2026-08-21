// Navigation: the notebook tree and trash access.
//
// A notebook is itself a page — its row opens that page, and only the pages created
// inside it are listed beneath. Expansion is independent of selection, so any number
// of notebooks can stay open at once and each is collapsed by its own chevron.
//
// Creating and deleting notebooks and pages lives here rather than in the Toolbar, so
// each action sits next to the list it affects.

import { useState } from 'react'
import { childPages, notebookCanvasId, useStore } from '../store'
import InlineNameForm from './InlineNameForm'
import TrashPanel from './TrashPanel'

export default function Sidebar() {
  const notebooks = useStore((state) => state.notebooks)
  const currentNotebookId = useStore((state) => state.currentNotebookId)
  const currentPageId = useStore((state) => state.currentPageId)

  const selectNotebook = useStore((state) => state.selectNotebook)
  const createNotebook = useStore((state) => state.createNotebook)
  const deleteNotebook = useStore((state) => state.deleteNotebook)
  const selectPage = useStore((state) => state.selectPage)
  const createPage = useStore((state) => state.createPage)
  const deletePage = useStore((state) => state.deletePage)

  const [expanded, setExpanded] = useState<string[]>([])
  const [lastNotebookId, setLastNotebookId] = useState<string | null>(null)
  const [creatingNotebook, setCreatingNotebook] = useState(false)
  const [creatingPageIn, setCreatingPageIn] = useState<string | null>(null)
  const [trashOpen, setTrashOpen] = useState(false)

  // Arriving in a notebook reveals its pages, however the selection was made — a row
  // click, startup, or a page created from elsewhere. Collapsing it afterwards sticks,
  // because this only fires on the render where the notebook actually changes.
  if (currentNotebookId !== lastNotebookId) {
    setLastNotebookId(currentNotebookId)
    if (currentNotebookId && !expanded.includes(currentNotebookId)) {
      setExpanded([...expanded, currentNotebookId])
    }
  }

  function toggleExpanded(notebookId: string) {
    setExpanded((open) =>
      open.includes(notebookId)
        ? open.filter((id) => id !== notebookId)
        : [...open, notebookId],
    )
  }

  // Opening a notebook reveals its pages; collapsing it again is the chevron's job.
  function openNotebook(notebookId: string) {
    setExpanded((open) => (open.includes(notebookId) ? open : [...open, notebookId]))
    void selectNotebook(notebookId)
  }

  return (
    <div className="sidebar">
      <div className="sidebar-section-header">
        <span>Notebooks</span>
        <button title="New notebook" onClick={() => setCreatingNotebook(true)}>
          +
        </button>
      </div>

      {creatingNotebook && (
        <InlineNameForm
          placeholder="Notebook name"
          onSubmit={(name) => {
            setCreatingNotebook(false)
            void createNotebook(name)
          }}
          onCancel={() => setCreatingNotebook(false)}
        />
      )}

      <ul className="sidebar-list">
        {notebooks.map((notebook) => {
          const isOpen = expanded.includes(notebook.id)
          const isCurrent = notebookCanvasId(notebook) === currentPageId
          return (
            <li key={notebook.id}>
              <div
                className={`sidebar-row notebook-row${isCurrent ? ' selected' : ''}`}
                onClick={() => openNotebook(notebook.id)}
              >
                <button
                  className="sidebar-chevron"
                  title={isOpen ? 'Collapse' : 'Expand'}
                  onClick={(event) => {
                    event.stopPropagation()
                    toggleExpanded(notebook.id)
                  }}
                >
                  {isOpen ? '▾' : '▸'}
                </button>
                <span className="sidebar-label">{notebook.name}</span>
                <button
                  className="sidebar-delete"
                  title="Move notebook to trash"
                  onClick={(event) => {
                    event.stopPropagation()
                    void deleteNotebook(notebook.id)
                  }}
                >
                  ×
                </button>
              </div>

              {isOpen && (
                <ul className="sidebar-list page-list">
                  {childPages(notebook).map((page) => (
                    <li
                      key={page.id}
                      className={`sidebar-row page-row${
                        page.id === currentPageId ? ' selected' : ''
                      }`}
                      onClick={() => void selectPage(page.id)}
                    >
                      <span className="sidebar-label">{page.title}</span>
                      <button
                        className="sidebar-delete"
                        title="Move page to trash"
                        onClick={(event) => {
                          event.stopPropagation()
                          void deletePage(notebook.id, page.id)
                        }}
                      >
                        ×
                      </button>
                    </li>
                  ))}

                  <li className="sidebar-row page-row">
                    {creatingPageIn === notebook.id ? (
                      <InlineNameForm
                        placeholder="Page title"
                        onSubmit={(title) => {
                          setCreatingPageIn(null)
                          void createPage(notebook.id, title)
                        }}
                        onCancel={() => setCreatingPageIn(null)}
                      />
                    ) : (
                      <button
                        className="sidebar-add"
                        onClick={() => setCreatingPageIn(notebook.id)}
                      >
                        + New page
                      </button>
                    )}
                  </li>
                </ul>
              )}
            </li>
          )
        })}
      </ul>

      {notebooks.length === 0 && (
        <p className="sidebar-empty">No notebooks yet. Use + to create one.</p>
      )}

      <button className="sidebar-trash" onClick={() => setTrashOpen(true)}>
        Trash
      </button>

      {trashOpen && <TrashPanel onClose={() => setTrashOpen(false)} />}
    </div>
  )
}
