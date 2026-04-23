import { INSTALL_COMMAND, START_COMMAND } from "../lib/constants.js";
import { gatewayFetch } from "../lib/gateway-client.js";
import { loadPopupPrefs, saveCachedRemoteStatus, saveCachedRemotes, savePopupMode, saveSelectedRemoteName } from "../lib/storage.js";
import {
  autoHideOperationPanel,
  cancelOperationAutohide,
  clearNotice,
  hideOperationPanel,
  renderLocal,
  renderOperation,
  renderRemote,
  renderRemoteSelect,
  setBusy,
  setGatewayState,
  setMode,
  showGatewayMissing,
  showGatewayReady,
  showNotice,
  showOperationPanel,
} from "./render.js";

export function createPopupActions(state, elements) {
  return {
    async boot() {
      const stored = await loadPopupPrefs()
      state.mode = stored.popupMode
      state.selectedRemoteName = stored.selectedRemoteName
      state.remotes = stored.cachedRemotes
      state.cachedRemoteStatuses = stored.cachedRemoteStatuses
      if (!state.selectedRemoteName && state.remotes.length > 0) {
        state.selectedRemoteName = state.remotes[0].name
      }
      if (state.selectedRemoteName && state.cachedRemoteStatuses[state.selectedRemoteName]) {
        state.selectedRemoteStatus = state.cachedRemoteStatuses[state.selectedRemoteName]
        state.selectedRemoteStatusStale = true
      }
      await this.refreshGateway()
    },

    async refreshGateway() {
      setBusy(elements, state, true)
      clearNotice(elements)
      setGatewayState(elements, "checking", "Checking...")
      cancelOperationAutohide(elements)
      hideOperationPanel(elements)
      state.localLoading = true
      state.remotesLoading = true
      state.remoteStatusLoading = false
      state.localStatus = null
      if (!state.selectedRemoteStatus && state.selectedRemoteName && state.cachedRemoteStatuses[state.selectedRemoteName]) {
        state.selectedRemoteStatus = state.cachedRemoteStatuses[state.selectedRemoteName]
        state.selectedRemoteStatusStale = true
      }
      try {
        await gatewayFetch("/healthz")
        state.gatewayReady = true
        setGatewayState(elements, "ready", "Gateway Ready")
        showGatewayReady(elements)
        renderLocal(elements, state)
        renderRemoteSelect(elements, state)
        renderRemote(elements, state)
        this.setMode(state.mode)
        await Promise.all([this.loadLocalStatus(), this.loadRemoteList()])
      } catch (_error) {
        state.gatewayReady = false
        setGatewayState(elements, "missing", "Gateway Missing")
        showGatewayMissing(elements)
        showNotice(elements, "Gateway 没响应。先在终端执行 `coco-flow gateway start -d`。", "warning")
      } finally {
        setBusy(elements, state, false)
      }
    },

    async loadLocalStatus() {
      state.localLoading = true
      renderLocal(elements, state)
      try {
        state.localStatus = await gatewayFetch("/local/status")
        renderLocal(elements, state)
      } catch (error) {
        showNotice(elements, error.message, "error")
      } finally {
        state.localLoading = false
        renderLocal(elements, state)
      }
    },

    async loadRemoteList() {
      state.remotesLoading = true
      renderRemoteSelect(elements, state)
      renderRemote(elements, state)
      try {
        const payload = await gatewayFetch("/remote/list")
        state.remotes = Array.isArray(payload.remotes) ? payload.remotes : []
        await saveCachedRemotes(state.remotes)
        if (!state.selectedRemoteName && state.remotes.length > 0) {
          state.selectedRemoteName = state.remotes[0].name
        }
        if (state.selectedRemoteName && !state.remotes.find((remote) => remote.name === state.selectedRemoteName)) {
          state.selectedRemoteName = state.remotes[0]?.name || ""
        }
        if (state.selectedRemoteName && state.cachedRemoteStatuses[state.selectedRemoteName]) {
          state.selectedRemoteStatus = state.cachedRemoteStatuses[state.selectedRemoteName]
          state.selectedRemoteStatusStale = true
        }
        state.remotesLoading = false
        renderRemoteSelect(elements, state)
        renderRemote(elements, state)
        await saveSelectedRemoteName(state.selectedRemoteName)
        await this.loadRemoteStatus()
      } catch (error) {
        state.remotesLoading = false
        renderRemoteSelect(elements, state)
        renderRemote(elements, state)
        showNotice(elements, error.message, "error")
      }
    },

    async loadRemoteStatus() {
      if (!state.selectedRemoteName) {
        state.selectedRemoteStatus = null
        state.selectedRemoteStatusStale = false
        state.remoteStatusLoading = false
        renderRemote(elements, state)
        return
      }
      state.remoteStatusLoading = true
      if (state.cachedRemoteStatuses[state.selectedRemoteName]) {
        state.selectedRemoteStatus = state.cachedRemoteStatuses[state.selectedRemoteName]
        state.selectedRemoteStatusStale = true
      } else {
        state.selectedRemoteStatus = null
        state.selectedRemoteStatusStale = false
      }
      renderRemote(elements, state)
      try {
        state.selectedRemoteStatus = await gatewayFetch(`/remote/${encodeURIComponent(state.selectedRemoteName)}/status`)
        state.cachedRemoteStatuses[state.selectedRemoteName] = state.selectedRemoteStatus
        state.selectedRemoteStatusStale = false
        await saveCachedRemoteStatus(state.selectedRemoteName, state.selectedRemoteStatus)
        renderRemote(elements, state)
      } catch (error) {
        if (state.selectedRemoteStatusStale) {
          showNotice(elements, "Remote 刷新变慢，先展示上一次成功状态。", "warning")
        } else {
          showNotice(elements, error.message, "error")
        }
      } finally {
        state.remoteStatusLoading = false
        renderRemote(elements, state)
      }
    },

    setMode(mode) {
      setMode(elements, state, mode)
      void savePopupMode(state.mode)
    },

    async onRemoteSelected(name) {
      state.selectedRemoteName = name
      await saveSelectedRemoteName(state.selectedRemoteName)
      await this.loadRemoteStatus()
    },

    async triggerOperation(path, options) {
      try {
        setBusy(elements, state, true)
        clearNotice(elements)
        const payload = await gatewayFetch(path, options)
        if (!payload.operation_id) {
          throw new Error("missing operation_id")
        }
        state.activeOperationId = payload.operation_id
        state.activeOperationKind = inferOperationKind(path)
        renderLocal(elements, state)
        renderRemote(elements, state)
        cancelOperationAutohide(elements)
        showOperationPanel(elements)
        await this.pollOperation(payload.operation_id)
      } catch (error) {
        renderOperation(elements, {
          kind: "request.failed",
          state: "failed",
          message: error.message,
          steps: [],
        })
        showNotice(elements, error.message, "error")
      } finally {
        state.activeOperationId = ""
        state.activeOperationKind = ""
        renderLocal(elements, state)
        renderRemote(elements, state)
        setBusy(elements, state, false)
      }
    },

    async pollOperation(operationId) {
      for (;;) {
        const operation = await gatewayFetch(`/operations/${encodeURIComponent(operationId)}`)
        renderOperation(elements, operation)
        if (operation.state === "succeeded") {
          await Promise.all([this.loadLocalStatus(), this.loadRemoteList()])
          const result = operation.result || {}
          showNotice(elements, operation.message || "Done", "success")
          if (
            operation.kind === "local.start" ||
            operation.kind === "local.stop" ||
            operation.kind === "remote.connect" ||
            operation.kind === "remote.disconnect"
          ) {
            autoHideOperationPanel(elements)
          }
          if ((operation.kind === "local.start" && result.url) || (operation.kind === "remote.connect" && result.local_url)) {
            void this.openUrl(result.local_url || result.url)
          }
          return
        }
        if (operation.state === "failed") {
          showNotice(elements, operation.error || operation.message || "Operation failed", "error")
          return
        }
        await delay(700)
      }
    },

    async copyInstallCommand() {
      await navigator.clipboard.writeText(INSTALL_COMMAND)
      showNotice(elements, "Command copied.", "success")
    },

    async copyStartCommand() {
      await navigator.clipboard.writeText(START_COMMAND)
      showNotice(elements, "Command copied.", "success")
    },

    openUrl(url) {
      if (!url) {
        return Promise.resolve()
      }
      return chrome.tabs.create({ url })
    },
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function inferOperationKind(path) {
  if (path === "/local/start") return "local.start"
  if (path === "/local/stop") return "local.stop"
  if (path.includes("/connect")) return "remote.connect"
  if (path.includes("/disconnect")) return "remote.disconnect"
  return ""
}
