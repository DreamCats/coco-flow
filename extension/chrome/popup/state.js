export function createPopupState() {
  return {
    mode: "local",
    gatewayReady: false,
    localStatus: null,
    remotes: [],
    selectedRemoteName: "",
    selectedRemoteStatus: null,
    activeOperationId: "",
    activeOperationKind: "",
    busy: false,
  };
}
