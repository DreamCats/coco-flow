import { startTransition, useDeferredValue, useEffect, useEffectEvent, useState } from 'react'

import type { CommandLogEvent, LocalStatusResponse } from '@shared/types'

import { newRequestId } from '../lib/launcher'

export function useLocalLauncherState(preflightOk: boolean) {
  const desktopApi = globalThis.window?.cocoFlowDesktop
  const [localStatus, setLocalStatus] = useState<LocalStatusResponse | null>(null)
  const [logText, setLogText] = useState('launcher ready.\n')
  const [busyAction, setBusyAction] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [showLogs, setShowLogs] = useState(false)
  const [activeRequestId, setActiveRequestId] = useState('')
  const [statusKey, setStatusKey] = useState(0)

  const deferredLogText = useDeferredValue(logText)

  const appendLog = (message: string) => {
    startTransition(() => {
      setLogText((current) => `${current}${message}`)
    })
  }

  const refreshStatus = async () => {
    if (!desktopApi) {
      throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
    }
    const result = await desktopApi.getLocalStatus()
    startTransition(() => {
      setLocalStatus(result)
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
    if (!preflightOk) {
      return
    }
    const loadStatus = async () => {
      try {
        await refreshStatus()
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
  }, [preflightOk, statusKey])

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

  const handleStart = async () => {
    await runAction('Starting local coco-flow...', async (requestId) => {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      const result = await desktopApi.startLocal({ requestId, openBrowser: true })
      setLocalStatus(result)
    })
  }

  const handleStop = async () => {
    await runAction('Stopping local coco-flow...', async (requestId) => {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      await desktopApi.stopLocal({ requestId })
      await refreshStatus()
    })
  }

  const handleRefreshStatus = async () => {
    setBusyAction('Refreshing local status...')
    setErrorMessage('')
    try {
      await refreshStatus()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error))
    } finally {
      setBusyAction('')
    }
  }

  const openWeb = async () => {
    const url = localStatus?.url || 'http://127.0.0.1:4318'
    try {
      if (!desktopApi) {
        throw new Error('Desktop preload API is unavailable. Check the Electron preload configuration.')
      }
      await desktopApi.openWeb(url)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error))
    }
  }

  return {
    localStatus,
    busyAction,
    errorMessage,
    showLogs,
    deferredLogText,
    setShowLogs,
    setLogText,
    handleStart,
    handleStop,
    handleRefreshStatus,
    openWeb,
  }
}
