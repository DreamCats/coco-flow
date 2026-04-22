import type { PreflightStatus } from '@shared/types'

type TopbarProps = {
  preflight: PreflightStatus | null
  compact?: boolean
}

export function Topbar({ preflight, compact = false }: TopbarProps) {
  const state = preflight?.state || 'checking'
  const label = state === 'ready' ? 'CLI Ready' : state === 'missing' ? 'CLI Missing' : 'Checking CLI...'
  const tone = state === 'ready' ? 'healthy' : state === 'missing' ? 'warning' : 'checking'
  const hint =
    state === 'ready'
      ? preflight?.binaryPath
      : state === 'missing'
        ? preflight?.error || 'coco-flow not found in PATH'
        : 'Looking for coco-flow in your shell environment...'

  return (
    <header className={`topbar${compact ? ' topbar--compact' : ''}`}>
      <div className="topbar__title">
        <h1>coco-flow</h1>
      </div>
      <div className="topbar__meta">
        <span className={`status-badge status-badge--${tone}`}>
          {label}
        </span>
        {!compact ? (
          <span className="topbar__hint">{hint}</span>
        ) : null}
      </div>
    </header>
  )
}
