import { clearNotice as clearNoticeEl, hide, show, setStatusBadge, showNotice as showNoticeEl, escapeHtml } from "../lib/dom.js";

export function renderLocal(elements, state) {
  const status = state.localStatus;
  const loading = state.localLoading && !status;
  elements.localRunning.textContent = loading ? "Checking..." : status?.running ? "Running" : "Stopped";
  elements.localHealth.textContent = loading ? "Checking..." : status?.healthy ? "Healthy" : "Unhealthy";
  elements.localUrl.textContent = loading ? "Checking..." : status?.url || "-";
  elements.localPid.textContent = loading ? "Checking..." : status?.pid ? String(status.pid) : "-";
  elements.localStart.textContent = state.activeOperationKind === "local.start" ? "Starting..." : "Start";
  elements.localStop.textContent = state.activeOperationKind === "local.stop" ? "Stopping..." : "Stop";
}

export function renderRemote(elements, state) {
  const connection = state.selectedRemoteStatus?.connections?.[0] || null;
  const selected = state.remotes.find((remote) => remote.name === state.selectedRemoteName) || null;
  const loadingStatus = state.remoteStatusLoading && Boolean(selected) && !connection;
  elements.remoteRefreshing.classList.toggle("hidden", !(state.remoteStatusLoading || state.remotesLoading));
  elements.remoteEmptyCopy.classList.toggle("hidden", Boolean(selected) || state.remotesLoading);
  if (state.remotesLoading && !selected) {
    elements.remoteEmptyCopy.classList.remove("hidden");
    elements.remoteEmptyCopy.textContent = "Loading saved remotes…";
  } else if (loadingStatus) {
    elements.remoteEmptyCopy.classList.remove("hidden");
    elements.remoteEmptyCopy.textContent = "Checking remote status… 网络慢时会稍后补齐。";
  } else {
    elements.remoteEmptyCopy.textContent = "No saved remotes yet. Add one from Manage remotes.";
  }
  elements.remoteHost.textContent = loadingStatus ? (selected?.host || "Checking...") : connection?.host || selected?.host || "-";
  elements.remoteSsh.textContent = loadingStatus
    ? (selected ? `${selected.user ? `${selected.user}@` : ""}${selected.host}` : "Checking...")
    : connection?.ssh_target || (selected ? `${selected.user ? `${selected.user}@` : ""}${selected.host}` : "-");
  elements.remoteUrl.textContent = loadingStatus ? "Checking..." : connection?.local_url || "-";
  elements.remoteHealth.textContent = loadingStatus ? "Checking..." : connection?.local_healthy ? "Healthy" : "Unknown";
  elements.remoteConnect.textContent = state.activeOperationKind === "remote.connect" ? "Connecting..." : "Connect";
  elements.remoteDisconnect.textContent = state.activeOperationKind === "remote.disconnect" ? "Disconnecting..." : "Disconnect";
  const sshTarget = connection?.ssh_target || (selected ? `${selected.user ? `${selected.user}@` : ""}${selected.host}` : "");
  elements.remoteAuthCopy.textContent = sshTarget
    ? `如果 Connect 失败并提示认证，先在终端执行 ssh ${sshTarget} 完成认证；若该主机依赖 Kerberos/GSSAPI，再先执行 kinit <邮箱前缀>@BYTEDANCE.COM。`
    : "如果 remote 依赖 SSH 密码或 Kerberos/GSSAPI，先在终端完成认证，再回来点击 Connect。";
  paintChip(
    elements.remoteConnectedChip,
    loadingStatus ? "Checking..." : connection?.local_healthy ? "Connected" : "Idle",
    loadingStatus ? "checking" : connection?.local_healthy ? "ready" : "checking",
  );
  paintChip(
    elements.remoteTunnelChip,
    loadingStatus ? "Checking..." : connection?.tunnel_alive ? "Tunnel alive" : "Tunnel idle",
    loadingStatus ? "checking" : connection?.tunnel_alive ? "ready" : "checking",
  );
  const fingerprintState = connection?.fingerprint_match;
  paintChip(
    elements.remoteFingerprintChip,
    loadingStatus
      ? "Checking..."
      : fingerprintState === true
        ? "Fingerprint ok"
        : fingerprintState === false
          ? "Fingerprint mismatch"
          : "Fingerprint unknown",
    loadingStatus ? "checking" : fingerprintState === false ? "missing" : fingerprintState === true ? "ready" : "checking",
  );
}

export function renderRemoteSelect(elements, state) {
  elements.remoteSelect.innerHTML = "";
  if (state.remotesLoading && !state.remotes.length) {
    const option = document.createElement("option");
    option.value = state.selectedRemoteName;
    option.textContent = "Loading remotes…";
    elements.remoteSelect.append(option);
    elements.remoteSelect.value = state.selectedRemoteName;
    return;
  }
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
}

export function setMode(elements, state, mode) {
  state.mode = mode === "remote" ? "remote" : "local";
  for (const button of elements.segmented) {
    button.classList.toggle("segmented__item--active", button.dataset.mode === state.mode);
  }
  elements.localPanel.classList.toggle("hidden", state.mode !== "local");
  elements.remotePanel.classList.toggle("hidden", state.mode !== "remote");
}

export function renderOperation(elements, operation) {
  elements.operationTitle.textContent = humanizeKind(operation.kind || "operation");
  elements.operationMessage.textContent = operation.message || "Working…";
  elements.operationPanel.dataset.operationKind = operation.kind || "";
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

export function setGatewayState(elements, stateName, label) {
  setStatusBadge(elements.gatewayBadge, stateName, label);
}

export function showGatewayMissing(elements) {
  hide(elements.appShell);
  show(elements.gatewayMissing);
}

export function showGatewayReady(elements) {
  hide(elements.gatewayMissing);
  show(elements.appShell);
}

export function hideOperationPanel(elements) {
  hide(elements.operationPanel);
}

export function showOperationPanel(elements) {
  show(elements.operationPanel);
}

export function autoHideOperationPanel(elements) {
  elements.operationPanel.dataset.autohide = "true";
  globalThis.setTimeout(() => {
    if (elements.operationPanel.dataset.autohide !== "true") {
      return;
    }
    hide(elements.operationPanel);
  }, 1400);
}

export function showNotice(elements, message, tone = "") {
  showNoticeEl(elements.notice, message, tone);
}

export function clearNotice(elements) {
  clearNoticeEl(elements.notice);
}

export function setBusy(elements, state, busy) {
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

export function cancelOperationAutohide(elements) {
  elements.operationPanel.dataset.autohide = "false";
}

function paintChip(element, label, stateName) {
  setStatusBadge(element, stateName, label);
}

function humanizeKind(kind) {
  if (kind === "local.start") return "Starting local coco-flow";
  if (kind === "local.stop") return "Stopping local coco-flow";
  if (kind === "remote.connect") return "Connecting remote";
  if (kind === "remote.disconnect") return "Disconnecting remote";
  return "Working";
}
