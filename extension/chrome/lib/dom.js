export function show(element) {
  element.classList.remove("hidden");
}

export function hide(element) {
  element.classList.add("hidden");
}

export function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export function showNotice(element, message, tone = "") {
  element.textContent = message;
  element.className = `notice${tone ? ` notice--${tone}` : ""}`;
}

export function clearNotice(element) {
  element.textContent = "";
  element.className = "notice hidden";
}

export function setStatusBadge(element, stateName, label) {
  element.textContent = label;
  element.className = `status-badge status-badge--${stateName}`;
}
