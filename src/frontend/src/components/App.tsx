// Root layout: Toolbar / (Sidebar + Canvas) / StatusBar
import { useEffect, useRef } from 'react'
import * as api from '../api'
import { useStore } from '../store'
import './App.css'
import ErrorBanner from './ErrorBanner'
import Toolbar from './Toolbar'
import Sidebar from './Sidebar'
import StatusBar from './StatusBar'
import Canvas from './canvas/Canvas'

export default function App() {
  const activeError = useStore((state) => state.activeError)
  const clearError = useStore((state) => state.clearError)
  const saveStatus = useStore((state) => state.saveStatus)
  const retrySave = useStore((state) => state.retrySave)

  // StrictMode runs effects twice in development; without this the bootstrap would
  // create two notebooks on a first run.
  const startedRef = useRef(false)

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true

    void (async () => {
      const store = useStore.getState()
      // Trade the injected token for the session cookie that <img> requests rely on.
      if (api.hasInjectedToken()) {
        try {
          await api.createSession()
        } catch {
          store.setError('Could not establish a session — images may not load')
        }
      }

      await store.loadNotebooks()
      const notebooks = useStore.getState().notebooks
      if (notebooks.length === 0) {
        await useStore.getState().createNotebook('My Notebook')
      } else {
        await useStore.getState().selectNotebook(notebooks[0].id)
      }
    })()
  }, [])

  return (
    <div className="app">
      <ErrorBanner
        error={activeError}
        onDismiss={clearError}
        onRetry={saveStatus === 'error' ? () => void retrySave() : undefined}
      />
      <div className="app-toolbar">
        <Toolbar />
      </div>
      <div className="app-middle">
        <div className="app-sidebar">
          <Sidebar />
        </div>
        <div className="app-canvas">
          <Canvas />
        </div>
      </div>
      <div className="app-statusbar">
        <StatusBar />
      </div>
    </div>
  )
}
