"use client";

import { useState, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import {
  BookOpen,
  TrendingUp,
  TrendingDown,
  Plus,
  X,
  Filter,
  Calendar,
  BarChart3,
  Target,
  Flame,
  Trophy,
  Skull,
  Hash,
  ChevronDown,
  ChevronUp,
  Clock,
  Award,
  FileText,
} from "lucide-react";
import { ExportMenu } from "@/components/ui/ExportMenu";

// ── Types ────────────────────────────────────────────────────────────────────
interface Trade {
  id: string;
  date: string;
  symbol: string;
  side: "Long" | "Short";
  entry: number;
  exit: number;
  qty: number;
  pnl: number;
  pnlPct: number;
  rMultiple: number;
  duration: string;
  notes: string;
}

interface Filters {
  dateFrom: string;
  dateTo: string;
  symbol: string;
  side: string;
  result: string;
}

// ── Mock Data Generator ──────────────────────────────────────────────────────
const SYMBOLS = ["AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META", "GOOG", "SPY", "QQQ", "AMD", "NFLX", "JPM", "BA", "CRM", "COIN"];
const DURATIONS = ["4m", "12m", "27m", "1h 3m", "2h 15m", "45m", "18m", "3h 42m", "55m", "1h 28m", "33m", "7m", "2h 5m", "1h 50m", "22m"];
const NOTES_POOL = [
  "Clean breakout above resistance", "Earnings gap fade", "VWAP rejection short", "Morning momentum scalp",
  "Failed breakdown reversal", "Sector rotation play", "Gap and go setup", "Overextended mean reversion",
  "Key level bounce", "News catalyst trade", "Opening range breakout", "Trend continuation pullback",
  "Double bottom entry", "Supply zone rejection", "Squeeze breakout play", "Weak close, sold early",
  "Added on pullback", "Stopped out at B/E", "Perfect entry, held too long", "Scaled out in thirds",
];

function seededRandom(seed: number) {
  let s = seed;
  return () => { s = (s * 16807 + 0) % 2147483647; return (s - 1) / 2147483646; };
}

function generateMockTrades(): Trade[] {
  const rand = seededRandom(42);
  const trades: Trade[] = [];
  const startDate = new Date("2025-11-01");

  for (let i = 0; i < 47; i++) {
    const daysOffset = Math.floor(rand() * 140);
    const date = new Date(startDate);
    date.setDate(date.getDate() + daysOffset);
    if (date.getDay() === 0) date.setDate(date.getDate() + 1);
    if (date.getDay() === 6) date.setDate(date.getDate() + 2);

    const symbol = SYMBOLS[Math.floor(rand() * SYMBOLS.length)];
    const side: "Long" | "Short" = rand() > 0.35 ? "Long" : "Short";
    const basePrice = 50 + rand() * 450;
    const entry = Math.round(basePrice * 100) / 100;
    const isWin = rand() < 0.57;
    const magnitude = isWin ? (rand() * 0.06 + 0.003) : (rand() * 0.04 + 0.002);
    const bigMove = rand() < 0.08 ? 2.5 : 1;
    const moveDir = side === "Long" ? (isWin ? 1 : -1) : (isWin ? -1 : 1);
    const exit = Math.round((entry + entry * magnitude * moveDir * bigMove) * 100) / 100;
    const qty = Math.floor(rand() * 400 + 10);
    const pnl = Math.round((exit - entry) * qty * (side === "Long" ? 1 : -1) * 100) / 100;
    const pnlPct = Math.round((pnl / (entry * qty)) * 10000) / 100;
    const risk = entry * 0.015;
    const rMultiple = Math.round((Math.abs(exit - entry) / risk) * (pnl >= 0 ? 1 : -1) * 100) / 100;

    trades.push({
      id: `t-${i}`,
      date: date.toISOString().split("T")[0],
      symbol,
      side,
      entry,
      exit,
      qty,
      pnl,
      pnlPct,
      rMultiple,
      duration: DURATIONS[Math.floor(rand() * DURATIONS.length)],
      notes: NOTES_POOL[Math.floor(rand() * NOTES_POOL.length)],
    });
  }
  return trades.sort((a, b) => b.date.localeCompare(a.date));
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const fmt = (n: number) => n >= 0 ? `+$${n.toLocaleString("en-US", { minimumFractionDigits: 2 })}` : `-$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
const fmtPct = (n: number) => `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
const pnlColor = (n: number) => n >= 0 ? "text-profit" : "text-loss";
const pnlBg = (n: number) => n >= 0 ? "bg-profit/10" : "bg-loss/10";

// ── Component ────────────────────────────────────────────────────────────────
export default function JournalPage() {
  const [allTrades, setAllTrades] = useState<Trade[]>(generateMockTrades);
  const [filters, setFilters] = useState<Filters>({ dateFrom: "", dateTo: "", symbol: "", side: "", result: "" });
  const [showAddModal, setShowAddModal] = useState(false);
  const [sortCol, setSortCol] = useState<keyof Trade>("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [showFilters, setShowFilters] = useState(false);

  // ── Filtering & Sorting ──────────────────────────────────────────────────
  const filtered = useMemo(() => {
    let t = [...allTrades];
    if (filters.dateFrom) t = t.filter((x) => x.date >= filters.dateFrom);
    if (filters.dateTo) t = t.filter((x) => x.date <= filters.dateTo);
    if (filters.symbol) t = t.filter((x) => x.symbol === filters.symbol);
    if (filters.side) t = t.filter((x) => x.side === filters.side);
    if (filters.result === "Win") t = t.filter((x) => x.pnl >= 0);
    if (filters.result === "Loss") t = t.filter((x) => x.pnl < 0);
    t.sort((a, b) => {
      const av = a[sortCol], bv = b[sortCol];
      if (typeof av === "number" && typeof bv === "number") return sortDir === "asc" ? av - bv : bv - av;
      return sortDir === "asc" ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
    return t;
  }, [allTrades, filters, sortCol, sortDir]);

  // ── Stats ────────────────────────────────────────────────────────────────
  const stats = useMemo(() => {
    const wins = filtered.filter((t) => t.pnl >= 0);
    const losses = filtered.filter((t) => t.pnl < 0);
    const totalPnl = filtered.reduce((s, t) => s + t.pnl, 0);
    const winRate = filtered.length ? (wins.length / filtered.length) * 100 : 0;
    const avgWin = wins.length ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0;
    const avgLoss = losses.length ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length : 0;
    const grossWin = wins.reduce((s, t) => s + t.pnl, 0);
    const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));
    const profitFactor = grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? Infinity : 0;
    const best = filtered.length ? Math.max(...filtered.map((t) => t.pnl)) : 0;
    const worst = filtered.length ? Math.min(...filtered.map((t) => t.pnl)) : 0;

    let streak = 0;
    let streakType: "W" | "L" | "—" = "—";
    if (filtered.length) {
      streakType = filtered[0].pnl >= 0 ? "W" : "L";
      for (const t of filtered) {
        if ((streakType === "W" && t.pnl >= 0) || (streakType === "L" && t.pnl < 0)) streak++;
        else break;
      }
    }

    return { totalPnl, winRate, avgWin, avgLoss, profitFactor, best, worst, total: filtered.length, streak, streakType };
  }, [filtered]);

  // ── Performance Summary ──────────────────────────────────────────────────
  const perfSummary = useMemo(() => {
    const totalEntries = filtered.length;
    const wins = filtered.filter((t) => t.pnl >= 0);
    const winRate = totalEntries > 0 ? (wins.length / totalEntries) * 100 : 0;
    const bestR = totalEntries > 0 ? Math.max(...filtered.map((t) => t.rMultiple)) : 0;

    // Parse duration strings to minutes for averaging
    function parseDuration(d: string): number {
      let mins = 0;
      const hMatch = d.match(/(\d+)\s*h/);
      const mMatch = d.match(/(\d+)\s*m/);
      if (hMatch) mins += parseInt(hMatch[1]) * 60;
      if (mMatch) mins += parseInt(mMatch[1]);
      return mins || 0;
    }
    const durations = filtered.map((t) => parseDuration(t.duration)).filter((d) => d > 0);
    const avgMins = durations.length > 0 ? durations.reduce((s, d) => s + d, 0) / durations.length : 0;
    const avgHoldingPeriod = avgMins >= 60 ? `${Math.floor(avgMins / 60)}h ${Math.round(avgMins % 60)}m` : `${Math.round(avgMins)}m`;

    return { totalEntries, winRate, bestR, avgHoldingPeriod };
  }, [filtered]);

  // ── Symbol Breakdown ─────────────────────────────────────────────────────
  const symbolStats = useMemo(() => {
    const map: Record<string, { trades: number; pnl: number; wins: number }> = {};
    filtered.forEach((t) => {
      if (!map[t.symbol]) map[t.symbol] = { trades: 0, pnl: 0, wins: 0 };
      map[t.symbol].trades++;
      map[t.symbol].pnl += t.pnl;
      if (t.pnl >= 0) map[t.symbol].wins++;
    });
    return Object.entries(map).map(([sym, d]) => ({ symbol: sym, ...d, winRate: (d.wins / d.trades) * 100 })).sort((a, b) => b.pnl - a.pnl);
  }, [filtered]);

  // ── Equity Curve ─────────────────────────────────────────────────────────
  const equityCurve = useMemo(() => {
    const sorted = [...filtered].sort((a, b) => a.date.localeCompare(b.date));
    let cum = 0;
    return sorted.map((t) => { cum += t.pnl; return { date: t.date, equity: cum }; });
  }, [filtered]);

  // ── Calendar Heatmap ─────────────────────────────────────────────────────
  const calendarData = useMemo(() => {
    const map: Record<string, number> = {};
    filtered.forEach((t) => { map[t.date] = (map[t.date] || 0) + t.pnl; });
    return map;
  }, [filtered]);

  // ── Sort handler ─────────────────────────────────────────────────────────
  function handleSort(col: keyof Trade) {
    if (sortCol === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("desc"); }
  }

  const SortIcon = ({ col }: { col: keyof Trade }) => sortCol === col ? (sortDir === "desc" ? <ChevronDown className="w-3 h-3 inline ml-1" /> : <ChevronUp className="w-3 h-3 inline ml-1" />) : null;

  // ── Unique symbols for filter ────────────────────────────────────────────
  const uniqueSymbols = useMemo(() => [...new Set(allTrades.map((t) => t.symbol))].sort(), [allTrades]);

  // ── Equity curve SVG ─────────────────────────────────────────────────────
  function renderEquityCurve() {
    if (equityCurve.length < 2) return <p className="text-text-secondary text-sm">Not enough data</p>;
    const w = 700, h = 180, px = 40, py = 20;
    const vals = equityCurve.map((d) => d.equity);
    const minV = Math.min(0, ...vals), maxV = Math.max(0, ...vals);
    const range = maxV - minV || 1;
    const points = equityCurve.map((d, i) => {
      const x = px + (i / (equityCurve.length - 1)) * (w - px * 2);
      const y = py + (1 - (d.equity - minV) / range) * (h - py * 2);
      return `${x},${y}`;
    });
    const zeroY = py + (1 - (0 - minV) / range) * (h - py * 2);
    const lastVal = vals[vals.length - 1];
    const lineColor = lastVal >= 0 ? "#22c55e" : "#e05252";
    const fillPoints = `${px},${zeroY} ${points.join(" ")} ${px + ((equityCurve.length - 1) / (equityCurve.length - 1)) * (w - px * 2)},${zeroY}`;

    return (
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto">
        <defs>
          <linearGradient id="eqFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
          </linearGradient>
        </defs>
        <line x1={px} y1={zeroY} x2={w - px} y2={zeroY} stroke="#333" strokeWidth="0.5" strokeDasharray="4" />
        <polygon points={fillPoints} fill="url(#eqFill)" />
        <polyline points={points.join(" ")} fill="none" stroke={lineColor} strokeWidth="2" strokeLinejoin="round" />
        <text x={px - 4} y={py + 4} fill="#888" fontSize="9" textAnchor="end">{fmt(maxV)}</text>
        <text x={px - 4} y={h - py + 4} fill="#888" fontSize="9" textAnchor="end">{fmt(minV)}</text>
        <text x={px - 4} y={zeroY + 3} fill="#555" fontSize="8" textAnchor="end">$0</text>
      </svg>
    );
  }

  // ── Calendar Heatmap ─────────────────────────────────────────────────────
  function renderCalendar() {
    const entries = Object.entries(calendarData);
    if (!entries.length) return <p className="text-text-secondary text-sm">No trade data</p>;
    const allDates = entries.map(([d]) => d).sort();
    const start = new Date(allDates[0]);
    start.setDate(start.getDate() - start.getDay());
    const end = new Date(allDates[allDates.length - 1]);
    const weeks: { date: string; pnl: number | null }[][] = [];
    let week: { date: string; pnl: number | null }[] = [];
    const cur = new Date(start);
    while (cur <= end) {
      const ds = cur.toISOString().split("T")[0];
      week.push({ date: ds, pnl: calendarData[ds] ?? null });
      if (week.length === 7) { weeks.push(week); week = []; }
      cur.setDate(cur.getDate() + 1);
    }
    if (week.length) weeks.push(week);
    const cellSize = 14, gap = 2;

    return (
      <div className="overflow-x-auto">
        <svg width={weeks.length * (cellSize + gap) + 20} height={7 * (cellSize + gap) + 20}>
          {["S", "M", "T", "W", "T", "F", "S"].map((d, i) => (
            <text key={d + i} x={4} y={i * (cellSize + gap) + 12 + 10} fill="#555" fontSize="8">{d}</text>
          ))}
          {weeks.map((wk, wi) =>
            wk.map((day, di) => {
              let fill = "#1a1a1a";
              if (day.pnl !== null) {
                const intensity = Math.min(Math.abs(day.pnl) / 3000, 1);
                fill = day.pnl >= 0
                  ? `rgba(34,197,94,${0.15 + intensity * 0.75})`
                  : `rgba(224,82,82,${0.15 + intensity * 0.75})`;
              }
              return (
                <rect key={day.date} x={wi * (cellSize + gap) + 20} y={di * (cellSize + gap) + 10}
                  width={cellSize} height={cellSize} rx={2} fill={fill}>
                  <title>{`${day.date}: ${day.pnl !== null ? fmt(day.pnl) : "No trades"}`}</title>
                </rect>
              );
            })
          )}
        </svg>
      </div>
    );
  }

  // ── Add Trade Handler ────────────────────────────────────────────────────
  function handleAddTrade(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const symbol = (fd.get("symbol") as string).toUpperCase();
    const side = fd.get("side") as "Long" | "Short";
    const entry = parseFloat(fd.get("entry") as string);
    const exit = parseFloat(fd.get("exit") as string);
    const qty = parseInt(fd.get("qty") as string);
    const date = fd.get("date") as string;
    const notes = fd.get("notes") as string;
    const pnl = Math.round((exit - entry) * qty * (side === "Long" ? 1 : -1) * 100) / 100;
    const pnlPct = Math.round((pnl / (entry * qty)) * 10000) / 100;
    const risk = entry * 0.015;
    const rMultiple = Math.round((Math.abs(exit - entry) / risk) * (pnl >= 0 ? 1 : -1) * 100) / 100;

    const newTrade: Trade = { id: `t-${Date.now()}`, date, symbol, side, entry, exit, qty, pnl, pnlPct, rMultiple, duration: "—", notes };
    setAllTrades((prev) => [newTrade, ...prev]);
    setShowAddModal(false);
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-bg-primary p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <BookOpen className="w-7 h-7 text-profit" />
          <h1 className="font-heading text-2xl font-bold text-white">Trade Journal</h1>
          <span className="text-text-tertiary text-sm font-mono ml-2">{filtered.length} trades</span>
        </div>
        <div className="flex gap-3 items-center">
          <ExportMenu
            data={filtered as unknown as Record<string, unknown>[]}
            filename="lumare_trade_journal"
            title="Trade Journal"
            columns={[
              { key: "date", label: "Date" },
              { key: "symbol", label: "Symbol" },
              { key: "side", label: "Side" },
              { key: "entry", label: "Entry" },
              { key: "exit", label: "Exit" },
              { key: "qty", label: "Qty" },
              { key: "pnl", label: "P&L ($)" },
              { key: "pnlPct", label: "P&L (%)" },
              { key: "rMultiple", label: "R-Multiple" },
              { key: "duration", label: "Duration" },
              { key: "notes", label: "Notes" },
            ]}
          />
          <button onClick={() => setShowFilters(!showFilters)} className="flex items-center gap-2 px-4 py-2 rounded-button border border-border text-text-secondary hover:text-white hover:border-profit/40 transition-colors text-sm">
            <Filter className="w-4 h-4" /> Filters
          </button>
          <button onClick={() => setShowAddModal(true)} className="flex items-center gap-2 px-4 py-2 rounded-button bg-profit/10 text-profit hover:bg-profit/20 transition-colors text-sm font-medium">
            <Plus className="w-4 h-4" /> Add Trade
          </button>
        </div>
      </div>

      {/* Filters */}
      {showFilters && (
        <Card className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-text-tertiary text-xs block mb-1">From</label>
            <input type="date" value={filters.dateFrom} onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })} className="bg-bg-elevated border border-border rounded-chip px-3 py-1.5 text-sm text-white" />
          </div>
          <div>
            <label className="text-text-tertiary text-xs block mb-1">To</label>
            <input type="date" value={filters.dateTo} onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })} className="bg-bg-elevated border border-border rounded-chip px-3 py-1.5 text-sm text-white" />
          </div>
          <div>
            <label className="text-text-tertiary text-xs block mb-1">Symbol</label>
            <select value={filters.symbol} onChange={(e) => setFilters({ ...filters, symbol: e.target.value })} className="bg-bg-elevated border border-border rounded-chip px-3 py-1.5 text-sm text-white">
              <option value="">All</option>
              {uniqueSymbols.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-text-tertiary text-xs block mb-1">Side</label>
            <select value={filters.side} onChange={(e) => setFilters({ ...filters, side: e.target.value })} className="bg-bg-elevated border border-border rounded-chip px-3 py-1.5 text-sm text-white">
              <option value="">All</option>
              <option value="Long">Long</option>
              <option value="Short">Short</option>
            </select>
          </div>
          <div>
            <label className="text-text-tertiary text-xs block mb-1">Result</label>
            <select value={filters.result} onChange={(e) => setFilters({ ...filters, result: e.target.value })} className="bg-bg-elevated border border-border rounded-chip px-3 py-1.5 text-sm text-white">
              <option value="">All</option>
              <option value="Win">Win</option>
              <option value="Loss">Loss</option>
            </select>
          </div>
          <button onClick={() => setFilters({ dateFrom: "", dateTo: "", symbol: "", side: "", result: "" })} className="text-text-tertiary hover:text-white text-xs underline pb-1">Clear</button>
        </Card>
      )}

      {/* Performance Dashboard */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
        {[
          { label: "Total P&L", value: fmt(stats.totalPnl), color: pnlColor(stats.totalPnl), icon: TrendingUp },
          { label: "Win Rate", value: `${stats.winRate.toFixed(1)}%`, color: stats.winRate >= 50 ? "text-profit" : "text-loss", icon: Target },
          { label: "Avg Win", value: fmt(stats.avgWin), color: "text-profit", icon: TrendingUp },
          { label: "Avg Loss", value: fmt(stats.avgLoss), color: "text-loss", icon: TrendingDown },
          { label: "Profit Factor", value: stats.profitFactor === Infinity ? "∞" : stats.profitFactor.toFixed(2), color: stats.profitFactor >= 1.5 ? "text-profit" : "text-text-secondary", icon: BarChart3 },
          { label: "Best Trade", value: fmt(stats.best), color: "text-profit", icon: Trophy },
          { label: "Worst Trade", value: fmt(stats.worst), color: "text-loss", icon: Skull },
          { label: "Total Trades", value: String(stats.total), color: "text-white", icon: Hash },
        ].map((s) => (
          <Card key={s.label} padding="sm" className="space-y-1">
            <div className="flex items-center gap-1.5">
              <s.icon className={`w-3.5 h-3.5 ${s.color}`} />
              <span className="text-text-tertiary text-[10px] uppercase tracking-wider">{s.label}</span>
            </div>
            <p className={`text-lg font-bold font-mono ${s.color}`}>{s.value}</p>
          </Card>
        ))}
      </div>

      {/* Streak Tracker */}
      <Card padding="sm" className="flex items-center gap-4">
        <Flame className={`w-5 h-5 ${stats.streakType === "W" ? "text-profit" : stats.streakType === "L" ? "text-loss" : "text-text-tertiary"}`} />
        <span className="text-text-secondary text-sm">Current Streak:</span>
        <span className={`font-mono font-bold text-lg ${stats.streakType === "W" ? "text-profit" : stats.streakType === "L" ? "text-loss" : "text-text-tertiary"}`}>
          {stats.streak}{stats.streakType !== "—" ? stats.streakType : ""} {stats.streakType === "W" && stats.streak >= 3 ? "🔥" : ""}
        </span>
      </Card>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card padding="md" className="lg:col-span-2">
          <h2 className="font-heading text-sm font-semibold text-white mb-3 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-profit" /> Equity Curve</h2>
          {renderEquityCurve()}
        </Card>
        <Card padding="md">
          <h2 className="font-heading text-sm font-semibold text-white mb-3 flex items-center gap-2"><Calendar className="w-4 h-4 text-profit" /> Daily P&L Heatmap</h2>
          {renderCalendar()}
        </Card>
      </div>

      {/* Symbol Breakdown */}
      <Card padding="none">
        <div className="px-5 py-3 border-b border-border">
          <h2 className="font-heading text-sm font-semibold text-white flex items-center gap-2"><BarChart3 className="w-4 h-4 text-profit" /> Performance by Symbol</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-tertiary text-xs uppercase tracking-wider">
                <th className="text-left px-5 py-2">Symbol</th>
                <th className="text-right px-5 py-2">Trades</th>
                <th className="text-right px-5 py-2">Win Rate</th>
                <th className="text-right px-5 py-2">Net P&L</th>
              </tr>
            </thead>
            <tbody>
              {symbolStats.map((s) => (
                <tr key={s.symbol} className="border-t border-border hover:bg-bg-elevated transition-colors">
                  <td className="px-5 py-2 font-mono font-semibold text-white">{s.symbol}</td>
                  <td className="px-5 py-2 text-right font-mono text-text-secondary">{s.trades}</td>
                  <td className="px-5 py-2 text-right font-mono"><span className={s.winRate >= 50 ? "text-profit" : "text-loss"}>{s.winRate.toFixed(0)}%</span></td>
                  <td className={`px-5 py-2 text-right font-mono font-semibold ${pnlColor(s.pnl)}`}>{fmt(s.pnl)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Trade Log Table */}
      <Card padding="none">
        <div className="px-5 py-3 border-b border-border">
          <h2 className="font-heading text-sm font-semibold text-white flex items-center gap-2"><BookOpen className="w-4 h-4 text-profit" /> Trade Log</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-text-tertiary text-xs uppercase tracking-wider">
                {([["date","Date"],["symbol","Symbol"],["side","Side"],["entry","Entry"],["exit","Exit"],["pnl","P&L ($)"],["pnlPct","P&L (%)"],["rMultiple","R-Mult"],["duration","Duration"],["notes","Notes"]] as [keyof Trade, string][]).map(([key, label]) => (
                  <th key={key} onClick={() => handleSort(key)} className="text-left px-4 py-2.5 cursor-pointer hover:text-white transition-colors select-none whitespace-nowrap">
                    {label}<SortIcon col={key} />
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.id} className="border-t border-border hover:bg-bg-elevated transition-colors">
                  <td className="px-4 py-2.5 font-mono text-text-secondary whitespace-nowrap">{t.date}</td>
                  <td className="px-4 py-2.5 font-mono font-semibold text-white">{t.symbol}</td>
                  <td className="px-4 py-2.5">
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-chip ${t.side === "Long" ? "bg-profit/10 text-profit" : "bg-loss/10 text-loss"}`}>
                      {t.side}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-text-secondary">${t.entry.toFixed(2)}</td>
                  <td className="px-4 py-2.5 font-mono text-text-secondary">${t.exit.toFixed(2)}</td>
                  <td className={`px-4 py-2.5 font-mono font-semibold ${pnlColor(t.pnl)}`}>{fmt(t.pnl)}</td>
                  <td className={`px-4 py-2.5 font-mono ${pnlColor(t.pnlPct)}`}>{fmtPct(t.pnlPct)}</td>
                  <td className="px-4 py-2.5 font-mono">
                    <span className={`px-1.5 py-0.5 rounded-chip text-xs ${pnlBg(t.rMultiple)} ${pnlColor(t.rMultiple)}`}>{t.rMultiple > 0 ? "+" : ""}{t.rMultiple}R</span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-text-tertiary">{t.duration}</td>
                  <td className="px-4 py-2.5 text-text-secondary max-w-[200px] truncate">{t.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Add Trade Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <Card className="w-full max-w-lg relative">
            <button onClick={() => setShowAddModal(false)} className="absolute top-4 right-4 text-text-tertiary hover:text-white"><X className="w-5 h-5" /></button>
            <h2 className="font-heading text-lg font-bold text-white mb-5 flex items-center gap-2"><Plus className="w-5 h-5 text-profit" /> Log New Trade</h2>
            <form onSubmit={handleAddTrade} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-text-tertiary text-xs block mb-1">Symbol</label>
                  <input name="symbol" required placeholder="AAPL" className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-2 text-sm text-white font-mono placeholder:text-text-tertiary focus:border-profit/50 outline-none" />
                </div>
                <div>
                  <label className="text-text-tertiary text-xs block mb-1">Side</label>
                  <select name="side" defaultValue="Long" className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-2 text-sm text-white">
                    <option value="Long">Long</option>
                    <option value="Short">Short</option>
                  </select>
                </div>
                <div>
                  <label className="text-text-tertiary text-xs block mb-1">Entry Price</label>
                  <input name="entry" type="number" step="0.01" required placeholder="150.00" className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-2 text-sm text-white font-mono placeholder:text-text-tertiary focus:border-profit/50 outline-none" />
                </div>
                <div>
                  <label className="text-text-tertiary text-xs block mb-1">Exit Price</label>
                  <input name="exit" type="number" step="0.01" required placeholder="155.00" className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-2 text-sm text-white font-mono placeholder:text-text-tertiary focus:border-profit/50 outline-none" />
                </div>
                <div>
                  <label className="text-text-tertiary text-xs block mb-1">Quantity</label>
                  <input name="qty" type="number" required placeholder="100" className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-2 text-sm text-white font-mono placeholder:text-text-tertiary focus:border-profit/50 outline-none" />
                </div>
                <div>
                  <label className="text-text-tertiary text-xs block mb-1">Date</label>
                  <input name="date" type="date" required defaultValue={new Date().toISOString().split("T")[0]} className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-2 text-sm text-white focus:border-profit/50 outline-none" />
                </div>
              </div>
              <div>
                <label className="text-text-tertiary text-xs block mb-1">Notes</label>
                <textarea name="notes" rows={2} placeholder="Trade thesis, setup, lessons learned..." className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-2 text-sm text-white placeholder:text-text-tertiary focus:border-profit/50 outline-none resize-none" />
              </div>
              <button type="submit" className="w-full py-2.5 rounded-button bg-profit/15 text-profit font-semibold hover:bg-profit/25 transition-colors text-sm">
                Log Trade
              </button>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}
