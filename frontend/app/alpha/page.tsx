"use client";

import { useEffect, useState, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import {
  Landmark,
  UserCheck,
  BarChart2,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Search,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Target,
  Shield,
  Zap,
  Activity,
  Filter,
  ArrowUpDown,
  Crosshair,
  Flame,
  Eye,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CongressionalTrade {
  politician: string | null;
  ticker: string | null;
  type: string | null;
  date: string | null;
  amount_range: string | null;
}

interface InsiderTransaction {
  insider: string | null;
  ticker: string | null;
  transaction_type: string | null;
  shares: number | null;
  price: number | null;
  date: string | null;
  title: string | null;
}

interface FloatProfile {
  symbol: string;
  float_shares: number | null;
  float_category: string | null;
  short_pct_of_float: number | null;
  squeeze_potential: number | null;
  liquidity_score: number | null;
  volatility_multiplier: number | null;
  market_cap: number | null;
  // Enhanced fields
  avg_volume: number;
  relative_volume: number;
  days_to_cover: number;
  institutional_pct: number;
  insider_pct: number;
  free_float_pct: number;
  cost_to_borrow: number | null;
  ftd_count: number | null;
  dark_pool_pct: number;
  trade_score: number;
  trade_direction: "LONG" | "SHORT" | "NEUTRAL";
  trade_rationale: string;
  momentum_score: number;
  flow_score: number;
  squeeze_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "EXTREME";
}

type Tab = "congressional" | "insider" | "float";
type SortKey =
  | "symbol"
  | "trade_score"
  | "squeeze_score"
  | "short_pct_of_float"
  | "volatility_multiplier"
  | "momentum_score"
  | "flow_score"
  | "days_to_cover"
  | "cost_to_borrow"
  | "dark_pool_pct"
  | "market_cap";
type DirectionFilter = "ALL" | "LONG" | "SHORT" | "NEUTRAL";
type RiskFilter = "ALL" | "LOW" | "MEDIUM" | "HIGH" | "EXTREME";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatShares(val: number | null): string {
  if (val == null) return "--";
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  return val.toFixed(0);
}

function formatVolume(val: number): string {
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(0)}K`;
  return val.toFixed(0);
}

function formatDollars(val: number | null): string {
  if (val == null) return "--";
  if (val >= 1_000_000_000_000) return `$${(val / 1_000_000_000_000).toFixed(2)}T`;
  if (val >= 1_000_000_000) return `$${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  return `$${val.toLocaleString()}`;
}

function scoreColor(score: number): string {
  if (score >= 75) return "text-profit";
  if (score >= 50) return "text-yellow-400";
  if (score >= 25) return "text-orange-400";
  return "text-loss";
}

function scoreBg(score: number): string {
  if (score >= 75) return "bg-profit";
  if (score >= 50) return "bg-yellow-400";
  if (score >= 25) return "bg-orange-400";
  return "bg-loss";
}

function riskColor(risk: string): string {
  switch (risk) {
    case "LOW": return "bg-profit/15 text-profit border border-profit/30";
    case "MEDIUM": return "bg-yellow-400/15 text-yellow-400 border border-yellow-400/30";
    case "HIGH": return "bg-orange-400/15 text-orange-400 border border-orange-400/30";
    case "EXTREME": return "bg-loss/15 text-loss border border-loss/30";
    default: return "bg-text-secondary/15 text-text-secondary";
  }
}

function directionStyle(dir: string): string {
  switch (dir) {
    case "LONG": return "bg-profit/15 text-profit border border-profit/30";
    case "SHORT": return "bg-loss/15 text-loss border border-loss/30";
    default: return "bg-text-secondary/15 text-text-secondary border border-text-secondary/30";
  }
}

// ---------------------------------------------------------------------------
// Circular Score Gauge SVG
// ---------------------------------------------------------------------------

function ScoreGauge({ score, size = 80, label }: { score: number; size?: number; label?: string }) {
  const radius = (size - 10) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.min(Math.max(score, 0), 100) / 100;
  const strokeDashoffset = circumference * (1 - pct);

  let strokeColor = "#ef4444";
  if (score >= 75) strokeColor = "#22c55e";
  else if (score >= 50) strokeColor = "#eab308";
  else if (score >= 25) strokeColor = "#f97316";

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size} className="transform -rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth={5}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={strokeColor}
          strokeWidth={5}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeDashoffset}
          className="transition-all duration-700 ease-out"
        />
      </svg>
      <div
        className="absolute flex flex-col items-center justify-center"
        style={{ width: size, height: size }}
      >
        <span className="text-lg font-bold font-mono" style={{ color: strokeColor }}>
          {score}
        </span>
      </div>
      {label && <span className="text-[10px] text-text-tertiary uppercase tracking-wider">{label}</span>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Horizontal Bar
// ---------------------------------------------------------------------------

function HorizontalBar({ value, max = 100, label, color }: { value: number; max?: number; label: string; color: string }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[11px]">
        <span className="text-text-secondary">{label}</span>
        <span className="font-mono text-text-primary">{value}</span>
      </div>
      <div className="h-2 bg-white/5 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Metric Cell
// ---------------------------------------------------------------------------

function MetricCell({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-lg p-3 space-y-1">
      <span className="text-[10px] text-text-tertiary uppercase tracking-wider">{label}</span>
      <div className="font-mono text-sm font-semibold text-text-primary">{value}</div>
      {sub && <div className="text-[10px] text-text-tertiary">{sub}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mock Data
// ---------------------------------------------------------------------------

const MOCK_CONGRESS: CongressionalTrade[] = [
  { politician: "Nancy Pelosi", ticker: "NVDA", type: "Purchase", date: "2026-03-15", amount_range: "$1M - $5M" },
  { politician: "Dan Crenshaw", ticker: "MSFT", type: "Purchase", date: "2026-03-12", amount_range: "$100K - $250K" },
  { politician: "Tommy Tuberville", ticker: "TSLA", type: "Sale", date: "2026-03-10", amount_range: "$250K - $500K" },
  { politician: "Ro Khanna", ticker: "AAPL", type: "Purchase", date: "2026-03-08", amount_range: "$50K - $100K" },
  { politician: "Mark Green", ticker: "LMT", type: "Purchase", date: "2026-03-05", amount_range: "$100K - $250K" },
  { politician: "Josh Gottheimer", ticker: "GOOGL", type: "Purchase", date: "2026-03-01", amount_range: "$500K - $1M" },
  { politician: "Michael McCaul", ticker: "CRM", type: "Sale", date: "2026-02-28", amount_range: "$250K - $500K" },
  { politician: "Virginia Foxx", ticker: "META", type: "Purchase", date: "2026-02-25", amount_range: "$100K - $250K" },
];

const MOCK_INSIDER: InsiderTransaction[] = [
  { insider: "Jensen Huang", ticker: "NVDA", transaction_type: "Sale (10b5-1)", shares: 120000, price: 890.50, date: "2026-03-20", title: "CEO" },
  { insider: "Tim Cook", ticker: "AAPL", transaction_type: "Sale (10b5-1)", shares: 75000, price: 195.20, date: "2026-03-18", title: "CEO" },
  { insider: "Satya Nadella", ticker: "MSFT", transaction_type: "Sale (10b5-1)", shares: 50000, price: 430.10, date: "2026-03-15", title: "CEO" },
  { insider: "Lisa Su", ticker: "AMD", transaction_type: "Sale", shares: 30000, price: 178.90, date: "2026-03-12", title: "CEO" },
  { insider: "Mark Zuckerberg", ticker: "META", transaction_type: "Sale (10b5-1)", shares: 200000, price: 520.30, date: "2026-03-10", title: "CEO" },
  { insider: "Elon Musk", ticker: "TSLA", transaction_type: "Purchase", shares: 500000, price: 242.80, date: "2026-03-08", title: "CEO" },
  { insider: "Andy Jassy", ticker: "AMZN", transaction_type: "Sale", shares: 25000, price: 188.40, date: "2026-03-05", title: "CEO" },
];

const MOCK_FLOAT: FloatProfile[] = [
  {
    symbol: "GME", float_shares: 305_000_000, float_category: "MID", short_pct_of_float: 24.1, squeeze_potential: 78, liquidity_score: 65, volatility_multiplier: 3.2, market_cap: 8_500_000_000,
    avg_volume: 12_400_000, relative_volume: 2.8, days_to_cover: 4.2, institutional_pct: 36.2, insider_pct: 12.1, free_float_pct: 51.7, cost_to_borrow: 32.5, ftd_count: 1_840_000, dark_pool_pct: 48.2,
    trade_score: 82, trade_direction: "LONG", trade_rationale: "Extreme SI with rising FTDs and elevated cost to borrow. Relative volume breakout suggests accumulation phase ahead of potential squeeze catalyst.",
    momentum_score: 74, flow_score: 68, squeeze_score: 88, risk_level: "HIGH",
  },
  {
    symbol: "AMC", float_shares: 520_000_000, float_category: "MID", short_pct_of_float: 18.5, squeeze_potential: 62, liquidity_score: 58, volatility_multiplier: 2.9, market_cap: 4_200_000_000,
    avg_volume: 28_600_000, relative_volume: 1.9, days_to_cover: 2.8, institutional_pct: 28.4, insider_pct: 0.3, free_float_pct: 71.3, cost_to_borrow: 18.7, ftd_count: 920_000, dark_pool_pct: 52.1,
    trade_score: 61, trade_direction: "LONG", trade_rationale: "Moderate squeeze setup with high dark pool routing. Insider ownership extremely low. Needs volume confirmation to trigger covering cycle.",
    momentum_score: 55, flow_score: 42, squeeze_score: 72, risk_level: "HIGH",
  },
  {
    symbol: "AAPL", float_shares: 15_200_000_000, float_category: "MEGA", short_pct_of_float: 0.8, squeeze_potential: 5, liquidity_score: 98, volatility_multiplier: 0.9, market_cap: 3_100_000_000_000,
    avg_volume: 58_200_000, relative_volume: 1.1, days_to_cover: 0.8, institutional_pct: 61.2, insider_pct: 0.1, free_float_pct: 99.7, cost_to_borrow: null, ftd_count: 142_000, dark_pool_pct: 38.4,
    trade_score: 68, trade_direction: "LONG", trade_rationale: "Mega-cap momentum play with strong institutional support. Low volatility provides favorable risk-reward for swing positions near key moving averages.",
    momentum_score: 72, flow_score: 78, squeeze_score: 5, risk_level: "LOW",
  },
  {
    symbol: "MSFT", float_shares: 7_430_000_000, float_category: "MEGA", short_pct_of_float: 0.6, squeeze_potential: 3, liquidity_score: 97, volatility_multiplier: 0.85, market_cap: 3_200_000_000_000,
    avg_volume: 22_100_000, relative_volume: 0.9, days_to_cover: 0.6, institutional_pct: 72.8, insider_pct: 0.8, free_float_pct: 99.1, cost_to_borrow: null, ftd_count: 89_000, dark_pool_pct: 35.6,
    trade_score: 55, trade_direction: "NEUTRAL", trade_rationale: "Consolidating near all-time highs. Institutional flow neutral. Wait for breakout above resistance or pullback to 50-day MA for entry.",
    momentum_score: 52, flow_score: 65, squeeze_score: 3, risk_level: "LOW",
  },
  {
    symbol: "NVDA", float_shares: 24_500_000_000, float_category: "MEGA", short_pct_of_float: 1.1, squeeze_potential: 8, liquidity_score: 97, volatility_multiplier: 1.4, market_cap: 2_200_000_000_000,
    avg_volume: 42_800_000, relative_volume: 1.4, days_to_cover: 1.0, institutional_pct: 65.5, insider_pct: 3.8, free_float_pct: 96.2, cost_to_borrow: null, ftd_count: 310_000, dark_pool_pct: 36.8,
    trade_score: 78, trade_direction: "LONG", trade_rationale: "AI sector leader with accelerating institutional accumulation. Elevated relative volume signals fresh buying interest. Momentum favors continuation.",
    momentum_score: 85, flow_score: 82, squeeze_score: 8, risk_level: "MEDIUM",
  },
  {
    symbol: "TSLA", float_shares: 2_530_000_000, float_category: "HIGH", short_pct_of_float: 3.2, squeeze_potential: 22, liquidity_score: 92, volatility_multiplier: 1.8, market_cap: 780_000_000_000,
    avg_volume: 68_400_000, relative_volume: 2.3, days_to_cover: 1.4, institutional_pct: 44.1, insider_pct: 13.2, free_float_pct: 86.8, cost_to_borrow: 0.8, ftd_count: 480_000, dark_pool_pct: 40.1,
    trade_score: 71, trade_direction: "LONG", trade_rationale: "Elevated relative volume with improving momentum. Insider buying from CEO provides conviction signal. Volatility premium allows wide stops.",
    momentum_score: 76, flow_score: 58, squeeze_score: 28, risk_level: "HIGH",
  },
  {
    symbol: "PLTR", float_shares: 2_080_000_000, float_category: "HIGH", short_pct_of_float: 3.8, squeeze_potential: 18, liquidity_score: 82, volatility_multiplier: 1.6, market_cap: 52_000_000_000,
    avg_volume: 38_200_000, relative_volume: 1.6, days_to_cover: 1.9, institutional_pct: 38.4, insider_pct: 8.2, free_float_pct: 91.8, cost_to_borrow: 1.2, ftd_count: 210_000, dark_pool_pct: 42.8,
    trade_score: 65, trade_direction: "LONG", trade_rationale: "Government contract pipeline expanding. Institutional accumulation increasing quarter-over-quarter. Dark pool activity suggests block buying.",
    momentum_score: 68, flow_score: 62, squeeze_score: 22, risk_level: "MEDIUM",
  },
  {
    symbol: "SOFI", float_shares: 960_000_000, float_category: "HIGH", short_pct_of_float: 8.4, squeeze_potential: 35, liquidity_score: 72, volatility_multiplier: 2.1, market_cap: 11_500_000_000,
    avg_volume: 24_800_000, relative_volume: 1.3, days_to_cover: 3.1, institutional_pct: 42.6, insider_pct: 2.4, free_float_pct: 97.6, cost_to_borrow: 4.8, ftd_count: 380_000, dark_pool_pct: 45.6,
    trade_score: 58, trade_direction: "NEUTRAL", trade_rationale: "Mixed signals with moderate SI and growing institutional interest. Needs to clear $13 resistance with volume for directional conviction.",
    momentum_score: 48, flow_score: 55, squeeze_score: 40, risk_level: "MEDIUM",
  },
  {
    symbol: "RIVN", float_shares: 840_000_000, float_category: "HIGH", short_pct_of_float: 14.2, squeeze_potential: 52, liquidity_score: 68, volatility_multiplier: 2.4, market_cap: 14_800_000_000,
    avg_volume: 18_600_000, relative_volume: 1.7, days_to_cover: 5.8, institutional_pct: 58.2, insider_pct: 16.4, free_float_pct: 83.6, cost_to_borrow: 12.4, ftd_count: 620_000, dark_pool_pct: 44.2,
    trade_score: 44, trade_direction: "SHORT", trade_rationale: "Elevated days-to-cover but deteriorating fundamentals. High institutional ownership creates overhang risk. Cost to borrow rising signals crowded trade.",
    momentum_score: 32, flow_score: 38, squeeze_score: 58, risk_level: "HIGH",
  },
  {
    symbol: "LCID", float_shares: 1_820_000_000, float_category: "HIGH", short_pct_of_float: 16.8, squeeze_potential: 58, liquidity_score: 62, volatility_multiplier: 2.6, market_cap: 7_200_000_000,
    avg_volume: 22_400_000, relative_volume: 2.1, days_to_cover: 6.2, institutional_pct: 52.8, insider_pct: 60.2, free_float_pct: 39.8, cost_to_borrow: 22.8, ftd_count: 890_000, dark_pool_pct: 50.4,
    trade_score: 38, trade_direction: "SHORT", trade_rationale: "Very low free float with massive insider lock-up creates illiquidity. High borrow cost and FTDs indicate extreme shorting pressure. Bearish trend intact.",
    momentum_score: 24, flow_score: 30, squeeze_score: 65, risk_level: "EXTREME",
  },
  {
    symbol: "MARA", float_shares: 280_000_000, float_category: "MID", short_pct_of_float: 22.6, squeeze_potential: 72, liquidity_score: 55, volatility_multiplier: 3.8, market_cap: 5_600_000_000,
    avg_volume: 32_200_000, relative_volume: 3.1, days_to_cover: 3.4, institutional_pct: 42.8, insider_pct: 3.2, free_float_pct: 96.8, cost_to_borrow: 28.4, ftd_count: 1_420_000, dark_pool_pct: 46.8,
    trade_score: 72, trade_direction: "LONG", trade_rationale: "Bitcoin proxy with extreme relative volume surge. High SI creates squeeze fuel. FTD accumulation approaching threshold. Momentum aligning with crypto cycle.",
    momentum_score: 78, flow_score: 52, squeeze_score: 82, risk_level: "EXTREME",
  },
  {
    symbol: "RIOT", float_shares: 320_000_000, float_category: "MID", short_pct_of_float: 19.4, squeeze_potential: 65, liquidity_score: 58, volatility_multiplier: 3.5, market_cap: 3_800_000_000,
    avg_volume: 18_600_000, relative_volume: 2.6, days_to_cover: 4.8, institutional_pct: 38.2, insider_pct: 4.8, free_float_pct: 95.2, cost_to_borrow: 24.2, ftd_count: 980_000, dark_pool_pct: 44.6,
    trade_score: 66, trade_direction: "LONG", trade_rationale: "Crypto-adjacent with high SI creating reflexive upside potential. Days-to-cover above 4 suggests shorts would struggle to exit quickly. Volatile but directional.",
    momentum_score: 70, flow_score: 48, squeeze_score: 76, risk_level: "EXTREME",
  },
];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function AlphaPage() {
  const [tab, setTab] = useState<Tab>("congressional");
  const [congressTrades, setCongressTrades] = useState<CongressionalTrade[]>([]);
  const [insiderTxns, setInsiderTxns] = useState<InsiderTransaction[]>([]);
  const [floatProfiles, setFloatProfiles] = useState<FloatProfile[]>([]);
  const [floatQuery, setFloatQuery] = useState("GME,AMC,AAPL,MSFT,NVDA,TSLA,PLTR,SOFI,RIVN,LCID,MARA,RIOT");
  const [loading, setLoading] = useState(false);

  // Float tab state
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("trade_score");
  const [sortAsc, setSortAsc] = useState(false);
  const [dirFilter, setDirFilter] = useState<DirectionFilter>("ALL");
  const [riskFilter, setRiskFilter] = useState<RiskFilter>("ALL");

  useEffect(() => {
    fetchData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  async function fetchData() {
    setLoading(true);
    try {
      if (tab === "congressional") {
        const res = await fetch(`${API_BASE}/api/alpha/congressional?days=90`);
        if (res.ok) {
          const data = await res.json();
          setCongressTrades(data.trades?.length ? data.trades : MOCK_CONGRESS);
        } else {
          setCongressTrades(MOCK_CONGRESS);
        }
      } else if (tab === "insider") {
        const res = await fetch(`${API_BASE}/api/alpha/insider?days=30`);
        if (res.ok) {
          const data = await res.json();
          setInsiderTxns(data.transactions?.length ? data.transactions : MOCK_INSIDER);
        } else {
          setInsiderTxns(MOCK_INSIDER);
        }
      } else if (tab === "float") {
        const res = await fetch(
          `${API_BASE}/api/float/summary?symbols=${encodeURIComponent(floatQuery)}`
        );
        if (res.ok) {
          const data = await res.json();
          setFloatProfiles(data.profiles?.length ? data.profiles : MOCK_FLOAT);
        } else {
          setFloatProfiles(MOCK_FLOAT);
        }
      }
    } catch {
      if (tab === "congressional") setCongressTrades(MOCK_CONGRESS);
      else if (tab === "insider") setInsiderTxns(MOCK_INSIDER);
      else if (tab === "float") setFloatProfiles(MOCK_FLOAT);
    } finally {
      setLoading(false);
    }
  }

  // Sort & filter float data
  const filteredFloat = useMemo(() => {
    let data = [...floatProfiles];
    if (dirFilter !== "ALL") data = data.filter((p) => p.trade_direction === dirFilter);
    if (riskFilter !== "ALL") data = data.filter((p) => p.risk_level === riskFilter);
    data.sort((a, b) => {
      const aVal = a[sortKey] ?? 0;
      const bVal = b[sortKey] ?? 0;
      if (typeof aVal === "string" && typeof bVal === "string") {
        return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
      }
      return sortAsc ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
    });
    return data;
  }, [floatProfiles, sortKey, sortAsc, dirFilter, riskFilter]);

  // Summary card helpers
  const topLong = useMemo(() => {
    const longs = floatProfiles.filter((p) => p.trade_direction === "LONG");
    return longs.length ? longs.reduce((a, b) => (a.trade_score > b.trade_score ? a : b)) : null;
  }, [floatProfiles]);

  const topShort = useMemo(() => {
    const shorts = floatProfiles.filter((p) => p.trade_direction === "SHORT");
    return shorts.length ? shorts.reduce((a, b) => (a.trade_score > b.trade_score ? a : b)) : null;
  }, [floatProfiles]);

  const highestSqueeze = useMemo(() => {
    return floatProfiles.length ? floatProfiles.reduce((a, b) => (a.squeeze_score > b.squeeze_score ? a : b)) : null;
  }, [floatProfiles]);

  const mostVolatile = useMemo(() => {
    return floatProfiles.length ? floatProfiles.reduce((a, b) => ((a.volatility_multiplier ?? 0) > (b.volatility_multiplier ?? 0) ? a : b)) : null;
  }, [floatProfiles]);

  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  }

  function SortHeader({ label, col, className }: { label: string; col: SortKey; className?: string }) {
    return (
      <th
        className={`py-2 pr-3 cursor-pointer select-none hover:text-text-primary transition-colors ${className || ""}`}
        onClick={() => handleSort(col)}
      >
        <div className="flex items-center gap-1">
          <span>{label}</span>
          {sortKey === col && (
            <span className="text-accent">{sortAsc ? "\u25B2" : "\u25BC"}</span>
          )}
        </div>
      </th>
    );
  }

  // Generate trade setup data from profile
  function getTradeSetup(p: FloatProfile) {
    const basePrice = p.market_cap && p.float_shares ? p.market_cap / (p.float_shares * 1.2) : 0;
    const atr = basePrice * ((p.volatility_multiplier ?? 1) * 0.015);
    if (p.trade_direction === "LONG") {
      return {
        entry: `$${(basePrice * 0.98).toFixed(2)} - $${(basePrice * 1.0).toFixed(2)}`,
        stop: `$${(basePrice * 0.98 - atr * 1.5).toFixed(2)}`,
        t1: `$${(basePrice + atr * 2).toFixed(2)}`,
        t2: `$${(basePrice + atr * 4).toFixed(2)}`,
        t3: `$${(basePrice + atr * 6).toFixed(2)}`,
      };
    } else if (p.trade_direction === "SHORT") {
      return {
        entry: `$${(basePrice * 1.0).toFixed(2)} - $${(basePrice * 1.02).toFixed(2)}`,
        stop: `$${(basePrice * 1.02 + atr * 1.5).toFixed(2)}`,
        t1: `$${(basePrice - atr * 2).toFixed(2)}`,
        t2: `$${(basePrice - atr * 4).toFixed(2)}`,
        t3: `$${(basePrice - atr * 6).toFixed(2)}`,
      };
    }
    return {
      entry: `$${(basePrice * 0.98).toFixed(2)} - $${(basePrice * 1.02).toFixed(2)}`,
      stop: `$${(basePrice * 0.95).toFixed(2)}`,
      t1: `$${(basePrice + atr * 2).toFixed(2)}`,
      t2: `$${(basePrice + atr * 4).toFixed(2)}`,
      t3: `$${(basePrice + atr * 6).toFixed(2)}`,
    };
  }

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <header>
        <div className="flex items-center gap-3 mb-1">
          <Landmark size={20} className="text-red-500" />
          <h1 className="font-heading text-2xl font-bold">Alpha</h1>
        </div>
        <p className="text-text-secondary text-sm">
          Congressional disclosures, insider Form 4 filings, and float analysis
        </p>
      </header>

      {/* Tab navigation */}
      <div className="flex bg-bg-card border border-border rounded-lg overflow-hidden w-fit">
        {(
          [
            { key: "congressional", label: "Congressional", icon: Landmark },
            { key: "insider", label: "Insider", icon: UserCheck },
            { key: "float", label: "Float Analysis", icon: BarChart2 },
          ] as const
        ).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium transition-colors ${
              tab === key
                ? "bg-accent text-text-primary"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {/* Congressional Trades */}
      {tab === "congressional" && (
        <section className="space-y-4">
          <Card>
            <div className="flex items-center gap-2 mb-4">
              <AlertTriangle size={14} className="text-warning" />
              <p className="text-xs text-text-secondary">
                Data from STOCK Act disclosures. Trades may be reported 30-45 days after execution.
              </p>
            </div>

            {congressTrades.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-text-tertiary text-xs border-b border-border">
                      <th className="text-left py-2 pr-4">Politician</th>
                      <th className="text-left py-2 pr-4">Ticker</th>
                      <th className="text-left py-2 pr-4">Type</th>
                      <th className="text-left py-2 pr-4">Date</th>
                      <th className="text-right py-2 pr-4">Amount</th>
                      <th className="text-center py-2">Filing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {congressTrades.slice(0, 50).map((t, i) => (
                      <tr key={i} className="border-b border-border-subtle hover:bg-bg-elevated">
                        <td className="py-2.5 pr-4">{t.politician || "--"}</td>
                        <td className="py-2.5 pr-4 font-mono text-xs">
                          {t.ticker || "--"}
                        </td>
                        <td className="py-2.5 pr-4">
                          <span
                            className={`text-xs px-1.5 py-0.5 rounded ${
                              t.type?.toLowerCase().includes("purchase")
                                ? "bg-profit/10 text-profit"
                                : "bg-loss/10 text-loss"
                            }`}
                          >
                            {t.type || "--"}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4 text-text-secondary text-xs">
                          {t.date || "--"}
                        </td>
                        <td className="py-2.5 pr-4 text-right text-xs text-text-secondary">
                          {t.amount_range || "--"}
                        </td>
                        <td className="py-2.5 text-center">
                          <a
                            href={`https://efts.sec.gov/LATEST/search-index?q=%22${encodeURIComponent(t.politician || "")}%22&dateRange=custom&startdt=${t.date || ""}&forms=4`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                          >
                            <ExternalLink size={12} />
                            View
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-12 text-text-tertiary text-sm">
                {loading ? "Loading..." : "Connect to the API to view congressional trades"}
              </div>
            )}
          </Card>
        </section>
      )}

      {/* Insider Transactions */}
      {tab === "insider" && (
        <section className="space-y-4">
          <Card>
            {insiderTxns.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-text-tertiary text-xs border-b border-border">
                      <th className="text-left py-2 pr-4">Insider</th>
                      <th className="text-left py-2 pr-4">Title</th>
                      <th className="text-left py-2 pr-4">Ticker</th>
                      <th className="text-left py-2 pr-4">Type</th>
                      <th className="text-right py-2 pr-4">Shares</th>
                      <th className="text-right py-2 pr-4">Price</th>
                      <th className="text-left py-2 pr-4">Date</th>
                      <th className="text-center py-2">Filing</th>
                    </tr>
                  </thead>
                  <tbody>
                    {insiderTxns.slice(0, 50).map((t, i) => (
                      <tr key={i} className="border-b border-border-subtle hover:bg-bg-elevated">
                        <td className="py-2.5 pr-4 text-xs">{t.insider || "--"}</td>
                        <td className="py-2.5 pr-4 text-xs text-text-secondary">
                          {t.title || "--"}
                        </td>
                        <td className="py-2.5 pr-4 font-mono text-xs">
                          {t.ticker || "--"}
                        </td>
                        <td className="py-2.5 pr-4">
                          <span
                            className={`text-xs px-1.5 py-0.5 rounded ${
                              t.transaction_type?.toLowerCase().includes("purchase") ||
                              t.transaction_type?.toLowerCase().includes("buy")
                                ? "bg-profit/10 text-profit"
                                : "bg-loss/10 text-loss"
                            }`}
                          >
                            {t.transaction_type || "--"}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">
                          {formatShares(t.shares)}
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">
                          {t.price != null ? `$${t.price.toFixed(2)}` : "--"}
                        </td>
                        <td className="py-2.5 pr-4 text-xs text-text-secondary">
                          {t.date || "--"}
                        </td>
                        <td className="py-2.5 text-center">
                          <a
                            href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=${encodeURIComponent(t.ticker || "")}&type=4&dateb=&owner=include&count=10`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300 transition-colors"
                          >
                            <ExternalLink size={12} />
                            Form 4
                          </a>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-12 text-text-tertiary text-sm">
                {loading ? "Loading..." : "Connect to the API to view insider filings"}
              </div>
            )}
          </Card>
        </section>
      )}

      {/* ================================================================= */}
      {/* Float Analysis — Complete Overhaul                                 */}
      {/* ================================================================= */}
      {tab === "float" && (
        <section className="space-y-4">
          {/* Search */}
          <div className="flex gap-3">
            <div className="flex-1 relative">
              <Search
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary"
              />
              <input
                type="text"
                value={floatQuery}
                onChange={(e) => setFloatQuery(e.target.value)}
                placeholder="Enter symbols separated by commas..."
                className="w-full bg-bg-card border border-border rounded-lg pl-9 pr-4 py-2.5 text-sm font-mono focus:outline-none focus:border-accent-hover"
              />
            </div>
            <button
              onClick={fetchData}
              className="bg-accent hover:bg-accent-hover px-4 py-2.5 rounded-lg text-sm font-medium transition-colors"
            >
              Analyze
            </button>
          </div>

          {/* Summary Cards */}
          {floatProfiles.length > 0 && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {/* Top Long */}
              <Card>
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp size={14} className="text-profit" />
                  <span className="text-[10px] text-text-tertiary uppercase tracking-wider">Top Long Setup</span>
                </div>
                {topLong ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-mono font-bold text-lg text-text-primary">{topLong.symbol}</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${directionStyle("LONG")}`}>LONG</span>
                        <span className={`font-mono text-xs ${scoreColor(topLong.trade_score)}`}>Score: {topLong.trade_score}</span>
                      </div>
                    </div>
                    <div className="relative">
                      <ScoreGauge score={topLong.trade_score} size={56} />
                    </div>
                  </div>
                ) : <span className="text-text-tertiary text-xs">No long setups</span>}
              </Card>

              {/* Top Short */}
              <Card>
                <div className="flex items-center gap-2 mb-2">
                  <TrendingDown size={14} className="text-loss" />
                  <span className="text-[10px] text-text-tertiary uppercase tracking-wider">Top Short Setup</span>
                </div>
                {topShort ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-mono font-bold text-lg text-text-primary">{topShort.symbol}</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${directionStyle("SHORT")}`}>SHORT</span>
                        <span className={`font-mono text-xs ${scoreColor(topShort.trade_score)}`}>Score: {topShort.trade_score}</span>
                      </div>
                    </div>
                    <div className="relative">
                      <ScoreGauge score={topShort.trade_score} size={56} />
                    </div>
                  </div>
                ) : <span className="text-text-tertiary text-xs">No short setups</span>}
              </Card>

              {/* Highest Squeeze */}
              <Card>
                <div className="flex items-center gap-2 mb-2">
                  <Flame size={14} className="text-orange-400" />
                  <span className="text-[10px] text-text-tertiary uppercase tracking-wider">Highest Squeeze</span>
                </div>
                {highestSqueeze ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-mono font-bold text-lg text-text-primary">{highestSqueeze.symbol}</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-text-secondary">SI: {highestSqueeze.short_pct_of_float}%</span>
                        <span className="font-mono text-xs text-orange-400">Sq: {highestSqueeze.squeeze_score}</span>
                      </div>
                    </div>
                    <div className="relative">
                      <ScoreGauge score={highestSqueeze.squeeze_score} size={56} />
                    </div>
                  </div>
                ) : <span className="text-text-tertiary text-xs">--</span>}
              </Card>

              {/* Most Volatile */}
              <Card>
                <div className="flex items-center gap-2 mb-2">
                  <Activity size={14} className="text-yellow-400" />
                  <span className="text-[10px] text-text-tertiary uppercase tracking-wider">Most Volatile</span>
                </div>
                {mostVolatile ? (
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-mono font-bold text-lg text-text-primary">{mostVolatile.symbol}</span>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-xs text-text-secondary">Vol: {mostVolatile.volatility_multiplier?.toFixed(1)}x</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${riskColor(mostVolatile.risk_level)}`}>{mostVolatile.risk_level}</span>
                      </div>
                    </div>
                    <div className="text-2xl font-mono font-bold text-yellow-400">
                      {mostVolatile.volatility_multiplier?.toFixed(1)}x
                    </div>
                  </div>
                ) : <span className="text-text-tertiary text-xs">--</span>}
              </Card>
            </div>
          )}

          {/* Filters Row */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Filter size={13} className="text-text-tertiary" />
              <span className="text-xs text-text-tertiary">Direction:</span>
              {(["ALL", "LONG", "SHORT", "NEUTRAL"] as DirectionFilter[]).map((d) => (
                <button
                  key={d}
                  onClick={() => setDirFilter(d)}
                  className={`text-[11px] px-2.5 py-1 rounded-md font-medium transition-colors ${
                    dirFilter === d
                      ? "bg-accent text-text-primary"
                      : "bg-white/5 text-text-secondary hover:text-text-primary hover:bg-white/10"
                  }`}
                >
                  {d}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2">
              <Shield size={13} className="text-text-tertiary" />
              <span className="text-xs text-text-tertiary">Risk:</span>
              {(["ALL", "LOW", "MEDIUM", "HIGH", "EXTREME"] as RiskFilter[]).map((r) => (
                <button
                  key={r}
                  onClick={() => setRiskFilter(r)}
                  className={`text-[11px] px-2.5 py-1 rounded-md font-medium transition-colors ${
                    riskFilter === r
                      ? "bg-accent text-text-primary"
                      : "bg-white/5 text-text-secondary hover:text-text-primary hover:bg-white/10"
                  }`}
                >
                  {r}
                </button>
              ))}
            </div>
            <div className="ml-auto text-[11px] text-text-tertiary">
              {filteredFloat.length} of {floatProfiles.length} symbols
            </div>
          </div>

          {/* Float profiles table */}
          <Card>
            {filteredFloat.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-text-tertiary text-xs border-b border-border">
                      <th className="text-left py-2 pr-3 w-6"></th>
                      <SortHeader label="Symbol" col="symbol" className="text-left" />
                      <SortHeader label="Score" col="trade_score" className="text-right" />
                      <th className="text-center py-2 pr-3">Dir</th>
                      <th className="text-center py-2 pr-3">Risk</th>
                      <SortHeader label="SI %" col="short_pct_of_float" className="text-right" />
                      <SortHeader label="Squeeze" col="squeeze_score" className="text-right" />
                      <SortHeader label="DTC" col="days_to_cover" className="text-right" />
                      <SortHeader label="Vol" col="volatility_multiplier" className="text-right" />
                      <SortHeader label="Dark Pool" col="dark_pool_pct" className="text-right" />
                      <SortHeader label="Mkt Cap" col="market_cap" className="text-right" />
                    </tr>
                  </thead>
                  <tbody>
                    {filteredFloat.map((p) => {
                      const isExpanded = expandedSymbol === p.symbol;
                      const setup = getTradeSetup(p);
                      return (
                        <React.Fragment key={p.symbol}>
                          {/* Main row */}
                          <tr
                            onClick={() => setExpandedSymbol(isExpanded ? null : p.symbol)}
                            className={`border-b border-border-subtle cursor-pointer transition-colors ${
                              isExpanded ? "bg-bg-elevated" : "hover:bg-bg-elevated"
                            }`}
                          >
                            <td className="py-2.5 pr-1 text-text-tertiary">
                              {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                            </td>
                            <td className="py-2.5 pr-3 font-mono font-semibold text-xs text-text-primary">
                              {p.symbol}
                              <span className="ml-2 text-[10px] font-normal text-text-tertiary">{p.float_category}</span>
                            </td>
                            <td className="py-2.5 pr-3 text-right">
                              <span className={`font-mono text-xs font-bold ${scoreColor(p.trade_score)}`}>
                                {p.trade_score}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-center">
                              <span className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${directionStyle(p.trade_direction)}`}>
                                {p.trade_direction}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-center">
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${riskColor(p.risk_level)}`}>
                                {p.risk_level}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono text-xs">
                              <span className={p.short_pct_of_float != null && p.short_pct_of_float > 10 ? "text-loss" : "text-text-secondary"}>
                                {p.short_pct_of_float != null ? `${p.short_pct_of_float.toFixed(1)}%` : "--"}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-right">
                              <span className={`font-mono text-xs ${scoreColor(p.squeeze_score)}`}>
                                {p.squeeze_score}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono text-xs text-text-secondary">
                              {p.days_to_cover.toFixed(1)}
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono text-xs">
                              <span className={(p.volatility_multiplier ?? 0) >= 2.5 ? "text-orange-400" : "text-text-secondary"}>
                                {p.volatility_multiplier != null ? `${p.volatility_multiplier.toFixed(1)}x` : "--"}
                              </span>
                            </td>
                            <td className="py-2.5 pr-3 text-right font-mono text-xs">
                              <span className={p.dark_pool_pct >= 45 ? "text-yellow-400" : "text-text-secondary"}>
                                {p.dark_pool_pct.toFixed(1)}%
                              </span>
                            </td>
                            <td className="py-2.5 text-right font-mono text-xs text-text-secondary">
                              {formatDollars(p.market_cap)}
                            </td>
                          </tr>

                          {/* Expanded detail row */}
                          {isExpanded && (
                            <tr>
                              <td colSpan={11} className="p-0">
                                <div className="bg-bg-elevated/50 border-b border-border px-4 py-5 space-y-5">

                                  {/* Row 1: Score gauge + Direction + Rationale */}
                                  <div className="flex flex-col lg:flex-row gap-5">
                                    {/* Trade Score Gauge */}
                                    <div className="flex flex-col items-center gap-2 min-w-[120px]">
                                      <div className="relative">
                                        <ScoreGauge score={p.trade_score} size={96} label="Trade Score" />
                                      </div>
                                    </div>

                                    {/* Direction + Rationale */}
                                    <div className="flex-1 space-y-3">
                                      <div className="flex items-center gap-3 flex-wrap">
                                        <span className={`text-sm px-3 py-1 rounded font-bold ${directionStyle(p.trade_direction)}`}>
                                          {p.trade_direction === "LONG" && <TrendingUp size={14} className="inline mr-1.5 -mt-0.5" />}
                                          {p.trade_direction === "SHORT" && <TrendingDown size={14} className="inline mr-1.5 -mt-0.5" />}
                                          {p.trade_direction}
                                        </span>
                                        <span className={`text-xs px-2 py-0.5 rounded ${riskColor(p.risk_level)}`}>
                                          {p.risk_level} RISK
                                        </span>
                                        <span className="text-xs text-text-tertiary">
                                          RVol: <span className={`font-mono ${p.relative_volume >= 2.0 ? "text-profit" : "text-text-secondary"}`}>{p.relative_volume.toFixed(1)}x</span>
                                        </span>
                                      </div>
                                      <p className="text-sm text-text-secondary leading-relaxed">
                                        {p.trade_rationale}
                                      </p>

                                      {/* Sub-scores */}
                                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2">
                                        <HorizontalBar value={p.momentum_score} label="Momentum" color={scoreBg(p.momentum_score)} />
                                        <HorizontalBar value={p.flow_score} label="Flow" color={scoreBg(p.flow_score)} />
                                        <HorizontalBar value={p.squeeze_score} label="Squeeze" color={scoreBg(p.squeeze_score)} />
                                      </div>
                                    </div>
                                  </div>

                                  {/* Row 2: Key metrics grid */}
                                  <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
                                    <MetricCell label="Days to Cover" value={p.days_to_cover.toFixed(1)} sub={p.days_to_cover >= 4 ? "ELEVATED" : "Normal"} />
                                    <MetricCell label="Cost to Borrow" value={p.cost_to_borrow != null ? `${p.cost_to_borrow.toFixed(1)}%` : "N/A"} sub={p.cost_to_borrow != null && p.cost_to_borrow > 20 ? "Hard to borrow" : p.cost_to_borrow != null ? "Easy to borrow" : undefined} />
                                    <MetricCell label="Institutional %" value={`${p.institutional_pct.toFixed(1)}%`} sub={p.institutional_pct > 60 ? "Heavily institutional" : "Mixed ownership"} />
                                    <MetricCell label="Dark Pool %" value={`${p.dark_pool_pct.toFixed(1)}%`} sub={p.dark_pool_pct >= 45 ? "High dark pool activity" : "Normal routing"} />
                                    <MetricCell label="FTDs" value={p.ftd_count != null ? formatShares(p.ftd_count) : "N/A"} sub={p.ftd_count != null && p.ftd_count > 1_000_000 ? "Threshold exceeded" : "Within limits"} />
                                    <MetricCell label="Free Float" value={`${p.free_float_pct.toFixed(1)}%`} sub={`Insider: ${p.insider_pct.toFixed(1)}%`} />
                                  </div>

                                  {/* Row 3: Additional metrics */}
                                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                                    <MetricCell label="Avg Volume" value={formatVolume(p.avg_volume)} />
                                    <MetricCell label="Relative Volume" value={`${p.relative_volume.toFixed(1)}x`} sub={p.relative_volume >= 2.0 ? "Volume breakout" : "Normal"} />
                                    <MetricCell label="Float Shares" value={formatShares(p.float_shares)} sub={p.float_category ?? undefined} />
                                    <MetricCell label="Liquidity Score" value={`${p.liquidity_score?.toFixed(0) ?? "--"}/100`} />
                                  </div>

                                  {/* Row 4: Trade Setup */}
                                  <div className="bg-white/[0.02] border border-white/[0.08] rounded-lg p-4">
                                    <div className="flex items-center gap-2 mb-3">
                                      <Crosshair size={14} className="text-accent" />
                                      <h4 className="text-xs font-semibold uppercase tracking-wider text-text-primary">Trade Setup</h4>
                                      <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded font-semibold ${directionStyle(p.trade_direction)}`}>
                                        {p.trade_direction}
                                      </span>
                                    </div>
                                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                                      <div className="space-y-1">
                                        <span className="text-[10px] text-text-tertiary uppercase">Entry Zone</span>
                                        <div className="font-mono text-sm text-text-primary">{setup.entry}</div>
                                      </div>
                                      <div className="space-y-1">
                                        <span className="text-[10px] text-loss uppercase">Stop Loss</span>
                                        <div className="font-mono text-sm text-loss">{setup.stop}</div>
                                      </div>
                                      <div className="space-y-1">
                                        <span className="text-[10px] text-text-tertiary uppercase">Target 1R</span>
                                        <div className="font-mono text-sm text-profit">{setup.t1}</div>
                                      </div>
                                      <div className="space-y-1">
                                        <span className="text-[10px] text-text-tertiary uppercase">Target 2R</span>
                                        <div className="font-mono text-sm text-profit">{setup.t2}</div>
                                      </div>
                                      <div className="space-y-1">
                                        <span className="text-[10px] text-text-tertiary uppercase">Target 3R</span>
                                        <div className="font-mono text-sm text-profit">{setup.t3}</div>
                                      </div>
                                    </div>
                                  </div>

                                </div>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-12 text-text-tertiary text-sm">
                {loading
                  ? "Analyzing float data..."
                  : filteredFloat.length === 0 && floatProfiles.length > 0
                  ? "No symbols match current filters"
                  : "Enter symbols above and click Analyze, or connect to the API"}
              </div>
            )}
          </Card>

          {/* Float legend */}
          <Card>
            <h3 className="font-heading font-semibold text-sm mb-3">
              Float Categories
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 text-xs">
              {[
                { cat: "NANO", range: "< 1M", risk: "Extreme vol" },
                { cat: "LOW", range: "1M-10M", risk: "High vol, momentum" },
                { cat: "MID", range: "10M-100M", risk: "Moderate" },
                { cat: "HIGH", range: "100M-1B", risk: "Liquid, stable" },
                { cat: "MEGA", range: "> 1B", risk: "Ultra-liquid" },
              ].map((item) => (
                <div key={item.cat} className="space-y-1">
                  <span className="font-mono font-semibold">{item.cat}</span>
                  <p className="text-text-tertiary">{item.range}</p>
                  <p className="text-text-secondary">{item.risk}</p>
                </div>
              ))}
            </div>
          </Card>
        </section>
      )}
    </div>
  );
}
