"use client";

import { useEffect, useState, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Building2,
  Filter,
  Layers,
  BarChart3,
  TrendingUp,
  TrendingDown,
  Zap,
  RefreshCw,
  Search,
  AlertTriangle,
} from "lucide-react";

// ─── Types ──────────────────────────────────────────────────────────────────

interface DarkPoolPrint {
  id: string;
  time: string;
  symbol: string;
  price: number;
  size: number;
  notional: number;
  venue: string;
  side: "Buy" | "Sell";
  isNew?: boolean;
}

interface InstitutionalFiling {
  id: string;
  institution: string;
  symbol: string;
  action: "New" | "Added" | "Reduced" | "Sold";
  shares: number;
  value: number;
  filingDate: string;
}

type SizeFilter = "ALL" | "1M" | "5M" | "10M";
type SideFilter = "ALL" | "Buy" | "Sell";
type ActionFilter = "ALL" | "New" | "Added" | "Reduced" | "Sold";

// ─── Mock Data Generators ───────────────────────────────────────────────────

const SYMBOLS = [
  "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "GOOGL", "META", "JPM", "V", "UNH",
  "XOM", "JNJ", "WMT", "PG", "MA", "HD", "BAC", "AVGO", "CVX", "LLY",
  "KO", "PEP", "MRK", "ABBV", "CRM", "TMO", "COST", "NFLX", "AMD", "ORCL",
];

const VENUES = ["FADF", "UBSS", "CDRG", "NSDQ", "ARCX", "EDGX", "BATS", "IEX", "MEMX", "LTSE"];

const INSTITUTIONS = [
  "Berkshire Hathaway", "Bridgewater Associates", "Renaissance Technologies",
  "Citadel Advisors", "BlackRock Inc.", "Vanguard Group", "Two Sigma Investments",
  "D.E. Shaw & Co.", "Point72 Asset Mgmt", "Millennium Management",
  "Tiger Global Management", "Coatue Management", "Dragoneer Investment",
  "Lone Pine Capital", "Viking Global Investors",
];

const SECTORS: Record<string, string> = {
  AAPL: "Technology", MSFT: "Technology", NVDA: "Technology", AVGO: "Technology",
  AMD: "Technology", CRM: "Technology", ORCL: "Technology", NFLX: "Communication",
  GOOGL: "Communication", META: "Communication",
  TSLA: "Consumer Disc.", AMZN: "Consumer Disc.", HD: "Consumer Disc.",
  JPM: "Financials", V: "Financials", MA: "Financials", BAC: "Financials",
  UNH: "Healthcare", JNJ: "Healthcare", LLY: "Healthcare", MRK: "Healthcare",
  ABBV: "Healthcare", TMO: "Healthcare",
  XOM: "Energy", CVX: "Energy",
  WMT: "Consumer Staples", PG: "Consumer Staples", KO: "Consumer Staples",
  PEP: "Consumer Staples", COST: "Consumer Staples",
};

function randomBetween(min: number, max: number) {
  return Math.random() * (max - min) + min;
}

function generatePrice(symbol: string): number {
  const prices: Record<string, number> = {
    AAPL: 198, MSFT: 445, NVDA: 142, TSLA: 265, AMZN: 210, GOOGL: 178,
    META: 595, JPM: 242, V: 310, UNH: 570, XOM: 112, JNJ: 158,
    WMT: 92, PG: 172, MA: 520, HD: 405, BAC: 44, AVGO: 185,
    CVX: 158, LLY: 825, KO: 62, PEP: 168, MRK: 128, ABBV: 192,
    CRM: 325, TMO: 572, COST: 935, NFLX: 1020, AMD: 168, ORCL: 182,
  };
  const base = prices[symbol] || 150;
  return +(base + randomBetween(-2, 2)).toFixed(2);
}

function generateDarkPoolPrint(id: number, hourOffset: number): DarkPoolPrint {
  const symbol = SYMBOLS[Math.floor(Math.random() * SYMBOLS.length)];
  const price = generatePrice(symbol);
  const sizeMultiplier = Math.random() < 0.15 ? randomBetween(50000, 200000) :
    Math.random() < 0.35 ? randomBetween(15000, 50000) : randomBetween(3000, 15000);
  const size = Math.round(sizeMultiplier);
  const notional = price * size;
  const hour = 9 + Math.floor(hourOffset);
  const minute = Math.floor(Math.random() * 60);
  const second = Math.floor(Math.random() * 60);

  return {
    id: `dp-${id}`,
    time: `${hour.toString().padStart(2, "0")}:${minute.toString().padStart(2, "0")}:${second.toString().padStart(2, "0")}`,
    symbol,
    price,
    size,
    notional,
    venue: VENUES[Math.floor(Math.random() * VENUES.length)],
    side: Math.random() > 0.48 ? "Buy" : "Sell",
  };
}

function generateFilings(): InstitutionalFiling[] {
  const actions: InstitutionalFiling["action"][] = ["New", "Added", "Reduced", "Sold"];
  const filings: InstitutionalFiling[] = [];

  for (let i = 0; i < 24; i++) {
    const symbol = SYMBOLS[Math.floor(Math.random() * 20)];
    const action = actions[Math.floor(Math.random() * actions.length)];
    const shares = Math.round(randomBetween(50000, 8000000));
    const price = generatePrice(symbol);
    const day = Math.floor(randomBetween(1, 26));

    filings.push({
      id: `f-${i}`,
      institution: INSTITUTIONS[Math.floor(Math.random() * INSTITUTIONS.length)],
      symbol,
      action,
      shares,
      value: shares * price,
      filingDate: `2026-03-${day.toString().padStart(2, "0")}`,
    });
  }
  return filings.sort((a, b) => b.filingDate.localeCompare(a.filingDate));
}

function generateInitialPrints(): DarkPoolPrint[] {
  const prints: DarkPoolPrint[] = [];
  for (let i = 0; i < 45; i++) {
    prints.push(generateDarkPoolPrint(i, randomBetween(0, 6.5)));
  }
  return prints.sort((a, b) => b.time.localeCompare(a.time));
}

// ─── Formatting Helpers ─────────────────────────────────────────────────────

function formatNotional(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function formatShares(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
  return n.toLocaleString();
}

function notionalColor(n: number): string {
  if (n >= 10_000_000) return "text-amber-400";
  if (n >= 5_000_000) return "text-purple-400";
  if (n >= 1_000_000) return "text-blue-400";
  return "text-text-secondary";
}

function notionalBg(n: number): string {
  if (n >= 10_000_000) return "bg-amber-400/5 border-l-2 border-l-amber-400/40";
  if (n >= 5_000_000) return "bg-purple-400/5 border-l-2 border-l-purple-400/30";
  if (n >= 1_000_000) return "bg-blue-400/5 border-l-2 border-l-blue-400/20";
  return "";
}

function actionColor(action: string): string {
  switch (action) {
    case "New": return "text-emerald-400 bg-emerald-400/10";
    case "Added": return "text-blue-400 bg-blue-400/10";
    case "Reduced": return "text-orange-400 bg-orange-400/10";
    case "Sold": return "text-red-400 bg-red-400/10";
    default: return "text-text-secondary";
  }
}

// ─── SVG Bar Chart Component ────────────────────────────────────────────────

function NetFlowChart({ prints }: { prints: DarkPoolPrint[] }) {
  const data = useMemo(() => {
    const flowMap: Record<string, number> = {};
    prints.forEach((p) => {
      const dir = p.side === "Buy" ? 1 : -1;
      flowMap[p.symbol] = (flowMap[p.symbol] || 0) + p.notional * dir;
    });
    return Object.entries(flowMap)
      .map(([symbol, flow]) => ({ symbol, flow }))
      .sort((a, b) => Math.abs(b.flow) - Math.abs(a.flow))
      .slice(0, 10);
  }, [prints]);

  const maxAbs = Math.max(...data.map((d) => Math.abs(d.flow)), 1);
  const barHeight = 28;
  const chartHeight = data.length * barHeight + 20;
  const midX = 220;
  const barMaxWidth = 160;

  return (
    <svg width="100%" viewBox={`0 0 460 ${chartHeight}`} className="overflow-visible">
      <line x1={midX} y1={0} x2={midX} y2={chartHeight} stroke="#1a1a1a" strokeWidth={1} />
      {data.map((d, i) => {
        const width = (Math.abs(d.flow) / maxAbs) * barMaxWidth;
        const isPositive = d.flow >= 0;
        const x = isPositive ? midX + 2 : midX - width - 2;
        const y = i * barHeight + 10;
        const fill = isPositive ? "#10b981" : "#ef4444";

        return (
          <g key={d.symbol}>
            <text x={midX - (isPositive ? 8 : -8)} y={y + 16} fill="#a3a3a3"
              fontSize="11" fontFamily="monospace"
              textAnchor={isPositive ? "end" : "start"}>
              {d.symbol}
            </text>
            <rect x={x} y={y + 4} width={width} height={18} rx={3} fill={fill} opacity={0.7} />
            <text x={isPositive ? x + width + 6 : x - 6} y={y + 16}
              fill={fill} fontSize="10" fontFamily="monospace"
              textAnchor={isPositive ? "start" : "end"}>
              {formatNotional(Math.abs(d.flow))}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── Sector Flow Component ──────────────────────────────────────────────────

function SectorFlow({ prints }: { prints: DarkPoolPrint[] }) {
  const sectors = useMemo(() => {
    const map: Record<string, { buy: number; sell: number }> = {};
    prints.forEach((p) => {
      const sector = SECTORS[p.symbol] || "Other";
      if (!map[sector]) map[sector] = { buy: 0, sell: 0 };
      if (p.side === "Buy") map[sector].buy += p.notional;
      else map[sector].sell += p.notional;
    });
    return Object.entries(map)
      .map(([name, { buy, sell }]) => ({ name, buy, sell, net: buy - sell }))
      .sort((a, b) => (b.buy + b.sell) - (a.buy + a.sell));
  }, [prints]);

  const maxVol = Math.max(...sectors.map((s) => s.buy + s.sell), 1);

  return (
    <div className="space-y-3">
      {sectors.map((s) => (
        <div key={s.name}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-text-secondary">{s.name}</span>
            <span className={`text-xs font-mono ${s.net >= 0 ? "text-emerald-400" : "text-red-400"}`}>
              {s.net >= 0 ? "+" : ""}{formatNotional(s.net)}
            </span>
          </div>
          <div className="h-2 rounded-full bg-[#1a1a1a] overflow-hidden flex">
            <div className="h-full bg-emerald-500/60 rounded-l-full"
              style={{ width: `${(s.buy / maxVol) * 100}%` }} />
            <div className="h-full bg-red-500/60 rounded-r-full"
              style={{ width: `${(s.sell / maxVol) * 100}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── Main Page Component ────────────────────────────────────────────────────

export default function FlowPage() {
  const [prints, setPrints] = useState<DarkPoolPrint[]>([]);
  const [filings] = useState<InstitutionalFiling[]>(generateFilings);
  const [printCounter, setPrintCounter] = useState(50);

  // Filters — Dark Pool
  const [dpSymbolFilter, setDpSymbolFilter] = useState("");
  const [dpSizeFilter, setDpSizeFilter] = useState<SizeFilter>("ALL");
  const [dpSideFilter, setDpSideFilter] = useState<SideFilter>("ALL");

  // Filters — 13F
  const [filingSearch, setFilingSearch] = useState("");
  const [filingAction, setFilingAction] = useState<ActionFilter>("ALL");

  // Initialize prints
  useEffect(() => {
    setPrints(generateInitialPrints());
  }, []);

  // Stream new prints every 3-5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      const newPrint = generateDarkPoolPrint(printCounter, randomBetween(0, 6.5));
      newPrint.time = new Date().toLocaleTimeString("en-US", { hour12: false });
      newPrint.isNew = true;
      setPrints((prev) => [newPrint, ...prev].slice(0, 200));
      setPrintCounter((c) => c + 1);

      setTimeout(() => {
        setPrints((prev) =>
          prev.map((p) => (p.id === newPrint.id ? { ...p, isNew: false } : p))
        );
      }, 2000);
    }, randomBetween(3000, 5000));

    return () => clearInterval(interval);
  }, [printCounter]);

  // ─── Computed Values ────────────────────────────────────────────────────

  const filteredPrints = useMemo(() => {
    return prints.filter((p) => {
      if (dpSymbolFilter && !p.symbol.toLowerCase().includes(dpSymbolFilter.toLowerCase())) return false;
      if (dpSizeFilter === "1M" && p.notional < 1_000_000) return false;
      if (dpSizeFilter === "5M" && p.notional < 5_000_000) return false;
      if (dpSizeFilter === "10M" && p.notional < 10_000_000) return false;
      if (dpSideFilter !== "ALL" && p.side !== dpSideFilter) return false;
      return true;
    });
  }, [prints, dpSymbolFilter, dpSizeFilter, dpSideFilter]);

  const filteredFilings = useMemo(() => {
    return filings.filter((f) => {
      if (filingSearch) {
        const q = filingSearch.toLowerCase();
        if (!f.institution.toLowerCase().includes(q) && !f.symbol.toLowerCase().includes(q)) return false;
      }
      if (filingAction !== "ALL" && f.action !== filingAction) return false;
      return true;
    });
  }, [filings, filingSearch, filingAction]);

  const stats = useMemo(() => {
    const totalVolume = prints.reduce((s, p) => s + p.notional, 0);
    const buys = prints.filter((p) => p.side === "Buy");
    const buyVol = buys.reduce((s, p) => s + p.notional, 0);
    const sellVol = totalVolume - buyVol;
    const ratio = sellVol > 0 ? buyVol / sellVol : 0;
    const avgBlock = prints.length > 0 ? totalVolume / prints.length : 0;
    return { totalVolume, ratio, avgBlock, count: prints.length };
  }, [prints]);

  const { accumulated, distributed } = useMemo(() => {
    const netMap: Record<string, number> = {};
    filings.forEach((f) => {
      const dir = f.action === "New" || f.action === "Added" ? 1 : -1;
      netMap[f.symbol] = (netMap[f.symbol] || 0) + f.value * dir;
    });
    const sorted = Object.entries(netMap).sort((a, b) => b[1] - a[1]);
    return {
      accumulated: sorted.filter(([, v]) => v > 0).slice(0, 5),
      distributed: sorted.filter(([, v]) => v < 0).slice(0, 5).map(([s, v]) => [s, Math.abs(v)] as [string, number]),
    };
  }, [filings]);

  const unusualPrints = useMemo(() => {
    const avgNotional = prints.length > 0 ? prints.reduce((s, p) => s + p.notional, 0) / prints.length : 0;
    return prints.filter((p) => p.notional > avgNotional * 4).slice(0, 5);
  }, [prints]);

  // ─── Render ─────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl font-bold text-text-primary flex items-center gap-3">
            <Layers className="w-7 h-7 text-purple-400" />
            Dark Pool &amp; Institutional Flow
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Real-time block trades, institutional filings, and smart money tracking
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            LIVE
          </span>
        </div>
      </div>

      {/* Summary Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-purple-500/10">
              <Activity className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="text-xs text-text-secondary">Total Dark Pool Volume</p>
              <p className="text-xl font-mono font-bold text-text-primary">
                {formatNotional(stats.totalVolume)}
              </p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-emerald-500/10">
              <BarChart3 className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <p className="text-xs text-text-secondary">Buy / Sell Ratio</p>
              <p className={`text-xl font-mono font-bold ${stats.ratio >= 1 ? "text-emerald-400" : "text-red-400"}`}>
                {stats.ratio.toFixed(2)}x
              </p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-blue-500/10">
              <Zap className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="text-xs text-text-secondary">Avg Block Size</p>
              <p className="text-xl font-mono font-bold text-text-primary">
                {formatNotional(stats.avgBlock)}
              </p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-amber-500/10">
              <Layers className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <p className="text-xs text-text-secondary"># of Prints</p>
              <p className="text-xl font-mono font-bold text-text-primary">
                {stats.count.toLocaleString()}
              </p>
            </div>
          </div>
        </Card>
      </div>

      {/* Main Grid: Dark Pool Prints + Charts */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Dark Pool Table — 2 columns */}
        <Card className="xl:col-span-2" padding="none">
          <div className="p-4 border-b border-border">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-heading text-lg font-bold text-text-primary flex items-center gap-2">
                <Activity className="w-5 h-5 text-purple-400" />
                Dark Pool Prints
              </h2>
              <span className="text-xs text-text-secondary font-mono">
                {filteredPrints.length} prints
              </span>
            </div>
            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-secondary" />
                <input
                  type="text"
                  placeholder="Symbol..."
                  value={dpSymbolFilter}
                  onChange={(e) => setDpSymbolFilter(e.target.value)}
                  className="pl-8 pr-3 py-1.5 text-xs rounded-md bg-[#0d0d0d] border border-border text-text-primary placeholder-text-secondary/50 focus:outline-none focus:border-purple-500/50 w-28"
                />
              </div>
              <div className="flex items-center gap-1 text-xs">
                <Filter className="w-3.5 h-3.5 text-text-secondary" />
                {(["ALL", "1M", "5M", "10M"] as SizeFilter[]).map((f) => (
                  <button key={f} onClick={() => setDpSizeFilter(f)}
                    className={`px-2 py-1 rounded text-xs transition-colors ${
                      dpSizeFilter === f
                        ? "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                        : "text-text-secondary hover:text-text-primary hover:bg-[#1a1a1a]"
                    }`}>
                    {f === "ALL" ? "All" : `$${f}+`}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1 text-xs">
                {(["ALL", "Buy", "Sell"] as SideFilter[]).map((f) => (
                  <button key={f} onClick={() => setDpSideFilter(f)}
                    className={`px-2 py-1 rounded text-xs transition-colors ${
                      dpSideFilter === f
                        ? f === "Buy" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : f === "Sell" ? "bg-red-500/20 text-red-300 border border-red-500/30"
                          : "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                        : "text-text-secondary hover:text-text-primary hover:bg-[#1a1a1a]"
                    }`}>
                    {f}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {/* Table */}
          <div className="overflow-auto max-h-[520px]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#0d0d0d] z-10">
                <tr className="text-text-secondary border-b border-border">
                  <th className="text-left px-4 py-2.5 font-medium">Time</th>
                  <th className="text-left px-4 py-2.5 font-medium">Symbol</th>
                  <th className="text-right px-4 py-2.5 font-medium">Price</th>
                  <th className="text-right px-4 py-2.5 font-medium">Size</th>
                  <th className="text-right px-4 py-2.5 font-medium">Notional</th>
                  <th className="text-left px-4 py-2.5 font-medium">Venue</th>
                  <th className="text-center px-4 py-2.5 font-medium">Side</th>
                </tr>
              </thead>
              <tbody>
                {filteredPrints.slice(0, 60).map((p) => (
                  <tr key={p.id}
                    className={`border-b border-border/50 hover:bg-[#111111] transition-all ${notionalBg(p.notional)} ${
                      p.isNew ? "animate-pulse bg-purple-500/10" : ""
                    }`}>
                    <td className="px-4 py-2 font-mono text-text-secondary">{p.time}</td>
                    <td className="px-4 py-2 font-semibold text-text-primary">{p.symbol}</td>
                    <td className="px-4 py-2 font-mono text-right text-text-primary">
                      ${p.price.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 font-mono text-right text-text-secondary">
                      {formatShares(p.size)}
                    </td>
                    <td className={`px-4 py-2 font-mono text-right font-semibold ${notionalColor(p.notional)}`}>
                      {formatNotional(p.notional)}
                      {p.notional >= 10_000_000 && (
                        <AlertTriangle className="inline w-3 h-3 ml-1 text-amber-400" />
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-[#1a1a1a] text-text-secondary font-mono">
                        {p.venue}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-center">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold ${
                        p.side === "Buy"
                          ? "bg-emerald-500/15 text-emerald-400"
                          : "bg-red-500/15 text-red-400"
                      }`}>
                        {p.side === "Buy" ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                        {p.side}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Right Column: Charts + Analysis */}
        <div className="space-y-6">
          {/* Net Flow Chart */}
          <Card>
            <h3 className="font-heading text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <BarChart3 className="w-4 h-4 text-blue-400" />
              Net Flow by Symbol
            </h3>
            <NetFlowChart prints={prints} />
            <div className="flex items-center justify-center gap-4 mt-3 text-[10px] text-text-secondary">
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500/70" /> Net Buying
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-red-500/70" /> Net Selling
              </span>
            </div>
          </Card>

          {/* Sector Breakdown */}
          <Card>
            <h3 className="font-heading text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              Sector Flow Breakdown
            </h3>
            <SectorFlow prints={prints} />
          </Card>

          {/* Unusual Activity */}
          <Card>
            <h3 className="font-heading text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              Unusual Activity
            </h3>
            <div className="space-y-2">
              {unusualPrints.length === 0 && (
                <p className="text-xs text-text-secondary italic">No unusual prints detected</p>
              )}
              {unusualPrints.map((p) => (
                <div key={p.id} className="flex items-center justify-between py-1.5 px-2 rounded bg-amber-400/5 border border-amber-400/10">
                  <div className="flex items-center gap-2">
                    <Zap className="w-3.5 h-3.5 text-amber-400" />
                    <span className="text-xs font-semibold text-text-primary">{p.symbol}</span>
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${p.side === "Buy" ? "bg-emerald-500/15 text-emerald-400" : "bg-red-500/15 text-red-400"}`}>
                      {p.side}
                    </span>
                  </div>
                  <span className="text-xs font-mono text-amber-400 font-semibold">
                    {formatNotional(p.notional)}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>

      {/* 13F Institutional Holdings */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Card className="xl:col-span-2" padding="none">
          <div className="p-4 border-b border-border">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-heading text-lg font-bold text-text-primary flex items-center gap-2">
                <Building2 className="w-5 h-5 text-blue-400" />
                13F Institutional Holdings
              </h2>
              <span className="text-xs text-text-secondary font-mono">
                {filteredFilings.length} filings
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-secondary" />
                <input
                  type="text"
                  placeholder="Institution or symbol..."
                  value={filingSearch}
                  onChange={(e) => setFilingSearch(e.target.value)}
                  className="pl-8 pr-3 py-1.5 text-xs rounded-md bg-[#0d0d0d] border border-border text-text-primary placeholder-text-secondary/50 focus:outline-none focus:border-blue-500/50 w-48"
                />
              </div>
              <div className="flex items-center gap-1 text-xs">
                {(["ALL", "New", "Added", "Reduced", "Sold"] as ActionFilter[]).map((f) => (
                  <button key={f} onClick={() => setFilingAction(f)}
                    className={`px-2 py-1 rounded text-xs transition-colors ${
                      filingAction === f
                        ? f === "New" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                          : f === "Added" ? "bg-blue-500/20 text-blue-300 border border-blue-500/30"
                          : f === "Reduced" ? "bg-orange-500/20 text-orange-300 border border-orange-500/30"
                          : f === "Sold" ? "bg-red-500/20 text-red-300 border border-red-500/30"
                          : "bg-purple-500/20 text-purple-300 border border-purple-500/30"
                        : "text-text-secondary hover:text-text-primary hover:bg-[#1a1a1a]"
                    }`}>
                    {f}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className="overflow-auto max-h-[420px]">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[#0d0d0d] z-10">
                <tr className="text-text-secondary border-b border-border">
                  <th className="text-left px-4 py-2.5 font-medium">Institution</th>
                  <th className="text-left px-4 py-2.5 font-medium">Symbol</th>
                  <th className="text-center px-4 py-2.5 font-medium">Action</th>
                  <th className="text-right px-4 py-2.5 font-medium">Shares</th>
                  <th className="text-right px-4 py-2.5 font-medium">Value</th>
                  <th className="text-left px-4 py-2.5 font-medium">Filed</th>
                </tr>
              </thead>
              <tbody>
                {filteredFilings.map((f) => (
                  <tr key={f.id} className="border-b border-border/50 hover:bg-[#111111] transition-colors">
                    <td className="px-4 py-2.5 font-semibold text-text-primary max-w-[200px] truncate">
                      {f.institution}
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-text-primary">{f.symbol}</td>
                    <td className="px-4 py-2.5 text-center">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${actionColor(f.action)}`}>
                        {f.action}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-right text-text-secondary">
                      {formatShares(f.shares)}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-right text-text-primary font-semibold">
                      {formatNotional(f.value)}
                    </td>
                    <td className="px-4 py-2.5 text-text-secondary font-mono">{f.filingDate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        {/* Right Column: Accumulation / Distribution */}
        <div className="space-y-6">
          {/* Most Accumulated */}
          <Card>
            <h3 className="font-heading text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              Most Accumulated
            </h3>
            <div className="space-y-2">
              {accumulated.map(([symbol, value], i) => (
                <div key={symbol} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-text-secondary w-4">{i + 1}.</span>
                    <span className="text-xs font-semibold text-text-primary">{symbol}</span>
                  </div>
                  <span className="text-xs font-mono text-emerald-400">+{formatNotional(value)}</span>
                </div>
              ))}
              {accumulated.length === 0 && (
                <p className="text-xs text-text-secondary italic">No accumulation data</p>
              )}
            </div>
          </Card>

          {/* Most Distributed */}
          <Card>
            <h3 className="font-heading text-sm font-bold text-text-primary mb-3 flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-red-400" />
              Most Distributed
            </h3>
            <div className="space-y-2">
              {distributed.map(([symbol, value], i) => (
                <div key={symbol} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-text-secondary w-4">{i + 1}.</span>
                    <span className="text-xs font-semibold text-text-primary">{symbol}</span>
                  </div>
                  <span className="text-xs font-mono text-red-400">-{formatNotional(value)}</span>
                </div>
              ))}
              {distributed.length === 0 && (
                <p className="text-xs text-text-secondary italic">No distribution data</p>
              )}
            </div>
          </Card>

          {/* Legend */}
          <Card>
            <h3 className="font-heading text-sm font-bold text-text-primary mb-3">Print Size Legend</h3>
            <div className="space-y-2 text-xs">
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-sm bg-amber-400" />
                <span className="text-amber-400 font-semibold">$10M+</span>
                <span className="text-text-secondary">Whale block</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-sm bg-purple-400" />
                <span className="text-purple-400 font-semibold">$5M+</span>
                <span className="text-text-secondary">Large institutional</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-sm bg-blue-400" />
                <span className="text-blue-400 font-semibold">$1M+</span>
                <span className="text-text-secondary">Institutional block</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-3 h-3 rounded-sm bg-neutral-600" />
                <span className="text-text-secondary">Standard dark pool</span>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
