import { useEffect, useRef, useState, useCallback } from "react";

export interface WsEvent {
  type: string;
  data?: Record<string, unknown>;
  correlation_id?: string;
  intent?: string;
  report?: Record<string, unknown>;
  received_at?: string;
  timestamp?: string;
}

export function useWebSocket(url: string) {
  const wsRef = useRef<WebSocket | null>(null);
  const [events, setEvents] = useState<WsEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        console.log("[WS] Connected");
      };

      ws.onmessage = (e) => {
        try {
          const evt: WsEvent = JSON.parse(e.data);
          setEvents((prev) => [...prev, evt]);
        } catch {
          console.warn("[WS] Non-JSON message:", e.data);
        }
      };

      ws.onclose = () => {
        setConnected(false);
        console.log("[WS] Disconnected, reconnecting in 3s...");
        reconnectTimer.current = setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectTimer.current = setTimeout(connect, 3000);
    }
  }, [url]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const clearEvents = useCallback(() => setEvents([]), []);

  return { events, connected, clearEvents };
}
