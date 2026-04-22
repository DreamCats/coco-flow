import { startTransition, useDeferredValue, useEffect, useEffectEvent, useMemo, useState, type FormEvent } from 'react'

import type { AddRemoteInput, CommandLogEvent, ConnectRemoteResult, PreflightStatus, RemoteConnection, RemoteProfile } from '@shared/types'

import {
  DEFAULT_FORM,
  LAST_SELECTED_REMOTE_KEY,
  connectionLabel,
  connectionTone,
  newRequestId,
  type FormState,
} from '../lib/launcher'

export function useLauncherState() {
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
  const canAddRemote = Boolean(preflight?.ok) && !busyAction

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
