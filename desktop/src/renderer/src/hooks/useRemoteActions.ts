import { useState, type FormEvent } from 'react'

import type { AddRemoteInput, ConnectRemoteResult, DesktopApi } from '@shared/types'

import { DEFAULT_FORM, newRequestId, type FormState } from '../lib/launcher'

type UseRemoteActionsParams = {
  desktopApi: DesktopApi | undefined
  preflightOk: boolean
  selectedRemoteName: string
  form: FormState
  selectedConnectionUrl: string
  refreshRemotes: (nextSelectedName?: string) => Promise<void>
  refreshStatus: (name: string) => Promise<void>
  appendLog: (message: string) => void
  setForm: (value: FormState) => void
  setIsAddModalOpen: (value: boolean) => void
  setActiveRequestId: (value: string) => void
  setLogText: (value: string) => void
}

export function useRemoteActions({
  desktopApi,
  preflightOk,
  selectedRemoteName,
  form,
  selectedConnectionUrl,
  refreshRemotes,
  refreshStatus,
  appendLog,
  setForm,
  setIsAddModalOpen,
  setActiveRequestId,
  setLogText,
}: UseRemoteActionsParams) {
  const [busyAction, setBusyAction] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [lastOpenedUrl, setLastOpenedUrl] = useState('')
  const [statusKey, setStatusKey] = useState(0)
  const openWebUrl = lastOpenedUrl || selectedConnectionUrl

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
    if (!preflightOk) {
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
  }
}
