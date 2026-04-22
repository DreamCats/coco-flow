import { randomUUID } from 'node:crypto'
import { spawn } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { app, BrowserWindow, ipcMain, shell } from 'electron'

import type {
  AddRemoteInput,
  AddRemoteResult,
  ConnectRemoteInput,
  ConnectRemoteResult,
  DisconnectRemoteInput,
  DisconnectRemoteResult,
  PreflightStatus,
  RemoteListResponse,
  RemoteStatusResponse,
} from '@shared/types'

const __dirname = dirname(fileURLToPath(import.meta.url))
const ELECTRON_RENDERER_URL = process.env.ELECTRON_RENDERER_URL
const PRELOAD_PATH = join(__dirname, '../preload/index.mjs')
const RENDERER_HTML = join(__dirname, '../renderer/index.html')
const IS_DEV = Boolean(ELECTRON_RENDERER_URL)

let mainWindow: BrowserWindow | null = null
let cachedBinaryPath: string | null = null

type ShellResult = {
  stdout: string
  stderr: string
  code: number | null
}

function createWindow(): void {
  const window = new BrowserWindow({
    width: 1380,
    height: 920,
    minWidth: 1120,
    minHeight: 760,
    show: false,
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#f5f4ed',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
      preload: PRELOAD_PATH,
    },
  })

  mainWindow = window
  window.once('ready-to-show', () => {
    window.show()
  })
  window.webContents.on('did-finish-load', () => {
    console.log(`[desktop] did-finish-load: ${window.webContents.getURL()}`)
  })
  window.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    console.error(`[desktop] did-fail-load: code=${errorCode} url=${validatedURL} error=${errorDescription}`)
  })
  window.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    console.log(`[desktop][console:${level}] ${message} (${sourceId}:${line})`)
  })
  window.webContents.on('render-process-gone', (_event, details) => {
    console.error(`[desktop] render-process-gone: reason=${details.reason} exitCode=${details.exitCode}`)
  })
  window.webContents.on('preload-error', (_event, preloadPath, error) => {
    console.error(`[desktop] preload-error: path=${preloadPath} error=${error.message}`)
  })

  if (ELECTRON_RENDERER_URL) {
    void window.loadURL(ELECTRON_RENDERER_URL)
    window.webContents.openDevTools({ mode: 'detach' })
    return
  }
  void window.loadFile(RENDERER_HTML)
  if (IS_DEV) {
    window.webContents.openDevTools({ mode: 'detach' })
  }
}

function currentShell(): string {
  if (process.platform === 'darwin') {
    return '/bin/zsh'
  }
  return process.env.SHELL || '/bin/sh'
}

function shellArguments(command: string): string[] {
  if (process.platform === 'darwin') {
    return ['-lc', command]
  }
  return ['-lc', command]
}

function runLoginShell(command: string): Promise<ShellResult> {
  return new Promise((resolve, reject) => {
    const child = spawn(currentShell(), shellArguments(command), {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: process.env,
    })
    let stdout = ''
    let stderr = ''

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.on('error', reject)
    child.on('close', (code) => {
      resolve({ stdout, stderr, code })
    })
  })
}

async function ensureBinaryPath(): Promise<string> {
  if (cachedBinaryPath) {
    return cachedBinaryPath
  }
  const result = await runLoginShell('command -v coco-flow')
  const candidate = result.stdout.trim().split('\n').find(Boolean)?.trim() || ''
  if (!candidate) {
    throw new Error(result.stderr.trim() || 'coco-flow not found in PATH')
  }
  cachedBinaryPath = candidate
  return candidate
}

function emitCommandLog(requestId: string, message: string): void {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return
  }
  mainWindow.webContents.send('desktop:command-log', { requestId, message })
}

async function runJsonCommand<T>(args: string[]): Promise<T> {
  const binaryPath = await ensureBinaryPath()
  return new Promise((resolve, reject) => {
    const child = spawn(binaryPath, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: process.env,
    })
    let stdout = ''
    let stderr = ''

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || stdout.trim() || `coco-flow exited with code ${code ?? 'unknown'}`))
        return
      }
      try {
        resolve(JSON.parse(stdout) as T)
      } catch (error) {
        reject(new Error(`failed to parse coco-flow JSON output: ${error instanceof Error ? error.message : String(error)}`))
      }
    })
  })
}

async function runStreamingJsonCommand<T>(requestId: string, args: string[]): Promise<T> {
  const binaryPath = await ensureBinaryPath()
  emitCommandLog(requestId, `$ ${['coco-flow', ...args].join(' ')}\n`)
  return new Promise((resolve, reject) => {
    const child = spawn(binaryPath, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: process.env,
    })
    let stdout = ''
    let stderr = ''

    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.on('data', (chunk) => {
      const message = chunk.toString()
      stderr += message
      emitCommandLog(requestId, message)
    })
    child.on('error', reject)
    child.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || stdout.trim() || `coco-flow exited with code ${code ?? 'unknown'}`))
        return
      }
      try {
        resolve(JSON.parse(stdout) as T)
      } catch (error) {
        reject(new Error(`failed to parse coco-flow JSON output: ${error instanceof Error ? error.message : String(error)}`))
      }
    })
  })
}

async function preflight(): Promise<PreflightStatus> {
  try {
    const binaryPath = await ensureBinaryPath()
    const versionResult = await runJsonCommand<{ version?: string }>(['version', '--json'])
    return {
      ok: true,
      binaryPath,
      version: versionResult.version,
    }
  } catch (error) {
    cachedBinaryPath = null
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

function registerIpcHandlers(): void {
  ipcMain.handle('desktop:preflight', () => preflight())
  ipcMain.handle('desktop:list-remotes', () => runJsonCommand<RemoteListResponse>(['remote', 'list', '--json']))
  ipcMain.handle('desktop:add-remote', (_event, input: AddRemoteInput) =>
    runJsonCommand<AddRemoteResult>([
      'remote',
      'add',
      input.name,
      '--host',
      input.host,
      '--user',
      input.user,
      '--local-port',
      String(input.localPort),
      '--remote-port',
      String(input.remotePort),
      '--json',
    ]),
  )
  ipcMain.handle('desktop:remove-remote', (_event, name: string) =>
    runJsonCommand<{ removed: string }>(['remote', 'remove', name, '--json']),
  )
  ipcMain.handle('desktop:get-status', (_event, name: string) =>
    runJsonCommand<RemoteStatusResponse>(['remote', 'status', name, '--json']),
  )
  ipcMain.handle('desktop:connect-remote', async (_event, input: ConnectRemoteInput) => {
    const requestId = input.requestId || randomUUID()
    const result = await runStreamingJsonCommand<ConnectRemoteResult>(requestId, [
      'remote',
      'connect',
      input.name,
      '--json',
      '--no-open',
      ...(input.restart ? ['--restart'] : []),
    ])
    if (input.openBrowser !== false) {
      await shell.openExternal(result.local_url)
      emitCommandLog(requestId, `open_browser: ${result.local_url}\n`)
    }
    return result
  })
  ipcMain.handle('desktop:disconnect-remote', (_event, input: DisconnectRemoteInput) =>
    runStreamingJsonCommand<DisconnectRemoteResult>(input.requestId || randomUUID(), [
      'remote',
      'disconnect',
      input.name,
      '--json',
    ]),
  )
  ipcMain.handle('desktop:open-web', async (_event, url: string) => {
    await shell.openExternal(url)
  })
}

app.whenReady().then(() => {
  registerIpcHandlers()
  createWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
