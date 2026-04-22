const GATEWAY_ORIGIN = "http://127.0.0.1:4319";
const CLIENT_HEADERS = {
  "Content-Type": "application/json",
  "X-Coco-Flow-Client": "chrome-extension",
};

const elements = {
  badge: document.getElementById("options-gateway-badge"),
  notice: document.getElementById("options-notice"),
  missing: document.getElementById("options-missing"),
  retry: document.getElementById("options-retry"),
  app: document.getElementById("options-app"),
  form: document.getElementById("remote-form"),
  list: document.getElementById("remote-list"),
  message: document.getElementById("options-message"),
  refresh: document.getElementById("refresh-remotes"),
};

const state = {
  busy: false,
};

async function boot() {
  bindEvents();
  await refreshGateway();
}

function bindEvents() {
  elements.retry.addEventListener("click", () => {
    void refreshGateway();
  });
  elements.refresh.addEventListener("click", () => {
    void loadRemotes();
  });
  elements.form.addEventListener("submit", (event) => {
    event.preventDefault();
    void createRemote();
  });
}

async function refreshGateway() {
  setBusy(true);
  clearNotice();
  setBadge("checking", "Checking...");
  try {
    await gatewayFetch("/healthz");
    setBadge("ready", "Gateway Ready");
    hide(elements.missing);
    show(elements.app);
    await loadRemotes();
  } catch (_error) {
    setBadge("missing", "Gateway Missing");
    hide(elements.app);
    show(elements.missing);
    showNotice("Gateway 没响应。先在终端执行 `coco-flow gateway start -d`。", "warning");
  } finally {
    setBusy(false);
  }
}

async function loadRemotes() {
  try {
    elements.message.textContent = "Loading remotes…";
    const payload = await gatewayFetch("/remote/list");
    const remotes = Array.isArray(payload.remotes) ? payload.remotes : [];
    elements.list.innerHTML = "";
    if (!remotes.length) {
      elements.message.textContent = "No saved remotes yet.";
      return;
    }
    elements.message.textContent = `${remotes.length} remote${remotes.length > 1 ? "s" : ""}`;
    for (const remote of remotes) {
      const item = document.createElement("article");
      item.className = "remote-item";
      item.innerHTML = `
        <div class="remote-item__head">
          <div class="remote-item__name">${escapeHtml(remote.name)}</div>
          <button class="button button--ghost" data-delete="${escapeHtml(remote.name)}" type="button">Delete</button>
        </div>
        <div class="remote-item__meta">
          ${escapeHtml(remote.user ? `${remote.user}@${remote.host}` : remote.host)}<br />
          local ${remote.local_port} → remote ${remote.remote_port}
        </div>
      `;
      elements.list.append(item);
    }
    for (const button of elements.list.querySelectorAll("[data-delete]")) {
      button.addEventListener("click", () => {
        void deleteRemote(button.getAttribute("data-delete"));
      });
    }
  } catch (error) {
    elements.message.textContent = "Failed to load remotes.";
    showNotice(error.message, "error");
  }
}

async function createRemote() {
  setBusy(true);
  clearNotice();
  try {
    const formData = new FormData(elements.form);
    const payload = {
      name: String(formData.get("name") || "").trim(),
      host: String(formData.get("host") || "").trim(),
      user: String(formData.get("user") || "").trim(),
      local_port: Number(formData.get("local_port") || 4318),
      remote_port: Number(formData.get("remote_port") || 4318),
    };
    await gatewayFetch("/remote", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    elements.form.reset();
    elements.form.local_port.value = "4318";
    elements.form.remote_port.value = "4318";
    showNotice(`Saved remote ${payload.name}.`, "success");
    await loadRemotes();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function deleteRemote(name) {
  if (!name) {
    return;
  }
  setBusy(true);
  clearNotice();
  try {
    await gatewayFetch(`/remote/${encodeURIComponent(name)}`, { method: "DELETE" });
    showNotice(`Deleted remote ${name}.`, "success");
    await loadRemotes();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    setBusy(false);
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

function setBadge(stateName, label) {
  elements.badge.textContent = label;
  elements.badge.className = `status-badge status-badge--${stateName}`;
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
  elements.retry.disabled = busy;
  elements.refresh.disabled = busy;
  for (const element of elements.form.querySelectorAll("input, button")) {
    element.disabled = busy;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

void boot();
