"use client";

import { useState, useCallback } from "react";
import { Maximize2, Minimize2, Link, Unlink, ChevronDown } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { TradingChart } from "@/components/charts/TradingChart";

const SYMBOLS = [
  "BTCUSDT", "ETHUSDT", "SOLUSDT", "SPY", "QQQ", "AAPL", "TSLA",
  "NVDA", "AMZN", "MSFT", "META", "GOOG", "AMD", "NFLX", "JPM",
];

const LAYOUTS = [
  { label: "1x1", rows: 1, cols: 1 },
  { label: "1x2", rows: 1, cols: 2 },
  { label: "2x2", rows: 2, cols: 2 },
  { label: "2x3", rows: 2, cols: 3 },
  { label: "3x3", rows: 3, cols: 3 },
] as const;

type LayoutConfig = (typeof LAYOUTS)[number];

const DEFAULT_SYMBOLS = [
  "BTCUSDT", "ETHUSDT", "SPY", "NVDA", "SOLUSDT", "QQQ",
  "AAPL", "TSLA", "AMZN",
];

function LayoutIcon({ rows, cols, active }: { rows: number; cols: number; active: boolean }) {
  return (
    <div
      className="grid gap-[2px] p-1.5"
      style={{
        gridTemplateRows: `repeat(${rows}, 1fr)`,
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        width: 28,
        height: 28,
      }}
    >
      {Array.from({ length: rows * cols }).map((_, i) => (
        <div
          key={i}
          className="rounded-[2px]"
          style={{
            background: active ? "#3b82f6" : "#555",
            minWidth: 4,
            minHeight: 4,
          }}
        />
      ))}
    </div>
  );
}

function SymbolSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (s: string) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 px-2 py-1 rounded text-xs font-semibold tracking-wide hover:bg-white/5 transition-colors"
        style={{ color: "#e5e5e5" }}
      >
        {value}
        <ChevronDown size={12} className="opacity-50" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute top-full left-0 z-50 mt-1 rounded-md border overflow-hidden shadow-xl max-h-64 overflow-y-auto"
            style={{
              background: "#0d0d0d",
              borderColor: "#1a1a1a",
              minWidth: 120,
            }}
          >
            {SYMBOLS.map((s) => (
              <button
                key={s}
                onClick={() => { onChange(s); setOpen(false); }}
                className="block w-full text-left px-3 py-1.5 text-xs font-medium hover:bg-white/5 transition-colors"
                style={{
                  color: s === value ? "#3b82f6" : "#a1a1a1",
                  background: s === value ? "rgba(59,130,246,0.08)" : undefined,
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

interface CellState {
  symbol: string;
  timeframe: string;
}

export default function ChartsPage() {
  const [layout, setLayout] = useState<LayoutConfig>(LAYOUTS[2]); // 2x2
  const [cells, setCells] = useState<CellState[]>(
    DEFAULT_SYMBOLS.map((s) => ({ symbol: s, timeframe: "1H" }))
  );
  const [maximized, setMaximized] = useState<number | null>(null);
  const [syncTimeframes, setSyncTimeframes] = useState(false);

  const totalCells = layout.rows * layout.cols;

  const updateSymbol = useCallback((idx: number, symbol: string) => {
    setCells((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], symbol };
      return next;
    });
  }, []);

  const updateTimeframe = useCallback(
    (idx: number, timeframe: string) => {
      setCells((prev) => {
        if (syncTimeframes) {
          return prev.map((c) => ({ ...c, timeframe }));
        }
        const next = [...prev];
        next[idx] = { ...next[idx], timeframe };
        return next;
      });
    },
    [syncTimeframes]
  );

  const toggleMaximize = useCallback((idx: number) => {
    setMaximized((prev) => (prev === idx ? null : idx));
  }, []);

  const renderChart = (idx: number, fullHeight?: number) => {
    const cell = cells[idx] || { symbol: DEFAULT_SYMBOLS[idx % DEFAULT_SYMBOLS.length], timeframe: "1H" };
    const isMax = maximized === idx;

    return (
      <Card key={idx} padding="none" className="relative flex flex-col overflow-hidden h-full">
        {/* Chart header */}
        <div
          className="flex items-center justify-between px-2 py-1 border-b shrink-0"
          style={{ borderColor: "#1a1a1a", background: "#0a0a0a" }}
        >
          <SymbolSelect
            value={cell.symbol}
            onChange={(s) => updateSymbol(idx, s)}
          />
          <button
            onClick={() => toggleMaximize(idx)}
            className="p-1 rounded hover:bg-white/5 transition-colors"
            title={isMax ? "Restore" : "Maximize"}
          >
            {isMax ? (
              <Minimize2 size={14} style={{ color: "#777" }} />
            ) : (
              <Maximize2 size={14} style={{ color: "#777" }} />
            )}
          </button>
        </div>

        {/* Chart body */}
        <div className="flex-1 min-h-0">
          <TradingChart
            symbol={cell.symbol}
            initialTimeframe={cell.timeframe}
            height={fullHeight ? fullHeight - 34 : undefined}
            showTimeframes
            showVolume
          />
        </div>
      </Card>
    );
  };

  // Maximized view
  if (maximized !== null) {
    return (
      <div
        className="flex flex-col"
        style={{
          height: "calc(100vh - 56px)",
          background: "#080808",
        }}
      >
        {/* Toolbar */}
        <div
          className="flex items-center gap-3 px-4 py-2 border-b shrink-0"
          style={{ borderColor: "#1a1a1a", background: "#0a0a0a" }}
        >
          <span className="text-xs font-medium" style={{ color: "#777" }}>
            CHARTS
          </span>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setMaximized(null)}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs hover:bg-white/5 transition-colors"
              style={{ color: "#a1a1a1" }}
            >
              <Minimize2 size={13} />
              Restore Grid
            </button>
          </div>
        </div>

        {/* Full chart */}
        <div className="flex-1 min-h-0 p-1">
          {renderChart(maximized, window?.innerHeight ? window.innerHeight - 56 - 44 : 700)}
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col"
      style={{
        height: "calc(100vh - 56px)",
        background: "#080808",
      }}
    >
      {/* Toolbar */}
      <div
        className="flex items-center gap-3 px-4 py-2 border-b shrink-0"
        style={{ borderColor: "#1a1a1a", background: "#0a0a0a" }}
      >
        <span className="text-xs font-semibold tracking-wider uppercase" style={{ color: "#555" }}>
          Charts
        </span>

        {/* Layout picker */}
        <div className="flex items-center gap-1 ml-3">
          {LAYOUTS.map((l) => (
            <button
              key={l.label}
              onClick={() => setLayout(l)}
              className="rounded border transition-all"
              style={{
                borderColor: layout.label === l.label ? "#3b82f6" : "#1a1a1a",
                background: layout.label === l.label ? "rgba(59,130,246,0.06)" : "transparent",
              }}
              title={l.label}
            >
              <LayoutIcon
                rows={l.rows}
                cols={l.cols}
                active={layout.label === l.label}
              />
            </button>
          ))}
        </div>

        {/* Sync toggle */}
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={() => setSyncTimeframes((p) => !p)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-all"
            style={{
              color: syncTimeframes ? "#3b82f6" : "#666",
              background: syncTimeframes ? "rgba(59,130,246,0.08)" : "transparent",
              border: `1px solid ${syncTimeframes ? "rgba(59,130,246,0.3)" : "#1a1a1a"}`,
            }}
            title="Sync timeframes across all charts"
          >
            {syncTimeframes ? <Link size={13} /> : <Unlink size={13} />}
            Sync TF
          </button>
        </div>
      </div>

      {/* Chart grid */}
      <div
        className="flex-1 min-h-0 grid gap-[1px] p-[1px]"
        style={{
          gridTemplateRows: `repeat(${layout.rows}, 1fr)`,
          gridTemplateColumns: `repeat(${layout.cols}, 1fr)`,
          background: "#1a1a1a",
        }}
      >
        {Array.from({ length: totalCells }).map((_, i) => (
          <div
            key={`${layout.label}-${i}`}
            className="min-h-0 min-w-0"
            style={{ background: "#080808" }}
          >
            {renderChart(i)}
          </div>
        ))}
      </div>
    </div>
  );
}