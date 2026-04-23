export async function loadPopupPrefs() {
  const stored = await chrome.storage.local.get([
    "popupMode",
    "selectedRemoteName",
    "cachedRemotes",
    "cachedRemoteStatuses",
  ]);
  return {
    popupMode: stored.popupMode || "local",
    selectedRemoteName: stored.selectedRemoteName || "",
    cachedRemotes: Array.isArray(stored.cachedRemotes) ? stored.cachedRemotes : [],
    cachedRemoteStatuses: stored.cachedRemoteStatuses && typeof stored.cachedRemoteStatuses === "object" ? stored.cachedRemoteStatuses : {},
  };
}

export function savePopupMode(mode) {
  return chrome.storage.local.set({ popupMode: mode });
}

export function saveSelectedRemoteName(name) {
  return chrome.storage.local.set({ selectedRemoteName: name });
}

export function saveCachedRemotes(remotes) {
  return chrome.storage.local.set({ cachedRemotes: Array.isArray(remotes) ? remotes : [] });
}

export async function saveCachedRemoteStatus(name, status) {
  if (!name || !status || typeof status !== "object") {
    return;
  }
  const stored = await chrome.storage.local.get(["cachedRemoteStatuses"]);
  const cachedRemoteStatuses = stored.cachedRemoteStatuses && typeof stored.cachedRemoteStatuses === "object"
    ? stored.cachedRemoteStatuses
    : {};
  cachedRemoteStatuses[name] = status;
  await chrome.storage.local.set({ cachedRemoteStatuses });
}
