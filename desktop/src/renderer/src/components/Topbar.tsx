import type { PreflightStatus } from '@shared/types'

type TopbarProps = {
  preflight: PreflightStatus | null
}

export function Topbar({ preflight }: TopbarProps) {
  return (
    <header className="topbar">
      <div className="topbar__title">
        <p className="eyebrow">coco-flow</p>
        <h1>Remote launcher</h1>
      </div>
      <div className="topbar__meta">
        <span className={`status-badge status-badge--${preflight?.ok ? 'healthy' : 'warning'}`}>
          {preflight?.ok ? 'CLI Ready' : 'CLI Missing'}
        </span>
        <span className="topbar__hint">
          {preflight?.ok ? preflight.binaryPath : preflight?.error || 'Checking environment...'}
        </span>
      </div>
    </header>
  )
}
