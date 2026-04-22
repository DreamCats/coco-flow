import { useEffect, useState } from 'react'

import { AddRemoteModal } from './components/AddRemoteModal'
import { LocalDetails } from './components/LocalDetails'
import { LogsPanel } from './components/LogsPanel'
import { ModePicker } from './components/ModePicker'
import { ModeSwitch } from './components/ModeSwitch'
import { RemoteDetails } from './components/RemoteDetails'
import { RemoteSidebar } from './components/RemoteSidebar'
import { Topbar } from './components/Topbar'
import { useLocalLauncherState } from './hooks/useLocalLauncherState'
import { useLauncherState } from './hooks/useLauncherState'
import type { LauncherMode } from './lib/launcher'

export function App() {
  const [mode, setMode] = useState<LauncherMode>('picker')
  const [transitioningMode, setTransitioningMode] = useState<Exclude<LauncherMode, 'picker'> | null>(null)
  const launcher = useLauncherState()
  const localLauncher = useLocalLauncherState(Boolean(launcher.preflight?.ok))
  const modeError = mode === 'local' ? localLauncher.errorMessage : mode === 'remote' ? launcher.errorMessage : ''
  const currentLogs = mode === 'local' ? localLauncher : launcher

  useEffect(() => {
    void globalThis.window?.cocoFlowDesktop?.setWindowMode(mode)
  }, [mode])

  const handleSelectMode = (nextMode: Exclude<LauncherMode, 'picker'>) => {
    setTransitioningMode(nextMode)
    globalThis.window?.setTimeout(() => {
      setMode(nextMode)
      setTransitioningMode(null)
    }, 140)
  }

  return (
    <div className="app-shell">
      <Topbar preflight={launcher.preflight} compact={mode === 'picker'} />

      {mode !== 'picker' ? <ModeSwitch mode={mode} onChangeMode={setMode} /> : null}
      {modeError ? <div className="banner banner--error">{modeError}</div> : null}
      {launcher.preflight?.state === 'missing' ? (
        <div className="banner banner--warning">
          需要先在本机安装并让 shell 可见 <code>coco-flow</code>。
        </div>
      ) : null}

      {mode === 'picker' ? <ModePicker transitioningMode={transitioningMode} onSelectMode={handleSelectMode} /> : null}

      {mode === 'remote' ? (
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
      ) : null}

      {mode === 'local' ? (
        <main className="layout layout--single">
          <LocalDetails
            preflightOk={Boolean(launcher.preflight?.ok)}
            localStatus={localLauncher.localStatus}
            busyAction={localLauncher.busyAction}
            onStart={localLauncher.handleStart}
            onStop={localLauncher.handleStop}
            onRefreshStatus={localLauncher.handleRefreshStatus}
            onOpenWeb={localLauncher.openWeb}
          />
        </main>
      ) : null}

      {mode !== 'picker' ? (
        <LogsPanel
          showLogs={currentLogs.showLogs}
          logText={currentLogs.deferredLogText}
          onToggleLogs={() => currentLogs.setShowLogs((value: boolean) => !value)}
          onClearLogs={() => currentLogs.setLogText('')}
        />
      ) : null}

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
