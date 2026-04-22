export type BuildMeta = {
  version?: string
  fingerprint?: string
  [key: string]: unknown
}

export type PreflightStatus = {
  ok: boolean
  binaryPath?: string
  version?: string
  error?: string
}

export type RemoteProfile = {
  name: string
  host: string
  user?: string
  local_port: number
  remote_port: number
  created_at?: string
  updated_at?: string
}

export type RemoteConnection = {
  target: string
  host: string
  ssh_target: string
  local_port: number
  remote_port: number
  local_url: string
  local_healthy: boolean
  tunnel_pid: number
  tunnel_alive: boolean
  remote_healthy?: boolean
  remote_build?: BuildMeta | null
  fingerprint_match?: boolean | null
  created_at?: string
  updated_at?: string
}

export type RemoteListResponse = {
  remotes: RemoteProfile[]
  config_path: string
}

export type RemoteStatusResponse = {
  connections: RemoteConnection[]
  config_path: string
  local_build?: BuildMeta | null
  remotes: RemoteProfile[]
}

export type AddRemoteInput = {
  name: string
  host: string
  user: string
  localPort: number
  remotePort: number
}

export type AddRemoteResult = {
  name: string
  host: string
  user: string
  local_port: number
  remote_port: number
  updated: boolean
}

export type ConnectRemoteInput = {
  requestId: string
  name: string
  restart?: boolean
  openBrowser?: boolean
}

export type ConnectRemoteResult = {
  target: string
  host: string
  ssh_target: string
  local_url: string
  local_build?: BuildMeta | null
  remote_build?: BuildMeta | null
  fingerprint_match?: boolean | null
  remote_started: boolean
  tunnel_started: boolean
  reused_local: boolean
  reused_remote: boolean
}

export type DisconnectRemoteInput = {
  requestId: string
  name: string
}

export type DisconnectRemoteResult = {
  disconnected: number
  targets: string[]
}

export type LocalStatusResponse = {
  running: boolean
  pid?: number | null
  pid_file: string
  log_file: string
  url: string
  healthy: boolean
}

export type LocalStartInput = {
  requestId: string
  openBrowser?: boolean
}

export type LocalStopInput = {
  requestId: string
}

export type LocalStopResult = {
  stopped: boolean
  message: string
  url: string
}

export type CommandLogEvent = {
  requestId: string
  message: string
}

export type DesktopApi = {
  preflight: () => Promise<PreflightStatus>
  getLocalStatus: () => Promise<LocalStatusResponse>
  startLocal: (input: LocalStartInput) => Promise<LocalStatusResponse>
  stopLocal: (input: LocalStopInput) => Promise<LocalStopResult>
  listRemotes: () => Promise<RemoteListResponse>
  addRemote: (input: AddRemoteInput) => Promise<AddRemoteResult>
  removeRemote: (name: string) => Promise<{ removed: string }>
  getStatus: (name: string) => Promise<RemoteStatusResponse>
  connectRemote: (input: ConnectRemoteInput) => Promise<ConnectRemoteResult>
  disconnectRemote: (input: DisconnectRemoteInput) => Promise<DisconnectRemoteResult>
  openWeb: (url: string) => Promise<void>
  onCommandLog: (listener: (event: CommandLogEvent) => void) => () => void
}
