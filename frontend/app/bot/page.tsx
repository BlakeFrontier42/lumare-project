"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  Play,
  Square,
  Activity,
  TrendingUp,
  TrendingDown,
  Zap,
  Shield,
  Clock,
  BarChart3,
  Target,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Settings,
  ChevronDown,
  ChevronUp,
  X,
  DollarSign,
  Percent,
  Award,
  Flame,
  ArrowUpRight,
  ArrowDownRight,
  Pause,
  Layers,
  Lock,
  Unlock,
} from "lucide-react";

import { useAppStore, type AssetClass } from "@/store";

const API = "";

// Symbol universe per asset class — drives the config panel
const ASSET_CLASS_UNIVERSE: Record<AssetClass, string[]> = {
  crypto: ["BTC", "ETH", "SOL", "XRP", "AVAX", "ADA", "DOT", "LINK"],
  equity: ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL", "META"],
  futures: ["ES", "NQ", "CL", "GC", "SI", "ZB"],
  options: ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "MSFT"],
};

// ── Types ────────────────────────────────────────────────────
interface BotStatus {
  running: boolean;
  uptime_seconds: number;
  symbols: string[];
  strategies: string[];
  interval_seconds: number;
  max_concurrent_positions: number;
  signals_generated: number;
  trades_placed: number;
  open_positions: number;
}

interface BotPerformance {
  total_pnl: number;
  total_trades: number;
  win_rate: number;
  avg_gain: number;
  avg_loss: number;
  profit_factor: number;
  sharpe: number;
  strategy_breakdown: Record<string, { trades: number; pnl: number; win_rate: number }>;
}

interface BotSignal {
  signal_id: string;
  symbol: string;
  strategy: string;
  direction: string;
  confidence: number;
  entry: number;
  stop_loss: number;
  take_profit: number;
  timestamp: string;
  acted: boolean;
  reason: string;
}

interface ActivityEntry {
  type: string;
  message: string;
  timestamp: string;
}

interface OpenPosition {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  strategy: string;
  entryPrice: number;
  currentPrice: number;
  quantity: number;
  stopLoss: number;
  takeProfit: number;
  entryTime: number; // timestamp ms
}

interface ClosedTrade {
  id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  strategy: string;
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  stopLoss: number;
  takeProfit: number;
  entryTime: number;
  exitTime: number;
  pnl: number;
}

interface RiskConfig {
  sizingMode: "fixed" | "percent" | "kelly";
  fixedAmount: number;
  percentOfEquity: number;
  kellyFraction: number;
  maxDailyLoss: number;
  dailyLossUsed: number;
  circuitBreakerActive: boolean;
  maxCorrelation: number;
  trailingStopEnabled: Record<string, boolean>;
}

// ── Constants ────────────────────────────────────────────────
const STRATEGY_COLORS: Record<string, string> = {
  momentum: "#3b82f6",
  mean_reversion: "#8b5cf6",
  trend_following: "#10b981",
  breakout: "#f59e0b",
  ict: "#ef4444",
};

const AVAILABLE_SYMBOLS = [
  "BTC", "ETH", "SOL", "XRP", "AVAX", "ADA", "DOT", "LINK",
  "SPY", "QQQ", "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "GOOGL",
];

const AVAILABLE_STRATEGIES = [
  { id: "momentum", label: "Momentum", desc: "RSI + MACD crossover signals" },
  { id: "mean_reversion", label: "Mean Reversion", desc: "Bollinger Band deviation + RSI extremes" },
  { id: "trend_following", label: "Trend Following", desc: "EMA crossovers with volume confirmation" },
  { id: "breakout", label: "Breakout", desc: "Key level breaks with ATR-based stops" },
  { id: "ict", label: "ICT / Smart Money", desc: "Fair value gaps, order blocks, liquidity sweeps" },
];

// ── Helpers ──────────────────────────────────────────────────
function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h < 24) return `${h}h ${m}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

function fmtMoney(v: number, decimals = 2): string {
  const abs = Math.abs(v);
  const sign = v >= 0 ? "+" : "-";
  return `${sign}$${abs.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;
}

function fmtPct(v: number): string {
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function tradeGrade(rMultiple: number): { letter: string; color: string } {
  if (rMultiple >= 3) return { letter: "A", color: "text-green-400" };
  if (rMultiple >= 2) return { letter: "B", color: "text-blue-400" };
  if (rMultiple >= 1) return { letter: "C", color: "text-amber-400" };
  if (rMultiple >= 0) return { letter: "D", color: "text-orange-400" };
  return { letter: "F", color: "text-red-400" };
}

function computeRMultiple(pos: { direction: "LONG" | "SHORT"; entryPrice: number; currentPrice?: number; exitPrice?: number; stopLoss: number }): number {
  const price = pos.exitPrice ?? pos.currentPrice ?? pos.entryPrice;
  const risk = Math.abs(pos.entryPrice - pos.stopLoss);
  if (risk === 0) return 0;
  const rawPnl = pos.direction === "LONG" ? price - pos.entryPrice : pos.entryPrice - price;
  return rawPnl / risk;
}

// ── Mock Data Generators ─────────────────────────────────────
const BASE_PRICES: Record<string, number> = {
  BTC: 67420, ETH: 3285, SOL: 178.5, XRP: 0.62, AVAX: 38.2,
  ADA: 0.48, DOT: 7.85, LINK: 16.42, SPY: 525.3, QQQ: 448.7,
  AAPL: 189.4, TSLA: 248.6, NVDA: 875.3, MSFT: 422.8, AMZN: 186.2, GOOGL: 157.9,
};

function generateMockPositions(): OpenPosition[] {
  const now = Date.now();
  return [
    {
      id: "pos-1", symbol: "BTC", direction: "LONG", strategy: "trend_following",
      entryPrice: 66800, currentPrice: 67420, quantity: 0.15,
      stopLoss: 65500, takeProfit: 70000, entryTime: now - 4 * 3600000,
    },
    {
      id: "pos-2", symbol: "NVDA", direction: "LONG", strategy: "momentum",
      entryPrice: 862, currentPrice: 875.3, quantity: 12,
      stopLoss: 840, takeProfit: 920, entryTime: now - 7 * 3600000,
    },
    {
      id: "pos-3", symbol: "ETH", direction: "SHORT", strategy: "mean_reversion",
      entryPrice: 3340, currentPrice: 3285, quantity: 3,
      stopLoss: 3420, takeProfit: 3180, entryTime: now - 1.5 * 3600000,
    },
    {
      id: "pos-4", symbol: "SPY", direction: "LONG", strategy: "breakout",
      entryPrice: 522.8, currentPrice: 525.3, quantity: 20,
      stopLoss: 518.0, takeProfit: 535.0, entryTime: now - 12 * 3600000,
    },
  ];
}

function generateMockClosedTrades(): ClosedTrade[] {
  const now = Date.now();
  const DAY = 86400000;
  const trades: ClosedTrade[] = [
    { id: "ct-1", symbol: "BTC", direction: "LONG", strategy: "momentum", entryPrice: 63200, exitPrice: 65800, quantity: 0.2, stopLoss: 61800, takeProfit: 66500, entryTime: now - 7 * DAY, exitTime: now - 6.5 * DAY, pnl: 520 },
    { id: "ct-2", symbol: "ETH", direction: "SHORT", strategy: "mean_reversion", entryPrice: 3480, exitPrice: 3520, quantity: 5, stopLoss: 3560, takeProfit: 3350, entryTime: now - 6.5 * DAY, exitTime: now - 6.2 * DAY, pnl: -200 },
    { id: "ct-3", symbol: "TSLA", direction: "LONG", strategy: "breakout", entryPrice: 235, exitPrice: 252, quantity: 15, stopLoss: 225, takeProfit: 260, entryTime: now - 6 * DAY, exitTime: now - 5.5 * DAY, pnl: 255 },
    { id: "ct-4", symbol: "SOL", direction: "LONG", strategy: "trend_following", entryPrice: 162, exitPrice: 178, quantity: 30, stopLoss: 152, takeProfit: 185, entryTime: now - 5.5 * DAY, exitTime: now - 5 * DAY, pnl: 480 },
    { id: "ct-5", symbol: "AAPL", direction: "SHORT", strategy: "mean_reversion", entryPrice: 195, exitPrice: 192, quantity: 25, stopLoss: 199, takeProfit: 186, entryTime: now - 5 * DAY, exitTime: now - 4.7 * DAY, pnl: 75 },
    { id: "ct-6", symbol: "NVDA", direction: "LONG", strategy: "momentum", entryPrice: 820, exitPrice: 812, quantity: 10, stopLoss: 800, takeProfit: 870, entryTime: now - 4.5 * DAY, exitTime: now - 4.3 * DAY, pnl: -80 },
    { id: "ct-7", symbol: "QQQ", direction: "LONG", strategy: "trend_following", entryPrice: 435, exitPrice: 448, quantity: 30, stopLoss: 428, takeProfit: 455, entryTime: now - 4 * DAY, exitTime: now - 3.5 * DAY, pnl: 390 },
    { id: "ct-8", symbol: "XRP", direction: "SHORT", strategy: "ict", entryPrice: 0.68, exitPrice: 0.71, quantity: 10000, stopLoss: 0.72, takeProfit: 0.58, entryTime: now - 3.5 * DAY, exitTime: now - 3.3 * DAY, pnl: -300 },
    { id: "ct-9", symbol: "BTC", direction: "LONG", strategy: "breakout", entryPrice: 64500, exitPrice: 66200, quantity: 0.12, stopLoss: 63200, takeProfit: 67800, entryTime: now - 3 * DAY, exitTime: now - 2.7 * DAY, pnl: 204 },
    { id: "ct-10", symbol: "MSFT", direction: "LONG", strategy: "momentum", entryPrice: 415, exitPrice: 423, quantity: 20, stopLoss: 408, takeProfit: 435, entryTime: now - 2.8 * DAY, exitTime: now - 2.5 * DAY, pnl: 160 },
    { id: "ct-11", symbol: "ETH", direction: "LONG", strategy: "trend_following", entryPrice: 3180, exitPrice: 3310, quantity: 4, stopLoss: 3080, takeProfit: 3400, entryTime: now - 2.5 * DAY, exitTime: now - 2 * DAY, pnl: 520 },
    { id: "ct-12", symbol: "TSLA", direction: "SHORT", strategy: "mean_reversion", entryPrice: 255, exitPrice: 260, quantity: 12, stopLoss: 265, takeProfit: 238, entryTime: now - 2 * DAY, exitTime: now - 1.8 * DAY, pnl: -60 },
    { id: "ct-13", symbol: "AVAX", direction: "LONG", strategy: "ict", entryPrice: 34.5, exitPrice: 38.8, quantity: 100, stopLoss: 31.5, takeProfit: 40, entryTime: now - 1.8 * DAY, exitTime: now - 1.5 * DAY, pnl: 430 },
    { id: "ct-14", symbol: "SPY", direction: "LONG", strategy: "breakout", entryPrice: 518, exitPrice: 524, quantity: 25, stopLoss: 514, takeProfit: 530, entryTime: now - 1.5 * DAY, exitTime: now - 1.2 * DAY, pnl: 150 },
    { id: "ct-15", symbol: "LINK", direction: "SHORT", strategy: "momentum", entryPrice: 17.8, exitPrice: 17.2, quantity: 200, stopLoss: 18.5, takeProfit: 15.5, entryTime: now - 1 * DAY, exitTime: now - 0.8 * DAY, pnl: 120 },
    { id: "ct-16", symbol: "DOT", direction: "LONG", strategy: "trend_following", entryPrice: 7.2, exitPrice: 7.1, quantity: 500, stopLoss: 6.8, takeProfit: 8.2, entryTime: now - 0.8 * DAY, exitTime: now - 0.5 * DAY, pnl: -50 },
    { id: "ct-17", symbol: "BTC", direction: "SHORT", strategy: "ict", entryPrice: 68100, exitPrice: 67200, quantity: 0.1, stopLoss: 69000, takeProfit: 65500, entryTime: now - 0.5 * DAY, exitTime: now - 0.3 * DAY, pnl: 90 },
    { id: "ct-18", symbol: "GOOGL", direction: "LONG", strategy: "momentum", entryPrice: 153, exitPrice: 158, quantity: 30, stopLoss: 149, takeProfit: 164, entryTime: now - 0.3 * DAY, exitTime: now - 0.15 * DAY, pnl: 150 },
  ];
  return trades;
}

function generateEquityCurve(closedTrades: ClosedTrade[]): { x: number; y: number }[] {
  const startingEquity = 100000;
  const points: { x: number; y: number }[] = [{ x: 0, y: startingEquity }];
  let equity = startingEquity;
  const sorted = [...closedTrades].sort((a, b) => a.exitTime - b.exitTime);
  sorted.forEach((t, i) => {
    equity += t.pnl;
    points.push({ x: i + 1, y: equity });
  });
  return points;
}

function generateDailyPnl(closedTrades: ClosedTrade[]): { day: string; pnl: number }[] {
  const now = Date.now();
  const DAY = 86400000;
  const days: { day: string; pnl: number }[] = [];
  for (let i = 6; i >= 0; i--) {
    const dayStart = now - (i + 1) * DAY;
    const dayEnd = now - i * DAY;
    const dayLabel = new Date(dayEnd).toLocaleDateString("en-US", { weekday: "short" });
    const dayPnl = closedTrades
      .filter((t) => t.exitTime >= dayStart && t.exitTime < dayEnd)
      .reduce((sum, t) => sum + t.pnl, 0);
    days.push({ day: dayLabel, pnl: dayPnl });
  }
  return days;
}

// ── SVG Chart Components ─────────────────────────────────────
function EquityCurveSVG({ points, width = 600, height = 140 }: { points: { x: number; y: number }[]; width?: number; height?: number }) {
  if (points.length < 2) return null;
  const minY = Math.min(...points.map((p) => p.y));
  const maxY = Math.max(...points.map((p) => p.y));
  const rangeY = maxY - minY || 1;
  const padY = rangeY * 0.1;

  const scaleX = (i: number) => (i / (points.length - 1)) * width;
  const scaleY = (v: number) => height - ((v - minY + padY) / (rangeY + 2 * padY)) * height;

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${scaleX(p.x).toFixed(1)} ${scaleY(p.y).toFixed(1)}`).join(" ");
  const areaD = `${pathD} L ${scaleX(points[points.length - 1].x).toFixed(1)} ${height} L ${scaleX(points[0].x).toFixed(1)} ${height} Z`;

  const isUp = points[points.length - 1].y >= points[0].y;
  const strokeColor = isUp ? "#22c55e" : "#ef4444";
  const fillColor = isUp ? "#22c55e" : "#ef4444";

  const lastPoint = points[points.length - 1];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none">
      <defs>
        <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={fillColor} stopOpacity="0.25" />
          <stop offset="100%" stopColor={fillColor} stopOpacity="0" />
        </linearGradient>
      </defs>
      {/* gridlines */}
      {[0.25, 0.5, 0.75].map((f) => (
        <line key={f} x1="0" y1={height * f} x2={width} y2={height * f} stroke="#1a1a1a" strokeWidth="1" />
      ))}
      <path d={areaD} fill="url(#eqGrad)" />
      <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      {/* current point */}
      <circle cx={scaleX(lastPoint.x)} cy={scaleY(lastPoint.y)} r="3.5" fill={strokeColor} />
      <circle cx={scaleX(lastPoint.x)} cy={scaleY(lastPoint.y)} r="6" fill={strokeColor} opacity="0.3">
        <animate attributeName="r" values="4;8;4" dur="2s" repeatCount="indefinite" />
        <animate attributeName="opacity" values="0.4;0.1;0.4" dur="2s" repeatCount="indefinite" />
      </circle>
      {/* labels */}
      <text x="4" y="12" fill="#6b7280" fontSize="10" fontFamily="monospace">${maxY.toLocaleString()}</text>
      <text x="4" y={height - 4} fill="#6b7280" fontSize="10" fontFamily="monospace">${minY.toLocaleString()}</text>
    </svg>
  );
}

function DailyPnlBars({ data, width = 300, height = 80 }: { data: { day: string; pnl: number }[]; width?: number; height?: number }) {
  const maxAbs = Math.max(...data.map((d) => Math.abs(d.pnl)), 1);
  const barW = width / data.length - 6;
  const midY = height / 2;

  return (
    <svg viewBox={`0 0 ${width} ${height + 20}`} className="w-full" preserveAspectRatio="xMidYMid meet">
      <line x1="0" y1={midY} x2={width} y2={midY} stroke="#333" strokeWidth="1" />
      {data.map((d, i) => {
        const barH = (Math.abs(d.pnl) / maxAbs) * (height / 2 - 4);
        const x = i * (width / data.length) + 3;
        const y = d.pnl >= 0 ? midY - barH : midY;
        const color = d.pnl >= 0 ? "#22c55e" : "#ef4444";
        return (
          <g key={i}>
            <rect x={x} y={y} width={barW} height={Math.max(barH, 1)} rx="2" fill={color} opacity="0.7" />
            <text x={x + barW / 2} y={height + 14} fill="#6b7280" fontSize="9" textAnchor="middle" fontFamily="sans-serif">{d.day}</text>
          </g>
        );
      })}
    </svg>
  );
}

function MiniEquityCurve({ points, width = 200, height = 40 }: { points: { x: number; y: number }[]; width?: number; height?: number }) {
  if (points.length < 2) return null;
  const minY = Math.min(...points.map((p) => p.y));
  const maxY = Math.max(...points.map((p) => p.y));
  const rangeY = maxY - minY || 1;
  const scaleX = (i: number) => (i / (points.length - 1)) * width;
  const scaleY = (v: number) => height - ((v - minY) / rangeY) * (height - 4) - 2;

  const pathD = points.map((p, i) => `${i === 0 ? "M" : "L"} ${scaleX(p.x).toFixed(1)} ${scaleY(p.y).toFixed(1)}`).join(" ");
  const isUp = points[points.length - 1].y >= points[0].y;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none">
      <path d={pathD} fill="none" stroke={isUp ? "#22c55e" : "#ef4444"} strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

// ── Position progress bar ────────────────────────────────────
function PriceProgressBar({ pos }: { pos: OpenPosition }) {
  const { direction, entryPrice, currentPrice, stopLoss, takeProfit } = pos;
  const range = Math.abs(takeProfit - stopLoss);
  if (range === 0) return null;

  let progress: number;
  if (direction === "LONG") {
    progress = ((currentPrice - stopLoss) / range) * 100;
  } else {
    progress = ((stopLoss - currentPrice) / range) * 100;
  }
  progress = Math.max(0, Math.min(100, progress));

  const entryPct = direction === "LONG"
    ? ((entryPrice - stopLoss) / range) * 100
    : ((stopLoss - entryPrice) / range) * 100;

  const color = progress > entryPct
    ? "bg-green-500"
    : progress > entryPct * 0.5
      ? "bg-amber-500"
      : "bg-red-500";

  return (
    <div className="w-full">
      <div className="relative h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
        <div className={`absolute left-0 top-0 h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${progress}%` }} />
        {/* entry marker */}
        <div
          className="absolute top-0 h-full w-0.5 bg-white/40"
          style={{ left: `${Math.max(0, Math.min(100, entryPct))}%` }}
        />
      </div>
      <div className="flex justify-between mt-0.5 text-[9px] text-gray-600 font-mono">
        <span>SL</span>
        <span>TP</span>
      </div>
    </div>
  );
}

// ── Component ────────────────────────────────────────────────
type TabType = "dashboard" | "positions" | "history" | "signals" | "activity" | "config";

export default function BotPage() {
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [perf, setPerf] = useState<BotPerformance | null>(null);
  const [signals, setSignals] = useState<BotSignal[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [tab, setTab] = useState<TabType>("dashboard");

  // Positions & trades state
  const [positions, setPositions] = useState<OpenPosition[]>([]);
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([]);
  const [tickCounter, setTickCounter] = useState(0);

  // Asset class mode (persisted via zustand)
  const botAssetClass = useAppStore((s) => s.botAssetClass);
  const setBotAssetClass = useAppStore((s) => s.setBotAssetClass);

  // Config state — initialise symbols from the active asset class
  const [cfgSymbols, setCfgSymbols] = useState<string[]>(ASSET_CLASS_UNIVERSE[botAssetClass]);
  const [cfgStrategies, setCfgStrategies] = useState<string[]>(["momentum", "mean_reversion", "trend_following", "breakout"]);
  // Demo mode lowers the score threshold so trades fire on mock data.
  // In Live/Paper mode the production threshold (70) applies.
  const [demoMode, setDemoMode] = useState<boolean>(true);
  const [cfgInterval, setCfgInterval] = useState(60);
  const [cfgMaxPositions, setCfgMaxPositions] = useState(3);
  const [showConfig, setShowConfig] = useState(false);

  // Risk config state
  const [riskConfig, setRiskConfig] = useState<RiskConfig>({
    sizingMode: "percent",
    fixedAmount: 5000,
    percentOfEquity: 2,
    kellyFraction: 0.25,
    maxDailyLoss: 2000,
    dailyLossUsed: 340,
    circuitBreakerActive: false,
    maxCorrelation: 0.6,
    trailingStopEnabled: {
      momentum: true,
      mean_reversion: false,
      trend_following: true,
      breakout: true,
      ict: false,
    },
  });

  // Flash tracking for P/L changes
  const prevPnlRef = useRef<Record<string, number>>({});
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set());

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Heartbeat tick — drives flash animations between API polls.
  // No longer mutates positions (real prices come from the backend
  // via fetchAll → /api/bot/positions).
  useEffect(() => {
    tickRef.current = setInterval(() => {
      setTickCounter((c) => c + 1);
    }, 1000);
    return () => {
      if (tickRef.current) clearInterval(tickRef.current);
    };
  }, []);

  // Flash animation on P/L change
  useEffect(() => {
    const newFlash = new Set<string>();
    positions.forEach((pos) => {
      const pnl = (pos.direction === "LONG" ? pos.currentPrice - pos.entryPrice : pos.entryPrice - pos.currentPrice) * pos.quantity;
      const prevPnl = prevPnlRef.current[pos.id];
      if (prevPnl !== undefined && Math.abs(pnl - prevPnl) > 0.01) {
        newFlash.add(pos.id);
      }
      prevPnlRef.current[pos.id] = pnl;
    });
    if (newFlash.size > 0) {
      setFlashIds(newFlash);
      const t = setTimeout(() => setFlashIds(new Set()), 600);
      return () => clearTimeout(t);
    }
  }, [tickCounter, positions]);

  const fetchAll = useCallback(async () => {
    try {
      const [sRes, pRes, sigRes, actRes, posRes, trdRes] = await Promise.all([
        fetch(`${API}/api/bot/status`).then((r) => r.json()),
        fetch(`${API}/api/bot/performance`).then((r) => r.json()),
        fetch(`${API}/api/bot/signals?limit=50`).then((r) => r.json()),
        fetch(`${API}/api/bot/activity?limit=100`).then((r) => r.json()),
        fetch(`${API}/api/bot/positions`).then((r) => r.json()),
        fetch(`${API}/api/bot/trades?limit=100`).then((r) => r.json()),
      ]);
      setStatus(sRes);
      setPerf(pRes);
      setSignals(sigRes.signals || []);
      setActivity(actRes.activity || []);
      setPositions(posRes.positions || []);
      setClosedTrades(trdRes.trades || []);
    } catch {
      // API offline -- keep previous state, don't blow away
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    pollRef.current = setInterval(fetchAll, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchAll]);

  // Derived data
  const equityCurve = useMemo(() => generateEquityCurve(closedTrades), [closedTrades]);
  const dailyPnl = useMemo(() => generateDailyPnl(closedTrades), [closedTrades]);

  const totalClosedPnl = useMemo(() => closedTrades.reduce((s, t) => s + t.pnl, 0), [closedTrades]);
  const wins = useMemo(() => closedTrades.filter((t) => t.pnl > 0), [closedTrades]);
  const losses = useMemo(() => closedTrades.filter((t) => t.pnl <= 0), [closedTrades]);
  const winRate = closedTrades.length > 0 ? wins.length / closedTrades.length : 0;

  const bestTrade = useMemo(() => closedTrades.reduce((best, t) => (t.pnl > (best?.pnl ?? -Infinity) ? t : best), closedTrades[0]), [closedTrades]);
  const worstTrade = useMemo(() => closedTrades.reduce((worst, t) => (t.pnl < (worst?.pnl ?? Infinity) ? t : worst), closedTrades[0]), [closedTrades]);

  // Consecutive streak
  const { winStreak, lossStreak } = useMemo(() => {
    let maxWin = 0, maxLoss = 0, curWin = 0, curLoss = 0;
    const sorted = [...closedTrades].sort((a, b) => a.exitTime - b.exitTime);
    sorted.forEach((t) => {
      if (t.pnl > 0) { curWin++; curLoss = 0; maxWin = Math.max(maxWin, curWin); }
      else { curLoss++; curWin = 0; maxLoss = Math.max(maxLoss, curLoss); }
    });
    return { winStreak: maxWin, lossStreak: maxLoss };
  }, [closedTrades]);

  // Drawdown
  const { currentDrawdown, maxDrawdown } = useMemo(() => {
    let peak = 100000;
    let maxDD = 0;
    let curDD = 0;
    equityCurve.forEach((p) => {
      if (p.y > peak) peak = p.y;
      const dd = ((peak - p.y) / peak) * 100;
      if (dd > maxDD) maxDD = dd;
      curDD = dd;
    });
    return { currentDrawdown: curDD, maxDrawdown: maxDD };
  }, [equityCurve]);

  // Unrealized P/L total
  const unrealizedTotal = useMemo(() =>
    positions.reduce((sum, pos) => {
      const pnl = (pos.direction === "LONG" ? pos.currentPrice - pos.entryPrice : pos.entryPrice - pos.currentPrice) * pos.quantity;
      return sum + pnl;
    }, 0),
    [positions, tickCounter]
  );

  const handleStart = async () => {
    setStarting(true);
    try {
      await fetch(`${API}/api/bot/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbols: cfgSymbols,
          strategies: cfgStrategies,
          interval: cfgInterval,
          max_concurrent: cfgMaxPositions,
          mode: "paper",
          // Demo mode runs a permissive score floor so the operator sees
          // signals materialise into trades within the first cycle on
          // sim data. Live/Paper-production uses settings.trade.min_score_to_trade (70).
          min_score: demoMode ? 5 : undefined,
        }),
      });
      await fetchAll();
    } catch { /* */ }
    setStarting(false);
  };

  const handleStop = async () => {
    setStopping(true);
    try {
      await fetch(`${API}/api/bot/stop`, { method: "POST" });
      await fetchAll();
    } catch { /* */ }
    setStopping(false);
  };

  const handleClosePosition = async (posId: string) => {
    const pos = positions.find((p) => p.id === posId);
    if (!pos) return;
    // Optimistic remove for snappy UX; next poll will reconcile from backend.
    setPositions((prev) => prev.filter((p) => p.id !== posId));
    try {
      await fetch(
        `${API}/api/bot/positions/${encodeURIComponent(pos.symbol)}/close`,
        { method: "POST" },
      );
      await fetchAll();
    } catch {
      /* leave reconciliation to next poll */
    }
  };

  const toggleSymbol = (sym: string) => {
    setCfgSymbols((prev) =>
      prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]
    );
  };

  const toggleStrategy = (id: string) => {
    setCfgStrategies((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  };

  const isRunning = status?.running ?? false;

  if (loading) {
    return (
      <div className="min-h-screen bg-[#080808] flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-blue-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#080808] text-white pb-24">
      {/* Header */}
      <div className="p-4 md:p-6 border-b border-[#1a1a1a]">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl ${isRunning ? "bg-green-500/20" : "bg-[#1a1a1a]"}`}>
              <Bot className={`w-6 h-6 ${isRunning ? "text-green-400" : "text-gray-400"}`} />
            </div>
            <div>
              <h1 className="text-lg md:text-2xl font-bold tracking-tight">Autonomous Trading Bot</h1>
              <div className="flex items-center gap-2 mt-0.5">
                <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${
                  isRunning ? "bg-green-500/20 text-green-400" : "bg-gray-500/20 text-gray-400"
                }`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${isRunning ? "bg-green-400 animate-pulse" : "bg-gray-500"}`} />
                  {isRunning ? "RUNNING" : "STOPPED"}
                </span>
                {isRunning && status && (
                  <span className="text-xs text-gray-500">
                    <Clock className="w-3 h-3 inline mr-1" />
                    {formatUptime(status.uptime_seconds)}
                  </span>
                )}
                {positions.length > 0 && (
                  <span className={`text-xs font-mono font-medium ${unrealizedTotal >= 0 ? "text-green-400" : "text-red-400"}`}>
                    Unreal: {fmtMoney(unrealizedTotal)}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowConfig(!showConfig)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-[#1a1a1a] hover:bg-[#252525] text-sm transition-colors"
            >
              <Settings className="w-4 h-4" />
              Config
              {showConfig ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </button>
            {isRunning ? (
              <button
                onClick={handleStop}
                disabled={stopping}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 font-medium text-sm transition-colors disabled:opacity-50"
              >
                {stopping ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
                Stop Bot
              </button>
            ) : (
              <button
                onClick={handleStart}
                disabled={starting || cfgSymbols.length === 0 || cfgStrategies.length === 0}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 font-medium text-sm transition-colors disabled:opacity-50"
              >
                {starting ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Start Bot
              </button>
            )}
          </div>
        </div>

        {/* Quick Config Panel */}
        {showConfig && (
          <div className="mt-4 p-4 rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] space-y-4">
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Symbols</label>
              <div className="flex flex-wrap gap-1.5">
                {AVAILABLE_SYMBOLS.map((sym) => (
                  <button
                    key={sym}
                    onClick={() => toggleSymbol(sym)}
                    disabled={isRunning}
                    className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                      cfgSymbols.includes(sym)
                        ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                        : "bg-[#1a1a1a] text-gray-500 border border-transparent hover:text-gray-300"
                    } ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
                  >
                    {sym}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Strategies</label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {AVAILABLE_STRATEGIES.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => toggleStrategy(s.id)}
                    disabled={isRunning}
                    className={`flex items-start gap-2 p-2.5 rounded-lg text-left transition-colors ${
                      cfgStrategies.includes(s.id)
                        ? "bg-[#1a1a1a] border border-blue-500/30"
                        : "bg-[#111] border border-transparent hover:border-[#333]"
                    } ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
                  >
                    <div
                      className="w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0"
                      style={{ background: STRATEGY_COLORS[s.id] || "#666" }}
                    />
                    <div>
                      <p className={`text-sm font-medium ${cfgStrategies.includes(s.id) ? "text-white" : "text-gray-400"}`}>
                        {s.label}
                      </p>
                      <p className="text-xs text-gray-600">{s.desc}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
            <div className="flex gap-4">
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-1 block">Scan Interval (s)</label>
                <input
                  type="number"
                  value={cfgInterval}
                  onChange={(e) => setCfgInterval(Math.max(10, +e.target.value))}
                  disabled={isRunning}
                  className="w-24 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm disabled:opacity-50"
                />
              </div>
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-1 block">Max Positions</label>
                <input
                  type="number"
                  value={cfgMaxPositions}
                  onChange={(e) => setCfgMaxPositions(Math.max(1, Math.min(10, +e.target.value)))}
                  disabled={isRunning}
                  className="w-24 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm disabled:opacity-50"
                />
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Asset-class switcher pills + Demo/Live mode */}
      <div className="flex gap-2 px-4 md:px-6 mt-4 items-center flex-wrap">
        {(["crypto", "equity", "futures", "options"] as const).map((cls) => (
          <button
            key={cls}
            disabled={isRunning}
            onClick={() => {
              setBotAssetClass(cls);
              setCfgSymbols(ASSET_CLASS_UNIVERSE[cls]);
            }}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors ${
              botAssetClass === cls
                ? "bg-blue-500/20 text-blue-400 border border-blue-500/40"
                : "bg-[#111] text-gray-500 hover:text-gray-300 border border-[#1a1a1a]"
            } ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
          >
            {cls}
          </button>
        ))}
        <span className="w-px h-5 bg-[#1a1a1a] mx-1" />
        <button
          disabled={isRunning}
          onClick={() => setDemoMode((v) => !v)}
          title={
            demoMode
              ? "Demo Mode: low score threshold so trades fire on sim data"
              : "Live Mode: production score threshold (70+)"
          }
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors flex items-center gap-1.5 ${
            demoMode
              ? "bg-amber-500/20 text-amber-400 border border-amber-500/40"
              : "bg-emerald-500/20 text-emerald-400 border border-emerald-500/40"
          } ${isRunning ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${demoMode ? "bg-amber-400" : "bg-emerald-400 animate-pulse"}`} />
          {demoMode ? "Demo" : "Live"}
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-2 mx-4 md:mx-6 mt-4 bg-[#0a0a0a] rounded-lg w-fit overflow-x-auto">
        {(["dashboard", "positions", "history", "signals", "activity", "config"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded text-xs font-medium capitalize transition-colors whitespace-nowrap flex items-center gap-1.5 ${
              tab === t ? "bg-[#1a1a1a] text-white" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            {t === "positions" && <Layers className="w-3 h-3" />}
            {t === "history" && <Clock className="w-3 h-3" />}
            {t}
            {t === "positions" && positions.length > 0 && (
              <span className="bg-blue-500/20 text-blue-400 text-[10px] px-1.5 py-0.5 rounded-full font-mono">{positions.length}</span>
            )}
          </button>
        ))}
      </div>

      <div className="p-4 md:p-6">
        {/* ═══════════════ DASHBOARD TAB ═══════════════ */}
        {tab === "dashboard" && (
          <div className="space-y-4">
            {/* Equity Curve */}
            <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold flex items-center gap-2">
                  <TrendingUp className="w-4 h-4 text-green-400" />
                  Equity Curve
                </h3>
                <div className="flex items-center gap-3 text-xs">
                  <span className="text-gray-500">Starting: <span className="text-gray-300 font-mono">$100,000</span></span>
                  <span className="text-gray-500">Current: <span className={`font-mono ${equityCurve[equityCurve.length - 1]?.y >= 100000 ? "text-green-400" : "text-red-400"}`}>
                    ${equityCurve[equityCurve.length - 1]?.y.toLocaleString()}
                  </span></span>
                </div>
              </div>
              <EquityCurveSVG points={equityCurve} />
            </div>

            {/* Performance Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <MetricCard
                label="Realized P&L"
                value={fmtMoney(totalClosedPnl)}
                color={totalClosedPnl >= 0 ? "green" : "red"}
                icon={<DollarSign className="w-4 h-4" />}
              />
              <MetricCard
                label="Unrealized"
                value={fmtMoney(unrealizedTotal)}
                color={unrealizedTotal >= 0 ? "green" : "red"}
                icon={<Activity className="w-4 h-4" />}
              />
              <MetricCard
                label="Win Rate"
                value={`${(winRate * 100).toFixed(1)}%`}
                color={winRate >= 0.5 ? "green" : "amber"}
                icon={<Target className="w-4 h-4" />}
              />
              <MetricCard
                label="Profit Factor"
                value={losses.length > 0 ? (wins.reduce((s, t) => s + t.pnl, 0) / Math.abs(losses.reduce((s, t) => s + t.pnl, 0)) || 0).toFixed(2) : "--"}
                color="blue"
                icon={<BarChart3 className="w-4 h-4" />}
              />
              <MetricCard
                label="Drawdown"
                value={`${currentDrawdown.toFixed(2)}%`}
                color={currentDrawdown > 5 ? "red" : currentDrawdown > 2 ? "amber" : "green"}
                icon={<TrendingDown className="w-4 h-4" />}
              />
              <MetricCard
                label="Open Positions"
                value={`${positions.length}`}
                color="blue"
                icon={<Layers className="w-4 h-4" />}
              />
            </div>

            {/* Daily P/L + Stats Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Daily P/L Bars */}
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-blue-400" />
                  Daily P&L (Last 7 Days)
                </h3>
                <DailyPnlBars data={dailyPnl} />
              </div>

              {/* Stats Grid */}
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <Award className="w-4 h-4 text-amber-400" />
                  Trade Stats
                </h3>
                <div className="grid grid-cols-2 gap-2">
                  <MiniStat label="Total Trades" value={closedTrades.length.toString()} />
                  <MiniStat label="Best Trade" value={bestTrade ? fmtMoney(bestTrade.pnl) : "--"} color={bestTrade?.pnl >= 0 ? "green" : "red"} sub={bestTrade?.symbol} />
                  <MiniStat label="Worst Trade" value={worstTrade ? fmtMoney(worstTrade.pnl) : "--"} color="red" sub={worstTrade?.symbol} />
                  <MiniStat label="Avg Win" value={wins.length > 0 ? fmtMoney(wins.reduce((s, t) => s + t.pnl, 0) / wins.length) : "--"} color="green" />
                  <MiniStat label="Avg Loss" value={losses.length > 0 ? fmtMoney(losses.reduce((s, t) => s + t.pnl, 0) / losses.length) : "--"} color="red" />
                  <MiniStat label="Win Streak" value={`${winStreak}`} color="green" icon={<Flame className="w-3 h-3" />} />
                  <MiniStat label="Loss Streak" value={`${lossStreak}`} color="red" icon={<Flame className="w-3 h-3" />} />
                  <MiniStat label="Max Drawdown" value={`${maxDrawdown.toFixed(2)}%`} color={maxDrawdown > 5 ? "red" : "amber"} />
                </div>
              </div>
            </div>

            {/* Strategy Breakdown */}
            {perf?.strategy_breakdown && Object.keys(perf.strategy_breakdown).length > 0 && (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-400" />
                  Strategy Performance
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(perf.strategy_breakdown).map(([name, data]) => (
                    <div key={name} className="flex items-center gap-3 p-3 rounded-lg bg-[#111] border border-[#1a1a1a]">
                      <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ background: STRATEGY_COLORS[name] || "#666" }} />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium capitalize">{name.replace(/_/g, " ")}</p>
                        <p className="text-xs text-gray-500">{data.trades} trades</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-sm font-mono ${data.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>{fmtMoney(data.pnl)}</p>
                        <p className="text-xs text-gray-500">{(data.win_rate * 100).toFixed(0)}% WR</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Active Symbols */}
            {isRunning && status?.symbols && status.symbols.length > 0 && (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <Shield className="w-4 h-4 text-blue-400" />
                  Active Watchlist
                </h3>
                <div className="flex flex-wrap gap-2">
                  {status.symbols.map((sym) => (
                    <span key={sym} className="px-3 py-1.5 bg-[#111] border border-[#1a1a1a] rounded-lg text-sm font-mono text-gray-300">{sym}</span>
                  ))}
                </div>
              </div>
            )}

            {/* Empty state */}
            {!isRunning && closedTrades.length === 0 && positions.length === 0 && (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-12 text-center">
                <Bot className="w-12 h-12 text-gray-600 mx-auto mb-3" />
                <p className="text-gray-400 font-medium">Bot is offline</p>
                <p className="text-sm text-gray-600 mt-1">
                  Configure symbols &amp; strategies above, then hit Start to begin autonomous paper trading.
                </p>
              </div>
            )}
          </div>
        )}

        {/* ═══════════════ POSITIONS TAB ═══════════════ */}
        {tab === "positions" && (
          <div className="space-y-4">
            {positions.length === 0 ? (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-12 text-center">
                <Layers className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500">No open positions</p>
                <p className="text-xs text-gray-600 mt-1">Positions will appear here when the bot opens trades</p>
              </div>
            ) : (
              <>
                {/* Summary bar */}
                <div className="flex items-center gap-4 p-3 rounded-xl bg-[#0a0a0a] border border-[#1a1a1a]">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-blue-400" />
                    <span className="text-xs text-gray-400">{positions.length} open</span>
                  </div>
                  <div className="flex-1" />
                  <div className="text-xs text-gray-400">
                    Total Unrealized:
                    <span className={`ml-2 font-mono font-semibold text-sm ${unrealizedTotal >= 0 ? "text-green-400" : "text-red-400"}`}>
                      {fmtMoney(unrealizedTotal)}
                    </span>
                  </div>
                </div>

                {/* Position cards */}
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                  {positions.map((pos) => {
                    const pnl = (pos.direction === "LONG" ? pos.currentPrice - pos.entryPrice : pos.entryPrice - pos.currentPrice) * pos.quantity;
                    const pnlPct = ((pos.direction === "LONG" ? pos.currentPrice - pos.entryPrice : pos.entryPrice - pos.currentPrice) / pos.entryPrice) * 100;
                    const rMul = computeRMultiple({ ...pos });
                    const isFlashing = flashIds.has(pos.id);
                    const held = Date.now() - pos.entryTime;

                    return (
                      <div
                        key={pos.id}
                        className={`rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4 transition-all duration-300 ${
                          isFlashing ? (pnl >= 0 ? "ring-1 ring-green-500/30 bg-green-500/[0.02]" : "ring-1 ring-red-500/30 bg-red-500/[0.02]") : ""
                        }`}
                      >
                        {/* Row 1: Symbol, direction, strategy, close */}
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-base font-bold">{pos.symbol}</span>
                            <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded ${
                              pos.direction === "LONG" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                            }`}>
                              {pos.direction === "LONG" ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                              {pos.direction}
                            </span>
                            <span className="flex items-center gap-1">
                              <span className="w-2 h-2 rounded-full" style={{ background: STRATEGY_COLORS[pos.strategy] || "#666" }} />
                              <span className="text-[10px] text-gray-500 capitalize">{pos.strategy.replace(/_/g, " ")}</span>
                            </span>
                          </div>
                          <button
                            onClick={() => handleClosePosition(pos.id)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 text-xs font-medium transition-colors"
                          >
                            <X className="w-3 h-3" />
                            Close
                          </button>
                        </div>

                        {/* Row 2: Prices grid */}
                        <div className="grid grid-cols-3 gap-3 mb-3">
                          <div>
                            <p className="text-[10px] text-gray-600 uppercase">Entry</p>
                            <p className="text-sm font-mono text-gray-300">${pos.entryPrice.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-[10px] text-gray-600 uppercase">Current</p>
                            <p className={`text-sm font-mono font-semibold ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                              ${pos.currentPrice.toLocaleString()}
                            </p>
                          </div>
                          <div>
                            <p className="text-[10px] text-gray-600 uppercase">Qty</p>
                            <p className="text-sm font-mono text-gray-300">{pos.quantity}</p>
                          </div>
                        </div>

                        {/* Row 3: P/L, R-multiple, time */}
                        <div className="grid grid-cols-3 gap-3 mb-3">
                          <div>
                            <p className="text-[10px] text-gray-600 uppercase">Unrealized P&L</p>
                            <p className={`text-sm font-mono font-bold ${pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {fmtMoney(pnl)} <span className="text-[10px] font-normal">({fmtPct(pnlPct)})</span>
                            </p>
                          </div>
                          <div>
                            <p className="text-[10px] text-gray-600 uppercase">R-Multiple</p>
                            <p className={`text-sm font-mono font-bold ${rMul >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {rMul >= 0 ? "+" : ""}{rMul.toFixed(2)}R
                            </p>
                          </div>
                          <div>
                            <p className="text-[10px] text-gray-600 uppercase">Time Held</p>
                            <p className="text-sm font-mono text-gray-300 flex items-center gap-1">
                              <Clock className="w-3 h-3 text-gray-500" />
                              {formatDuration(held)}
                            </p>
                          </div>
                        </div>

                        {/* Row 4: Progress bar */}
                        <PriceProgressBar pos={pos} />

                        {/* Row 5: SL / TP labels */}
                        <div className="flex justify-between mt-1 text-[10px] font-mono">
                          <span className="text-red-400/60">${pos.stopLoss.toLocaleString()}</span>
                          <span className="text-green-400/60">${pos.takeProfit.toLocaleString()}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        )}

        {/* ═══════════════ HISTORY TAB ═══════════════ */}
        {tab === "history" && (
          <div className="space-y-4">
            {/* Mini equity curve at top */}
            {closedTrades.length > 1 && (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-sm font-semibold flex items-center gap-2">
                    <Activity className="w-4 h-4 text-blue-400" />
                    Running Equity
                  </h3>
                  <span className={`text-sm font-mono font-semibold ${totalClosedPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                    {fmtMoney(totalClosedPnl)}
                  </span>
                </div>
                <MiniEquityCurve points={equityCurve} height={50} />
              </div>
            )}

            {closedTrades.length === 0 ? (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-12 text-center">
                <Clock className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500">No trade history yet</p>
              </div>
            ) : (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#1a1a1a] text-gray-500 text-[10px] uppercase">
                        <th className="text-left p-3">Symbol</th>
                        <th className="text-left p-3">Dir</th>
                        <th className="text-left p-3">Strategy</th>
                        <th className="text-right p-3">Entry</th>
                        <th className="text-right p-3">Exit</th>
                        <th className="text-right p-3">P&L</th>
                        <th className="text-right p-3">P&L %</th>
                        <th className="text-right p-3">R-Mult</th>
                        <th className="text-center p-3">Grade</th>
                        <th className="text-right p-3">Duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...closedTrades].sort((a, b) => b.exitTime - a.exitTime).map((trade) => {
                        const pnlPct = ((trade.direction === "LONG" ? trade.exitPrice - trade.entryPrice : trade.entryPrice - trade.exitPrice) / trade.entryPrice) * 100;
                        const rMul = computeRMultiple({ ...trade });
                        const grade = tradeGrade(rMul);
                        const dur = trade.exitTime - trade.entryTime;

                        return (
                          <tr key={trade.id} className="border-b border-[#111] hover:bg-[#111] transition-colors">
                            <td className="p-3 font-mono font-medium">{trade.symbol}</td>
                            <td className="p-3">
                              <span className={`inline-flex items-center gap-0.5 text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                trade.direction === "LONG" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                              }`}>
                                {trade.direction}
                              </span>
                            </td>
                            <td className="p-3">
                              <span className="flex items-center gap-1">
                                <span className="w-2 h-2 rounded-full" style={{ background: STRATEGY_COLORS[trade.strategy] || "#666" }} />
                                <span className="text-gray-400 capitalize text-xs">{trade.strategy.replace(/_/g, " ")}</span>
                              </span>
                            </td>
                            <td className="p-3 text-right font-mono text-xs text-gray-300">${trade.entryPrice.toLocaleString()}</td>
                            <td className="p-3 text-right font-mono text-xs text-gray-300">${trade.exitPrice.toLocaleString()}</td>
                            <td className={`p-3 text-right font-mono text-xs font-semibold ${trade.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {fmtMoney(trade.pnl)}
                            </td>
                            <td className={`p-3 text-right font-mono text-xs ${trade.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {fmtPct(pnlPct)}
                            </td>
                            <td className={`p-3 text-right font-mono text-xs ${rMul >= 0 ? "text-green-400" : "text-red-400"}`}>
                              {rMul >= 0 ? "+" : ""}{rMul.toFixed(2)}R
                            </td>
                            <td className="p-3 text-center">
                              <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${grade.color} bg-white/5`}>
                                {grade.letter}
                              </span>
                            </td>
                            <td className="p-3 text-right text-xs text-gray-500">{formatDuration(dur)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══════════════ SIGNALS TAB ═══════════════ */}
        {tab === "signals" && (
          <div className="space-y-2">
            {signals.length === 0 ? (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-12 text-center">
                <Zap className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500">No signals generated yet</p>
              </div>
            ) : (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-[#1a1a1a] text-gray-500 text-xs uppercase">
                        <th className="text-left p-3">Time</th>
                        <th className="text-left p-3">Symbol</th>
                        <th className="text-left p-3">Direction</th>
                        <th className="text-left p-3">Strategy</th>
                        <th className="text-right p-3">Confidence</th>
                        <th className="text-right p-3">Entry</th>
                        <th className="text-right p-3">SL</th>
                        <th className="text-right p-3">TP</th>
                        <th className="text-center p-3">Acted</th>
                      </tr>
                    </thead>
                    <tbody>
                      {signals.map((sig) => (
                        <tr key={sig.signal_id} className="border-b border-[#111] hover:bg-[#111]">
                          <td className="p-3 text-gray-500 text-xs">{timeAgo(sig.timestamp)}</td>
                          <td className="p-3 font-mono font-medium">{sig.symbol}</td>
                          <td className="p-3">
                            <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded ${
                              sig.direction === "long" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                            }`}>
                              {sig.direction === "long" ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                              {sig.direction.toUpperCase()}
                            </span>
                          </td>
                          <td className="p-3">
                            <span className="flex items-center gap-1.5">
                              <span className="w-2 h-2 rounded-full" style={{ background: STRATEGY_COLORS[sig.strategy] || "#666" }} />
                              <span className="text-gray-300 capitalize text-xs">{sig.strategy.replace(/_/g, " ")}</span>
                            </span>
                          </td>
                          <td className="p-3 text-right">
                            <span className={`font-mono text-xs ${
                              sig.confidence >= 0.7 ? "text-green-400" : sig.confidence >= 0.55 ? "text-amber-400" : "text-gray-500"
                            }`}>
                              {(sig.confidence * 100).toFixed(0)}%
                            </span>
                          </td>
                          <td className="p-3 text-right font-mono text-xs">${sig.entry.toLocaleString()}</td>
                          <td className="p-3 text-right font-mono text-xs text-red-400/70">${sig.stop_loss.toLocaleString()}</td>
                          <td className="p-3 text-right font-mono text-xs text-green-400/70">${sig.take_profit.toLocaleString()}</td>
                          <td className="p-3 text-center">
                            {sig.acted ? <CheckCircle className="w-4 h-4 text-green-400 mx-auto" /> : <XCircle className="w-4 h-4 text-gray-600 mx-auto" />}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ═══════════════ ACTIVITY TAB ═══════════════ */}
        {tab === "activity" && (
          <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] overflow-hidden">
            {activity.length === 0 ? (
              <div className="p-12 text-center">
                <Activity className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-500">No activity yet</p>
              </div>
            ) : (
              <div className="max-h-[600px] overflow-y-auto divide-y divide-[#111]">
                {activity.map((entry, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 hover:bg-[#111] overflow-hidden">
                    <ActivityIcon type={entry.type} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-300 break-words">{entry.message}</p>
                      <p className="text-xs text-gray-600 mt-0.5">{timeAgo(entry.timestamp)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ═══════════════ CONFIG TAB ═══════════════ */}
        {tab === "config" && (
          <div className="space-y-4 max-w-3xl">
            {/* Bot Configuration */}
            <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4 space-y-4">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Settings className="w-4 h-4 text-gray-400" />
                Bot Configuration
              </h3>
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Symbols ({cfgSymbols.length} selected)</label>
                <div className="flex flex-wrap gap-1.5">
                  {AVAILABLE_SYMBOLS.map((sym) => (
                    <button
                      key={sym}
                      onClick={() => toggleSymbol(sym)}
                      disabled={isRunning}
                      className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                        cfgSymbols.includes(sym)
                          ? "bg-blue-500/20 text-blue-400 border border-blue-500/30"
                          : "bg-[#1a1a1a] text-gray-500 border border-transparent hover:text-gray-300"
                      }`}
                    >
                      {sym}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Strategies ({cfgStrategies.length} selected)</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {AVAILABLE_STRATEGIES.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => toggleStrategy(s.id)}
                      disabled={isRunning}
                      className={`flex items-start gap-2 p-3 rounded-lg text-left transition-colors ${
                        cfgStrategies.includes(s.id)
                          ? "bg-[#1a1a1a] border border-blue-500/30"
                          : "bg-[#111] border border-transparent hover:border-[#333]"
                      }`}
                    >
                      <div className="w-3 h-3 rounded-full mt-0.5 flex-shrink-0" style={{ background: STRATEGY_COLORS[s.id] || "#666" }} />
                      <div>
                        <p className={`text-sm font-medium ${cfgStrategies.includes(s.id) ? "text-white" : "text-gray-400"}`}>{s.label}</p>
                        <p className="text-xs text-gray-600 mt-0.5">{s.desc}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex gap-6">
                <div>
                  <label className="text-xs text-gray-400 uppercase tracking-wider mb-1 block">Scan Interval</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      value={cfgInterval}
                      onChange={(e) => setCfgInterval(Math.max(10, +e.target.value))}
                      disabled={isRunning}
                      className="w-20 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm disabled:opacity-50"
                    />
                    <span className="text-xs text-gray-500">seconds</span>
                  </div>
                </div>
                <div>
                  <label className="text-xs text-gray-400 uppercase tracking-wider mb-1 block">Max Positions</label>
                  <input
                    type="number"
                    value={cfgMaxPositions}
                    onChange={(e) => setCfgMaxPositions(Math.max(1, Math.min(10, +e.target.value)))}
                    disabled={isRunning}
                    className="w-20 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm disabled:opacity-50"
                  />
                </div>
              </div>
              {isRunning && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  Stop the bot to change configuration
                </div>
              )}
            </div>

            {/* ── Risk Management Panel ── */}
            <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4 space-y-5">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <Shield className="w-4 h-4 text-red-400" />
                Risk Management
              </h3>

              {/* Position Sizing */}
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Position Sizing Mode</label>
                <div className="grid grid-cols-3 gap-2">
                  {([
                    { id: "fixed" as const, label: "Fixed $", icon: <DollarSign className="w-3.5 h-3.5" /> },
                    { id: "percent" as const, label: "% of Equity", icon: <Percent className="w-3.5 h-3.5" /> },
                    { id: "kelly" as const, label: "Kelly Criterion", icon: <Target className="w-3.5 h-3.5" /> },
                  ]).map((mode) => (
                    <button
                      key={mode.id}
                      onClick={() => setRiskConfig((p) => ({ ...p, sizingMode: mode.id }))}
                      className={`flex items-center gap-2 p-3 rounded-lg text-xs font-medium transition-colors ${
                        riskConfig.sizingMode === mode.id
                          ? "bg-blue-500/10 border border-blue-500/30 text-blue-400"
                          : "bg-[#111] border border-[#1a1a1a] text-gray-500 hover:text-gray-300"
                      }`}
                    >
                      {mode.icon}
                      {mode.label}
                    </button>
                  ))}
                </div>
                <div className="mt-3">
                  {riskConfig.sizingMode === "fixed" && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">Amount per trade:</span>
                      <div className="flex items-center">
                        <span className="text-xs text-gray-600 mr-1">$</span>
                        <input
                          type="number"
                          value={riskConfig.fixedAmount}
                          onChange={(e) => setRiskConfig((p) => ({ ...p, fixedAmount: Math.max(100, +e.target.value) }))}
                          className="w-28 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm font-mono"
                        />
                      </div>
                    </div>
                  )}
                  {riskConfig.sizingMode === "percent" && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">Risk per trade:</span>
                      <input
                        type="number"
                        step="0.5"
                        value={riskConfig.percentOfEquity}
                        onChange={(e) => setRiskConfig((p) => ({ ...p, percentOfEquity: Math.max(0.1, Math.min(10, +e.target.value)) }))}
                        className="w-20 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm font-mono"
                      />
                      <span className="text-xs text-gray-600">% of equity</span>
                    </div>
                  )}
                  {riskConfig.sizingMode === "kelly" && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">Kelly fraction:</span>
                      <input
                        type="number"
                        step="0.05"
                        value={riskConfig.kellyFraction}
                        onChange={(e) => setRiskConfig((p) => ({ ...p, kellyFraction: Math.max(0.05, Math.min(1, +e.target.value)) }))}
                        className="w-20 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm font-mono"
                      />
                      <span className="text-xs text-gray-600">of full Kelly</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Daily Loss Limit + Circuit Breaker */}
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Daily Loss Limit</label>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1">
                    <span className="text-xs text-gray-600">$</span>
                    <input
                      type="number"
                      value={riskConfig.maxDailyLoss}
                      onChange={(e) => setRiskConfig((p) => ({ ...p, maxDailyLoss: Math.max(100, +e.target.value) }))}
                      className="w-28 bg-[#1a1a1a] border border-[#333] rounded px-2 py-1.5 text-sm font-mono"
                    />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] text-gray-500">Used today: ${riskConfig.dailyLossUsed.toLocaleString()}</span>
                      <span className="text-[10px] text-gray-500">{((riskConfig.dailyLossUsed / riskConfig.maxDailyLoss) * 100).toFixed(0)}%</span>
                    </div>
                    <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${
                          riskConfig.dailyLossUsed / riskConfig.maxDailyLoss > 0.8 ? "bg-red-500" :
                          riskConfig.dailyLossUsed / riskConfig.maxDailyLoss > 0.5 ? "bg-amber-500" : "bg-green-500"
                        }`}
                        style={{ width: `${Math.min(100, (riskConfig.dailyLossUsed / riskConfig.maxDailyLoss) * 100)}%` }}
                      />
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 mt-3">
                  <button
                    onClick={() => setRiskConfig((p) => ({ ...p, circuitBreakerActive: !p.circuitBreakerActive }))}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors ${
                      riskConfig.circuitBreakerActive
                        ? "bg-red-500/20 text-red-400 border border-red-500/30"
                        : "bg-[#111] text-gray-500 border border-[#1a1a1a] hover:text-gray-300"
                    }`}
                  >
                    {riskConfig.circuitBreakerActive ? <Lock className="w-3.5 h-3.5" /> : <Unlock className="w-3.5 h-3.5" />}
                    Circuit Breaker {riskConfig.circuitBreakerActive ? "ACTIVE" : "Armed"}
                  </button>
                  <span className="text-[10px] text-gray-600">Auto-halts trading when daily limit is hit</span>
                </div>
              </div>

              {/* Max Correlation */}
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Max Position Correlation</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0.1"
                    max="1"
                    step="0.05"
                    value={riskConfig.maxCorrelation}
                    onChange={(e) => setRiskConfig((p) => ({ ...p, maxCorrelation: +e.target.value }))}
                    className="flex-1 accent-blue-500"
                  />
                  <span className="text-sm font-mono text-gray-300 w-12 text-right">{riskConfig.maxCorrelation.toFixed(2)}</span>
                </div>
                <p className="text-[10px] text-gray-600 mt-1">Blocks new positions if correlation to existing holdings exceeds threshold</p>
              </div>

              {/* Trailing Stop per Strategy */}
              <div>
                <label className="text-xs text-gray-400 uppercase tracking-wider mb-2 block">Trailing Stop (per Strategy)</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {AVAILABLE_STRATEGIES.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setRiskConfig((p) => ({
                        ...p,
                        trailingStopEnabled: { ...p.trailingStopEnabled, [s.id]: !p.trailingStopEnabled[s.id] },
                      }))}
                      className={`flex items-center gap-2 p-2.5 rounded-lg text-xs transition-colors ${
                        riskConfig.trailingStopEnabled[s.id]
                          ? "bg-green-500/10 border border-green-500/20 text-green-400"
                          : "bg-[#111] border border-[#1a1a1a] text-gray-500"
                      }`}
                    >
                      <span className="w-2.5 h-2.5 rounded-full" style={{ background: STRATEGY_COLORS[s.id] || "#666" }} />
                      <span className="flex-1">{s.label}</span>
                      {riskConfig.trailingStopEnabled[s.id] ? (
                        <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                      ) : (
                        <XCircle className="w-3.5 h-3.5 text-gray-600" />
                      )}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Static Risk Limits */}
            <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Risk Limits (Policy Engine)
              </h3>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="flex justify-between p-2 bg-[#111] rounded">
                  <span className="text-gray-400">Max Daily Loss</span>
                  <span className="text-red-400 font-mono">-4%</span>
                </div>
                <div className="flex justify-between p-2 bg-[#111] rounded">
                  <span className="text-gray-400">Max Drawdown</span>
                  <span className="text-red-400 font-mono">-15%</span>
                </div>
                <div className="flex justify-between p-2 bg-[#111] rounded">
                  <span className="text-gray-400">Portfolio Heat</span>
                  <span className="text-amber-400 font-mono">20%</span>
                </div>
                <div className="flex justify-between p-2 bg-[#111] rounded">
                  <span className="text-gray-400">Max Leverage</span>
                  <span className="text-amber-400 font-mono">8x</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Sub-Components ───────────────────────────────────────────

function MetricCard({ label, value, color, icon }: { label: string; value: string; color: string; icon: React.ReactNode }) {
  const colors: Record<string, string> = {
    green: "text-green-400",
    red: "text-red-400",
    amber: "text-amber-400",
    blue: "text-blue-400",
  };
  return (
    <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-3">
      <div className="flex items-center gap-1.5 text-gray-500 mb-1">
        {icon}
        <span className="text-[10px] uppercase tracking-wider">{label}</span>
      </div>
      <p className={`text-lg font-bold font-mono ${colors[color] || "text-white"}`}>{value}</p>
    </div>
  );
}

function MiniStat({ label, value, color, sub, icon }: { label: string; value: string; color?: string; sub?: string; icon?: React.ReactNode }) {
  const colors: Record<string, string> = {
    green: "text-green-400",
    red: "text-red-400",
    amber: "text-amber-400",
    blue: "text-blue-400",
  };
  return (
    <div className="p-2.5 rounded-lg bg-[#111] border border-[#1a1a1a]">
      <p className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</p>
      <div className="flex items-center gap-1 mt-0.5">
        {icon}
        <span className={`text-sm font-bold font-mono ${color ? colors[color] || "text-white" : "text-white"}`}>{value}</span>
        {sub && <span className="text-[10px] text-gray-600 ml-1">{sub}</span>}
      </div>
    </div>
  );
}

function SignalRow({ signal }: { signal: BotSignal }) {
  return (
    <div className="flex items-center gap-3 p-2 rounded-lg bg-[#111] border border-[#1a1a1a]">
      <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: STRATEGY_COLORS[signal.strategy] || "#666" }} />
      <span className="font-mono text-sm font-medium w-16">{signal.symbol}</span>
      <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${
        signal.direction === "long" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
      }`}>
        {signal.direction.toUpperCase()}
      </span>
      <span className="text-xs text-gray-500 capitalize flex-1">{signal.strategy.replace(/_/g, " ")}</span>
      <span className="text-xs font-mono text-gray-400">{(signal.confidence * 100).toFixed(0)}%</span>
      <span className="text-xs text-gray-600">{timeAgo(signal.timestamp)}</span>
      {signal.acted && <CheckCircle className="w-3.5 h-3.5 text-green-500" />}
    </div>
  );
}

function ActivityIcon({ type }: { type: string }) {
  switch (type) {
    case "signal":
      return <Zap className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />;
    case "trade":
      return <TrendingUp className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />;
    case "close":
      return <Target className="w-4 h-4 text-blue-400 mt-0.5 flex-shrink-0" />;
    case "risk":
      return <Shield className="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0" />;
    case "error":
      return <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />;
    default:
      return <Activity className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0" />;
  }
}
