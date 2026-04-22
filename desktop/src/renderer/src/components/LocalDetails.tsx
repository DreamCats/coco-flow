import type { LocalStatusResponse } from '@shared/types'

import { formatBoolLabel } from '../lib/launcher'

type LocalDetailsProps = {
  preflightOk: boolean
  localStatus: LocalStatusResponse | null
  busyAction: string
  onStart: () => Promise<void>
  onStop: () => Promise<void>
  onRefreshStatus: () => Promise<void>
  onOpenWeb: () => Promise<void>
}

export function LocalDetails({
  preflightOk,
  localStatus,
  busyAction,
  onStart,
  onStop,
  onRefreshStatus,
  onOpenWeb,
}: LocalDetailsProps) {
  const running = Boolean(localStatus?.running)
  const healthy = Boolean(localStatus?.healthy)
  const statusTone = running && healthy ? 'healthy' : running ? 'warning' : 'idle'
  const statusLabel = running ? (healthy ? 'Running' : 'Starting up') : 'Stopped'

  return (
    <section className="panel main-panel main-panel--wide">
      <div className="section-head section-head--main">
        <div>
          <p className="section-label">Use on this Mac</p>
          <h2>Local workspace</h2>
          <p className="subtitle">在本机启动 `coco-flow` 并直接打开本地 Web UI。</p>
        </div>
        <div className="action-row">
          <button className="button button--primary" type="button" onClick={() => void onStart()} disabled={!preflightOk || Boolean(busyAction)}>
            Start
          </button>
          <button className="button button--ghost" type="button" onClick={() => void onStop()} disabled={!preflightOk || Boolean(busyAction)}>
            Stop
          </button>
        </div>
      </div>

      <div className="chip-row">
        <span className={`status-badge status-badge--${statusTone}`}>{statusLabel}</span>
        <span className="chip">URL {localStatus?.url || 'http://127.0.0.1:4318'}</span>
        <span className="chip">Health {formatBoolLabel(localStatus?.healthy, 'ok', 'down')}</span>
      </div>

      <div className="fact-grid">
        <div className="fact-card">
          <span className="fact-card__label">Current URL</span>
          <strong>{localStatus?.url || 'http://127.0.0.1:4318'}</strong>
        </div>
        <div className="fact-card">
          <span className="fact-card__label">Server PID</span>
          <strong>{localStatus?.pid || 'Not running'}</strong>
        </div>
        <div className="fact-card">
          <span className="fact-card__label">Action</span>
          <strong>{busyAction || 'Ready'}</strong>
        </div>
      </div>

      <div className="toolbar-row">
        <button className="button button--ghost" type="button" onClick={() => void onRefreshStatus()} disabled={!preflightOk || Boolean(busyAction)}>
          Refresh Status
        </button>
        <button className="button button--ghost" type="button" onClick={() => void onOpenWeb()} disabled={!localStatus?.url}>
          Open Web
        </button>
      </div>
    </section>
  )
}
