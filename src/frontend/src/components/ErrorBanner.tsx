// Fixed overlay at top; shown when the store has an activeError.
// Hidden by default (no active error in this phase).
const bannerStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  zIndex: 1000,
  padding: '10px 16px',
  background: '#c0392b',
  color: '#fff',
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  fontSize: 14,
}

interface Props {
  error?: string | null
  onDismiss?: () => void
  // Supplied only for failures worth attempting again, such as a failed save.
  onRetry?: () => void
}

export default function ErrorBanner({ error, onDismiss, onRetry }: Props) {
  if (!error) return null
  return (
    <div style={bannerStyle}>
      <span style={{ flex: 1 }}>{error}</span>
      {onRetry && <button onClick={onRetry}>Retry</button>}
      <button onClick={onDismiss}>Dismiss</button>
    </div>
  )
}
