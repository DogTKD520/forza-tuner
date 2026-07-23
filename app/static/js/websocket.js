/**
 * websocket.js — WebSocket connection with auto-reconnect.
 *
 * Emits a 'telemetry' custom event on the window each time a frame arrives
 * so other modules can subscribe without coupling to the socket directly.
 */

const WS_URL = `ws://${location.host}/ws/telemetry`;
const RECONNECT_DELAY_MS = 3000;

let socket = null;
let reconnectTimer = null;

export function connectWebSocket() {
  if (socket && socket.readyState === WebSocket.OPEN) return;

  socket = new WebSocket(WS_URL);

  socket.addEventListener('open', () => {
    clearTimeout(reconnectTimer);
    window.dispatchEvent(new CustomEvent('ws:connected'));
  });

  socket.addEventListener('message', (event) => {
    try {
      const frame = JSON.parse(event.data);
      window.dispatchEvent(new CustomEvent('telemetry', { detail: frame }));
    } catch {
      // Ignore malformed frames
    }
  });

  socket.addEventListener('close', () => {
    window.dispatchEvent(new CustomEvent('ws:disconnected'));
    reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
  });

  socket.addEventListener('error', () => {
    socket.close();
  });
}

export function disconnectWebSocket() {
  clearTimeout(reconnectTimer);
  socket?.close();
}
