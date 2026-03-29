"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { apiFetch, formatCurrency, type RiskMetric, type StressTestResult } from "@/lib/api";
import {
  Shield,
  AlertTriangle,
  Activity,
  BarChart2,
  Thermometer,
  Siren,
  RefreshCw,
  Loader2,
  CheckCircle2,
  XCircle,
  TrendingDown,
} from "lucide-react";

interface RiskDashboard {
  metrics: RiskMetric[];
  stress_tests: StressTestResult[];
  war_room_status: string;
  total_equity: number | null;
  peak_equity: number | null;
  drawdown_pct: number | null;
  open_positions: number;
  timestamp: string;
}

const STATUS_COLORS: Record<string, string> = {
  NORMAL: "text-profit",
  ALERT: "text-warning",
  REDUCE: "text-orange-400",
  SHUTDOWN: "text-loss",
};

const STATUS_BG: Record<string, string> = {
  NORMAL: "bg-profit/10",
  ALERT: "bg-warning/10",
  REDUCE: "bg-orange-400/10",
  SHUTDOWN: "bg-loss/10",
};

const METRIC_ICONS: Record<string, typeof Thermometer> = {
  "Portfolio Heat": Thermometer,
  "VaR (95%)": AlertTriangle,
  "VaR (99%)": AlertTriangle,
  "Max Drawdown": TrendingDown,
  "Sharpe Ratio": BarChart2,
  "Sortino Ratio": Activity,
  "Daily P&L": Activity,
};

export default function RiskPage() {
  const [data, setData] = useState<RiskDashboard | null>(null);
  const [loading, setLoading] = useState(true);

  async function fetchRisk() {
    setLoading(true);
    const result = await apiFetch<RiskDashboard>("/api/risk/dashboard");
    if (result) setData(result);
    setLoading(false);
  }

  useEffect(() => {
    fetchRisk();
    const interval = setInterval(fetchRisk, 15_000);
    return () => clearInterval(interval);
  }, []);

  const warRoom = data?.war_room_status || "NORMAL";

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-7xl mx-auto">
      <header className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <Shield size={20} className="text-orange-500" />
            <h1 className="font-heading text-2xl font-bold">Risk</h1>
          </div>
          <p className="text-text-secondary text-sm">
            War Room mode with real-time risk monitoring, VaR, stress tests, and correlation analysis
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className={`px-3 py-1.5 rounded-lg font-mono text-xs font-bold ${STATUS_BG[warRoom]} ${STATUS_COLORS[warRoom]}`}>
            {warRoom === "NORMAL" ? "ALL CLEAR" : warRoom}
          </div>
          <button onClick={fetchRisk} className="p-2 rounded-lg hover:bg-bg-elevated transition-colors text-text-tertiary">
            {loading ? <Loader2 size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </button>
        </div>
      </header>

      {/* War Room Banner */}
      {warRoom !== "NORMAL" && (
        <Card className={`border-loss/50 ${warRoom === "SHUTDOWN" ? "bg-loss/5" : "bg-warning/5"}`}>
          <div className="flex items-center gap-3">
            <Siren size={24} className={STATUS_COLORS[warRoom]} />
            <div>
              <p className={`font-heading font-bold ${STATUS_COLORS[warRoom]}`}>
                War Room {warRoom === "SHUTDOWN" ? "ACTIVE — ALL TRADING HALTED" :
                          warRoom === "REDUCE" ? "ACTIVE — Position Size Reduced 50%" :
                          "ALERT — Approaching Drawdown Limits"}
              </p>
              <p className="text-text-secondary text-xs mt-0.5">
                {warRoom === "SHUTDOWN" ? "Drawdown exceeds 15%. No new entries permitted." :
                 warRoom === "REDUCE" ? "Drawdown exceeds 12%. All new positions at 50% size." :
                 "Drawdown exceeds 10%. Tightening stops on all open positions."}
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Risk Metrics Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {data?.metrics.map((metric) => {
          const Icon = METRIC_ICONS[metric.name] || Activity;
          const statusColor = metric.status === "ok" ? "text-profit" :
                             metric.status === "warning" ? "text-warning" : "text-loss";
          const iconColor = metric.status === "ok" ? "text-blue-500" :
                           metric.status === "warning" ? "text-warning" : "text-loss";
          return (
            <Card key={metric.name}>
              <div className="flex items-center gap-2 mb-2">
                <Icon size={14} className={iconColor} />
                <p className="text-text-secondary text-xs uppercase">{metric.name}</p>
              </div>
              <p className={`font-mono text-2xl font-bold ${
                metric.name === "Daily P&L" && metric.value != null
                  ? metric.value >= 0 ? "text-profit" : "text-loss"
                  : metric.status === "danger" ? "text-loss" : ""
              }`}>
                {metric.value != null ? (
                  metric.unit === "$" ? formatCurrency(metric.value) :
                  metric.unit === "%" ? `${metric.value}%` :
                  metric.value.toFixed(2)
                ) : "--"}
              </p>
              {metric.limit != null && (
                <div className="mt-2">
                  <div className="flex justify-between text-[10px] text-text-tertiary mb-1">
                    <span>Current</span>
                    <span>Limit: {metric.unit === "$" ? formatCurrency(metric.limit) : `${metric.limit}${metric.unit}`}</span>
                  </div>
                  <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        metric.status === "ok" ? "bg-profit" : metric.status === "warning" ? "bg-warning" : "bg-loss"
                      }`}
                      style={{
                        width: `${Math.min(100, Math.abs((metric.value || 0) / (metric.limit || 1)) * 100)}%`,
                      }}
                    />
                  </div>
                </div>
              )}
            </Card>
          );
        }) || (
          // Skeleton loading
          [...Array(4)].map((_, i) => (
            <Card key={i} className="animate-pulse">
              <div className="h-4 bg-bg-elevated rounded w-24 mb-3" />
              <div className="h-8 bg-bg-elevated rounded w-20" />
            </Card>
          ))
        )}
      </div>

      {/* Portfolio Overview */}
      {data && (
        <div className="grid grid-cols-3 gap-4">
          <Card>
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Total Equity</p>
            <p className="font-mono text-xl font-bold mt-1">{formatCurrency(data.total_equity)}</p>
          </Card>
          <Card>
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Peak Equity</p>
            <p className="font-mono text-xl font-bold mt-1">{formatCurrency(data.peak_equity)}</p>
          </Card>
          <Card>
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Open Positions</p>
            <p className="font-mono text-xl font-bold mt-1">{data.open_positions}</p>
          </Card>
        </div>
      )}

      {/* Stress Tests */}
      <section>
        <div className="flex items-center gap-3 mb-4">
          <Siren size={18} className="text-loss" />
          <h2 className="font-heading text-lg font-semibold">Stress Tests</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {(data?.stress_tests || []).map((test) => {
            const impactPct = Math.abs(test.portfolio_impact_pct || 0);
            return (
              <Card key={test.scenario}>
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="font-heading font-semibold text-sm">{test.scenario}</h3>
                    <p className="text-text-secondary text-xs mt-0.5">{test.description}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-loss font-mono text-xs font-bold">{test.market_impact}</span>
                    {test.survives ? (
                      <CheckCircle2 size={14} className="text-profit" />
                    ) : (
                      <XCircle size={14} className="text-loss" />
                    )}
                  </div>
                </div>
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="text-text-tertiary">Portfolio Impact</span>
                  <span className="font-mono text-loss font-bold">
                    {test.portfolio_impact != null ? formatCurrency(test.portfolio_impact) : "--"}
                    {test.portfolio_impact_pct != null && ` (${test.portfolio_impact_pct}%)`}
                  </span>
                </div>
                <div className="h-2 bg-bg-elevated rounded-full overflow-hidden">
                  <div
                    className="h-full bg-loss/50 rounded-full transition-all"
                    style={{ width: `${Math.min(100, impactPct)}%` }}
                  />
                </div>
                <p className="text-[10px] mt-1.5 font-mono text-text-tertiary">
                  {test.survives ? "Portfolio survives this scenario" : "Portfolio at risk — would breach shutdown threshold"}
                </p>
              </Card>
            );
          })}
          {!data?.stress_tests?.length && (
            [...Array(4)].map((_, i) => (
              <Card key={i} className="animate-pulse">
                <div className="h-4 bg-bg-elevated rounded w-40 mb-2" />
                <div className="h-3 bg-bg-elevated rounded w-60 mb-4" />
                <div className="h-2 bg-bg-elevated rounded-full" />
              </Card>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
