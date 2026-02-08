import { useEffect, useRef, useState, useCallback } from "react";
import type { AgentEvent, WSMessage } from "../types";

const WS_URL = "ws://localhost:6020/ws";
const EVENTS_HTTP_URL = "http://localhost:6020/events?limit=500";
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;
const PING_INTERVAL_MS = 25000;

interface UseWebSocketReturn {
  /** All events received so far (history + live). */
  events: AgentEvent[];
  /** Whether the WebSocket is currently connected. */
  connected: boolean;
  /** Whether the WebSocket has been permanently stopped (cascade done). */
  stopped: boolean;
  /** Manually reconnect. */
  reconnect: () => void;
  /** Permanently disconnect the WebSocket (no reconnection). */
  disconnect: () => void;
  /** Fetch event history via HTTP GET (fallback when WS is down). */
  fetchHistory: () => Promise<void>;
  /** Clear all events and re-fetch from server, resetting to initial state. */
  reset: () => Promise<void>;
  /** Clear all events from memory (no fetch). */
  clearEvents: () => void;
  /** Trim events array to a specific count (for simulation reset). */
  trimEventsTo: (count: number) => void;
  /** Reset simulation: trim to pre-sim count and remove all disruption events. */
  resetSimulationEvents: (preSimCount: number) => void;
}

/**
 * Hook that connects to the Event Bus WebSocket and accumulates events.
 *
 * On connect, the server sends a HISTORY message with recent events.
 * After that, individual event objects arrive in real-time.
 *
 * After CASCADE_COMPLETE, call `disconnect()` to permanently stop
 * the WebSocket — all data is already stored in React state.
 *
 * Uses a mountedRef guard to be safe under React Strict Mode (double-mount).
 */
export function useWebSocket(): UseWebSocketReturn {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [stopped, setStopped] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const mountedRef = useRef(false);
  const stoppedRef = useRef(false);          // prevents reconnection after disconnect()
  const reconnectAttempt = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Stable helpers stored in refs (never trigger effect re-runs) ──

  const clearTimers = () => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (pingTimer.current) {
      clearInterval(pingTimer.current);
      pingTimer.current = null;
    }
  };

  const closeSocket = () => {
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  // Store connect in a ref so the reconnect timer and manual reconnect
  // always call the latest version without being a useCallback dependency.
  const connectRef = useRef<() => void>(() => {});

  connectRef.current = () => {
    // Guard: don't connect if component unmounted OR permanently stopped
    if (!mountedRef.current || stoppedRef.current) return;

    // Clean up any existing connection
    closeSocket();
    clearTimers();

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) {
        ws.close();
        return;
      }
      setConnected(true);
      reconnectAttempt.current = 0;

      // Start client-side keep-alive pings
      pingTimer.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send("PING");
        }
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (evt) => {
      if (!mountedRef.current) return;
      try {
        const msg: WSMessage = JSON.parse(evt.data);

        // Handle history batch (sent on connect)
        if ("type" in msg && msg.type === "HISTORY") {
          const history = (msg as { type: string; events: AgentEvent[] }).events;
          setEvents((prev) => {
            const existing = new Set(
              prev.map((e) => `${e.timestamp}:${e.agent_id}:${e.event_type}`),
            );
            const newEvents = history.filter(
              (e) => !existing.has(`${e.timestamp}:${e.agent_id}:${e.event_type}`),
            );
            if (newEvents.length === 0) return prev;  // no change → skip re-render
            return [...prev, ...newEvents];
          });
          return;
        }

        // Ignore PING / PONG
        if ("type" in msg && (msg.type === "PING" || msg.type === "PONG")) {
          return;
        }

        // Regular event
        if ("event_type" in msg) {
          setEvents((prev) => [...prev, msg as AgentEvent]);
        }
      } catch {
        // Ignore unparseable messages
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setConnected(false);
      clearTimers();

      // Don't reconnect if permanently stopped
      if (stoppedRef.current) return;

      // Exponential backoff reconnect
      const delay = Math.min(
        RECONNECT_BASE_MS * 2 ** reconnectAttempt.current,
        RECONNECT_MAX_MS,
      );
      reconnectAttempt.current += 1;
      reconnectTimer.current = setTimeout(() => connectRef.current(), delay);
    };

    ws.onerror = () => {
      // onclose will fire after onerror, which handles reconnection
    };
  };

  // ── Manual reconnect (stable callback, no deps) ──
  const reconnect = useCallback(() => {
    stoppedRef.current = false;
    setStopped(false);
    reconnectAttempt.current = 0;
    connectRef.current();
  }, []);

  // ── Permanent disconnect — stops WebSocket and prevents reconnection ──
  const disconnect = useCallback(() => {
    stoppedRef.current = true;
    setStopped(true);
    clearTimers();
    closeSocket();
    setConnected(false);
  }, []);

  // ── HTTP fallback: fetch history via GET /events ──
  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(EVENTS_HTTP_URL);
      if (!res.ok) return;
      const history: AgentEvent[] = await res.json();
      if (!Array.isArray(history) || history.length === 0) return;

      setEvents((prev) => {
        if (prev.length > 0) {
          // Merge: deduplicate by key
          const existing = new Set(
            prev.map((e) => `${e.timestamp}:${e.agent_id}:${e.event_type}`),
          );
          const newEvents = history.filter(
            (e) => !existing.has(`${e.timestamp}:${e.agent_id}:${e.event_type}`),
          );
          if (newEvents.length === 0) return prev;
          return [...prev, ...newEvents];
        }
        // Replace: first load
        return history;
      });
    } catch {
      // Network error — event bus may be down, silently ignore
    }
  }, []);

  // ── Reset: clear all state and re-fetch fresh from server ──
  const reset = useCallback(async () => {
    // Clear all accumulated events
    setEvents([]);

    // Try to fetch fresh history from server
    try {
      const res = await fetch(EVENTS_HTTP_URL);
      if (!res.ok) return;
      const history: AgentEvent[] = await res.json();
      if (Array.isArray(history) && history.length > 0) {
        setEvents(history);
      }
    } catch {
      // Server may be down — dashboard starts empty, which is fine
    }
  }, []);

  // ── Clear events: clear all events from memory without fetching ──
  const clearEvents = useCallback(() => {
    setEvents([]);
  }, []);

  // ── Trim events: keep only the first N events (for simulation reset) ──
  const trimEventsTo = useCallback((count: number) => {
    setEvents((prev) => prev.slice(0, count));
  }, []);

  // ── Reset simulation: trim to pre-sim count AND remove all disruption-related events ──
  const resetSimulationEvents = useCallback((preSimCount: number) => {
    setEvents((prev) => {
      // First trim to the pre-simulation count
      const trimmed = prev.slice(0, preSimCount);
      // Then filter out ALL disruption-related events (from this or previous simulations)
      return trimmed.filter((e) =>
        e.event_type !== "DISRUPTION_DETECTED" &&
        e.event_type !== "ORDER_FAILED"
      );
    });
  }, []);

  // ── Single effect with empty deps — Strict Mode safe ──
  useEffect(() => {
    mountedRef.current = true;
    connectRef.current();

    return () => {
      mountedRef.current = false;
      clearTimers();
      closeSocket();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { events, connected, stopped, reconnect, disconnect, fetchHistory, reset, clearEvents, trimEventsTo, resetSimulationEvents };
}
