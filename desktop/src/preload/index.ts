import { contextBridge, ipcRenderer } from 'electron'

import type {
  AddRemoteInput,
  CommandLogEvent,
  ConnectRemoteInput,
  DesktopApi,
  DisconnectRemoteInput,
  InstallCliInput,
  LocalStartInput,
  LocalStopInput,
  WindowMode,
} from '@shared/types'

const api: DesktopApi = {
  preflight: () => ipcRenderer.invoke('desktop:preflight'),
  installCli: (input: InstallCliInput) => ipcRenderer.invoke('desktop:install-cli', input),
  getLocalStatus: () => ipcRenderer.invoke('desktop:get-local-status'),
  startLocal: (input: LocalStartInput) => ipcRenderer.invoke('desktop:start-local', input),
  stopLocal: (input: LocalStopInput) => ipcRenderer.invoke('desktop:stop-local', input),
  listRemotes: () => ipcRenderer.invoke('desktop:list-remotes'),
  addRemote: (input: AddRemoteInput) => ipcRenderer.invoke('desktop:add-remote', input),
  removeRemote: (name: string) => ipcRenderer.invoke('desktop:remove-remote', name),
  getStatus: (name: string) => ipcRenderer.invoke('desktop:get-status', name),
  connectRemote: (input: ConnectRemoteInput) => ipcRenderer.invoke('desktop:connect-remote', input),
  disconnectRemote: (input: DisconnectRemoteInput) => ipcRenderer.invoke('desktop:disconnect-remote', input),
  openWeb: (url: string) => ipcRenderer.invoke('desktop:open-web', url),
  setWindowMode: (mode: WindowMode) => ipcRenderer.invoke('desktop:set-window-mode', mode),
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
