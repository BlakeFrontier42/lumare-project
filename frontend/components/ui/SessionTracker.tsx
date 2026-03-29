"use client";

import { useState, useEffect } from "react";
import { Globe, Clock } from "lucide-react";

interface Session {
  name: string;
  city: string;
  tz: string;
  openHourUTC: number;
  closeHourUTC: number;
  color: string;
  high: number | null;
  low: number | null;
}

// Session times in UTC (approximate, adjusted for DST manually)
const SESSIONS: Session[] = [
  { name: "Asia", city: "Tokyo", tz: "JST", openHourUTC: 0, closeHourUTC: 9, color: "#f59e0b", high: null, low: null },
  { name: "London", city: "London", tz: "GMT", openHourUTC: 8, closeHourUTC: 16, color: "#3b82f6", high: null, low: null },
  { name: "New York", city: "New York", tz: "EST", openHourUTC: 13, closeHourUTC: 21, color: "#22c55e", high: null, low: null },
];

function isSessionLive(session: Session, nowUTC: Date): boolean {
  const hour = nowUTC.getUTCHours();
  if (session.openHourUTC < session.closeHourUTC) {
    return hour >= session.openHourUTC && hour < session.closeHourUTC;
  }
  // Wraps midnight (like Asia)
  return hour >= session.openHourUTC || hour < session.closeHourUTC;
}

function getSessionTime(session: Session, now: Date): string {
  const offsets: Record<string, number> = { JST: 9, GMT: 0, EST: -5 };
  const offset = offsets[session.tz] ?? 0;
  const d = new Date(now.getTime() + offset * 3600000 + now.getTimezoneOffset() * 60000);
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: true });
}

// Generate mock session highs/lows based on time
function getSessionLevels(session: Session): { high: number; low: number } {
  const t = Date.now() / 60000;
  const bases: Record<string, [number, number]> = {
    Asia: [5672 + Math.sin(t / 30) * 8, 5658 + Math.sin(t / 30) * 8],
    London: [5688 + Math.sin(t / 25) * 6, 5665 + Math.sin(t / 25) * 6],
    "New York": [5695 + Math.sin(t / 20) * 10, 5660 + Math.sin(t / 20) * 10],
  };
  const [h, l] = bases[session.name] ?? [5680, 5660];
  return { high: Math.round(h * 100) / 100, low: Math.round(l * 100) / 100 };
}

export function SessionTracker({ compact = false }: { compact?: boolean }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className={`flex ${compact ? "gap-3" : "gap-4"} ${compact ? "" : "flex-wrap"}`}>
      {SESSIONS.map((session) => {
        const live = isSessionLive(session, now);
        const time = getSessionTime(session, now);
        const levels = getSessionLevels(session);

        return (
          <div
            key={session.name}
            className={`flex items-center gap-3 ${compact ? "px-3 py-1.5" : "px-4 py-2.5"} rounded-card border transition-all ${
              live ? "border-border bg-bg-card" : "border-transparent bg-bg-elevated/50 opacity-60"
            }`}
          >
            {/* Status dot */}
            <div className="flex items-center gap-2">
              <span
                className={`w-2 h-2 rounded-full ${live ? "animate-pulse" : ""}`}
                style={{ backgroundColor: live ? session.color : "#555" }}
              />
              <div>
                <div className="flex items-center gap-1.5">
                  <span className="font-heading text-xs font-semibold">{session.name}</span>
                  <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                    live ? "bg-profit/10 text-profit" : "bg-bg-elevated text-text-tertiary"
                  }`}>
                    {live ? "LIVE" : "CLOSED"}
                  </span>
                </div>
                <span className="text-[10px] text-text-tertiary font-mono">{time} {session.tz}</span>
              </div>
            </div>

            {/* Session levels (only show if not compact and session is live) */}
            {!compact && live && (
              <div className="flex gap-3 ml-2 border-l border-border pl-3">
                <div>
                  <p className="text-[9px] text-text-tertiary uppercase">High</p>
                  <p className="font-mono text-xs text-profit font-medium">{levels.high.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-[9px] text-text-tertiary uppercase">Low</p>
                  <p className="font-mono text-xs text-loss font-medium">{levels.low.toFixed(2)}</p>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
