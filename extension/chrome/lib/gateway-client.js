import { CLIENT_HEADERS, GATEWAY_ORIGIN } from "./constants.js";

export async function gatewayFetch(path, options = {}) {
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
