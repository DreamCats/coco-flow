export async function loadPopupPrefs() {
  const stored = await chrome.storage.local.get(["popupMode", "selectedRemoteName"]);
  return {
    popupMode: stored.popupMode || "local",
    selectedRemoteName: stored.selectedRemoteName || "",
  };
}

export function savePopupMode(mode) {
  return chrome.storage.local.set({ popupMode: mode });
}

export function saveSelectedRemoteName(name) {
  return chrome.storage.local.set({ selectedRemoteName: name });
}
