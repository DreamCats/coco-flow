import {
  FormEvent,
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useMemo,
  useState,
} from 'react'

import type {
  AddRemoteInput,
  CommandLogEvent,
  ConnectRemoteResult,
  PreflightStatus,
  RemoteConnection,
  RemoteProfile,
} from '@shared/types'

type FormState = {
  name: string
  host: string
  user: string
  localPort: string
  remotePort: string
}

const DEFAULT_FORM: FormState = {
  name: '',
  host: '',
  user: '',
  localPort: '4318',
  remotePort: '4318',
}
const LAST_SELECTED_REMOTE_KEY = 'coco-flow.desktop.last-selected-remote'

function newRequestId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function formatBoolLabel(value: boolean | null | undefined, yes: string, no: string, unknown = 'Unknown'): string {
  if (value === true) {
    return yes
  }
  if (value === false) {
    return no
  }
  return unknown
}

function connectionTone(connection: RemoteConnection | null): 'idle' | 'healthy' | 'warning' {
  if (!connection) {
    return 'idle'
  }
  if (connection.local_healthy && connection.tunnel_alive) {
    return 'healthy'
  }
  return 'warning'
}

function connectionLabel(connection: RemoteConnection | null): string {
  if (!connection) {
    return 'Not connected'
  }
  if (connection.local_healthy && connection.tunnel_alive) {
    return 'Connected'
  }
  return 'Needs attention'
}

export function App() {
  const desktopApi = globalThis.window?.cocoFlowDesktop
  const [preflight, setPreflight] = useState<PreflightStatus | null>(null)
  const [remotes, setRemotes] = useState<RemoteProfile[]>([])
  const [selectedRemoteName, setSelectedRemoteName] = useState('')
  const [selectedConnection, setSelectedConnection] = useState<RemoteConnection | null>(null)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [logText, setLogText] = useState('launcher ready.\n')
  const [busyAction, setBusyAction] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [lastOpenedUrl, setLastOpenedUrl] = useState('')
  const [isBootstrapping, setIsBootstrapping] = useState(true)
  const [statusKey, setStatusKey] = useState(0)
  const [activeRequestId, setActiveRequestId] = useState('')
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [showLogs, setShowLogs] = useState(false)

  const deferredLogText = useDeferredValue(logText)
  const openWebUrl = lastOpenedUrl || selectedConnection?.local_url || ''

  const selectedRemote = useMemo(
    () => remotes.find((item) => item.name === selectedRemoteName) ?? null,
    [remotes, selectedRemoteName],
  )
  const statusTone = connectionTone(selectedConnection)
  const statusLabel = connectionLabel(selectedConnection)

  const refreshRemotes = async (nextSelectedName?: string) => {
    if (!desktopApi) {
      throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
    }
    const result = await desktopApi.listRemotes()
    startTransition(() => {
      setRemotes(result.remotes)
    })
    const rememberedSelection = globalThis.window?.localStorage.getItem(LAST_SELECTED_REMOTE_KEY) || ''
    const preferredSelection =
      nextSelectedName && result.remotes.some((item) => item.name === nextSelectedName)
        ? nextSelectedName
        : rememberedSelection && result.remotes.some((item) => item.name === rememberedSelection)
          ? rememberedSelection
        : selectedRemoteName && result.remotes.some((item) => item.name === selectedRemoteName)
          ? selectedRemoteName
          : result.remotes[0]?.name || ''
    setSelectedRemoteName(preferredSelection)
  }

  const refreshStatus = async (name: string) => {
    if (!name) {
      setSelectedConnection(null)
      return
    }
    if (!desktopApi) {
      throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
    }
    const result = await desktopApi.getStatus(name)
    startTransition(() => {
      setSelectedConnection(result.connections[0] ?? null)
    })
  }

  const appendLog = (message: string) => {
    startTransition(() => {
      setLogText((current) => `${current}${message}`)
    })
  }

  const handleCommandLog = useEffectEvent((event: CommandLogEvent) => {
    if (!activeRequestId || event.requestId !== activeRequestId) {
      return
    }
    appendLog(event.message)
  })

  useEffect(() => {
    if (!desktopApi) {
      return
    }
    const dispose = desktopApi.onCommandLog(handleCommandLog)
    return dispose
  }, [desktopApi, handleCommandLog])

  useEffect(() => {
    let cancelled = false

    const bootstrap = async () => {
      setIsBootstrapping(true)
      setErrorMessage('')
      if (!desktopApi) {
        setErrorMessage('Desktop preload API is unavailable. Restart the Electron app after the preload fix is applied.')
        setIsBootstrapping(false)
        return
      }
      const nextPreflight = await desktopApi.preflight()
      if (cancelled) {
        return
      }
      setPreflight(nextPreflight)
      if (!nextPreflight.ok) {
        setIsBootstrapping(false)
        return
      }
      try {
        await refreshRemotes()
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : String(error))
        }
      } finally {
        if (!cancelled) {
          setIsBootstrapping(false)
        }
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [desktopApi])

  useEffect(() => {
    if (!selectedRemoteName) {
      globalThis.window?.localStorage.removeItem(LAST_SELECTED_REMOTE_KEY)
      return
    }
    globalThis.window?.localStorage.setItem(LAST_SELECTED_REMOTE_KEY, selectedRemoteName)
  }, [selectedRemoteName])

  useEffect(() => {
    let cancelled = false
    if (!selectedRemoteName || !preflight?.ok) {
      setSelectedConnection(null)
      return
    }
    const loadStatus = async () => {
      try {
        await refreshStatus(selectedRemoteName)
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(error instanceof Error ? error.message : String(error))
        }
      }
    }
    void loadStatus()
    return () => {
      cancelled = true
    }
  }, [preflight?.ok, selectedRemoteName, statusKey])

  const runAction = async (actionName: string, runner: (requestId: string) => Promise<void>) => {
    setBusyAction(actionName)
    setErrorMessage('')
    const requestId = newRequestId()
    setActiveRequestId(requestId)
    setLogText(`${actionName}\n`)
    try {
      await runner(requestId)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      appendLog(`error: ${message}\n`)
      setErrorMessage(message)
    } finally {
      setBusyAction('')
      setActiveRequestId('')
      setStatusKey((value) => value + 1)
    }
  }

  const handleAddRemote = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setErrorMessage('')
    if (!preflight?.ok) {
      return
    }
    const payload: AddRemoteInput = {
      name: form.name.trim(),
      host: form.host.trim(),
      user: form.user.trim(),
      localPort: Number(form.localPort),
      remotePort: Number(form.remotePort),
    }
    setBusyAction('Saving remote...')
    try {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      const result = await desktopApi.addRemote(payload)
      appendLog(`saved: ${result.name} -> ${result.host}\n`)
      setForm(DEFAULT_FORM)
      setIsAddModalOpen(false)
      await refreshRemotes(result.name)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyAction('')
    }
  }

  const handleConnect = async (restart: boolean) => {
    if (!selectedRemoteName) {
      return
    }
    await runAction(restart ? 'Restarting remote and reconnecting...' : 'Connecting remote...', async (requestId) => {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      const result: ConnectRemoteResult = await desktopApi.connectRemote({
        requestId,
        name: selectedRemoteName,
        restart,
        openBrowser: true,
      })
      appendLog(`connected: ${result.ssh_target}\n`)
      appendLog(`url: ${result.local_url}\n`)
      setLastOpenedUrl(result.local_url)
      await refreshStatus(selectedRemoteName)
    })
  }

  const handleDisconnect = async () => {
    if (!selectedRemoteName) {
      return
    }
    await runAction('Disconnecting tunnel...', async (requestId) => {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      const result = await desktopApi.disconnectRemote({
        requestId,
        name: selectedRemoteName,
      })
      appendLog(`disconnected: ${result.targets.join(', ')}\n`)
      await refreshStatus(selectedRemoteName)
    })
  }

  const handleDeleteRemote = async () => {
    if (!selectedRemoteName) {
      return
    }
    if (!window.confirm(`Delete remote "${selectedRemoteName}"?`)) {
      return
    }
    setBusyAction('Deleting remote...')
    setErrorMessage('')
    try {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      await desktopApi.removeRemote(selectedRemoteName)
      appendLog(`removed: ${selectedRemoteName}\n`)
      setLastOpenedUrl('')
      await refreshRemotes()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyAction('')
    }
  }

  const handleRefreshStatus = async () => {
    if (!selectedRemoteName) {
      return
    }
    setBusyAction('Refreshing status...')
    setErrorMessage('')
    try {
      await refreshStatus(selectedRemoteName)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyAction('')
    }
  }

  const openWeb = async () => {
    if (!openWebUrl) {
      return
    }
    try {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      await desktopApi.openWeb(openWebUrl)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error))
    }
  }

  return (
    <div className="app-shell">
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

      {errorMessage ? <div className="banner banner--error">{errorMessage}</div> : null}
      {!preflight?.ok ? (
        <div className="banner banner--warning">
          需要先在本机安装并让 shell 可见 <code>coco-flow</code>。
        </div>
      ) : null}

      <main className="layout">
        <aside className="panel sidebar">
          <div className="section-head">
            <div>
              <p className="section-label">Saved remotes</p>
              <h2>Machines</h2>
            </div>
            <button
              className="button button--secondary"
              type="button"
              onClick={() => setIsAddModalOpen(true)}
              disabled={!preflight?.ok || Boolean(busyAction)}
            >
              Add
            </button>
          </div>

          <div className="remote-list">
            {isBootstrapping ? <p className="empty-copy">Loading remotes…</p> : null}
            {!isBootstrapping && remotes.length === 0 ? (
              <div className="empty-block">
                <p>还没有保存 remote。</p>
                <button
                  className="button button--primary"
                  type="button"
                  onClick={() => setIsAddModalOpen(true)}
                  disabled={!preflight?.ok}
                >
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
                  onClick={() => setSelectedRemoteName(remote.name)}
                >
                  <span className="remote-item__name">{remote.name}</span>
                  <span className="remote-item__meta">
                    {remote.user ? `${remote.user}@${remote.host}` : remote.host}
                  </span>
                </button>
              )
            })}
          </div>
        </aside>

        <section className="panel main-panel">
          {selectedRemote ? (
            <>
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
                  <button
                    className="button button--primary"
                    type="button"
                    onClick={() => void handleConnect(false)}
                    disabled={!preflight?.ok || Boolean(busyAction)}
                  >
                    Connect
                  </button>
                  <button
                    className="button button--secondary"
                    type="button"
                    onClick={() => void handleConnect(true)}
                    disabled={!preflight?.ok || Boolean(busyAction)}
                  >
                    Restart
                  </button>
                  <button
                    className="button button--ghost"
                    type="button"
                    onClick={() => void handleDisconnect()}
                    disabled={!preflight?.ok || Boolean(busyAction)}
                  >
                    Disconnect
                  </button>
                </div>
              </div>

              <div className="chip-row">
                <span className={`status-badge status-badge--${statusTone}`}>{statusLabel}</span>
                <span className="chip">{selectedRemote.local_port} → {selectedRemote.remote_port}</span>
                <span className="chip">
                  Tunnel {formatBoolLabel(selectedConnection?.tunnel_alive, 'alive', 'down')}
                </span>
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
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={() => void handleRefreshStatus()}
                  disabled={!preflight?.ok || Boolean(busyAction)}
                >
                  Refresh Status
                </button>
                <button
                  className="button button--ghost"
                  type="button"
                  onClick={() => void openWeb()}
                  disabled={!openWebUrl}
                >
                  Open Web
                </button>
                <button
                  className="button button--danger"
                  type="button"
                  onClick={() => void handleDeleteRemote()}
                  disabled={!preflight?.ok || Boolean(busyAction)}
                >
                  Delete Remote
                </button>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p className="section-label">No selection</p>
              <h2>Pick a remote to connect.</h2>
              <p className="empty-copy">左侧选择一台开发机；如果还没有，就先添加一台。</p>
              <button
                className="button button--primary"
                type="button"
                onClick={() => setIsAddModalOpen(true)}
                disabled={!preflight?.ok}
              >
                Add Remote
              </button>
            </div>
          )}
        </section>
      </main>

      <section className="panel logs-panel">
        <div className="section-head">
          <div>
            <p className="section-label">Logs</p>
            <h2>Command output</h2>
          </div>
          <div className="action-row">
            <button className="button button--ghost" type="button" onClick={() => setShowLogs((value) => !value)}>
              {showLogs ? 'Hide logs' : 'Show logs'}
            </button>
            <button className="button button--ghost" type="button" onClick={() => setLogText('')}>
              Clear
            </button>
          </div>
        </div>
        {showLogs ? (
          <pre className="log-panel">{deferredLogText || 'No logs yet.'}</pre>
        ) : (
          <p className="collapsed-copy">默认收起。连接异常时再展开看完整日志。</p>
        )}
      </section>

      {isAddModalOpen ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setIsAddModalOpen(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="section-head">
              <div>
                <p className="section-label">Add remote</p>
                <h2>New machine</h2>
              </div>
              <button className="button button--ghost" type="button" onClick={() => setIsAddModalOpen(false)}>
                Close
              </button>
            </div>

            <form className="remote-form" onSubmit={handleAddRemote}>
              <label>
                <span>Name</span>
                <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
              </label>
              <label>
                <span>Host</span>
                <input value={form.host} onChange={(event) => setForm((current) => ({ ...current, host: event.target.value }))} />
              </label>
              <label>
                <span>User</span>
                <input
                  value={form.user}
                  placeholder="Optional"
                  onChange={(event) => setForm((current) => ({ ...current, user: event.target.value }))}
                />
              </label>
              <div className="field-row">
                <label>
                  <span>Local port</span>
                  <input
                    inputMode="numeric"
                    value={form.localPort}
                    onChange={(event) => setForm((current) => ({ ...current, localPort: event.target.value }))}
                  />
                </label>
                <label>
                  <span>Remote port</span>
                  <input
                    inputMode="numeric"
                    value={form.remotePort}
                    onChange={(event) => setForm((current) => ({ ...current, remotePort: event.target.value }))}
                  />
                </label>
              </div>
              <button className="button button--primary" type="submit" disabled={!preflight?.ok || Boolean(busyAction)}>
                Save Remote
              </button>
            </form>
          </div>
        </div>
      ) : null}
    </div>
  )
}
