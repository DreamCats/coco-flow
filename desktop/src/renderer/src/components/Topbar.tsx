import type { PreflightStatus } from '@shared/types'

type TopbarProps = {
  preflight: PreflightStatus | null
  compact?: boolean
}

export function Topbar({ preflight, compact = false }: TopbarProps) {
  return (
    <header className={`topbar${compact ? ' topbar--compact' : ''}`}>
      <div className="topbar__title">
        <h1>coco-flow</h1>
      </div>
      <div className="topbar__meta">
        <span className={`status-badge status-badge--${preflight?.ok ? 'healthy' : 'warning'}`}>
          {preflight?.ok ? 'CLI Ready' : 'CLI Missing'}
        </span>
        {!compact ? (
          <span className="topbar__hint">
            {preflight?.ok ? preflight.binaryPath : preflight?.error || 'Checking environment...'}
          </span>
        ) : null}
      </div>
    </header>
  )
}
