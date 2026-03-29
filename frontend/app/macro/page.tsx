"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { apiFetch, type MacroIndicator } from "@/lib/api";
import {
  Globe,
  Activity,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Calendar,
  RefreshCw,
  Loader2,
} from "lucide-react";

interface MacroSnapshot {
  indicators: MacroIndicator[];
  regime: string | null;
  regime_timestamp: string | null;
  timestamp: string;
}

const REGIMES = [
  { name: "RISK_ON", color: "text-profit", bg: "bg-profit/10", border: "border-profit/30", desc: "Favorable conditions — trend-following and momentum strategies active" },
  { name: "RISK_OFF", color: "text-loss", bg: "bg-loss/10", border: "border-loss/30", desc: "Defensive posture — reduce exposure, favor cash and hedges" },
  { name: "RANGE", color: "text-blue-400", bg: "bg-blue-500/10", border: "border-blue-500/30", desc: "Mean-reversion environment — sideways, low ADX" },
  { name: "TREND", color: "text-cyan-400", bg: "bg-cyan-500/10", border: "border-cyan-500/30", desc: "Strong directional move — trend-following strategies dominant" },
  { name: "EXPANSION", color: "text-yellow-400", bg: "bg-yellow-500/10", border: "border-yellow-500/30", desc: "Breakout conditions — high volume expansion with directional momentum" },
  { name: "CHAOTIC", color: "text-warning", bg: "bg-warning/10", border: "border-warning/30", desc: "Extreme uncertainty — NO TRADING, all positions reduced" },
];

const CATEGORY_ORDER = ["Rates", "Inflation", "Labor", "Liquidity", "Volatility", "FX"];

const FOMC_DATES = [
  { date: "2026-01-29", event: "FOMC Decision", impact: "HIGH" },
  { date: "2026-03-19", event: "FOMC Decision + SEP", impact: "HIGH" },
  { date: "2026-05-07", event: "FOMC Decision", impact: "HIGH" },
  { date: "2026-06-18", event: "FOMC Decision + SEP", impact: "HIGH" },
  { date: "2026-07-30", event: "FOMC Decision", impact: "HIGH" },
  { date: "2026-04-04", event: "NFP Report", impact: "HIGH" },
  { date: "2026-04-10", event: "CPI Release", impact: "HIGH" },
  { date: "2026-03-28", event: "PCE Inflation", impact: "MEDIUM" },
];

export default function MacroPage() {
  const [snapshot, setSnapshot] = useState<MacroSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchMacro() {
    setLoading(true);
    const data = await apiFetch<MacroSnapshot>("/api/macro/snapshot");
    if (data) setSnapshot(data);

    // Fallback: also try the regime endpoint directly
    if (!data?.regime) {
      const regimeData = await apiFetch<{ regime: string; timestamp: string }>(
        "/api/scoring/regime?symbol=BTCUSDT"
      );
      if (regimeData && !data?.regime) {
        setSnapshot((prev) => prev ? { ...prev, regime: regimeData.regime } : null);
      }
    }
    setLoading(false);
  }

  useEffect(() => {
    fetchMacro();
    const interval = setInterval(fetchMacro, 60_000); // Refresh every 60s
    return () => clearInterval(interval);
  }, []);

  const regime = snapshot?.regime;

  // Group indicators by category
  const grouped: Record<string, MacroIndicator[]> = {};
  for (const ind of snapshot?.indicators || []) {
    if (!grouped[ind.category]) grouped[ind.category] = [];
    grouped[ind.category].push(ind);
  }

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-7xl mx-auto">
      <header className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Globe size={20} className="text-purple-500" />
            <h1 className="font-heading text-2xl font-bold">Macro</h1>
          </div>
          <p className="text-text-secondary text-sm">
            Regime detection, economic indicators, FOMC calendar, liquidity tracking
          </p>
        </div>
        <button
          onClick={fetchMacro}
          className="p-2 rounded-lg hover:bg-bg-elevated transition-colors text-text-tertiary hover:text-text-primary"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
        </button>
      </header>

      {/* Current Regime */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Market Regime</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {REGIMES.map((r) => {
            const isActive = regime === r.name;
            return (
              <Card
                key={r.name}
                className={`transition-all ${
                  isActive ? `${r.border} ring-1 ring-current shadow-lg` : "opacity-60"
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <span className={`font-mono text-sm font-bold ${r.color}`}>
                      {r.name}
                    </span>
                    <p className="text-text-tertiary text-xs mt-1 leading-relaxed">{r.desc}</p>
                  </div>
                  {isActive && (
                    <div className="flex flex-col items-end gap-1">
                      <span className={`px-2 py-1 rounded text-[10px] font-mono font-bold ${r.bg} ${r.color}`}>
                        ACTIVE
                      </span>
                      <span className="w-2 h-2 rounded-full bg-profit animate-pulse" />
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Macro Indicators */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Key Indicators</h2>
        {(snapshot?.indicators?.length ?? 0) > 0 ? (
          <div className="space-y-4">
            {CATEGORY_ORDER.filter((cat) => grouped[cat]).map((cat) => (
              <div key={cat}>
                <h3 className="text-text-tertiary text-[10px] uppercase tracking-widest mb-2 font-mono">{cat}</h3>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  {grouped[cat].map((ind) => (
                    <Card key={ind.key} className="py-3">
                      <p className="text-text-secondary text-xs">{ind.label}</p>
                      <div className="flex items-baseline gap-1.5 mt-1">
                        <p className="font-mono text-lg font-bold">
                          {ind.value != null ? ind.value.toLocaleString() : "--"}
                        </p>
                        {ind.unit && (
                          <span className="text-text-tertiary text-xs font-mono">{ind.unit}</span>
                        )}
                      </div>
                      {ind.source === "fallback" && (
                        <p className="text-text-tertiary text-[9px] mt-0.5 font-mono">est.</p>
                      )}
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[...Array(8)].map((_, i) => (
              <Card key={i} className="animate-pulse">
                <div className="h-4 bg-bg-elevated rounded w-20 mb-2" />
                <div className="h-6 bg-bg-elevated rounded w-16" />
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Economic Calendar */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">
          <Calendar size={16} className="inline mr-2" />
          Economic Calendar
        </h2>
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-text-tertiary text-xs border-b border-border">
                  <th className="text-left py-2 pr-4">Date</th>
                  <th className="text-left py-2 pr-4">Event</th>
                  <th className="text-center py-2">Impact</th>
                  <th className="text-right py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {FOMC_DATES
                  .sort((a, b) => a.date.localeCompare(b.date))
                  .map((evt, i) => {
                    const isPast = new Date(evt.date) < new Date();
                    const isToday = evt.date === new Date().toISOString().slice(0, 10);
                    return (
                      <tr key={i} className={`border-b border-border-subtle ${isToday ? "bg-warning/5" : ""}`}>
                        <td className="py-2.5 pr-4 font-mono text-xs">
                          {new Date(evt.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                        </td>
                        <td className="py-2.5 pr-4 text-xs">{evt.event}</td>
                        <td className="py-2.5 text-center">
                          <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                            evt.impact === "HIGH" ? "bg-loss/10 text-loss" : "bg-warning/10 text-warning"
                          }`}>
                            {evt.impact}
                          </span>
                        </td>
                        <td className="py-2.5 text-right text-xs text-text-tertiary font-mono">
                          {isToday ? "TODAY" : isPast ? "PAST" : "UPCOMING"}
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </Card>
      </section>
    </div>
  );
}
