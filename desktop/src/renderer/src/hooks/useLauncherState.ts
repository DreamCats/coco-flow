import { startTransition, useDeferredValue, useEffect, useEffectEvent, useState } from 'react'

import type { CommandLogEvent, PreflightStatus, RemoteConnection, RemoteProfile } from '@shared/types'

import { DEFAULT_FORM, connectionLabel, connectionTone, type FormState } from '../lib/launcher'
import { useRemoteActions } from './useRemoteActions'
import { useRemoteSelection } from './useRemoteSelection'

export function useLauncherState() {
  const desktopApi = globalThis.window?.cocoFlowDesktop
  const [preflight, setPreflight] = useState<PreflightStatus>({
    state: 'checking',
    ok: false,
  })
  const [remotes, setRemotes] = useState<RemoteProfile[]>([])
  const [selectedConnection, setSelectedConnection] = useState<RemoteConnection | null>(null)
  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [logText, setLogText] = useState('launcher ready.\n')
  const [isBootstrapping, setIsBootstrapping] = useState(true)
  const [activeRequestId, setActiveRequestId] = useState('')
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const [showLogs, setShowLogs] = useState(false)
  const { selectedRemoteName, selectedRemote, setSelectedRemoteName, selectPreferredRemote } = useRemoteSelection(remotes)

  const deferredLogText = useDeferredValue(logText)
  const appendLog = (message: string) => {
    startTransition(() => {
      setLogText((current) => `${current}${message}`)
    })
  }

  const refreshRemotes = async (nextSelectedName?: string) => {
    if (!desktopApi) {
      throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
    }
    const result = await desktopApi.listRemotes()
    startTransition(() => {
      setRemotes(result.remotes)
    })
    selectPreferredRemote(nextSelectedName, result.remotes)
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

  const {
    busyAction,
    errorMessage,
    openWebUrl,
    statusKey,
    setErrorMessage,
    handleAddRemote,
    handleConnect,
    handleDisconnect,
    handleDeleteRemote,
    handleRefreshStatus,
    openWeb,
  } = useRemoteActions({
    desktopApi,
    preflightOk: Boolean(preflight?.ok),
    selectedRemoteName,
    form,
    selectedConnectionUrl: selectedConnection?.local_url || '',
    refreshRemotes,
    refreshStatus,
    appendLog,
    setForm,
    setIsAddModalOpen,
    setActiveRequestId,
    setLogText,
  })
  const statusTone = connectionTone(selectedConnection)
  const statusLabel = connectionLabel(selectedConnection)
  const canAddRemote = Boolean(preflight?.ok) && !busyAction

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
        setPreflight({
          state: 'missing',
          ok: false,
          error: 'Desktop preload API is unavailable. Restart the Electron app after the preload fix is applied.',
        })
        setErrorMessage('Desktop preload API is unavailable. Restart the Electron app after the preload fix is applied.')
        setIsBootstrapping(false)
        return
      }
      const startTime = Date.now()
      const nextPreflight = await desktopApi.preflight()
      const elapsed = Date.now() - startTime
      if (elapsed < 280) {
        await new Promise((resolve) => globalThis.window.setTimeout(resolve, 280 - elapsed))
      }
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

  return {
    preflight,
    remotes,
    selectedRemoteName,
    selectedRemote,
    selectedConnection,
    form,
    busyAction,
    errorMessage,
    isBootstrapping,
    isAddModalOpen,
    showLogs,
    deferredLogText,
    openWebUrl,
    statusTone,
    statusLabel,
    canAddRemote,
    setSelectedRemoteName,
    setForm,
    setIsAddModalOpen,
    setShowLogs,
    setLogText,
    handleAddRemote,
    handleConnect,
    handleDisconnect,
    handleDeleteRemote,
    handleRefreshStatus,
    openWeb,
  }
}
