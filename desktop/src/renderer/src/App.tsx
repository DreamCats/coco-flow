import { AddRemoteModal } from './components/AddRemoteModal'
import { LogsPanel } from './components/LogsPanel'
import { RemoteDetails } from './components/RemoteDetails'
import { RemoteSidebar } from './components/RemoteSidebar'
import { Topbar } from './components/Topbar'
import { useLauncherState } from './hooks/useLauncherState'

export function App() {
  const launcher = useLauncherState()

  return (
    <div className="app-shell">
      <Topbar preflight={launcher.preflight} />

      {launcher.errorMessage ? <div className="banner banner--error">{launcher.errorMessage}</div> : null}
      {!launcher.preflight?.ok ? (
        <div className="banner banner--warning">
          需要先在本机安装并让 shell 可见 <code>coco-flow</code>。
        </div>
      ) : null}

      <main className="layout">
        <RemoteSidebar
          remotes={launcher.remotes}
          selectedRemoteName={launcher.selectedRemoteName}
          isBootstrapping={launcher.isBootstrapping}
          canAddRemote={launcher.canAddRemote}
          onAddRemote={() => launcher.setIsAddModalOpen(true)}
          onSelectRemote={launcher.setSelectedRemoteName}
        />

        <RemoteDetails
          preflightOk={Boolean(launcher.preflight?.ok)}
          selectedRemote={launcher.selectedRemote}
          selectedConnection={launcher.selectedConnection}
          statusTone={launcher.statusTone}
          statusLabel={launcher.statusLabel}
          openWebUrl={launcher.openWebUrl}
          busyAction={launcher.busyAction}
          onAddRemote={() => launcher.setIsAddModalOpen(true)}
          onConnect={launcher.handleConnect}
          onDisconnect={launcher.handleDisconnect}
          onRefreshStatus={launcher.handleRefreshStatus}
          onOpenWeb={launcher.openWeb}
          onDeleteRemote={launcher.handleDeleteRemote}
        />
      </main>

      <LogsPanel
        showLogs={launcher.showLogs}
        logText={launcher.deferredLogText}
        onToggleLogs={() => launcher.setShowLogs((value) => !value)}
        onClearLogs={() => launcher.setLogText('')}
      />

      <AddRemoteModal
        open={launcher.isAddModalOpen}
        form={launcher.form}
        canSubmit={Boolean(launcher.preflight?.ok) && !launcher.busyAction}
        onClose={() => launcher.setIsAddModalOpen(false)}
        onSubmit={launcher.handleAddRemote}
        onChange={launcher.setForm}
      />
    </div>
  )
}
