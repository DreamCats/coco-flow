import { getPopupElements } from "./elements.js";
import { createPopupActions } from "./actions.js";
import { createPopupState } from "./state.js";

const state = createPopupState();
const elements = getPopupElements();
const actions = createPopupActions(state, elements);

function bindEvents() {
  elements.retryGateway.addEventListener("click", () => {
    void actions.refreshGateway();
  });
  elements.copyInstall.addEventListener("click", () => {
    void actions.copyInstallCommand();
  });
  elements.copyStart.addEventListener("click", () => {
    void actions.copyStartCommand();
  });
  for (const button of elements.segmented) {
    button.addEventListener("click", () => {
      actions.setMode(button.dataset.mode || "local");
    });
  }
  elements.localRefresh.addEventListener("click", () => {
    void actions.loadLocalStatus();
  });
  elements.localStart.addEventListener("click", () => {
    void actions.triggerOperation("/local/start", {
      method: "POST",
      body: JSON.stringify({ host: "127.0.0.1", port: 4318, build_web: true }),
    });
  });
  elements.localStop.addEventListener("click", () => {
    void actions.triggerOperation("/local/stop", { method: "POST" });
  });
  elements.localOpen.addEventListener("click", () => {
    void actions.openUrl(state.localStatus?.url);
  });
  elements.remoteSelect.addEventListener("change", () => {
    void actions.onRemoteSelected(elements.remoteSelect.value);
  });
  elements.remoteRefresh.addEventListener("click", () => {
    void actions.loadRemoteStatus();
  });
  elements.remoteConnect.addEventListener("click", () => {
    if (!state.selectedRemoteName) {
      return;
    }
    void actions.triggerOperation(`/remote/${encodeURIComponent(state.selectedRemoteName)}/connect`, {
      method: "POST",
      body: JSON.stringify({ restart: false, reconnect_tunnel: false, build_web: true }),
    });
  });
  elements.remoteDisconnect.addEventListener("click", () => {
    if (!state.selectedRemoteName) {
      return;
    }
    void actions.triggerOperation(`/remote/${encodeURIComponent(state.selectedRemoteName)}/disconnect`, {
      method: "POST",
    });
  });
  elements.remoteOpen.addEventListener("click", () => {
    void actions.openUrl(state.selectedRemoteStatus?.connections?.[0]?.local_url);
  });
  elements.openOptions.addEventListener("click", () => {
    void chrome.runtime.openOptionsPage();
  });
}

async function boot() {
  bindEvents();
  await actions.boot();
}

void boot();
