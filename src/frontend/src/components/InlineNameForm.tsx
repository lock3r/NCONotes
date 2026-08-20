// A one-field form for naming a new notebook or page, shown in place in the sidebar.
//
// The desktop shell's webview does not reliably implement window.prompt(), so naming
// happens inline rather than in a native dialog.

import { useRef, useState } from 'react'

interface Props {
  placeholder: string
  onSubmit: (name: string) => void
  onCancel: () => void
}

export default function InlineNameForm({ placeholder, onSubmit, onCancel }: Props) {
  const [name, setName] = useState('')
  // Removing a focused input fires blur, so Escape would otherwise also submit.
  const settledRef = useRef(false)

  function settle(action: () => void) {
    if (settledRef.current) return
    settledRef.current = true
    action()
  }

  function submit() {
    const trimmed = name.trim()
    settle(() => (trimmed ? onSubmit(trimmed) : onCancel()))
  }

  return (
    <input
      className="sidebar-name-input"
      autoFocus
      placeholder={placeholder}
      value={name}
      onChange={(event) => setName(event.target.value)}
      onBlur={submit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') submit()
        if (event.key === 'Escape') settle(onCancel)
      }}
    />
  )
}
