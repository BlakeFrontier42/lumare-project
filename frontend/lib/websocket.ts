/**
 * Lumare WebSocket — Notification hook for real-time trade alerts.
 *
 * useNotifications() connects to ws://localhost:8000/ws/notifications,
 * auto-reconnects on disconnect, and exposes a reactive notifications array
 * plus connection status.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_BASE } from "./api";

// ─── Types ───────────────────────────────────────────────

export type NotificationType =
  | "signal_triggered"
  | "sl_hit"
  | "tp_hit"
  | "position_closed"
  | "price_alert"
  | "system";

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: string;
  data?: Record<string, unknown>;
  /** Set by the hook when the toast auto-dismisses */
  dismissed?: boolean;
}

export type ConnectionStatus = "connecting" | "connected" | "disconnected";

// ─── Constants ───────────────────────────────────────────

const WS_URL = `${WS_BASE}/ws/notifications`;
const RECONNECT_DELAY_MS = 3_000;
const MAX_NOTIFICATIONS = 50;

// ─── Hook ────────────────────────────────────────────────

let _idCounter = 0;
function nextId(): string {
  _idCounter += 1;
  return `notif-${Date.now()}-${_idCounter}`;
}

export function useNotifications() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const dismiss = useCallback((id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, dismissed: true } : n))
    );
  }, []);

  const clearAll = useCallback(() => {
    setNotifications([]);
  }, []);

  const connect = useCallback(() => {
    // Avoid double-connecting
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    setStatus("connecting");

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      setStatus("connected");
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const payload = JSON.parse(event.data);
        const notif: Notification = {
          id: nextId(),
          type: payload.type ?? "system",
          title: payload.title ?? "",
          message: payload.message ?? "",
          timestamp: payload.timestamp ?? new Date().toISOString(),
          data: payload.data,
        };
        setNotifications((prev) => {
          const updated = [notif, ...prev];
          // Cap at MAX_NOTIFICATIONS to prevent unbounded memory growth
          return updated.length > MAX_NOTIFICATIONS
            ? updated.slice(0, MAX_NOTIFICATIONS)
            : updated;
        });
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      setStatus("disconnected");
      wsRef.current = null;
      // Auto-reconnect
      reconnectTimer.current = setTimeout(() => {
        if (mountedRef.current) connect();
      }, RECONNECT_DELAY_MS);
    };

    ws.onerror = () => {
      // onclose fires after onerror — reconnect handled there
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return {
    notifications,
    status,
    dismiss,
    clearAll,
  };
}
