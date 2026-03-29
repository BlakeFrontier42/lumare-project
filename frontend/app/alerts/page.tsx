"use client";

import { useState, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import {
  Bell,
  BellRing,
  Plus,
  Trash2,
  ToggleLeft,
  ToggleRight,
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Zap,
  Target,
  Clock,
  CheckCircle2,
  XCircle,
  ChevronDown,
  Search,
  Sparkles,
  Volume2,
  ArrowUpDown,
} from "lucide-react";

/* ─── Types ─── */

type ConditionType =
  | "price_above"
  | "price_below"
  | "pct_change_1d"
  | "pct_change_1w"
  | "volume_spike_2x"
  | "volume_spike_3x"
  | "volume_spike_5x"
  | "rsi_above_70"
  | "rsi_below_30"
  | "golden_cross"
  | "death_cross"
  | "new_52w_high"
  | "new_52w_low";

type AlertStatus = "active" | "triggered" | "expired";

interface Alert {
  id: string;
  symbol: string;
  condition: ConditionType;
  value: number | null;
  currentPrice: number;
  status: AlertStatus;
  enabled: boolean;
  createdAt: string;
  triggeredAt: string | null;
  triggerPrice: number | null;
  note: string;
}

interface AlertTemplate {
  name: string;
  description: string;
  icon: typeof Sparkles;
  conditions: { symbol: string; condition: ConditionType; value: number | null; note: string }[];
}

/* ─── Condition labels ─── */

const CONDITION_LABELS: Record<ConditionType, string> = {
  price_above: "Price Above",
  price_below: "Price Below",
  pct_change_1d: "% Change (1D)",
  pct_change_1w: "% Change (1W)",
  volume_spike_2x: "Volume Spike 2x",
  volume_spike_3x: "Volume Spike 3x",
  volume_spike_5x: "Volume Spike 5x",
  rsi_above_70: "RSI Above 70",
  rsi_below_30: "RSI Below 30",
  golden_cross: "Golden Cross (50/200 MA)",
  death_cross: "Death Cross (50/200 MA)",
  new_52w_high: "New 52-Week High",
  new_52w_low: "New 52-Week Low",
};

const CONDITIONS_NEEDING_VALUE: ConditionType[] = [
  "price_above",
  "price_below",
  "pct_change_1d",
  "pct_change_1w",
];

/* ─── Templates ─── */

const TEMPLATES: AlertTemplate[] = [
  {
    name: "Earnings Volatility Watch",
    description: "Monitors for volume spikes and large moves ahead of earnings",
    icon: Activity,
    conditions: [
      { symbol: "NVDA", condition: "volume_spike_3x", value: null, note: "Pre-earnings volume surge" },
      { symbol: "NVDA", condition: "pct_change_1d", value: 5, note: "Earnings day volatility" },
    ],
  },
  {
    name: "Breakout Scanner",
    description: "Catches new highs with volume confirmation",
    icon: TrendingUp,
    conditions: [
      { symbol: "AAPL", condition: "new_52w_high", value: null, note: "Breakout to new highs" },
      { symbol: "AAPL", condition: "volume_spike_2x", value: null, note: "Volume confirmation" },
    ],
  },
  {
    name: "Oversold Alert",
    description: "RSI and price level alerts for mean-reversion entries",
    icon: TrendingDown,
    conditions: [
      { symbol: "META", condition: "rsi_below_30", value: null, note: "Oversold bounce candidate" },
      { symbol: "META", condition: "price_below", value: 540, note: "Key support level" },
    ],
  },
  {
    name: "Gap Fill Monitor",
    description: "Tracks gap-fill levels and trend reversals",
    icon: ArrowUpDown,
    conditions: [
      { symbol: "TSLA", condition: "price_above", value: 285, note: "Gap fill target" },
      { symbol: "TSLA", condition: "golden_cross", value: null, note: "Trend reversal confirmation" },
    ],
  },
];

/* ─── Mock data generator ─── */

function generateMockAlerts(): Alert[] {
  const now = Date.now();
  const day = 86400000;

  return [
    { id: "a1", symbol: "AAPL", condition: "price_above", value: 198, currentPrice: 195.42, status: "active", enabled: true, createdAt: new Date(now - 2 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Resistance breakout" },
    { id: "a2", symbol: "NVDA", condition: "volume_spike_3x", value: null, currentPrice: 875.30, status: "triggered", enabled: true, createdAt: new Date(now - 5 * day).toISOString(), triggeredAt: new Date(now - 0.5 * day).toISOString(), triggerPrice: 878.15, note: "Earnings run-up" },
    { id: "a3", symbol: "TSLA", condition: "rsi_below_30", value: null, currentPrice: 248.60, status: "active", enabled: true, createdAt: new Date(now - 1 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Oversold bounce play" },
    { id: "a4", symbol: "META", condition: "price_below", value: 540, currentPrice: 552.18, status: "active", enabled: false, createdAt: new Date(now - 3 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Support level watch" },
    { id: "a5", symbol: "AMZN", condition: "golden_cross", value: null, currentPrice: 186.75, status: "triggered", enabled: true, createdAt: new Date(now - 10 * day).toISOString(), triggeredAt: new Date(now - 1 * day).toISOString(), triggerPrice: 185.90, note: "Trend reversal signal" },
    { id: "a6", symbol: "GOOG", condition: "pct_change_1d", value: 4, currentPrice: 163.20, status: "active", enabled: true, createdAt: new Date(now - 0.5 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Unusual move detector" },
    { id: "a7", symbol: "MSFT", condition: "new_52w_high", value: null, currentPrice: 428.50, status: "triggered", enabled: true, createdAt: new Date(now - 7 * day).toISOString(), triggeredAt: new Date(now - 0.2 * day).toISOString(), triggerPrice: 430.12, note: "ATH breakout" },
    { id: "a8", symbol: "SPY", condition: "price_below", value: 510, currentPrice: 524.30, status: "expired", enabled: false, createdAt: new Date(now - 30 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Market pullback watch" },
    { id: "a9", symbol: "QQQ", condition: "death_cross", value: null, currentPrice: 445.20, status: "active", enabled: true, createdAt: new Date(now - 4 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Bearish trend warning" },
    { id: "a10", symbol: "AMD", condition: "volume_spike_5x", value: null, currentPrice: 162.35, status: "triggered", enabled: true, createdAt: new Date(now - 6 * day).toISOString(), triggeredAt: new Date(now - 2 * day).toISOString(), triggerPrice: 165.80, note: "Massive volume event" },
    { id: "a11", symbol: "COIN", condition: "pct_change_1w", value: 15, currentPrice: 225.40, status: "active", enabled: true, createdAt: new Date(now - 2 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Crypto correlation move" },
    { id: "a12", symbol: "SMCI", condition: "rsi_above_70", value: null, currentPrice: 745.90, status: "triggered", enabled: true, createdAt: new Date(now - 8 * day).toISOString(), triggeredAt: new Date(now - 3 * day).toISOString(), triggerPrice: 752.30, note: "Overbought — trim signal" },
    { id: "a13", symbol: "BA", condition: "price_above", value: 195, currentPrice: 188.20, status: "expired", enabled: false, createdAt: new Date(now - 45 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Recovery play" },
    { id: "a14", symbol: "PLTR", condition: "new_52w_low", value: null, currentPrice: 22.85, status: "active", enabled: true, createdAt: new Date(now - 1 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "52W low breakdown" },
    { id: "a15", symbol: "SOFI", condition: "volume_spike_2x", value: null, currentPrice: 8.92, status: "active", enabled: true, createdAt: new Date(now - 3 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Accumulation signal" },
    { id: "a16", symbol: "JPM", condition: "price_above", value: 205, currentPrice: 198.60, status: "active", enabled: true, createdAt: new Date(now - 2 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Breakout above range" },
    { id: "a17", symbol: "XOM", condition: "golden_cross", value: null, currentPrice: 112.40, status: "expired", enabled: false, createdAt: new Date(now - 60 * day).toISOString(), triggeredAt: null, triggerPrice: null, note: "Energy sector trend" },
    { id: "a18", symbol: "RIVN", condition: "pct_change_1d", value: 8, currentPrice: 14.25, status: "triggered", enabled: true, createdAt: new Date(now - 4 * day).toISOString(), triggeredAt: new Date(now - 0.1 * day).toISOString(), triggerPrice: 15.42, note: "Earnings gap alert" },
  ];
}

/* ─── Helpers ─── */

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function conditionDisplay(c: ConditionType, v: number | null): string {
  const label = CONDITION_LABELS[c];
  if (v !== null && CONDITIONS_NEEDING_VALUE.includes(c)) {
    if (c === "pct_change_1d" || c === "pct_change_1w") return `${label} > ${v}%`;
    return `${label} $${v.toLocaleString()}`;
  }
  return label;
}

/* ─── Component ─── */

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<Alert[]>(generateMockAlerts);
  const [showForm, setShowForm] = useState(false);
  const [filterStatus, setFilterStatus] = useState<"all" | AlertStatus>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Form state
  const [formSymbol, setFormSymbol] = useState("");
  const [formCondition, setFormCondition] = useState<ConditionType>("price_above");
  const [formValue, setFormValue] = useState("");
  const [formNote, setFormNote] = useState("");

  /* ─── Derived data ─── */

  const counts = useMemo(() => {
    const today = new Date().toDateString();
    return {
      active: alerts.filter((a) => a.status === "active" && a.enabled).length,
      triggeredToday: alerts.filter((a) => a.status === "triggered" && a.triggeredAt && new Date(a.triggeredAt).toDateString() === today).length,
      pending: alerts.filter((a) => a.status === "active" && !a.enabled).length,
      total: alerts.length,
    };
  }, [alerts]);

  const filtered = useMemo(() => {
    return alerts.filter((a) => {
      if (filterStatus !== "all" && a.status !== filterStatus) return false;
      if (searchQuery && !a.symbol.toLowerCase().includes(searchQuery.toLowerCase()) && !a.note.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      return true;
    });
  }, [alerts, filterStatus, searchQuery]);

  const triggeredAlerts = useMemo(() => alerts.filter((a) => a.status === "triggered").sort((a, b) => new Date(b.triggeredAt!).getTime() - new Date(a.triggeredAt!).getTime()), [alerts]);

  /* ─── Handlers ─── */

  function handleCreate() {
    if (!formSymbol.trim()) return;
    const needsValue = CONDITIONS_NEEDING_VALUE.includes(formCondition);
    const val = needsValue ? parseFloat(formValue) || 0 : null;
    const newAlert: Alert = {
      id: `a${Date.now()}`,
      symbol: formSymbol.toUpperCase().trim(),
      condition: formCondition,
      value: val,
      currentPrice: Math.random() * 500 + 10,
      status: "active",
      enabled: true,
      createdAt: new Date().toISOString(),
      triggeredAt: null,
      triggerPrice: null,
      note: formNote,
    };
    setAlerts((prev) => [newAlert, ...prev]);
    setFormSymbol("");
    setFormValue("");
    setFormNote("");
    setShowForm(false);
  }

  function handleToggle(id: string) {
    setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, enabled: !a.enabled } : a)));
  }

  function handleDelete(id: string) {
    setAlerts((prev) => prev.filter((a) => a.id !== id));
  }

  function applyTemplate(template: AlertTemplate) {
    const newAlerts: Alert[] = template.conditions.map((c, i) => ({
      id: `t${Date.now()}-${i}`,
      symbol: c.symbol,
      condition: c.condition,
      value: c.value,
      currentPrice: Math.random() * 500 + 50,
      status: "active" as AlertStatus,
      enabled: true,
      createdAt: new Date().toISOString(),
      triggeredAt: null,
      triggerPrice: null,
      note: c.note,
    }));
    setAlerts((prev) => [...newAlerts, ...prev]);
  }

  /* ─── Status badge ─── */

  function StatusBadge({ status, enabled }: { status: AlertStatus; enabled: boolean }) {
    if (status === "triggered")
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-500/15 text-yellow-400 animate-pulse">
          <BellRing className="w-3 h-3" /> Triggered
        </span>
      );
    if (status === "expired")
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-white/5 text-text-muted">
          <XCircle className="w-3 h-3" /> Expired
        </span>
      );
    if (!enabled)
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-white/5 text-text-muted">
          <Clock className="w-3 h-3" /> Paused
        </span>
      );
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400">
        <CheckCircle2 className="w-3 h-3" /> Active
      </span>
    );
  }

  /* ─── Render ─── */

  return (
    <div className="min-h-screen bg-[#080808] p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-yellow-500/10">
            <Bell className="w-6 h-6 text-yellow-400" />
          </div>
          <div>
            <h1 className="font-heading text-2xl font-bold text-white">Alerts</h1>
            <p className="text-sm text-text-muted">Price, volume, and technical alerts across your watchlist</p>
          </div>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 text-sm font-medium text-white transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Alert
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="flex items-center gap-4">
          <div className="p-2.5 rounded-lg bg-emerald-500/10">
            <Target className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Active</p>
            <p className="text-2xl font-bold font-mono text-white">{counts.active}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-4">
          <div className="p-2.5 rounded-lg bg-yellow-500/10">
            <BellRing className="w-5 h-5 text-yellow-400" />
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Triggered Today</p>
            <p className="text-2xl font-bold font-mono text-white">{counts.triggeredToday}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-4">
          <div className="p-2.5 rounded-lg bg-blue-500/10">
            <Clock className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Pending</p>
            <p className="text-2xl font-bold font-mono text-white">{counts.pending}</p>
          </div>
        </Card>
        <Card className="flex items-center gap-4">
          <div className="p-2.5 rounded-lg bg-white/5">
            <BarChart3 className="w-5 h-5 text-text-muted" />
          </div>
          <div>
            <p className="text-xs text-text-muted uppercase tracking-wider">Total Alerts</p>
            <p className="text-2xl font-bold font-mono text-white">{counts.total}</p>
          </div>
        </Card>
      </div>

      {/* Create Alert Form */}
      {showForm && (
        <Card>
          <h2 className="text-sm font-semibold text-white mb-4">Create New Alert</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <div>
              <label className="block text-xs text-text-muted mb-1">Symbol</label>
              <input
                type="text"
                placeholder="AAPL"
                value={formSymbol}
                onChange={(e) => setFormSymbol(e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-text-muted focus:outline-none focus:border-white/30"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Condition</label>
              <div className="relative">
                <select
                  value={formCondition}
                  onChange={(e) => setFormCondition(e.target.value as ConditionType)}
                  className="w-full appearance-none bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-white/30"
                >
                  {Object.entries(CONDITION_LABELS).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-2.5 w-4 h-4 text-text-muted pointer-events-none" />
              </div>
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Value</label>
              <input
                type="number"
                placeholder={CONDITIONS_NEEDING_VALUE.includes(formCondition) ? "0.00" : "N/A"}
                value={formValue}
                onChange={(e) => setFormValue(e.target.value)}
                disabled={!CONDITIONS_NEEDING_VALUE.includes(formCondition)}
                className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-text-muted focus:outline-none focus:border-white/30 disabled:opacity-40"
              />
            </div>
            <div>
              <label className="block text-xs text-text-muted mb-1">Note (optional)</label>
              <input
                type="text"
                placeholder="Breakout trade..."
                value={formNote}
                onChange={(e) => setFormNote(e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-sm text-white placeholder:text-text-muted focus:outline-none focus:border-white/30"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={handleCreate}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 text-sm font-medium transition-colors"
              >
                <Zap className="w-4 h-4" />
                Create Alert
              </button>
            </div>
          </div>
        </Card>
      )}

      {/* Templates */}
      <Card>
        <h2 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-yellow-400" />
          Quick Templates
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {TEMPLATES.map((t) => {
            const Icon = t.icon;
            return (
              <button
                key={t.name}
                onClick={() => applyTemplate(t)}
                className="text-left p-3 rounded-lg border border-border bg-[#080808] hover:bg-bg-elevated transition-colors group"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Icon className="w-4 h-4 text-yellow-400 group-hover:text-yellow-300" />
                  <span className="text-xs font-semibold text-white">{t.name}</span>
                </div>
                <p className="text-xs text-text-muted leading-relaxed">{t.description}</p>
              </button>
            );
          })}
        </div>
      </Card>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-2.5 w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search by symbol or note..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-bg-elevated border border-border rounded-lg pl-9 pr-3 py-2 text-sm text-white placeholder:text-text-muted focus:outline-none focus:border-white/30"
          />
        </div>
        <div className="flex gap-1.5">
          {(["all", "active", "triggered", "expired"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                filterStatus === s ? "bg-white/10 text-white" : "text-text-muted hover:text-white hover:bg-white/5"
              }`}
            >
              {s === "all" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Active Alerts Table */}
      <Card padding="none">
        <div className="px-5 py-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Alert Monitor</h2>
          <span className="text-xs text-text-muted">{filtered.length} alert{filtered.length !== 1 ? "s" : ""}</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-xs text-text-muted uppercase tracking-wider">
                <th className="text-left px-5 py-3 font-medium">Symbol</th>
                <th className="text-left px-5 py-3 font-medium">Condition</th>
                <th className="text-right px-5 py-3 font-medium">Target</th>
                <th className="text-right px-5 py-3 font-medium">Current</th>
                <th className="text-center px-5 py-3 font-medium">Status</th>
                <th className="text-left px-5 py-3 font-medium">Created</th>
                <th className="text-left px-5 py-3 font-medium">Note</th>
                <th className="text-center px-5 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center text-text-muted text-sm">
                    No alerts match your filters
                  </td>
                </tr>
              ) : (
                filtered.map((a) => (
                  <tr key={a.id} className="border-b border-border/50 hover:bg-bg-elevated transition-colors">
                    <td className="px-5 py-3">
                      <span className="font-mono font-semibold text-white">{a.symbol}</span>
                    </td>
                    <td className="px-5 py-3 text-text-muted">{CONDITION_LABELS[a.condition]}</td>
                    <td className="px-5 py-3 text-right font-mono text-white">
                      {a.value !== null
                        ? a.condition.includes("pct_change")
                          ? `${a.value}%`
                          : `$${a.value.toLocaleString()}`
                        : "—"}
                    </td>
                    <td className="px-5 py-3 text-right font-mono text-white">${a.currentPrice.toFixed(2)}</td>
                    <td className="px-5 py-3 text-center">
                      <StatusBadge status={a.status} enabled={a.enabled} />
                    </td>
                    <td className="px-5 py-3 text-text-muted text-xs">{formatDate(a.createdAt)}</td>
                    <td className="px-5 py-3 text-text-muted text-xs max-w-[160px] truncate">{a.note || "—"}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={() => handleToggle(a.id)}
                          className="p-1.5 rounded hover:bg-white/5 transition-colors"
                          title={a.enabled ? "Disable alert" : "Enable alert"}
                        >
                          {a.enabled ? (
                            <ToggleRight className="w-4 h-4 text-emerald-400" />
                          ) : (
                            <ToggleLeft className="w-4 h-4 text-text-muted" />
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(a.id)}
                          className="p-1.5 rounded hover:bg-red-500/10 transition-colors"
                          title="Delete alert"
                        >
                          <Trash2 className="w-4 h-4 text-text-muted hover:text-red-400" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Triggered History */}
      <Card padding="none">
        <div className="px-5 py-3 border-b border-border">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <BellRing className="w-4 h-4 text-yellow-400" />
            Triggered History
          </h2>
        </div>
        <div className="divide-y divide-border/50">
          {triggeredAlerts.length === 0 ? (
            <div className="px-5 py-12 text-center text-text-muted text-sm">No triggered alerts yet</div>
          ) : (
            triggeredAlerts.map((a) => (
              <div key={a.id} className="px-5 py-3 flex items-center justify-between hover:bg-bg-elevated transition-colors">
                <div className="flex items-center gap-4">
                  <div className="p-1.5 rounded bg-yellow-500/10">
                    <BellRing className="w-4 h-4 text-yellow-400" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-white">{a.symbol}</span>
                      <span className="text-xs text-text-muted">{CONDITION_LABELS[a.condition]}</span>
                    </div>
                    <p className="text-xs text-text-muted mt-0.5">{a.note}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-mono text-sm text-yellow-400">${a.triggerPrice?.toFixed(2)}</p>
                  <p className="text-xs text-text-muted">{a.triggeredAt ? formatDate(a.triggeredAt) : ""}</p>
                </div>
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  );
}
