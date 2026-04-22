import type { RemoteProfile } from '@shared/types'

type RemoteSidebarProps = {
  remotes: RemoteProfile[]
  selectedRemoteName: string
  isBootstrapping: boolean
  canAddRemote: boolean
  onAddRemote: () => void
  onSelectRemote: (name: string) => void
}

export function RemoteSidebar({
  remotes,
  selectedRemoteName,
  isBootstrapping,
  canAddRemote,
  onAddRemote,
  onSelectRemote,
}: RemoteSidebarProps) {
  return (
    <aside className="panel sidebar">
      <div className="section-head">
        <div>
          <p className="section-label">Saved remotes</p>
          <h2>Machines</h2>
        </div>
        <button className="button button--secondary" type="button" onClick={onAddRemote} disabled={!canAddRemote}>
          Add
        </button>
      </div>

      <div className="remote-list">
        {isBootstrapping ? <p className="empty-copy">Loading remotes…</p> : null}
        {!isBootstrapping && remotes.length === 0 ? (
          <div className="empty-block">
            <p>还没有保存 remote。</p>
            <button className="button button--primary" type="button" onClick={onAddRemote} disabled={!canAddRemote}>
              Add your first remote
            </button>
          </div>
        ) : null}

        {remotes.map((remote) => {
          const active = remote.name === selectedRemoteName
          return (
            <button
              key={remote.name}
              className={`remote-item${active ? ' remote-item--active' : ''}`}
              type="button"
              onClick={() => onSelectRemote(remote.name)}
            >
              <span className="remote-item__name">{remote.name}</span>
              <span className="remote-item__meta">{remote.user ? `${remote.user}@${remote.host}` : remote.host}</span>
            </button>
          )
        })}
      </div>
    </aside>
  )
}
