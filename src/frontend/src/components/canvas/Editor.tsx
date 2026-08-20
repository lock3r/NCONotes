// The single TipTap instance for the whole application.
//
// One editor is created once and re-pointed at whichever item is active, rather than
// mounting an editor per note. It renders inside the world div, positioned over the
// active item's body so it inherits the canvas pan and zoom transform.
//
// Content changes are pushed to the store on every update; the store coalesces rapid
// edits into a single undo step. TipTap keeps its own undo history while focused.

import Image from '@tiptap/extension-image'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { useEffect, useRef } from 'react'
import * as api from '../../api'
import { ApiError } from '../../api'
import { useStore } from '../../store'
import { imageFileFrom } from './geometry'

export default function Editor() {
  const activeItemId = useStore((state) => state.activeItemId)
  const commitEdit = useStore((state) => state.commitEdit)
  const setActiveItem = useStore((state) => state.setActiveItem)
  const setError = useStore((state) => state.setError)

  const activeItem = useStore((state) =>
    state.items.find((item) => item.id === state.activeItemId),
  )

  // Content as last written to the store, so each undo op records the true previous value.
  const lastContentRef = useRef('')
  // handlePaste is installed before the editor exists, so it reaches it through a ref.
  const editorRef = useRef<ReturnType<typeof useEditor> | null>(null)

  const editor = useEditor({
    extensions: [StarterKit, Image],
    content: '',
    editorProps: {
      handlePaste: (_view, event) => {
        const file = imageFileFrom(event.clipboardData)
        const currentNotebook = useStore.getState().currentNotebookId
        if (!file || !currentNotebook) return false
        void (async () => {
          try {
            const uploaded = await api.uploadImage(currentNotebook, file)
            editorRef.current?.chain().focus().setImage({ src: uploaded.url }).run()
          } catch (cause) {
            setError(cause instanceof ApiError ? cause.detail : String(cause))
          }
        })()
        // The upload is handled here, so ProseMirror must not also paste the raw file.
        return true
      },
    },
    onUpdate: ({ editor: instance }) => {
      const itemId = useStore.getState().activeItemId
      if (!itemId) return
      const html = instance.getHTML()
      commitEdit(itemId, lastContentRef.current, html)
      lastContentRef.current = html
    },
  })

  useEffect(() => {
    editorRef.current = editor
  }, [editor])

  // Load the active item's content whenever the activation target changes.
  useEffect(() => {
    if (!editor || !activeItemId) return
    const item = useStore.getState().items.find((candidate) => candidate.id === activeItemId)
    if (!item || item.type !== 'text') return
    lastContentRef.current = item.content
    // emitUpdate:false keeps the programmatic load from recording an undo step.
    editor.commands.setContent(item.content, { emitUpdate: false })
    editor.commands.focus('end')
  }, [editor, activeItemId])

  // Escape returns to display mode.
  useEffect(() => {
    if (!activeItemId) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.stopPropagation()
        setActiveItem(null)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeItemId, setActiveItem])

  if (!activeItem || activeItem.type !== 'text') return null

  return (
    <div
      className="editor-overlay"
      style={{
        left: activeItem.x,
        top: activeItem.y,
        width: activeItem.width,
        height: activeItem.height,
        zIndex: activeItem.z_index,
      }}
      // Clicks inside the editor must not reach the canvas, which deactivates on click.
      onPointerDown={(event) => event.stopPropagation()}
      onDoubleClick={(event) => event.stopPropagation()}
    >
      <div className="editor-header" />
      <EditorContent className="editor-body" editor={editor} />
    </div>
  )
}
