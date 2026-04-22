import { useCallback, useEffect, useMemo, useState } from 'react'

import type { RemoteProfile } from '@shared/types'

import { LAST_SELECTED_REMOTE_KEY } from '../lib/launcher'

export function useRemoteSelection(remotes: RemoteProfile[]) {
  const [selectedRemoteName, setSelectedRemoteName] = useState('')

  const selectedRemote = useMemo(
    () => remotes.find((item) => item.name === selectedRemoteName) ?? null,
    [remotes, selectedRemoteName],
  )

  const selectPreferredRemote = useCallback(
    (nextSelectedName: string | undefined, nextRemotes: RemoteProfile[]) => {
      const rememberedSelection = globalThis.window?.localStorage.getItem(LAST_SELECTED_REMOTE_KEY) || ''
      const preferredSelection =
        nextSelectedName && nextRemotes.some((item) => item.name === nextSelectedName)
          ? nextSelectedName
          : rememberedSelection && nextRemotes.some((item) => item.name === rememberedSelection)
            ? rememberedSelection
            : selectedRemoteName && nextRemotes.some((item) => item.name === selectedRemoteName)
              ? selectedRemoteName
              : nextRemotes[0]?.name || ''
      setSelectedRemoteName(preferredSelection)
    },
    [selectedRemoteName],
  )

  useEffect(() => {
    if (!selectedRemoteName) {
      globalThis.window?.localStorage.removeItem(LAST_SELECTED_REMOTE_KEY)
      return
    }
    globalThis.window?.localStorage.setItem(LAST_SELECTED_REMOTE_KEY, selectedRemoteName)
  }, [selectedRemoteName])

  return {
    selectedRemoteName,
    selectedRemote,
    setSelectedRemoteName,
    selectPreferredRemote,
  }
}
