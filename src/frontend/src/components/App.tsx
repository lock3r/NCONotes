// Root layout: Toolbar / (Sidebar + Canvas) / StatusBar
import './App.css'
import ErrorBanner from './ErrorBanner'
import Toolbar from './Toolbar'
import Sidebar from './Sidebar'
import StatusBar from './StatusBar'
import Canvas from './canvas/Canvas'

export default function App() {
  return (
    <div className="app">
      <ErrorBanner />
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
