"use client";

import { useEffect, useState, useRef, useCallback, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import {
  BookOpen,
  Activity,
  Pause,
  Play,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  Zap,
  BarChart3,
  Layers,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";

// ── Symbol config ──────────────────────────────────────────────────────────
const SYMBOLS = [
  { value: "BTCUSDT", label: "BTC/USDT", basePrice: 67250.0, tickSize: 0.01, lotStep: 0.001 },
  { value: "ETHUSDT", label: "ETH/USDT", basePrice: 3480.0, tickSize: 0.01, lotStep: 0.01 },
  { value: "SPY",     label: "SPY",      basePrice: 521.35, tickSize: 0.01, lotStep: 1 },
  { value: "AAPL",    label: "AAPL",     basePrice: 178.72, tickSize: 0.01, lotStep: 1 },
  { value: "TSLA",    label: "TSLA",     basePrice: 248.50, tickSize: 0.01, lotStep: 1 },
  { value: "NVDA",    label: "NVDA",     basePrice: 875.30, tickSize: 0.01, lotStep: 1 },
  { value: "QQQ",     label: "QQQ",      basePrice: 447.80, tickSize: 0.01, lotStep: 1 },
  { value: "AMZN",    label: "AMZN",     basePrice: 186.40, tickSize: 0.01, lotStep: 1 },
];

const GROUPINGS = [0.01, 0.1, 1, 10, 100];

// ── Types ──────────────────────────────────────────────────────────────────
interface OrderLevel {
  price: number;
  size: number;
  total: number;
}

interface TapeEntry {
  id: number;
  time: string;
  price: number;
  size: number;
  side: "buy" | "sell";
  notional: number;
}

// ── Mock data generators ───────────────────────────────────────────────────
let tapeIdCounter = 0;

function generateOrderBook(
  basePrice: number,
  tickSize: number,
  grouping: number,
  levels: number
): { bids: OrderLevel[]; asks: OrderLevel[] } {
  const mid = Math.round(basePrice / grouping) * grouping;
  const spreadTicks = Math.max(1, Math.round((basePrice * 0.0001) / grouping));
  const bestBid = mid - spreadTicks * grouping;
  const bestAsk = mid + spreadTicks * grouping;

  const bids: OrderLevel[] = [];
  let bidTotal = 0;
  for (let i = 0; i < levels; i++) {
    const price = bestBid - i * grouping;
    const distFactor = 1 + i * 0.15;
    const size = parseFloat(
      (Math.random() * 5 * distFactor + 0.5).toFixed(
        grouping >= 1 ? 0 : grouping >= 0.1 ? 1 : 3
      )
    );
    bidTotal += size;
    bids.push({ price: parseFloat(price.toFixed(8)), size, total: parseFloat(bidTotal.toFixed(4)) });
  }

  const asks: OrderLevel[] = [];
  let askTotal = 0;
  for (let i = 0; i < levels; i++) {
    const price = bestAsk + i * grouping;
    const distFactor = 1 + i * 0.15;
    const size = parseFloat(
      (Math.random() * 5 * distFactor + 0.5).toFixed(
        grouping >= 1 ? 0 : grouping >= 0.1 ? 1 : 3
      )
    );
    askTotal += size;
    asks.push({ price: parseFloat(price.toFixed(8)), size, total: parseFloat(askTotal.toFixed(4)) });
  }

  return { bids, asks };
}

function mutateBook(
  book: { bids: OrderLevel[]; asks: OrderLevel[] },
  grouping: number
): { bids: OrderLevel[]; asks: OrderLevel[] } {
  const mutateSide = (levels: OrderLevel[]): OrderLevel[] => {
    let cumulative = 0;
    return levels.map((lvl) => {
      const delta = (Math.random() - 0.5) * lvl.size * 0.3;
      const newSize = Math.max(0.001, lvl.size + delta);
      const rounded = parseFloat(
        newSize.toFixed(grouping >= 1 ? 0 : grouping >= 0.1 ? 1 : 3)
      );
      cumulative += rounded;
      return { ...lvl, size: rounded, total: parseFloat(cumulative.toFixed(4)) };
    });
  };
  return { bids: mutateSide(book.bids), asks: mutateSide(book.asks) };
}

function generateTapeEntry(basePrice: number, lotStep: number): TapeEntry {
  const now = new Date();
  const side: "buy" | "sell" = Math.random() > 0.48 ? "buy" : "sell";
  const priceOffset = (Math.random() - 0.5) * basePrice * 0.0005;
  const price = parseFloat((basePrice + priceOffset).toFixed(2));

  // Power-law distribution for size — mostly small, occasional large
  const u = Math.random();
  let rawSize: number;
  if (u > 0.995) rawSize = 50 + Math.random() * 200; // whale
  else if (u > 0.97) rawSize = 10 + Math.random() * 40; // large
  else if (u > 0.85) rawSize = 2 + Math.random() * 8; // medium
  else rawSize = 0.01 + Math.random() * 2; // retail

  const size = parseFloat((rawSize * lotStep).toFixed(lotStep >= 1 ? 0 : 3));
  const notional = price * size;

  const ms = String(now.getMilliseconds()).padStart(3, "0");
  const time = `${String(now.getHours()).padStart(2, "0")}:${String(
    now.getMinutes()
  ).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}.${ms}`;

  return { id: ++tapeIdCounter, time, price, size, side, notional };
}

// ── Price formatters ───────────────────────────────────────────────────────
function formatPrice(price: number, grouping: number): string {
  if (grouping >= 100) return price.toFixed(0);
  if (grouping >= 10) return price.toFixed(0);
  if (grouping >= 1) return price.toFixed(0);
  if (grouping >= 0.1) return price.toFixed(1);
  return price.toFixed(2);
}

function formatSize(size: number, lotStep: number): string {
  if (lotStep >= 1) return size.toFixed(0);
  return size.toFixed(3);
}

function formatNotional(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(1)}K`;
  return `$${n.toFixed(0)}`;
}

// ── Component ──────────────────────────────────────────────────────────────
export default function TapePage() {
  const [selectedSymbol, setSelectedSymbol] = useState(SYMBOLS[0]);
  const [grouping, setGrouping] = useState(0.01);
  const [showSymbolDropdown, setShowSymbolDropdown] = useState(false);
  const [showGroupDropdown, setShowGroupDropdown] = useState(false);
  const [tapePaused, setTapePaused] = useState(false);

  const [book, setBook] = useState<{ bids: OrderLevel[]; asks: OrderLevel[] }>({
    bids: [],
    asks: [],
  });
  const [tape, setTape] = useState<TapeEntry[]>([]);
  const [buyVol, setBuyVol] = useState(0);
  const [sellVol, setSellVol] = useState(0);
  const [blockCount, setBlockCount] = useState(0);

  const tapeRef = useRef<HTMLDivElement>(null);
  const tapePausedRef = useRef(false);
  const symbolRef = useRef(selectedSymbol);

  // Keep refs in sync
  useEffect(() => {
    tapePausedRef.current = tapePaused;
  }, [tapePaused]);

  useEffect(() => {
    symbolRef.current = selectedSymbol;
  }, [selectedSymbol]);

  // Initialize & reset on symbol change
  useEffect(() => {
    const sym = selectedSymbol;
    const initial = generateOrderBook(sym.basePrice, sym.tickSize, grouping, 20);
    setBook(initial);
    setTape([]);
    setBuyVol(0);
    setSellVol(0);
    setBlockCount(0);
    tapeIdCounter = 0;

    // Seed tape with 30 entries
    const seed: TapeEntry[] = [];
    for (let i = 0; i < 30; i++) {
      seed.push(generateTapeEntry(sym.basePrice, sym.lotStep));
    }
    setTape(seed);
    let bv = 0, sv = 0, bc = 0;
    seed.forEach((e) => {
      if (e.side === "buy") bv += e.notional;
      else sv += e.notional;
      if (e.notional >= 100_000) bc++;
    });
    setBuyVol(bv);
    setSellVol(sv);
    setBlockCount(bc);
  }, [selectedSymbol, grouping]);

  // Order book update interval — 500ms
  useEffect(() => {
    const iv = setInterval(() => {
      setBook((prev) => mutateBook(prev, grouping));
    }, 500);
    return () => clearInterval(iv);
  }, [grouping, selectedSymbol]);

  // Tape stream — new trade every 200-500ms
  useEffect(() => {
    let timeout: ReturnType<typeof setTimeout>;
    const tick = () => {
      if (!tapePausedRef.current) {
        const sym = symbolRef.current;
        const entry = generateTapeEntry(sym.basePrice, sym.lotStep);
        setTape((prev) => [entry, ...prev].slice(0, 200));
        if (entry.side === "buy") setBuyVol((v) => v + entry.notional);
        else setSellVol((v) => v + entry.notional);
        if (entry.notional >= 100_000) setBlockCount((c) => c + 1);
      }
      timeout = setTimeout(tick, 200 + Math.random() * 300);
    };
    timeout = setTimeout(tick, 200);
    return () => clearTimeout(timeout);
  }, [selectedSymbol]);

  // Derived stats
  const spread = useMemo(() => {
    if (!book.bids.length || !book.asks.length) return { price: 0, pct: 0 };
    const s = book.asks[0].price - book.bids[0].price;
    const mid = (book.asks[0].price + book.bids[0].price) / 2;
    return { price: s, pct: (s / mid) * 100 };
  }, [book]);

  const vwap = useMemo(() => {
    if (!tape.length) return 0;
    let sumPV = 0, sumV = 0;
    tape.forEach((t) => {
      sumPV += t.price * t.size;
      sumV += t.size;
    });
    return sumV > 0 ? sumPV / sumV : 0;
  }, [tape]);

  const totalBidDepth = useMemo(
    () => book.bids.reduce((s, l) => s + l.size, 0),
    [book.bids]
  );
  const totalAskDepth = useMemo(
    () => book.asks.reduce((s, l) => s + l.size, 0),
    [book.asks]
  );
  const imbalance = useMemo(() => {
    const total = totalBidDepth + totalAskDepth;
    return total > 0 ? ((totalBidDepth - totalAskDepth) / total) * 100 : 0;
  }, [totalBidDepth, totalAskDepth]);

  const maxTotal = useMemo(() => {
    const maxBid = book.bids.length ? book.bids[book.bids.length - 1].total : 1;
    const maxAsk = book.asks.length ? book.asks[book.asks.length - 1].total : 1;
    return Math.max(maxBid, maxAsk);
  }, [book]);

  const buyRatio = useMemo(() => {
    const total = buyVol + sellVol;
    return total > 0 ? (buyVol / total) * 100 : 50;
  }, [buyVol, sellVol]);

  return (
    <div className="min-h-screen bg-[#080808] text-white p-4 md:p-6">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500/20 to-cyan-500/20 border border-blue-500/30 flex items-center justify-center">
            <BookOpen className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h1 className="font-heading text-2xl font-bold text-white">
              Order Book & Tape
            </h1>
            <p className="text-sm text-neutral-500">Level 2 depth &amp; time &amp; sales</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Symbol selector */}
          <div className="relative">
            <button
              onClick={() => {
                setShowSymbolDropdown((v) => !v);
                setShowGroupDropdown(false);
              }}
              className="flex items-center gap-2 px-4 py-2 bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg text-sm font-mono hover:border-[#2a2a2a] transition-colors"
            >
              <Activity className="w-4 h-4 text-blue-400" />
              {selectedSymbol.label}
              <ChevronDown className="w-3 h-3 text-neutral-500" />
            </button>
            {showSymbolDropdown && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg py-1 min-w-[160px] shadow-xl">
                {SYMBOLS.map((sym) => (
                  <button
                    key={sym.value}
                    onClick={() => {
                      setSelectedSymbol(sym);
                      setShowSymbolDropdown(false);
                    }}
                    className={`w-full text-left px-4 py-2 text-sm font-mono hover:bg-[#1a1a1a] transition-colors ${
                      sym.value === selectedSymbol.value
                        ? "text-blue-400"
                        : "text-neutral-300"
                    }`}
                  >
                    {sym.label}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Grouping selector */}
          <div className="relative">
            <button
              onClick={() => {
                setShowGroupDropdown((v) => !v);
                setShowSymbolDropdown(false);
              }}
              className="flex items-center gap-2 px-4 py-2 bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg text-sm font-mono hover:border-[#2a2a2a] transition-colors"
            >
              <Layers className="w-4 h-4 text-neutral-400" />
              {grouping}
              <ChevronDown className="w-3 h-3 text-neutral-500" />
            </button>
            {showGroupDropdown && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-[#0d0d0d] border border-[#1a1a1a] rounded-lg py-1 min-w-[100px] shadow-xl">
                {GROUPINGS.map((g) => (
                  <button
                    key={g}
                    onClick={() => {
                      setGrouping(g);
                      setShowGroupDropdown(false);
                    }}
                    className={`w-full text-left px-4 py-2 text-sm font-mono hover:bg-[#1a1a1a] transition-colors ${
                      g === grouping ? "text-blue-400" : "text-neutral-300"
                    }`}
                  >
                    {g}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Main grid ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* ── ORDER BOOK (3 cols) ──────────────────────────────────────── */}
        <Card className="lg:col-span-3" padding="none">
          <div className="p-4 border-b border-[#1a1a1a] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-blue-400" />
              <span className="text-sm font-semibold text-white">Order Book</span>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="text-neutral-500">Imbalance</span>
              <span
                className={
                  imbalance > 0
                    ? "text-emerald-400"
                    : imbalance < 0
                    ? "text-red-400"
                    : "text-neutral-400"
                }
              >
                {imbalance > 0 ? "+" : ""}
                {imbalance.toFixed(1)}%
                {imbalance > 5 ? (
                  <ArrowUpRight className="w-3 h-3 inline ml-0.5" />
                ) : imbalance < -5 ? (
                  <ArrowDownRight className="w-3 h-3 inline ml-0.5" />
                ) : null}
              </span>
            </div>
          </div>

          <div className="grid grid-cols-2 divide-x divide-[#1a1a1a]">
            {/* ── Bids ─────────────────────────────────────────────────── */}
            <div>
              <div className="grid grid-cols-3 px-3 py-2 text-[10px] text-neutral-600 uppercase tracking-wider border-b border-[#1a1a1a]">
                <span className="text-right">Total</span>
                <span className="text-right">Size</span>
                <span className="text-right">Bid</span>
              </div>
              <div className="relative">
                {book.bids.map((lvl, i) => (
                  <div
                    key={`bid-${i}`}
                    className="relative grid grid-cols-3 px-3 py-[5px] text-xs font-mono hover:bg-emerald-500/5 transition-colors"
                  >
                    {/* Depth bar */}
                    <div
                      className="absolute inset-y-0 right-0 bg-emerald-500/8"
                      style={{ width: `${(lvl.total / maxTotal) * 100}%` }}
                    />
                    <span className="relative text-right text-neutral-500">
                      {formatSize(lvl.total, selectedSymbol.lotStep)}
                    </span>
                    <span className="relative text-right text-neutral-300">
                      {formatSize(lvl.size, selectedSymbol.lotStep)}
                    </span>
                    <span className="relative text-right text-emerald-400 font-medium">
                      {formatPrice(lvl.price, grouping)}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Asks ─────────────────────────────────────────────────── */}
            <div>
              <div className="grid grid-cols-3 px-3 py-2 text-[10px] text-neutral-600 uppercase tracking-wider border-b border-[#1a1a1a]">
                <span>Ask</span>
                <span>Size</span>
                <span>Total</span>
              </div>
              <div className="relative">
                {book.asks.map((lvl, i) => (
                  <div
                    key={`ask-${i}`}
                    className="relative grid grid-cols-3 px-3 py-[5px] text-xs font-mono hover:bg-red-500/5 transition-colors"
                  >
                    {/* Depth bar */}
                    <div
                      className="absolute inset-y-0 left-0 bg-red-500/8"
                      style={{ width: `${(lvl.total / maxTotal) * 100}%` }}
                    />
                    <span className="relative text-red-400 font-medium">
                      {formatPrice(lvl.price, grouping)}
                    </span>
                    <span className="relative text-neutral-300">
                      {formatSize(lvl.size, selectedSymbol.lotStep)}
                    </span>
                    <span className="relative text-neutral-500">
                      {formatSize(lvl.total, selectedSymbol.lotStep)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Spread indicator */}
          <div className="border-t border-[#1a1a1a] px-4 py-3 flex items-center justify-center gap-4">
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="text-neutral-500">Spread</span>
              <span className="text-white font-medium">
                {formatPrice(spread.price, grouping)}
              </span>
              <span className="text-neutral-600">
                ({spread.pct.toFixed(3)}%)
              </span>
            </div>
            <div className="w-px h-4 bg-[#1a1a1a]" />
            <div className="flex items-center gap-2 text-xs font-mono">
              <span className="text-neutral-500">Mid</span>
              <span className="text-white">
                {book.bids.length && book.asks.length
                  ? formatPrice(
                      (book.bids[0].price + book.asks[0].price) / 2,
                      0.01
                    )
                  : "—"}
              </span>
            </div>
          </div>
        </Card>

        {/* ── TIME & SALES (2 cols) ────────────────────────────────────── */}
        <Card className="lg:col-span-2" padding="none">
          <div className="p-4 border-b border-[#1a1a1a] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span className="text-sm font-semibold text-white">Time & Sales</span>
            </div>
            <button
              onClick={() => setTapePaused((v) => !v)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                tapePaused
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-[#1a1a1a] text-neutral-400 border border-[#2a2a2a] hover:text-white"
              }`}
            >
              {tapePaused ? (
                <>
                  <Play className="w-3 h-3" /> Resume
                </>
              ) : (
                <>
                  <Pause className="w-3 h-3" /> Pause
                </>
              )}
            </button>
          </div>

          {/* Aggregate bar */}
          <div className="px-4 py-2.5 border-b border-[#1a1a1a]">
            <div className="flex items-center justify-between text-[10px] font-mono mb-1.5">
              <span className="text-emerald-400">
                Buy {formatNotional(buyVol)}
              </span>
              <span className="text-neutral-600">
                {buyRatio.toFixed(0)}% / {(100 - buyRatio).toFixed(0)}%
              </span>
              <span className="text-red-400">
                Sell {formatNotional(sellVol)}
              </span>
            </div>
            <div className="h-1.5 rounded-full bg-[#1a1a1a] overflow-hidden flex">
              <div
                className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-300"
                style={{ width: `${buyRatio}%` }}
              />
              <div
                className="h-full bg-gradient-to-r from-red-400 to-red-600 transition-all duration-300"
                style={{ width: `${100 - buyRatio}%` }}
              />
            </div>
          </div>

          {/* Column headers */}
          <div className="grid grid-cols-4 px-4 py-2 text-[10px] text-neutral-600 uppercase tracking-wider border-b border-[#1a1a1a]">
            <span>Time</span>
            <span className="text-right">Price</span>
            <span className="text-right">Size</span>
            <span className="text-right">Value</span>
          </div>

          {/* Tape feed */}
          <div
            ref={tapeRef}
            className="h-[480px] overflow-y-auto scrollbar-thin scrollbar-thumb-[#1a1a1a] scrollbar-track-transparent"
          >
            {tape.map((entry) => {
              const isBlock = entry.notional >= 100_000;
              return (
                <div
                  key={entry.id}
                  className={`grid grid-cols-4 px-4 py-[5px] text-xs font-mono transition-colors hover:bg-white/[0.02] ${
                    isBlock
                      ? "border-l-2 border-yellow-500 bg-yellow-500/[0.03]"
                      : ""
                  }`}
                >
                  <span className="text-neutral-500 tabular-nums">
                    {entry.time}
                  </span>
                  <span
                    className={`text-right font-medium tabular-nums ${
                      entry.side === "buy" ? "text-emerald-400" : "text-red-400"
                    }`}
                  >
                    {entry.price.toFixed(2)}
                  </span>
                  <span className="text-right text-neutral-300 tabular-nums">
                    {formatSize(entry.size, selectedSymbol.lotStep)}
                  </span>
                  <span className="text-right flex items-center justify-end gap-1 tabular-nums">
                    <span className="text-neutral-500">
                      {formatNotional(entry.notional)}
                    </span>
                    {isBlock && (
                      <span className="text-[9px] font-bold text-yellow-500 bg-yellow-500/10 px-1 py-px rounded">
                        BLOCK
                      </span>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* ── Summary Panel ───────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mt-4">
        <SummaryCard
          label="VWAP"
          value={vwap > 0 ? vwap.toFixed(2) : "—"}
          icon={<TrendingUp className="w-4 h-4 text-blue-400" />}
        />
        <SummaryCard
          label="Spread"
          value={`${formatPrice(spread.price, grouping)} (${spread.pct.toFixed(3)}%)`}
          icon={<BarChart3 className="w-4 h-4 text-cyan-400" />}
        />
        <SummaryCard
          label="Bid Depth"
          value={formatSize(totalBidDepth, selectedSymbol.lotStep)}
          icon={<ArrowUpRight className="w-4 h-4 text-emerald-400" />}
          valueColor="text-emerald-400"
        />
        <SummaryCard
          label="Ask Depth"
          value={formatSize(totalAskDepth, selectedSymbol.lotStep)}
          icon={<ArrowDownRight className="w-4 h-4 text-red-400" />}
          valueColor="text-red-400"
        />
        <SummaryCard
          label="Imbalance"
          value={`${imbalance > 0 ? "+" : ""}${imbalance.toFixed(1)}%`}
          icon={<Layers className="w-4 h-4 text-purple-400" />}
          valueColor={
            imbalance > 0
              ? "text-emerald-400"
              : imbalance < 0
              ? "text-red-400"
              : "text-neutral-400"
          }
        />
        <SummaryCard
          label="Block Trades"
          value={blockCount.toString()}
          icon={<Zap className="w-4 h-4 text-yellow-400" />}
          valueColor="text-yellow-400"
        />
      </div>
    </div>
  );
}

// ── Summary card sub-component ─────────────────────────────────────────────
function SummaryCard({
  label,
  value,
  icon,
  valueColor = "text-white",
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  valueColor?: string;
}) {
  return (
    <Card padding="sm">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-[10px] text-neutral-500 uppercase tracking-wider">
          {label}
        </span>
      </div>
      <span className={`text-sm font-mono font-semibold ${valueColor}`}>
        {value}
      </span>
    </Card>
  );
}
