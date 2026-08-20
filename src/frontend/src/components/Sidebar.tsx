// Navigation: the notebook list, the pages of the selected notebook, and trash access.
//
// Only the selected notebook expands its page list — navigating is what expands it, so
// there is no separate expand/collapse state to keep in sync with the selection.
//
// Creating and deleting notebooks and pages lives here rather than in the Toolbar, so
// each action sits next to the list it affects.

import { useState } from 'react'
import { pageTitle, useStore } from '../store'
import InlineNameForm from './InlineNameForm'
import TrashPanel from './TrashPanel'

type Creating = 'notebook' | 'page' | null

export default function Sidebar() {
  const notebooks = useStore((state) => state.notebooks)
  const pages = useStore((state) => state.pages)
  const currentNotebookId = useStore((state) => state.currentNotebookId)
  const currentPageId = useStore((state) => state.currentPageId)

  const selectNotebook = useStore((state) => state.selectNotebook)
  const createNotebook = useStore((state) => state.createNotebook)
  const deleteNotebook = useStore((state) => state.deleteNotebook)
  const selectPage = useStore((state) => state.selectPage)
  const createPage = useStore((state) => state.createPage)
  const deletePage = useStore((state) => state.deletePage)

  const [creating, setCreating] = useState<Creating>(null)
  const [trashOpen, setTrashOpen] = useState(false)

  return (
    <div className="sidebar">
      <div className="sidebar-section-header">
        <span>Notebooks</span>
        <button title="New notebook" onClick={() => setCreating('notebook')}>
          +
        </button>
      </div>

      {creating === 'notebook' && (
        <InlineNameForm
          placeholder="Notebook name"
          onSubmit={(name) => {
            setCreating(null)
            void createNotebook(name)
          }}
          onCancel={() => setCreating(null)}
        />
      )}

      <ul className="sidebar-list">
        {notebooks.map((notebook) => {
          const isCurrent = notebook.id === currentNotebookId
          const canvas = notebook.pages[0]
          return (
            <li key={notebook.id}>
              <div
                className={`sidebar-row notebook-row${isCurrent ? ' selected' : ''}`}
                onClick={() => void selectNotebook(notebook.id)}
              >
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

              {isCurrent && (
                <ul className="sidebar-list page-list">
                  {canvas && (
                    <li
                      className={`sidebar-row page-row${
                        canvas.id === currentPageId ? ' selected' : ''
                      }`}
                      onClick={() => void selectPage(canvas.id)}
                    >
                      <span className="sidebar-label">{pageTitle(canvas)}</span>
                    </li>
                  )}

                  {pages.map((page) => (
                    <li
                      key={page.id}
                      className={`sidebar-row page-row${
                        page.id === currentPageId ? ' selected' : ''
                      }`}
                      onClick={() => void selectPage(page.id)}
                    >
                      <span className="sidebar-label">{pageTitle(page)}</span>
                      <button
                        className="sidebar-delete"
                        title="Move page to trash"
                        onClick={(event) => {
                          event.stopPropagation()
                          void deletePage(page.id)
                        }}
                      >
                        ×
                      </button>
                    </li>
                  ))}

                  <li className="sidebar-row page-row">
                    {creating === 'page' ? (
                      <InlineNameForm
                        placeholder="Page title"
                        onSubmit={(title) => {
                          setCreating(null)
                          void createPage(title)
                        }}
                        onCancel={() => setCreating(null)}
                      />
                    ) : (
                      <button className="sidebar-add" onClick={() => setCreating('page')}>
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
