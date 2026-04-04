"use client";

import { useState, useMemo, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import {
  GitCompare,
  TrendingUp,
  TrendingDown,
  History,
  AlertTriangle,
  ChevronDown,
  ArrowRight,
  BarChart3,
  Zap,
  Shield,
  Target,
  Info,
} from "lucide-react";

/* ════════════════════════════════════════════════════════════════
   TYPES
   ════════════════════════════════════════════════════════════════ */

type Lookback = "30d" | "90d" | "1y";

interface SectorData {
  name: string;
  performance: number;
  flowDirection: "inflow" | "outflow" | "neutral";
  flowMagnitude: number;
  relativeStrength: number;
}

interface HistoricalEvent {
  id: string;
  label: string;
  period: string;
  description: string;
  impacts: {
    asset: string;
    maxDrawdown: number;
    recoveryDays: number;
    totalReturn: number;
  }[];
}

interface PivotSignal {
  id: string;
  pair: string;
  message: string;
  confidence: number;
  direction: "bullish" | "bearish" | "neutral";
  timeDetected: string;
}

/* ════════════════════════════════════════════════════════════════
   ASSETS
   ════════════════════════════════════════════════════════════════ */

const ASSETS = [
  "BTC", "ETH", "SOL", "SPY", "QQQ", "AAPL", "TSLA", "NVDA", "GC", "CL", "DXY", "VIX",
];

const ASSET_LABELS: Record<string, string> = {
  BTC: "Bitcoin", ETH: "Ethereum", SOL: "Solana",
  SPY: "S&P 500", QQQ: "Nasdaq 100", AAPL: "Apple",
  TSLA: "Tesla", NVDA: "NVIDIA", GC: "Gold",
  CL: "Crude Oil", DXY: "US Dollar", VIX: "Volatility",
};

/* ════════════════════════════════════════════════════════════════
   CORRELATION DATA GENERATOR
   ════════════════════════════════════════════════════════════════ */

function generateCorrelationMatrix(lookback: Lookback): number[][] {
  // Base correlations reflecting real-world relationships
  const base: Record<string, Record<string, number>> = {
    BTC:  { BTC: 1.00, ETH: 0.87, SOL: 0.82, SPY: 0.42, QQQ: 0.48, AAPL: 0.35, TSLA: 0.52, NVDA: 0.45, GC: 0.08, CL: 0.15, DXY: -0.38, VIX: -0.55 },
    ETH:  { BTC: 0.87, ETH: 1.00, SOL: 0.88, SPY: 0.38, QQQ: 0.44, AAPL: 0.30, TSLA: 0.48, NVDA: 0.42, GC: 0.05, CL: 0.12, DXY: -0.35, VIX: -0.50 },
    SOL:  { BTC: 0.82, ETH: 0.88, SOL: 1.00, SPY: 0.35, QQQ: 0.40, AAPL: 0.28, TSLA: 0.55, NVDA: 0.48, GC: 0.02, CL: 0.10, DXY: -0.32, VIX: -0.48 },
    SPY:  { BTC: 0.42, ETH: 0.38, SOL: 0.35, SPY: 1.00, QQQ: 0.95, AAPL: 0.88, TSLA: 0.72, NVDA: 0.82, GC: -0.15, CL: 0.25, DXY: -0.20, VIX: -0.82 },
    QQQ:  { BTC: 0.48, ETH: 0.44, SOL: 0.40, SPY: 0.95, QQQ: 1.00, AAPL: 0.92, TSLA: 0.78, NVDA: 0.90, GC: -0.18, CL: 0.20, DXY: -0.22, VIX: -0.78 },
    AAPL: { BTC: 0.35, ETH: 0.30, SOL: 0.28, SPY: 0.88, QQQ: 0.92, AAPL: 1.00, TSLA: 0.62, NVDA: 0.78, GC: -0.10, CL: 0.18, DXY: -0.15, VIX: -0.70 },
    TSLA: { BTC: 0.52, ETH: 0.48, SOL: 0.55, SPY: 0.72, QQQ: 0.78, AAPL: 0.62, TSLA: 1.00, NVDA: 0.72, GC: -0.08, CL: 0.22, DXY: -0.25, VIX: -0.65 },
    NVDA: { BTC: 0.45, ETH: 0.42, SOL: 0.48, SPY: 0.82, QQQ: 0.90, AAPL: 0.78, TSLA: 0.72, NVDA: 1.00, GC: -0.12, CL: 0.15, DXY: -0.18, VIX: -0.72 },
    GC:   { BTC: 0.08, ETH: 0.05, SOL: 0.02, SPY: -0.15, QQQ: -0.18, AAPL: -0.10, TSLA: -0.08, NVDA: -0.12, GC: 1.00, CL: 0.22, DXY: -0.45, VIX: 0.30 },
    CL:   { BTC: 0.15, ETH: 0.12, SOL: 0.10, SPY: 0.25, QQQ: 0.20, AAPL: 0.18, TSLA: 0.22, NVDA: 0.15, GC: 0.22, CL: 1.00, DXY: -0.30, VIX: -0.15 },
    DXY:  { BTC: -0.38, ETH: -0.35, SOL: -0.32, SPY: -0.20, QQQ: -0.22, AAPL: -0.15, TSLA: -0.25, NVDA: -0.18, GC: -0.45, CL: -0.30, DXY: 1.00, VIX: 0.18 },
    VIX:  { BTC: -0.55, ETH: -0.50, SOL: -0.48, SPY: -0.82, QQQ: -0.78, AAPL: -0.70, TSLA: -0.65, NVDA: -0.72, GC: 0.30, CL: -0.15, DXY: 0.18, VIX: 1.00 },
  };

  // Apply lookback-specific noise
  const noiseFactor = lookback === "30d" ? 0.12 : lookback === "90d" ? 0.06 : 0.03;
  const seed = lookback === "30d" ? 42 : lookback === "90d" ? 137 : 256;

  function seededRandom(s: number): number {
    const x = Math.sin(s) * 10000;
    return x - Math.floor(x);
  }

  return ASSETS.map((a, i) =>
    ASSETS.map((b, j) => {
      if (i === j) return 1;
      const baseVal = base[a][b];
      const noise = (seededRandom(seed + i * 100 + j) - 0.5) * 2 * noiseFactor;
      return Math.max(-1, Math.min(1, parseFloat((baseVal + noise).toFixed(3))));
    })
  );
}

/* ════════════════════════════════════════════════════════════════
   SECTOR DATA GENERATOR
   ════════════════════════════════════════════════════════════════ */

function generateSectorData(lookback: Lookback): SectorData[] {
  const sectors: { name: string; base30: number; base90: number; base1y: number }[] = [
    { name: "Technology",      base30: 3.2,  base90: 8.5,  base1y: 22.4 },
    { name: "Healthcare",      base30: 1.8,  base90: 4.2,  base1y: 12.1 },
    { name: "Finance",         base30: 2.5,  base90: 6.8,  base1y: 18.5 },
    { name: "Energy",          base30: -1.2, base90: -3.5, base1y: -8.2 },
    { name: "Consumer",        base30: 0.8,  base90: 3.1,  base1y: 9.5 },
    { name: "Industrials",     base30: 1.5,  base90: 5.2,  base1y: 14.8 },
    { name: "Utilities",       base30: -0.5, base90: 1.2,  base1y: 4.5 },
    { name: "Real Estate",     base30: -0.8, base90: -1.5, base1y: -2.8 },
    { name: "Materials",       base30: 0.3,  base90: 2.8,  base1y: 7.2 },
    { name: "Communications",  base30: 2.8,  base90: 7.2,  base1y: 19.8 },
  ];

  return sectors.map((s) => {
    const perf = lookback === "30d" ? s.base30 : lookback === "90d" ? s.base90 : s.base1y;
    const flow = perf > 2 ? "inflow" : perf < -0.5 ? "outflow" : "neutral";
    const mag = Math.abs(perf) * 0.4 + Math.random() * 0.5;
    return {
      name: s.name,
      performance: perf,
      flowDirection: flow,
      flowMagnitude: parseFloat(mag.toFixed(1)),
      relativeStrength: parseFloat((perf / 3.2 * 100).toFixed(0)) / 100,
    };
  });
}

/* ════════════════════════════════════════════════════════════════
   HISTORICAL EVENTS DATA
   ════════════════════════════════════════════════════════════════ */

const HISTORICAL_EVENTS: HistoricalEvent[] = [
  {
    id: "covid",
    label: "COVID Crash (Mar 2020)",
    period: "Feb 19 - Mar 23, 2020",
    description: "Global pandemic triggered fastest bear market in history. SPY fell 34% in 23 trading days.",
    impacts: [
      { asset: "BTC",  maxDrawdown: -53.2, recoveryDays: 218, totalReturn: -8.4 },
      { asset: "ETH",  maxDrawdown: -63.1, recoveryDays: 295, totalReturn: -15.2 },
      { asset: "SOL",  maxDrawdown: -58.0, recoveryDays: 180, totalReturn: -12.0 },
      { asset: "SPY",  maxDrawdown: -33.9, recoveryDays: 148, totalReturn: -2.1 },
      { asset: "QQQ",  maxDrawdown: -28.6, recoveryDays: 82,  totalReturn: 5.8 },
      { asset: "AAPL", maxDrawdown: -31.2, recoveryDays: 96,  totalReturn: 12.5 },
      { asset: "TSLA", maxDrawdown: -60.6, recoveryDays: 42,  totalReturn: 68.2 },
      { asset: "NVDA", maxDrawdown: -35.8, recoveryDays: 105, totalReturn: 28.4 },
      { asset: "GC",   maxDrawdown: -12.4, recoveryDays: 18,  totalReturn: 8.2 },
      { asset: "CL",   maxDrawdown: -72.5, recoveryDays: 365, totalReturn: -42.8 },
      { asset: "DXY",  maxDrawdown: -4.2,  recoveryDays: 45,  totalReturn: 1.8 },
      { asset: "VIX",  maxDrawdown: 0,     recoveryDays: 0,   totalReturn: 285.6 },
    ],
  },
  {
    id: "fed-hike",
    label: "Fed Rate Hike Cycle (2022)",
    period: "Jan - Dec 2022",
    description: "Aggressive rate hikes crushed risk assets. 425bps of tightening in a single year.",
    impacts: [
      { asset: "BTC",  maxDrawdown: -76.8, recoveryDays: 540,  totalReturn: -64.2 },
      { asset: "ETH",  maxDrawdown: -82.1, recoveryDays: 580,  totalReturn: -67.5 },
      { asset: "SOL",  maxDrawdown: -96.2, recoveryDays: 650,  totalReturn: -93.8 },
      { asset: "SPY",  maxDrawdown: -25.4, recoveryDays: 285,  totalReturn: -19.4 },
      { asset: "QQQ",  maxDrawdown: -35.1, recoveryDays: 350,  totalReturn: -32.6 },
      { asset: "AAPL", maxDrawdown: -30.8, recoveryDays: 310,  totalReturn: -26.4 },
      { asset: "TSLA", maxDrawdown: -73.6, recoveryDays: 480,  totalReturn: -65.0 },
      { asset: "NVDA", maxDrawdown: -66.4, recoveryDays: 320,  totalReturn: -50.3 },
      { asset: "GC",   maxDrawdown: -22.1, recoveryDays: 195,  totalReturn: -0.3 },
      { asset: "CL",   maxDrawdown: -40.2, recoveryDays: 120,  totalReturn: 6.7 },
      { asset: "DXY",  maxDrawdown: -2.8,  recoveryDays: 15,   totalReturn: 7.9 },
      { asset: "VIX",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 28.4 },
    ],
  },
  {
    id: "svb",
    label: "SVB Crisis (Mar 2023)",
    period: "Mar 8 - Mar 15, 2023",
    description: "Silicon Valley Bank collapse sparked banking contagion fears. Regional banks plummeted.",
    impacts: [
      { asset: "BTC",  maxDrawdown: -10.2, recoveryDays: 14,  totalReturn: 22.5 },
      { asset: "ETH",  maxDrawdown: -12.8, recoveryDays: 18,  totalReturn: 18.2 },
      { asset: "SOL",  maxDrawdown: -15.5, recoveryDays: 22,  totalReturn: 12.8 },
      { asset: "SPY",  maxDrawdown: -5.8,  recoveryDays: 28,  totalReturn: -1.2 },
      { asset: "QQQ",  maxDrawdown: -4.2,  recoveryDays: 15,  totalReturn: 5.8 },
      { asset: "AAPL", maxDrawdown: -3.5,  recoveryDays: 12,  totalReturn: 8.2 },
      { asset: "TSLA", maxDrawdown: -8.2,  recoveryDays: 20,  totalReturn: 3.5 },
      { asset: "NVDA", maxDrawdown: -5.1,  recoveryDays: 8,   totalReturn: 15.2 },
      { asset: "GC",   maxDrawdown: -1.2,  recoveryDays: 3,   totalReturn: 9.5 },
      { asset: "CL",   maxDrawdown: -15.8, recoveryDays: 45,  totalReturn: -8.2 },
      { asset: "DXY",  maxDrawdown: -3.5,  recoveryDays: 22,  totalReturn: -2.1 },
      { asset: "VIX",  maxDrawdown: 0,     recoveryDays: 0,   totalReturn: 52.8 },
    ],
  },
  {
    id: "ai-rally",
    label: "AI Rally (2023-2024)",
    period: "Jan 2023 - Mar 2024",
    description: "ChatGPT-driven AI mania lifted semiconductors and mega-cap tech to all-time highs.",
    impacts: [
      { asset: "BTC",  maxDrawdown: -20.8, recoveryDays: 45,   totalReturn: 165.2 },
      { asset: "ETH",  maxDrawdown: -25.2, recoveryDays: 60,   totalReturn: 88.5 },
      { asset: "SOL",  maxDrawdown: -32.0, recoveryDays: 90,   totalReturn: 842.0 },
      { asset: "SPY",  maxDrawdown: -10.3, recoveryDays: 120,  totalReturn: 32.8 },
      { asset: "QQQ",  maxDrawdown: -8.5,  recoveryDays: 85,   totalReturn: 52.4 },
      { asset: "AAPL", maxDrawdown: -12.2, recoveryDays: 105,  totalReturn: 28.5 },
      { asset: "TSLA", maxDrawdown: -42.5, recoveryDays: 180,  totalReturn: -15.2 },
      { asset: "NVDA", maxDrawdown: -15.8, recoveryDays: 25,   totalReturn: 478.0 },
      { asset: "GC",   maxDrawdown: -8.5,  recoveryDays: 65,   totalReturn: 18.2 },
      { asset: "CL",   maxDrawdown: -22.5, recoveryDays: 150,  totalReturn: -5.8 },
      { asset: "DXY",  maxDrawdown: -5.8,  recoveryDays: 95,   totalReturn: -2.5 },
      { asset: "VIX",  maxDrawdown: -45.2, recoveryDays: 0,    totalReturn: -32.5 },
    ],
  },
  {
    id: "dotcom",
    label: "Dot-com Bubble (2000)",
    period: "Mar 2000 - Oct 2002",
    description: "Internet bubble burst. Nasdaq lost 78% from peak. Multi-year bear market for tech.",
    impacts: [
      { asset: "BTC",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "ETH",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "SOL",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "SPY",  maxDrawdown: -49.1, recoveryDays: 1485, totalReturn: -44.7 },
      { asset: "QQQ",  maxDrawdown: -82.9, recoveryDays: 5285, totalReturn: -78.4 },
      { asset: "AAPL", maxDrawdown: -81.5, recoveryDays: 2400, totalReturn: -72.3 },
      { asset: "TSLA", maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "NVDA", maxDrawdown: -90.2, recoveryDays: 3650, totalReturn: -85.1 },
      { asset: "GC",   maxDrawdown: -15.8, recoveryDays: 280,  totalReturn: 12.5 },
      { asset: "CL",   maxDrawdown: -55.2, recoveryDays: 1095, totalReturn: -22.8 },
      { asset: "DXY",  maxDrawdown: -8.2,  recoveryDays: 365,  totalReturn: 5.8 },
      { asset: "VIX",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 125.0 },
    ],
  },
  {
    id: "gfc",
    label: "2008 Financial Crisis",
    period: "Oct 2007 - Mar 2009",
    description: "Subprime mortgage crisis cascaded into global financial meltdown. Lehman Brothers collapsed.",
    impacts: [
      { asset: "BTC",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "ETH",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "SOL",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "SPY",  maxDrawdown: -56.8, recoveryDays: 1480, totalReturn: -52.6 },
      { asset: "QQQ",  maxDrawdown: -53.5, recoveryDays: 1095, totalReturn: -48.2 },
      { asset: "AAPL", maxDrawdown: -61.2, recoveryDays: 545,  totalReturn: -45.8 },
      { asset: "TSLA", maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 0 },
      { asset: "NVDA", maxDrawdown: -85.0, recoveryDays: 1825, totalReturn: -78.5 },
      { asset: "GC",   maxDrawdown: -30.2, recoveryDays: 125,  totalReturn: 25.5 },
      { asset: "CL",   maxDrawdown: -78.1, recoveryDays: 730,  totalReturn: -55.2 },
      { asset: "DXY",  maxDrawdown: -10.5, recoveryDays: 185,  totalReturn: 12.2 },
      { asset: "VIX",  maxDrawdown: 0,     recoveryDays: 0,    totalReturn: 358.5 },
    ],
  },
];

/* ════════════════════════════════════════════════════════════════
   PIVOT SIGNALS GENERATOR
   ════════════════════════════════════════════════════════════════ */

function generatePivotSignals(): PivotSignal[] {
  return [
    {
      id: "1",
      pair: "NVDA / QQQ",
      message: "NVDA decoupling from QQQ -- AI sector divergence from broad tech. Relative outperformance accelerating.",
      confidence: 0.88,
      direction: "bullish",
      timeDetected: "2h ago",
    },
    {
      id: "2",
      pair: "BTC / SPY",
      message: "BTC-SPY correlation breakdown below 0.30 -- crypto trading as independent macro asset. Decoupling window.",
      confidence: 0.82,
      direction: "bullish",
      timeDetected: "6h ago",
    },
    {
      id: "3",
      pair: "GC / DXY",
      message: "Gold surging despite dollar strength -- historical inverse correlation inverted. Safe haven demand dominant.",
      confidence: 0.91,
      direction: "bullish",
      timeDetected: "1d ago",
    },
    {
      id: "4",
      pair: "Energy / SPY",
      message: "Energy sector underperforming SPY by 3.2 sigma -- mean reversion setup or structural rotation out.",
      confidence: 0.75,
      direction: "bearish",
      timeDetected: "3h ago",
    },
    {
      id: "5",
      pair: "TSLA / QQQ",
      message: "TSLA beta compression vs QQQ -- retail momentum fading. Watch for continuation or snap-back.",
      confidence: 0.68,
      direction: "neutral",
      timeDetected: "12h ago",
    },
    {
      id: "6",
      pair: "VIX / CL",
      message: "VIX-Oil positive correlation spike -- geopolitical risk premium building. Hedging activity elevated.",
      confidence: 0.79,
      direction: "bearish",
      timeDetected: "4h ago",
    },
  ];
}

/* ════════════════════════════════════════════════════════════════
   HELPER: CORRELATION COLOR
   ════════════════════════════════════════════════════════════════ */

function correlationColor(val: number): string {
  if (val === 1) return "bg-blue-600";
  const abs = Math.abs(val);
  if (val > 0) {
    if (abs > 0.8) return "bg-blue-600/90";
    if (abs > 0.6) return "bg-blue-500/70";
    if (abs > 0.4) return "bg-blue-400/50";
    if (abs > 0.2) return "bg-blue-300/30";
    return "bg-blue-200/15";
  } else {
    if (abs > 0.8) return "bg-red-600/90";
    if (abs > 0.6) return "bg-red-500/70";
    if (abs > 0.4) return "bg-red-400/50";
    if (abs > 0.2) return "bg-red-300/30";
    return "bg-red-200/15";
  }
}

function correlationTextColor(val: number): string {
  const abs = Math.abs(val);
  if (abs > 0.5) return "text-white";
  return "text-text-secondary";
}

/* ════════════════════════════════════════════════════════════════
   COMPONENT: CORRELATION MATRIX
   ════════════════════════════════════════════════════════════════ */

function CorrelationMatrix({ lookback }: { lookback: Lookback }) {
  const [hoveredCell, setHoveredCell] = useState<{ row: number; col: number } | null>(null);

  const matrix = useMemo(() => generateCorrelationMatrix(lookback), [lookback]);

  return (
    <div className="overflow-x-auto">
      <div className="min-w-[700px]">
        {/* Header row */}
        <div className="flex">
          <div className="w-14 h-10 shrink-0" />
          {ASSETS.map((asset) => (
            <div
              key={asset}
              className="flex-1 h-10 flex items-center justify-center text-[11px] font-mono text-text-secondary"
            >
              {asset}
            </div>
          ))}
        </div>

        {/* Matrix rows */}
        {ASSETS.map((rowAsset, rowIdx) => (
          <div key={rowAsset} className="flex">
            <div className="w-14 h-10 shrink-0 flex items-center justify-end pr-2 text-[11px] font-mono text-text-secondary">
              {rowAsset}
            </div>
            {ASSETS.map((colAsset, colIdx) => {
              const val = matrix[rowIdx][colIdx];
              const isHovered =
                hoveredCell?.row === rowIdx && hoveredCell?.col === colIdx;
              const isRowHighlight = hoveredCell?.row === rowIdx || hoveredCell?.col === rowIdx;
              const isColHighlight = hoveredCell?.row === colIdx || hoveredCell?.col === colIdx;
              return (
                <div
                  key={colAsset}
                  className={`flex-1 h-10 flex items-center justify-center text-[10px] font-mono cursor-crosshair
                    transition-all duration-100 border border-transparent
                    ${correlationColor(val)}
                    ${isHovered ? "ring-2 ring-accent ring-offset-1 ring-offset-bg-primary z-10 scale-110" : ""}
                    ${!isHovered && (isRowHighlight || isColHighlight) ? "brightness-125" : ""}
                  `}
                  style={{ borderRadius: "2px", margin: "1px" }}
                  onMouseEnter={() => setHoveredCell({ row: rowIdx, col: colIdx })}
                  onMouseLeave={() => setHoveredCell(null)}
                  title={`${rowAsset} / ${colAsset}: ${val.toFixed(3)}`}
                >
                  <span className={correlationTextColor(val)}>
                    {isHovered ? val.toFixed(3) : val.toFixed(2)}
                  </span>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex items-center justify-center gap-2 mt-4 text-[10px] text-text-tertiary">
        <span>-1.0</span>
        <div className="flex h-3 rounded overflow-hidden">
          <div className="w-6 bg-red-600/90" />
          <div className="w-6 bg-red-500/70" />
          <div className="w-6 bg-red-400/50" />
          <div className="w-6 bg-red-300/30" />
          <div className="w-6 bg-gray-700/30" />
          <div className="w-6 bg-blue-300/30" />
          <div className="w-6 bg-blue-400/50" />
          <div className="w-6 bg-blue-500/70" />
          <div className="w-6 bg-blue-600/90" />
        </div>
        <span>+1.0</span>
      </div>

      {/* Hover details */}
      {hoveredCell && (
        <div className="mt-3 text-center text-sm text-text-secondary">
          <span className="font-mono text-text-primary">{ASSETS[hoveredCell.row]}</span>
          <span className="mx-2 text-text-tertiary">/</span>
          <span className="font-mono text-text-primary">{ASSETS[hoveredCell.col]}</span>
          <span className="mx-2">:</span>
          <span
            className={`font-mono font-semibold ${
              matrix[hoveredCell.row][hoveredCell.col] > 0 ? "text-blue-400" : matrix[hoveredCell.row][hoveredCell.col] < 0 ? "text-red-400" : "text-text-secondary"
            }`}
          >
            {matrix[hoveredCell.row][hoveredCell.col].toFixed(3)}
          </span>
          <span className="ml-3 text-text-tertiary text-xs">
            {ASSET_LABELS[ASSETS[hoveredCell.row]]} vs {ASSET_LABELS[ASSETS[hoveredCell.col]]}
          </span>
        </div>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   COMPONENT: SECTOR ROTATION
   ════════════════════════════════════════════════════════════════ */

function SectorRotation({ lookback }: { lookback: Lookback }) {
  const sectors = useMemo(() => generateSectorData(lookback), [lookback]);
  const sorted = useMemo(
    () => [...sectors].sort((a, b) => b.performance - a.performance),
    [sectors]
  );
  const maxAbs = useMemo(
    () => Math.max(...sorted.map((s) => Math.abs(s.performance)), 1),
    [sorted]
  );

  return (
    <div className="space-y-4">
      {/* Performance bars */}
      <div className="space-y-2">
        {sorted.map((sector) => {
          const pct = Math.abs(sector.performance) / maxAbs;
          const isPositive = sector.performance >= 0;
          return (
            <div key={sector.name} className="group">
              <div className="flex items-center gap-3">
                <span className="w-28 text-xs text-text-secondary truncate shrink-0">
                  {sector.name}
                </span>
                <div className="flex-1 h-6 bg-bg-elevated rounded overflow-hidden relative">
                  <div
                    className={`h-full rounded transition-all duration-500 ${
                      isPositive
                        ? "bg-gradient-to-r from-emerald-600/60 to-emerald-500/80"
                        : "bg-gradient-to-r from-red-500/80 to-red-600/60"
                    }`}
                    style={{ width: `${Math.max(pct * 100, 3)}%` }}
                  />
                  <span className="absolute inset-0 flex items-center px-2 text-[11px] font-mono text-text-primary">
                    {isPositive ? "+" : ""}
                    {sector.performance.toFixed(1)}%
                  </span>
                </div>
                <div className="w-20 flex items-center gap-1.5 shrink-0">
                  {sector.flowDirection === "inflow" && (
                    <>
                      <TrendingUp size={12} className="text-emerald-400" />
                      <span className="text-[10px] text-emerald-400 font-mono">
                        +${sector.flowMagnitude}B
                      </span>
                    </>
                  )}
                  {sector.flowDirection === "outflow" && (
                    <>
                      <TrendingDown size={12} className="text-red-400" />
                      <span className="text-[10px] text-red-400 font-mono">
                        -${sector.flowMagnitude}B
                      </span>
                    </>
                  )}
                  {sector.flowDirection === "neutral" && (
                    <span className="text-[10px] text-text-tertiary font-mono">
                      ~${sector.flowMagnitude}B
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Money Flow Summary */}
      <div className="border-t border-border pt-3">
        <div className="flex items-center gap-2 mb-2">
          <Zap size={14} className="text-yellow-400" />
          <span className="text-xs font-semibold text-text-primary">Capital Rotation Signal</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2">
            <p className="text-[10px] text-emerald-400 font-mono uppercase tracking-wider">Inflows</p>
            <p className="text-xs text-text-primary mt-0.5">
              {sorted
                .filter((s) => s.flowDirection === "inflow")
                .map((s) => s.name)
                .join(", ") || "None"}
            </p>
          </div>
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-2">
            <p className="text-[10px] text-red-400 font-mono uppercase tracking-wider">Outflows</p>
            <p className="text-xs text-text-primary mt-0.5">
              {sorted
                .filter((s) => s.flowDirection === "outflow")
                .map((s) => s.name)
                .join(", ") || "None"}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   COMPONENT: EVENT SIMULATOR
   ════════════════════════════════════════════════════════════════ */

function EventSimulator() {
  const [selectedEvent, setSelectedEvent] = useState<string>(HISTORICAL_EVENTS[0].id);
  const [simulating, setSimulating] = useState(false);
  const [simResult, setSimResult] = useState<{ asset: string; impact: number }[] | null>(null);

  const event = useMemo(
    () => HISTORICAL_EVENTS.find((e) => e.id === selectedEvent)!,
    [selectedEvent]
  );

  const handleSimulate = useCallback(() => {
    setSimulating(true);
    // Mock portfolio: BTC 30%, ETH 20%, SPY 25%, NVDA 15%, GC 10%
    const portfolio = [
      { asset: "BTC", weight: 0.30 },
      { asset: "ETH", weight: 0.20 },
      { asset: "SPY", weight: 0.25 },
      { asset: "NVDA", weight: 0.15 },
      { asset: "GC", weight: 0.10 },
    ];
    setTimeout(() => {
      const results = portfolio.map((p) => {
        const impact = event.impacts.find((i) => i.asset === p.asset);
        return {
          asset: p.asset,
          impact: impact ? parseFloat((impact.totalReturn * p.weight).toFixed(2)) : 0,
        };
      });
      setSimResult(results);
      setSimulating(false);
    }, 800);
  }, [event]);

  return (
    <div className="space-y-4">
      {/* Event selector */}
      <div className="relative">
        <select
          value={selectedEvent}
          onChange={(e) => {
            setSelectedEvent(e.target.value);
            setSimResult(null);
          }}
          className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2.5 text-sm text-text-primary appearance-none cursor-pointer focus:ring-1 focus:ring-accent focus:outline-none"
        >
          {HISTORICAL_EVENTS.map((ev) => (
            <option key={ev.id} value={ev.id}>
              {ev.label}
            </option>
          ))}
        </select>
        <ChevronDown
          size={14}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none"
        />
      </div>

      {/* Event description */}
      <div className="bg-bg-elevated/50 rounded-lg p-3 border border-border/50">
        <p className="text-xs text-text-tertiary font-mono">{event.period}</p>
        <p className="text-xs text-text-secondary mt-1">{event.description}</p>
      </div>

      {/* Impact table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-tertiary border-b border-border">
              <th className="text-left py-2 pr-2 font-mono font-normal">Asset</th>
              <th className="text-right py-2 px-2 font-mono font-normal">Max DD</th>
              <th className="text-right py-2 px-2 font-mono font-normal">Recovery</th>
              <th className="text-right py-2 pl-2 font-mono font-normal">Total Return</th>
            </tr>
          </thead>
          <tbody>
            {event.impacts.map((impact) => {
              if (impact.totalReturn === 0 && impact.maxDrawdown === 0) {
                return (
                  <tr key={impact.asset} className="border-b border-border/30">
                    <td className="py-1.5 pr-2 font-mono text-text-primary">{impact.asset}</td>
                    <td colSpan={3} className="text-center text-text-tertiary italic py-1.5">
                      N/A (not yet launched)
                    </td>
                  </tr>
                );
              }
              return (
                <tr key={impact.asset} className="border-b border-border/30 hover:bg-bg-elevated/30 transition-colors">
                  <td className="py-1.5 pr-2 font-mono text-text-primary">{impact.asset}</td>
                  <td className="text-right py-1.5 px-2 font-mono text-red-400">
                    {impact.maxDrawdown.toFixed(1)}%
                  </td>
                  <td className="text-right py-1.5 px-2 font-mono text-text-secondary">
                    {impact.recoveryDays > 0 ? `${impact.recoveryDays}d` : "--"}
                  </td>
                  <td
                    className={`text-right py-1.5 pl-2 font-mono font-semibold ${
                      impact.totalReturn >= 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {impact.totalReturn >= 0 ? "+" : ""}
                    {impact.totalReturn.toFixed(1)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Simulate button */}
      <div className="border-t border-border pt-3">
        <button
          onClick={handleSimulate}
          disabled={simulating}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-accent/10 border border-accent/30 text-accent rounded-lg text-sm font-medium hover:bg-accent/20 transition-colors disabled:opacity-50"
        >
          {simulating ? (
            <div className="w-4 h-4 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
          ) : (
            <Target size={14} />
          )}
          {simulating ? "Simulating..." : "Simulate on Current Portfolio"}
        </button>

        {simResult && (
          <div className="mt-3 bg-bg-elevated rounded-lg p-3 border border-border">
            <p className="text-[10px] text-text-tertiary font-mono uppercase tracking-wider mb-2">
              Portfolio Impact (BTC 30% / ETH 20% / SPY 25% / NVDA 15% / GC 10%)
            </p>
            <div className="space-y-1.5">
              {simResult.map((r) => (
                <div key={r.asset} className="flex items-center justify-between">
                  <span className="text-xs font-mono text-text-secondary">{r.asset}</span>
                  <span
                    className={`text-xs font-mono font-semibold ${
                      r.impact >= 0 ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {r.impact >= 0 ? "+" : ""}
                    {r.impact.toFixed(2)}%
                  </span>
                </div>
              ))}
              <div className="border-t border-border pt-1.5 flex items-center justify-between">
                <span className="text-xs font-mono text-text-primary font-semibold">Net Impact</span>
                <span
                  className={`text-sm font-mono font-bold ${
                    simResult.reduce((a, b) => a + b.impact, 0) >= 0
                      ? "text-emerald-400"
                      : "text-red-400"
                  }`}
                >
                  {simResult.reduce((a, b) => a + b.impact, 0) >= 0 ? "+" : ""}
                  {simResult.reduce((a, b) => a + b.impact, 0).toFixed(2)}%
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   COMPONENT: PIVOT SIGNALS
   ════════════════════════════════════════════════════════════════ */

function PivotSignals() {
  const signals = useMemo(() => generatePivotSignals(), []);

  return (
    <div className="space-y-3">
      {signals.map((signal) => (
        <div
          key={signal.id}
          className="bg-bg-elevated/50 border border-border/50 rounded-lg p-3 hover:border-border transition-colors"
        >
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold ${
                  signal.direction === "bullish"
                    ? "bg-emerald-500/15 text-emerald-400"
                    : signal.direction === "bearish"
                    ? "bg-red-500/15 text-red-400"
                    : "bg-yellow-500/15 text-yellow-400"
                }`}
              >
                {signal.direction === "bullish" && <TrendingUp size={10} />}
                {signal.direction === "bearish" && <TrendingDown size={10} />}
                {signal.direction === "neutral" && <ArrowRight size={10} />}
                {signal.direction.toUpperCase()}
              </span>
              <span className="text-xs font-mono text-text-primary font-semibold">
                {signal.pair}
              </span>
            </div>
            <span className="text-[10px] text-text-tertiary shrink-0">{signal.timeDetected}</span>
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">{signal.message}</p>
          <div className="flex items-center gap-2 mt-2">
            <div className="flex-1 h-1.5 bg-bg-primary rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  signal.confidence > 0.85
                    ? "bg-emerald-500"
                    : signal.confidence > 0.7
                    ? "bg-yellow-500"
                    : "bg-orange-500"
                }`}
                style={{ width: `${signal.confidence * 100}%` }}
              />
            </div>
            <span className="text-[10px] font-mono text-text-tertiary">
              {(signal.confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════
   MAIN PAGE
   ════════════════════════════════════════════════════════════════ */

export default function CorrelationsPage() {
  const [lookback, setLookback] = useState<Lookback>("30d");

  const lookbackOptions: { value: Lookback; label: string }[] = [
    { value: "30d", label: "30 Day" },
    { value: "90d", label: "90 Day" },
    { value: "1y", label: "1 Year" },
  ];

  return (
    <div className="min-h-screen p-6 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-accent/10 rounded-lg">
            <GitCompare size={20} className="text-accent" />
          </div>
          <div>
            <h1 className="text-xl font-heading font-semibold text-text-primary">
              Cross-Sector Correlations
            </h1>
            <p className="text-sm text-text-tertiary">
              Correlation matrix, sector rotation, and pivot analysis
            </p>
          </div>
        </div>

        {/* Lookback toggle */}
        <div className="flex items-center bg-bg-card border border-border rounded-lg p-1">
          {lookbackOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setLookback(opt.value)}
              className={`px-3 py-1.5 text-xs font-mono rounded-md transition-colors ${
                lookback === opt.value
                  ? "bg-accent text-white"
                  : "text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Correlation Matrix - spans 2 cols */}
        <div className="xl:col-span-2">
          <Card padding="md" className="h-full">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <BarChart3 size={16} className="text-accent" />
                <h2 className="text-sm font-semibold text-text-primary">Correlation Matrix</h2>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-text-tertiary">
                <Info size={10} />
                <span>Hover cells for detail</span>
              </div>
            </div>
            <CorrelationMatrix lookback={lookback} />
          </Card>
        </div>

        {/* Sector Rotation */}
        <div>
          <Card padding="md" className="h-full">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp size={16} className="text-emerald-400" />
              <h2 className="text-sm font-semibold text-text-primary">Sector Rotation</h2>
            </div>
            <SectorRotation lookback={lookback} />
          </Card>
        </div>
      </div>

      {/* Bottom grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Historical Event Simulator */}
        <Card padding="md">
          <div className="flex items-center gap-2 mb-4">
            <History size={16} className="text-blue-400" />
            <h2 className="text-sm font-semibold text-text-primary">Historical Event Simulator</h2>
          </div>
          <EventSimulator />
        </Card>

        {/* Pivot Signal Panel */}
        <Card padding="md">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-yellow-400" />
              <h2 className="text-sm font-semibold text-text-primary">Pivot Signals</h2>
            </div>
            <span className="text-[10px] font-mono text-text-tertiary px-2 py-0.5 bg-bg-elevated rounded">
              {generatePivotSignals().length} ACTIVE
            </span>
          </div>
          <PivotSignals />
        </Card>
      </div>
    </div>
  );
}
