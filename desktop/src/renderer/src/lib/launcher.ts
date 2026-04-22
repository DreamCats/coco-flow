import type { RemoteConnection } from '@shared/types'

export type FormState = {
  name: string
  host: string
  user: string
  localPort: string
  remotePort: string
}

export type ConnectionTone = 'idle' | 'healthy' | 'warning'
export type LauncherMode = 'picker' | 'local' | 'remote'

export const DEFAULT_FORM: FormState = {
  name: '',
  host: '',
  user: '',
  localPort: '4318',
  remotePort: '4318',
}

export const LAST_SELECTED_REMOTE_KEY = 'coco-flow.desktop.last-selected-remote'

export function newRequestId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function formatBoolLabel(value: boolean | null | undefined, yes: string, no: string, unknown = 'Unknown'): string {
  if (value === true) {
    return yes
  }
  if (value === false) {
    return no
  }
  return unknown
}

export function connectionTone(connection: RemoteConnection | null): ConnectionTone {
  if (!connection) {
    return 'idle'
  }
  if (connection.local_healthy && connection.tunnel_alive) {
    return 'healthy'
  }
  return 'warning'
}

export function connectionLabel(connection: RemoteConnection | null): string {
  if (!connection) {
    return 'Not connected'
  }
  if (connection.local_healthy && connection.tunnel_alive) {
    return 'Connected'
  }
  return 'Needs attention'
}
