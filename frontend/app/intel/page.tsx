"use client";

import { useEffect, useState, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { TradingChart } from "@/components/charts/TradingChart";
import { apiFetch, type SignalScore } from "@/lib/api";
import {
  BarChart3,
  Layers,
  TrendingUp,
  Activity,
  Eye,
  ChevronDown,
  Loader2,
  Gauge,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";

const TIMEFRAMES = ["5M", "15M", "1H", "4H", "1D"] as const;

const SYMBOLS = [
  { value: "BTCUSDT", label: "BTC/USDT", class: "crypto" },
  { value: "ETHUSDT", label: "ETH/USDT", class: "crypto" },
  { value: "SPY", label: "SPY", class: "equity" },
  { value: "AAPL", label: "AAPL", class: "equity" },
  { value: "TSLA", label: "TSLA", class: "equity" },
  { value: "NVDA", label: "NVDA", class: "equity" },
  { value: "QQQ", label: "QQQ", class: "equity" },
  { value: "AMZN", label: "AMZN", class: "equity" },
];

const ANALYSIS_METHODS = [
  { name: "ICT / Smart Money", description: "Order blocks, fair value gaps, liquidity sweeps, market structure shifts", icon: Layers, active: true, engine: "structure" },
  { name: "Wyckoff", description: "Accumulation/distribution phases, spring/upthrust, composite operator", icon: Eye, active: true, engine: "structure" },
  { name: "Momentum", description: "RSI, MACD, stochastic divergences, rate of change analysis", icon: Activity, active: true, engine: "momentum" },
  { name: "Trend", description: "Moving average alignment, ADX strength, linear regression slope", icon: TrendingUp, active: true, engine: "trend" },
];

function ScoreBar({ label, score, color }: { label: string; score: number | null; color: string }) {
  const val = score ?? 0;
  const width = Math.min(100, Math.max(0, val));
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-text-secondary">{label}</span>
        <span className="font-mono font-bold" style={{ color }}>{score != null ? score.toFixed(0) : "--"}</span>
      </div>
      <div className="h-2 bg-bg-elevated rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${width}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

export default function IntelPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState<string>("1H");
  const [signal, setSignal] = useState<SignalScore | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchScore = useCallback(async () => {
    setLoading(true);
    // Try compute endpoint first (fresh), fall back to latest (cached)
    let data = await apiFetch<{ signal: SignalScore | null }>(`/api/scoring/compute/${symbol}?direction=long`);
    if (!data?.signal) {
      data = await apiFetch<{ signal: SignalScore | null }>(`/api/scoring/latest/${symbol}`);
    }
    if (data?.signal) setSignal(data.signal);
    setLoading(false);
  }, [symbol]);

  useEffect(() => {
    fetchScore();
    const interval = setInterval(fetchScore, 30_000);
    return () => clearInterval(interval);
  }, [fetchScore]);

  const composite = signal?.composite_score ?? 0;
  const signalColor = composite >= 70 ? "#22c55e" : composite >= 50 ? "#f59e0b" : "#ef4444";
  const direction = composite >= 60 ? "BULLISH" : composite <= 40 ? "BEARISH" : "NEUTRAL";

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <header>
        <div className="flex items-center gap-3 mb-1">
          <BarChart3 size={20} className="text-blue-500" />
          <h1 className="font-heading text-2xl font-bold">Intel</h1>
        </div>
        <p className="text-text-secondary text-sm">
          CMT-grade technical analysis with multi-methodology confluence scoring
        </p>
      </header>

      {/* Symbol + Timeframe selectors */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="relative">
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="appearance-none bg-bg-card border border-border rounded-lg px-4 py-2 pr-8 text-sm font-mono focus:outline-none focus:border-accent-hover"
          >
            <optgroup label="Crypto">
              {SYMBOLS.filter(s => s.class === "crypto").map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </optgroup>
            <optgroup label="Equities">
              {SYMBOLS.filter(s => s.class === "equity").map(s => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </optgroup>
          </select>
          <ChevronDown size={14} className="absolute right-2 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none" />
        </div>

        <div className="flex bg-bg-card border border-border rounded-lg overflow-hidden">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3 py-2 text-xs font-mono transition-colors ${
                timeframe === tf ? "bg-accent text-text-primary" : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>

        {/* Signal Badge */}
        <div className="flex items-center gap-2 ml-auto">
          {loading && <Loader2 size={14} className="animate-spin text-text-tertiary" />}
          {signal && (
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg" style={{ backgroundColor: `${signalColor}15` }}>
              {direction === "BULLISH" ? (
                <ArrowUpRight size={14} style={{ color: signalColor }} />
              ) : direction === "BEARISH" ? (
                <ArrowDownRight size={14} style={{ color: signalColor }} />
              ) : (
                <Activity size={14} style={{ color: signalColor }} />
              )}
              <span className="font-mono text-sm font-bold" style={{ color: signalColor }}>
                {composite.toFixed(0)}
              </span>
              <span className="text-[10px] font-mono text-text-secondary">{direction}</span>
            </div>
          )}
          {signal?.regime && (
            <span className="text-[10px] font-mono px-2 py-1 rounded bg-bg-elevated text-text-tertiary">
              {signal.regime}
            </span>
          )}
        </div>
      </div>

      {/* Chart */}
      <Card className="overflow-hidden p-0">
        <TradingChart symbol={symbol} initialTimeframe={timeframe} height={500} showTimeframes showVolume />
      </Card>

      {/* Signal Score Breakdown */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">
          <Gauge size={16} className="inline mr-2" />
          Signal Breakdown
        </h2>
        {signal ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Composite Score */}
            <Card>
              <div className="flex items-center justify-between mb-4">
                <p className="text-text-secondary text-xs uppercase tracking-wider">Composite Score</p>
                <span className="font-mono text-3xl font-bold" style={{ color: signalColor }}>
                  {composite.toFixed(0)}
                </span>
              </div>
              <div className="h-3 bg-bg-elevated rounded-full overflow-hidden mb-4">
                <div
                  className="h-full rounded-full transition-all duration-700"
                  style={{
                    width: `${composite}%`,
                    background: `linear-gradient(90deg, ${signalColor}80, ${signalColor})`,
                  }}
                />
              </div>
              <div className="flex justify-between text-[10px] text-text-tertiary font-mono">
                <span>0 — Strong Sell</span>
                <span>50 — Neutral</span>
                <span>100 — Strong Buy</span>
              </div>
            </Card>

            {/* Individual Engine Scores */}
            <Card>
              <p className="text-text-secondary text-xs uppercase tracking-wider mb-4">Engine Scores</p>
              <div className="space-y-3">
                <ScoreBar label="Trend" score={signal.trend_score} color="#3b82f6" />
                <ScoreBar label="Momentum" score={signal.momentum_score} color="#8b5cf6" />
                <ScoreBar label="Structure" score={signal.structure_score} color="#22c55e" />
                <ScoreBar label="Flow" score={signal.flow_score} color="#f59e0b" />
                <ScoreBar label="Macro" score={signal.macro_score} color="#06b6d4" />
              </div>
            </Card>
          </div>
        ) : (
          <Card>
            <div className="text-center py-8">
              {loading ? (
                <div className="flex items-center justify-center gap-2 text-text-tertiary">
                  <Loader2 size={16} className="animate-spin" />
                  <span className="text-sm">Computing signal scores...</span>
                </div>
              ) : (
                <div className="text-text-tertiary text-sm">
                  <Activity size={24} className="mx-auto mb-2 opacity-50" />
                  <p>Start the API server to view live signal scores</p>
                  <p className="font-mono text-xs mt-2">uvicorn backend.api.app:app --port 8000</p>
                </div>
              )}
            </div>
          </Card>
        )}
      </section>

      {/* Analysis Methods */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Analysis Methods</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {ANALYSIS_METHODS.map((method) => {
            const Icon = method.icon;
            const engineScore = signal ? (
              method.engine === "trend" ? signal.trend_score :
              method.engine === "momentum" ? signal.momentum_score :
              method.engine === "structure" ? signal.structure_score : null
            ) : null;

            return (
              <Card key={method.name}>
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center bg-blue-500/10 flex-shrink-0">
                    <Icon size={18} className="text-blue-500" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <h3 className="font-heading font-semibold text-sm">{method.name}</h3>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-profit/10 text-profit">
                          ACTIVE
                        </span>
                      </div>
                      {engineScore != null && (
                        <span className="font-mono text-sm font-bold text-text-primary">
                          {engineScore.toFixed(0)}
                        </span>
                      )}
                    </div>
                    <p className="text-text-secondary text-xs mt-1 leading-relaxed">{method.description}</p>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      </section>
    </div>
  );
}
