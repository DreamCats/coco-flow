import { contextBridge, ipcRenderer } from 'electron'

import type {
  AddRemoteInput,
  CommandLogEvent,
  ConnectRemoteInput,
  DesktopApi,
  DisconnectRemoteInput,
} from '@shared/types'

const api: DesktopApi = {
  preflight: () => ipcRenderer.invoke('desktop:preflight'),
  listRemotes: () => ipcRenderer.invoke('desktop:list-remotes'),
  addRemote: (input: AddRemoteInput) => ipcRenderer.invoke('desktop:add-remote', input),
  removeRemote: (name: string) => ipcRenderer.invoke('desktop:remove-remote', name),
  getStatus: (name: string) => ipcRenderer.invoke('desktop:get-status', name),
  connectRemote: (input: ConnectRemoteInput) => ipcRenderer.invoke('desktop:connect-remote', input),
  disconnectRemote: (input: DisconnectRemoteInput) => ipcRenderer.invoke('desktop:disconnect-remote', input),
  openWeb: (url: string) => ipcRenderer.invoke('desktop:open-web', url),
  onCommandLog: (listener: (event: CommandLogEvent) => void) => {
    const wrapped = (_event: Electron.IpcRendererEvent, payload: CommandLogEvent) => {
      listener(payload)
    }
    ipcRenderer.on('desktop:command-log', wrapped)
    return () => {
      ipcRenderer.removeListener('desktop:command-log', wrapped)
    }
  },
}

contextBridge.exposeInMainWorld('cocoFlowDesktop', api)
