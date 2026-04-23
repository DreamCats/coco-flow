export const GATEWAY_ORIGIN = "http://127.0.0.1:4319";
export const INSTALL_COMMAND = "curl -fsSL https://raw.githubusercontent.com/DreamCats/coco-flow/main/install.sh | bash";
export const START_COMMAND = "coco-flow gateway start -d";
export const CLIENT_HEADERS = {
  "Content-Type": "application/json",
  "X-Coco-Flow-Client": "chrome-extension",
};
