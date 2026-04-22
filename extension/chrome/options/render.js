import { clearNotice as clearNoticeEl, hide, show, showNotice as showNoticeEl, setStatusBadge, escapeHtml } from "../lib/dom.js";

export function setOptionsBadge(elements, stateName, label) {
  setStatusBadge(elements.badge, stateName, label);
}

export function showOptionsApp(elements) {
  hide(elements.missing);
  show(elements.app);
}

export function showOptionsMissing(elements) {
  hide(elements.app);
  show(elements.missing);
}

export function renderRemoteList(elements, remotes, onDelete) {
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
      void onDelete(button.getAttribute("data-delete"));
    });
  }
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
  elements.retry.disabled = busy;
  elements.refresh.disabled = busy;
  for (const element of elements.form.querySelectorAll("input, button")) {
    element.disabled = busy;
  }
}
