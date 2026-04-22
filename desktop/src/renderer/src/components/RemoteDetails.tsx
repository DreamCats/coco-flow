import type { RemoteConnection, RemoteProfile } from '@shared/types'

import { formatBoolLabel, type ConnectionTone } from '../lib/launcher'

type RemoteDetailsProps = {
  preflightOk: boolean
  selectedRemote: RemoteProfile | null
  selectedConnection: RemoteConnection | null
  statusTone: ConnectionTone
  statusLabel: string
  openWebUrl: string
  busyAction: string
  onAddRemote: () => void
  onConnect: (restart: boolean) => Promise<void>
  onDisconnect: () => Promise<void>
  onRefreshStatus: () => Promise<void>
  onOpenWeb: () => Promise<void>
  onDeleteRemote: () => Promise<void>
}

export function RemoteDetails({
  preflightOk,
  selectedRemote,
  selectedConnection,
  statusTone,
  statusLabel,
  openWebUrl,
  busyAction,
  onAddRemote,
  onConnect,
  onDisconnect,
  onRefreshStatus,
  onOpenWeb,
  onDeleteRemote,
}: RemoteDetailsProps) {
  if (!selectedRemote) {
    return (
      <section className="panel main-panel">
        <div className="empty-state">
          <p className="section-label">No selection</p>
          <h2>Pick a remote to connect.</h2>
          <p className="empty-copy">左侧选择一台开发机；如果还没有，就先添加一台。</p>
          <button className="button button--primary" type="button" onClick={onAddRemote} disabled={!preflightOk}>
            Add Remote
          </button>
        </div>
      </section>
    )
  }

  return (
    <section className="panel main-panel">
      <div className="section-head section-head--main">
        <div>
          <p className="section-label">Selected remote</p>
          <h2>{selectedRemote.name}</h2>
          <p className="subtitle">
            {selectedRemote.user ? `${selectedRemote.user}@` : ''}
            {selectedRemote.host}
          </p>
        </div>
        <div className="action-row">
          <button className="button button--primary" type="button" onClick={() => void onConnect(false)} disabled={!preflightOk || Boolean(busyAction)}>
            Connect
          </button>
          <button className="button button--secondary" type="button" onClick={() => void onConnect(true)} disabled={!preflightOk || Boolean(busyAction)}>
            Restart
          </button>
          <button className="button button--ghost" type="button" onClick={() => void onDisconnect()} disabled={!preflightOk || Boolean(busyAction)}>
            Disconnect
          </button>
        </div>
      </div>

      <div className="chip-row">
        <span className={`status-badge status-badge--${statusTone}`}>{statusLabel}</span>
        <span className="chip">{selectedRemote.local_port} → {selectedRemote.remote_port}</span>
        <span className="chip">Tunnel {formatBoolLabel(selectedConnection?.tunnel_alive, 'alive', 'down')}</span>
        <span className="chip">
          Fingerprint {formatBoolLabel(selectedConnection?.fingerprint_match, 'matched', 'mismatch')}
        </span>
      </div>

      <div className="fact-grid">
        <div className="fact-card">
          <span className="fact-card__label">Current URL</span>
          <strong>{openWebUrl || 'Not connected yet'}</strong>
        </div>
        <div className="fact-card">
          <span className="fact-card__label">Remote health</span>
          <strong>{formatBoolLabel(selectedConnection?.remote_healthy, 'OK', 'Down')}</strong>
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
        <button className="button button--ghost" type="button" onClick={() => void onOpenWeb()} disabled={!openWebUrl}>
          Open Web
        </button>
        <button className="button button--danger" type="button" onClick={() => void onDeleteRemote()} disabled={!preflightOk || Boolean(busyAction)}>
          Delete Remote
        </button>
      </div>
    </section>
  )
}
