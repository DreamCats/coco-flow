export function createPopupState() {
  return {
    mode: "local",
    gatewayReady: false,
    localStatus: null,
    localLoading: false,
    remotes: [],
    remotesLoading: false,
    selectedRemoteName: "",
    cachedRemoteStatuses: {},
    selectedRemoteStatus: null,
    selectedRemoteStatusStale: false,
    remoteStatusLoading: false,
    activeOperationId: "",
    activeOperationKind: "",
    busy: false,
  };
}
