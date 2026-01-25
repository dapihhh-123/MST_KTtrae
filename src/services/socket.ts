
import { getSessionId } from "./session";

export type WebSocketListener = (data: any) => void;

class SocketService {
  private ws: WebSocket | null = null;
  private listeners: Set<WebSocketListener> = new Set();
  private reconnectTimer: any = null;

  connect() {
    const sessionId = getSessionId();
    if (!sessionId) {
      console.warn("Cannot connect WS: No session ID");
      return;
    }

    if (this.ws) {
        if (this.ws.readyState === WebSocket.OPEN) return;
        this.ws.close();
    }

    // A1. Fix: Connect directly to backend (8000) or VITE_WS_BASE
    // preventing "closed before established" if proxy is flaky
    const wsBase = import.meta.env.VITE_WS_BASE || "ws://localhost:8000";
    const url = `${wsBase}/ws/session/${sessionId}`;

    console.log("Connecting WS:", url);
    const newWs = new WebSocket(url);

    newWs.onopen = () => {
      console.log("WS Connected");
    };

    newWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.listeners.forEach(l => l(data));
      } catch (e) {
        console.error("WS Parse Error", e);
      }
    };

    newWs.onclose = () => {
      if (this.ws === newWs) { // Only reconnect if this is still the active socket
          console.log("WS Closed. Reconnecting in 3s...");
          this.ws = null;
          this.reconnectTimer = setTimeout(() => this.connect(), 3000);
      }
    };
    
    newWs.onerror = (e) => {
        // Suppress error if we are intentionally closing or switching
        if (this.ws === newWs) {
             console.error("WS Error", e);
        }
    };

    this.ws = newWs;
  }

  subscribe(listener: WebSocketListener) {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
    this.listeners.clear(); // Ensure no stale listeners
  }
}

export const socket = new SocketService();
