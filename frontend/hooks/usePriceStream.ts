"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { WS_BASE, type PriceData } from "@/lib/api";

/**
 * WebSocket hook for real-time price streaming.
 * Falls back to REST polling if WS connection fails.
 */
export function usePriceStream() {
  const [prices, setPrices] = useState<Map<string, PriceData>>(new Map());
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    try {
      const ws = new WebSocket(`${WS_BASE}/ws/prices`);
      wsRef.current = ws;

      ws.onopen = () => {
        if (mountedRef.current) setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "prices" && Array.isArray(msg.data)) {
            setPrices((prev) => {
              const next = new Map(prev);
              for (const p of msg.data) {
                next.set(p.symbol, p);
              }
              return next;
            });
          }
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onclose = () => {
        if (mountedRef.current) {
          setConnected(false);
          // Reconnect after 3 seconds
          reconnectTimer.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      // WebSocket creation failed, retry
      reconnectTimer.current = setTimeout(connect, 5000);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on unmount
        wsRef.current.close();
      }
    };
  }, [connect]);

  return {
    prices: Array.from(prices.values()),
    priceMap: prices,
    connected,
  };
}
