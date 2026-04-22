type LogsPanelProps = {
  showLogs: boolean
  logText: string
  onToggleLogs: () => void
  onClearLogs: () => void
}

export function LogsPanel({ showLogs, logText, onToggleLogs, onClearLogs }: LogsPanelProps) {
  return (
    <section className="panel logs-panel">
      <div className="section-head">
        <div>
          <p className="section-label">Logs</p>
          <h2>Command output</h2>
        </div>
        <div className="action-row">
          <button className="button button--ghost" type="button" onClick={onToggleLogs}>
            {showLogs ? 'Hide logs' : 'Show logs'}
          </button>
          <button className="button button--ghost" type="button" onClick={onClearLogs}>
            Clear
          </button>
        </div>
      </div>
      {showLogs ? (
        <pre className="log-panel">{logText || 'No logs yet.'}</pre>
      ) : (
        <p className="collapsed-copy">默认收起。连接异常时再展开看完整日志。</p>
      )}
    </section>
  )
}
