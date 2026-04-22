const GATEWAY_ORIGIN = "http://127.0.0.1:4319";
const INSTALL_COMMAND = "curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash";
const START_COMMAND = "coco-flow gateway start -d";
const CLIENT_HEADERS = {
  "Content-Type": "application/json",
  "X-Coco-Flow-Client": "chrome-extension",
};

const state = {
  mode: "local",
  gatewayReady: false,
  localStatus: null,
  remotes: [],
  selectedRemoteName: "",
  selectedRemoteStatus: null,
  activeOperationId: "",
  busy: false,
};

const elements = {
  gatewayBadge: document.getElementById("gateway-badge"),
  notice: document.getElementById("notice"),
  gatewayMissing: document.getElementById("gateway-missing"),
  retryGateway: document.getElementById("retry-gateway"),
  copyInstall: document.getElementById("copy-install"),
  copyStart: document.getElementById("copy-start"),
  appShell: document.getElementById("app-shell"),
  localPanel: document.getElementById("local-panel"),
  remotePanel: document.getElementById("remote-panel"),
  operationPanel: document.getElementById("operation-panel"),
  operationTitle: document.getElementById("operation-title"),
  operationMessage: document.getElementById("operation-message"),
  operationSteps: document.getElementById("operation-steps"),
  segmented: Array.from(document.querySelectorAll("[data-mode]")),
  localRunning: document.getElementById("local-running"),
  localHealth: document.getElementById("local-health"),
  localUrl: document.getElementById("local-url"),
  localPid: document.getElementById("local-pid"),
  localStart: document.getElementById("local-start"),
  localStop: document.getElementById("local-stop"),
  localOpen: document.getElementById("local-open"),
  localRefresh: document.getElementById("local-refresh"),
  remoteSelect: document.getElementById("remote-select"),
  remoteHost: document.getElementById("remote-host"),
  remoteSsh: document.getElementById("remote-ssh"),
  remoteUrl: document.getElementById("remote-url"),
  remoteHealth: document.getElementById("remote-health"),
  remoteConnectedChip: document.getElementById("remote-connected-chip"),
  remoteTunnelChip: document.getElementById("remote-tunnel-chip"),
  remoteFingerprintChip: document.getElementById("remote-fingerprint-chip"),
  remoteConnect: document.getElementById("remote-connect"),
  remoteDisconnect: document.getElementById("remote-disconnect"),
  remoteOpen: document.getElementById("remote-open"),
  remoteRefresh: document.getElementById("remote-refresh"),
  remoteEmptyCopy: document.getElementById("remote-empty-copy"),
  openOptions: document.getElementById("open-options"),
};

async function boot() {
  const stored = await chrome.storage.local.get(["popupMode", "selectedRemoteName"]);
  state.mode = stored.popupMode || "local";
  state.selectedRemoteName = stored.selectedRemoteName || "";
  bindEvents();
  await refreshGateway();
}

function bindEvents() {
  elements.retryGateway.addEventListener("click", () => {
    void refreshGateway();
  });
  elements.copyInstall.addEventListener("click", () => {
    void copyCommand(INSTALL_COMMAND);
  });
  elements.copyStart.addEventListener("click", () => {
    void copyCommand(START_COMMAND);
  });
  for (const button of elements.segmented) {
    button.addEventListener("click", () => {
      const nextMode = button.dataset.mode || "local";
      setMode(nextMode);
    });
  }
  elements.localRefresh.addEventListener("click", () => {
    void loadLocalStatus();
  });
  elements.localStart.addEventListener("click", () => {
    void triggerOperation("/local/start", {
      method: "POST",
      body: JSON.stringify({ host: "127.0.0.1", port: 4318, build_web: true }),
    });
  });
  elements.localStop.addEventListener("click", () => {
    void triggerOperation("/local/stop", { method: "POST" });
  });
  elements.localOpen.addEventListener("click", () => {
    void openUrl(state.localStatus?.url);
  });
  elements.remoteSelect.addEventListener("change", () => {
    state.selectedRemoteName = elements.remoteSelect.value;
    void chrome.storage.local.set({ selectedRemoteName: state.selectedRemoteName });
    void loadRemoteStatus();
  });
  elements.remoteRefresh.addEventListener("click", () => {
    void loadRemoteStatus();
  });
  elements.remoteConnect.addEventListener("click", () => {
    if (!state.selectedRemoteName) {
      return;
    }
    void triggerOperation(`/remote/${encodeURIComponent(state.selectedRemoteName)}/connect`, {
      method: "POST",
      body: JSON.stringify({ restart: false, reconnect_tunnel: false, build_web: true }),
    });
  });
  elements.remoteDisconnect.addEventListener("click", () => {
    if (!state.selectedRemoteName) {
      return;
    }
    void triggerOperation(`/remote/${encodeURIComponent(state.selectedRemoteName)}/disconnect`, {
      method: "POST",
    });
  });
  elements.remoteOpen.addEventListener("click", () => {
    void openUrl(state.selectedRemoteStatus?.connections?.[0]?.local_url);
  });
  elements.openOptions.addEventListener("click", () => {
    void chrome.runtime.openOptionsPage();
  });
}

async function refreshGateway() {
  setBusy(true);
  clearNotice();
  setGatewayBadge("checking", "Checking...");
  hide(elements.operationPanel);
  try {
    await gatewayFetch("/healthz");
    state.gatewayReady = true;
    setGatewayBadge("ready", "Gateway Ready");
    hide(elements.gatewayMissing);
    show(elements.appShell);
    await Promise.all([loadLocalStatus(), loadRemoteList()]);
    setMode(state.mode);
  } catch (_error) {
    state.gatewayReady = false;
    setGatewayBadge("missing", "Gateway Missing");
    hide(elements.appShell);
    show(elements.gatewayMissing);
    showNotice("Gateway 没响应。先在终端执行 `coco-flow gateway start -d`。", "warning");
  } finally {
    setBusy(false);
  }
}

async function loadLocalStatus() {
  try {
    state.localStatus = await gatewayFetch("/local/status");
    renderLocal();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function loadRemoteList() {
  try {
    const payload = await gatewayFetch("/remote/list");
    state.remotes = Array.isArray(payload.remotes) ? payload.remotes : [];
    if (!state.selectedRemoteName && state.remotes.length > 0) {
      state.selectedRemoteName = state.remotes[0].name;
    }
    if (state.selectedRemoteName && !state.remotes.find((remote) => remote.name === state.selectedRemoteName)) {
      state.selectedRemoteName = state.remotes[0]?.name || "";
    }
    elements.remoteSelect.innerHTML = "";
    if (!state.remotes.length) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No remotes yet";
      elements.remoteSelect.append(option);
    } else {
      for (const remote of state.remotes) {
        const option = document.createElement("option");
        option.value = remote.name;
        option.textContent = `${remote.name} · ${remote.host}`;
        elements.remoteSelect.append(option);
      }
    }
    elements.remoteSelect.value = state.selectedRemoteName;
    await chrome.storage.local.set({ selectedRemoteName: state.selectedRemoteName });
    await loadRemoteStatus();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

async function loadRemoteStatus() {
  if (!state.selectedRemoteName) {
    state.selectedRemoteStatus = null;
    renderRemote();
    return;
  }
  try {
    state.selectedRemoteStatus = await gatewayFetch(`/remote/${encodeURIComponent(state.selectedRemoteName)}/status`);
    renderRemote();
  } catch (error) {
    showNotice(error.message, "error");
  }
}

function renderLocal() {
  const status = state.localStatus;
  elements.localRunning.textContent = status?.running ? "Running" : "Stopped";
  elements.localHealth.textContent = status?.healthy ? "Healthy" : "Unhealthy";
  elements.localUrl.textContent = status?.url || "-";
  elements.localPid.textContent = status?.pid ? String(status.pid) : "-";
}

function renderRemote() {
  const connection = state.selectedRemoteStatus?.connections?.[0] || null;
  const selected = state.remotes.find((remote) => remote.name === state.selectedRemoteName) || null;
  elements.remoteEmptyCopy.classList.toggle("hidden", Boolean(selected));
  elements.remoteHost.textContent = connection?.host || selected?.host || "-";
  elements.remoteSsh.textContent = connection?.ssh_target || (selected ? `${selected.user ? `${selected.user}@` : ""}${selected.host}` : "-");
  elements.remoteUrl.textContent = connection?.local_url || "-";
  elements.remoteHealth.textContent = connection?.local_healthy ? "Healthy" : "Unknown";
  paintChip(elements.remoteConnectedChip, connection?.local_healthy ? "Connected" : "Idle", connection?.local_healthy ? "ready" : "checking");
  paintChip(elements.remoteTunnelChip, connection?.tunnel_alive ? "Tunnel alive" : "Tunnel idle", connection?.tunnel_alive ? "ready" : "checking");
  const fingerprintState = connection?.fingerprint_match;
  paintChip(
    elements.remoteFingerprintChip,
    fingerprintState === true ? "Fingerprint ok" : fingerprintState === false ? "Fingerprint mismatch" : "Fingerprint unknown",
    fingerprintState === false ? "missing" : fingerprintState === true ? "ready" : "checking",
  );
}

function setMode(mode) {
  state.mode = mode === "remote" ? "remote" : "local";
  void chrome.storage.local.set({ popupMode: state.mode });
  for (const button of elements.segmented) {
    button.classList.toggle("segmented__item--active", button.dataset.mode === state.mode);
  }
  elements.localPanel.classList.toggle("hidden", state.mode !== "local");
  elements.remotePanel.classList.toggle("hidden", state.mode !== "remote");
}

async function triggerOperation(path, options) {
  try {
    setBusy(true);
    clearNotice();
    const payload = await gatewayFetch(path, options);
    if (!payload.operation_id) {
      throw new Error("missing operation_id");
    }
    state.activeOperationId = payload.operation_id;
    show(elements.operationPanel);
    await pollOperation(payload.operation_id);
  } catch (error) {
    renderOperation({
      kind: "request.failed",
      state: "failed",
      message: error.message,
      steps: [],
    });
    showNotice(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function pollOperation(operationId) {
  for (;;) {
    const operation = await gatewayFetch(`/operations/${encodeURIComponent(operationId)}`);
    renderOperation(operation);
    if (operation.state === "succeeded") {
      await Promise.all([loadLocalStatus(), loadRemoteList()]);
      const result = operation.result || {};
      showNotice(operation.message || "Done", "success");
      if ((operation.kind === "local.start" && result.url) || (operation.kind === "remote.connect" && result.local_url)) {
        void openUrl(result.local_url || result.url);
      }
      return;
    }
    if (operation.state === "failed") {
      showNotice(operation.error || operation.message || "Operation failed", "error");
      return;
    }
    await delay(700);
  }
}

function renderOperation(operation) {
  elements.operationTitle.textContent = humanizeKind(operation.kind || "operation");
  elements.operationMessage.textContent = operation.message || "Working…";
  elements.operationSteps.innerHTML = "";
  for (const step of operation.steps || []) {
    const item = document.createElement("div");
    item.className = "step";
    item.innerHTML = `
      <div class="step__head">
        <strong>${step.label}</strong>
        <span class="step__state">${step.state}</span>
      </div>
      ${step.message ? `<div class="step__message">${escapeHtml(step.message)}</div>` : ""}
    `;
    elements.operationSteps.append(item);
  }
}

async function gatewayFetch(path, options = {}) {
  const response = await fetch(`${GATEWAY_ORIGIN}${path}`, {
    ...options,
    headers: {
      ...CLIENT_HEADERS,
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(payload.detail || `request failed: ${response.status}`);
  }
  return payload;
}

function setGatewayBadge(stateName, label) {
  elements.gatewayBadge.textContent = label;
  elements.gatewayBadge.className = `status-badge status-badge--${stateName}`;
}

function paintChip(element, label, stateName) {
  element.textContent = label;
  element.className = `status-badge status-badge--${stateName}`;
}

async function copyCommand(command) {
  await navigator.clipboard.writeText(command);
  showNotice("Command copied.", "success");
}

function openUrl(url) {
  if (!url) {
    return Promise.resolve();
  }
  return chrome.tabs.create({ url });
}

function humanizeKind(kind) {
  if (kind === "local.start") return "Starting local coco-flow";
  if (kind === "local.stop") return "Stopping local coco-flow";
  if (kind === "remote.connect") return "Connecting remote";
  if (kind === "remote.disconnect") return "Disconnecting remote";
  return "Working";
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function show(element) {
  element.classList.remove("hidden");
}

function hide(element) {
  element.classList.add("hidden");
}

function showNotice(message, tone = "") {
  elements.notice.textContent = message;
  elements.notice.className = `notice${tone ? ` notice--${tone}` : ""}`;
}

function clearNotice() {
  elements.notice.textContent = "";
  elements.notice.className = "notice hidden";
}

function setBusy(busy) {
  state.busy = busy;
  document.body.classList.toggle("is-busy", busy);
  const hasRemote = Boolean(state.selectedRemoteName);
  elements.localStart.disabled = busy || !state.gatewayReady;
  elements.localStop.disabled = busy || !state.gatewayReady;
  elements.localOpen.disabled = busy || !state.localStatus?.url;
  elements.localRefresh.disabled = busy || !state.gatewayReady;
  elements.remoteSelect.disabled = busy || !state.remotes.length;
  elements.remoteConnect.disabled = busy || !hasRemote;
  elements.remoteDisconnect.disabled = busy || !hasRemote;
  elements.remoteOpen.disabled = busy || !state.selectedRemoteStatus?.connections?.[0]?.local_url;
  elements.remoteRefresh.disabled = busy || !hasRemote;
  elements.retryGateway.disabled = busy;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

void boot();
