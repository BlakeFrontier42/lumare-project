"use client";

import { useEffect, useState, useCallback } from "react";
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
  Zap,
  Target,
  BarChart3,
  Grid3X3,
} from "lucide-react";

const API = "";

interface VaRMethod {
  method: string;
  confidence: number;
  var_pct: number;
  var_dollar: number;
  [key: string]: unknown;
}

interface VaRData {
  historical: VaRMethod;
  parametric: VaRMethod;
  monte_carlo: VaRMethod & { simulations: number; worst_case: number; best_case: number };
  confidence: number;
  portfolio_value: number;
}

interface StressScenario {
  scenario: string;
  market_drawdown_pct: number;
  portfolio_impact_pct: number;
  portfolio_impact_dollar: number;
  remaining_value: number;
  description: string;
  survives: boolean;
}

interface CorrelationData {
  symbols: string[];
  matrix: number[][];
}

interface AdvancedMetrics {
  beta: number;
  sortino_ratio: number;
  max_drawdown: { max_drawdown_pct: number; peak_day: number; trough_day: number; recovery_days: number; current_drawdown_pct: number };
  calmar_ratio: number;
  cvar_95: number;
  cvar_99: number;
  annualized_volatility: number;
  annualized_return: number;
  sharpe_ratio: number;
}

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
  const [varData, setVarData] = useState<VaRData | null>(null);
  const [stressData, setStressData] = useState<StressScenario[]>([]);
  const [corrData, setCorrData] = useState<CorrelationData | null>(null);
  const [advMetrics, setAdvMetrics] = useState<AdvancedMetrics | null>(null);
  const [tab, setTab] = useState<"overview" | "var" | "stress" | "correlation">("overview");

  async function fetchRisk() {
    setLoading(true);
    const result = await apiFetch<RiskDashboard>("/api/risk/dashboard");
    if (result) setData(result);
    setLoading(false);
  }

  const fetchAdvanced = useCallback(async () => {
    try {
      const [v, s, c, m] = await Promise.all([
        fetch(`${API}/api/risk/var`).then(r => r.json()).catch(() => null),
        fetch(`${API}/api/risk/stress`).then(r => r.json()).catch(() => null),
        fetch(`${API}/api/risk/correlation`).then(r => r.json()).catch(() => null),
        fetch(`${API}/api/risk/metrics`).then(r => r.json()).catch(() => null),
      ]);
      if (v) setVarData(v);
      if (s?.scenarios) setStressData(s.scenarios);
      if (c) setCorrData(c);
      if (m) setAdvMetrics(m);
    } catch { /* */ }
  }, []);

  useEffect(() => {
    fetchRisk();
    fetchAdvanced();
    const interval = setInterval(fetchRisk, 15_000);
    return () => clearInterval(interval);
  }, [fetchAdvanced]);

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

      {/* Advanced Analytics Tabs */}
      <div className="flex gap-1 p-1 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg w-fit">
        {([
          { key: "var" as const, label: "Value at Risk", icon: AlertTriangle },
          { key: "stress" as const, label: "Monte Carlo Stress", icon: Zap },
          { key: "correlation" as const, label: "Correlation Matrix", icon: Grid3X3 },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              tab === t.key ? "bg-[#1a1a1a] text-white" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {/* VaR Section */}
      {tab === "var" && (
        <section className="space-y-4">
          <h2 className="font-heading text-lg font-semibold flex items-center gap-2">
            <AlertTriangle size={18} className="text-amber-400" />
            Value at Risk Analysis
          </h2>
          {varData ? (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {[
                  { label: "Historical VaR", data: varData.historical, desc: "Based on past return distribution" },
                  { label: "Parametric VaR", data: varData.parametric, desc: "Normal distribution assumption" },
                  { label: "Monte Carlo VaR", data: varData.monte_carlo, desc: `${varData.monte_carlo.simulations?.toLocaleString() || "1,000"} GBM simulations` },
                ].map((item) => (
                  <Card key={item.label}>
                    <p className="text-text-secondary text-xs uppercase tracking-wider">{item.label}</p>
                    <p className="font-mono text-2xl font-bold text-red-400 mt-1">
                      -${Math.abs(item.data.var_dollar).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </p>
                    <p className="text-[10px] text-text-tertiary mt-1">{item.desc}</p>
                    <p className="text-[10px] text-text-tertiary">
                      {Math.abs(item.data.var_pct).toFixed(2)}% of portfolio
                    </p>
                  </Card>
                ))}
              </div>
              <Card>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs text-text-secondary mb-1">
                      At {(varData.confidence * 100).toFixed(0)}% confidence, your max expected 1-day loss:
                    </p>
                    <p className="font-mono text-lg font-bold text-red-400">
                      ${Math.abs(varData.monte_carlo.var_dollar).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </p>
                  </div>
                  <div className="text-right text-xs">
                    <p className="text-text-tertiary">Portfolio: ${varData.portfolio_value.toLocaleString()}</p>
                    <p className="text-text-tertiary">Worst case: <span className="text-red-400 font-mono">${Math.abs(varData.monte_carlo.worst_case || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}</span></p>
                    <p className="text-text-tertiary">Best case: <span className="text-green-400 font-mono">+${(varData.monte_carlo.best_case || 0).toLocaleString(undefined, {maximumFractionDigits: 0})}</span></p>
                  </div>
                </div>
              </Card>
            </>
          ) : (
            <Card className="animate-pulse"><div className="h-20 bg-bg-elevated rounded" /></Card>
          )}

          {/* Advanced Metrics */}
          {advMetrics && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "Beta", value: advMetrics.beta?.toFixed(2) ?? "--", color: (advMetrics.beta ?? 0) > 1.2 ? "text-red-400" : "text-green-400" },
                { label: "Sortino", value: advMetrics.sortino_ratio?.toFixed(2) ?? "--", color: (advMetrics.sortino_ratio ?? 0) > 1 ? "text-green-400" : "text-amber-400" },
                { label: "Calmar", value: advMetrics.calmar_ratio?.toFixed(2) ?? "--", color: (advMetrics.calmar_ratio ?? 0) > 1 ? "text-green-400" : "text-amber-400" },
                { label: "Max Drawdown", value: advMetrics.max_drawdown ? `${advMetrics.max_drawdown.max_drawdown_pct?.toFixed(1)}%` : "--", color: "text-red-400" },
                { label: "CVaR (95%)", value: advMetrics.cvar_95 != null ? `$${Math.abs(advMetrics.cvar_95).toLocaleString(undefined, {maximumFractionDigits: 0})}` : "--", color: "text-red-400" },
                { label: "CVaR (99%)", value: advMetrics.cvar_99 != null ? `$${Math.abs(advMetrics.cvar_99).toLocaleString(undefined, {maximumFractionDigits: 0})}` : "--", color: "text-red-400" },
                { label: "Ann. Return", value: advMetrics.annualized_return != null ? `${(advMetrics.annualized_return * 100).toFixed(1)}%` : "--", color: (advMetrics.annualized_return ?? 0) > 0 ? "text-green-400" : "text-red-400" },
                { label: "Ann. Volatility", value: advMetrics.annualized_volatility != null ? `${(advMetrics.annualized_volatility * 100).toFixed(1)}%` : "--", color: "text-amber-400" },
              ].map((m) => (
                <Card key={m.label}>
                  <p className="text-[10px] text-text-tertiary uppercase tracking-wider">{m.label}</p>
                  <p className={`font-mono text-lg font-bold mt-1 ${m.color}`}>{m.value}</p>
                </Card>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Monte Carlo Stress Section */}
      {tab === "stress" && (
        <section className="space-y-4">
          <h2 className="font-heading text-lg font-semibold flex items-center gap-2">
            <Zap size={18} className="text-red-400" />
            Monte Carlo Stress Scenarios
          </h2>
          {stressData.length > 0 ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {stressData.map((scenario) => (
                <Card key={scenario.scenario} className={`border ${scenario.survives ? "border-[#1a1a1a]" : "border-red-500/30"}`}>
                  <div className="flex items-start justify-between mb-2">
                    <h3 className="font-heading font-semibold text-sm">{scenario.scenario}</h3>
                    {scenario.survives ? (
                      <CheckCircle2 size={16} className="text-green-400 flex-shrink-0" />
                    ) : (
                      <XCircle size={16} className="text-red-400 flex-shrink-0" />
                    )}
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-text-tertiary">Market Drop</span>
                      <span className="font-mono text-red-400 font-bold">{scenario.market_drawdown_pct.toFixed(0)}%</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-text-tertiary">Portfolio Impact</span>
                      <span className="font-mono text-red-400">${Math.abs(scenario.portfolio_impact_dollar).toLocaleString(undefined, {maximumFractionDigits: 0})}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-text-tertiary">Impact %</span>
                      <span className="font-mono text-red-400">{scenario.portfolio_impact_pct.toFixed(1)}%</span>
                    </div>
                  </div>
                  <div className="h-2 bg-bg-elevated rounded-full overflow-hidden mt-3">
                    <div
                      className={`h-full rounded-full ${scenario.survives ? "bg-amber-500/60" : "bg-red-500"}`}
                      style={{ width: `${Math.min(100, Math.abs(scenario.portfolio_impact_pct))}%` }}
                    />
                  </div>
                  <p className={`text-[10px] mt-1.5 font-mono ${scenario.survives ? "text-green-400/70" : "text-red-400"}`}>
                    {scenario.survives ? "Portfolio survives" : "Breach — would trigger shutdown"}
                  </p>
                </Card>
              ))}
            </div>
          ) : (
            <Card className="animate-pulse"><div className="h-40 bg-bg-elevated rounded" /></Card>
          )}
        </section>
      )}

      {/* Correlation Matrix Section */}
      {tab === "correlation" && (
        <section className="space-y-4">
          <h2 className="font-heading text-lg font-semibold flex items-center gap-2">
            <Grid3X3 size={18} className="text-blue-400" />
            Portfolio Correlation Matrix
          </h2>
          {corrData ? (
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <th className="p-2 text-left text-xs text-text-tertiary"></th>
                      {corrData.symbols.map((sym) => (
                        <th key={sym} className="p-2 text-center text-xs font-mono text-text-secondary">{sym}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {corrData.symbols.map((rowSym, i) => (
                      <tr key={rowSym}>
                        <td className="p-2 text-xs font-mono text-text-secondary font-medium">{rowSym}</td>
                        {corrData.matrix[i].map((val, j) => {
                          const abs = Math.abs(val);
                          const bg = i === j
                            ? "bg-blue-500/20"
                            : val > 0.7 ? "bg-red-500/30"
                            : val > 0.3 ? "bg-amber-500/20"
                            : val < -0.3 ? "bg-green-500/20"
                            : "bg-[#111]";
                          const textColor = i === j
                            ? "text-blue-400"
                            : val > 0.7 ? "text-red-400"
                            : val > 0.3 ? "text-amber-400"
                            : val < -0.3 ? "text-green-400"
                            : "text-gray-500";
                          return (
                            <td key={j} className={`p-2 text-center text-xs font-mono font-medium ${bg} ${textColor}`}>
                              {val.toFixed(2)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="flex items-center gap-4 mt-4 text-[10px] text-text-tertiary justify-center">
                <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-500/30" /> High positive (&gt;0.7)</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-amber-500/20" /> Moderate (0.3-0.7)</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-[#111]" /> Low (-0.3 to 0.3)</span>
                <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-green-500/20" /> Negative (&lt;-0.3)</span>
              </div>
            </Card>
          ) : (
            <Card className="animate-pulse"><div className="h-60 bg-bg-elevated rounded" /></Card>
          )}
        </section>
      )}
    </div>
  );
}
