import { clearNotice as clearNoticeEl, hide, show, setStatusBadge, showNotice as showNoticeEl, escapeHtml } from "../lib/dom.js";

export function renderLocal(elements, state) {
  const status = state.localStatus;
  elements.localRunning.textContent = status?.running ? "Running" : "Stopped";
  elements.localHealth.textContent = status?.healthy ? "Healthy" : "Unhealthy";
  elements.localUrl.textContent = status?.url || "-";
  elements.localPid.textContent = status?.pid ? String(status.pid) : "-";
}

export function renderRemote(elements, state) {
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

export function renderRemoteSelect(elements, state) {
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
