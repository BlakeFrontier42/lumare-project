"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import {
  Activity,
  Clock,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Layers,
  Target,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Globe,
  ChevronDown,
} from "lucide-react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface FuturesContract {
  symbol: string;
  name: string;
  exchange: string;
  lastPrice: number;
  change: number;
  changePct: number;
  volume: number;
  openInterest: number;
  high: number;
  low: number;
  settlement: number;
  tickSize: number;
  tickValue: number;
  decimals: number;
}

interface BookLevel {
  price: number;
  size: number;
  cumulative: number;
}

interface SessionInfo {
  name: string;
  city: string;
  tz: string;
  openHourET: number;
  closeHourET: number;
  high: number;
  low: number;
}

interface KeyLevel {
  label: string;
  value: number;
}

/* ------------------------------------------------------------------ */
/*  Seed data                                                          */
/* ------------------------------------------------------------------ */

const CONTRACTS_SEED: FuturesContract[] = [
  { symbol: "ES", name: "S&P 500 E-mini", exchange: "CME", lastPrice: 5682.25, change: 12.50, changePct: 0.22, volume: 1_842_310, openInterest: 2_415_680, high: 5698.00, low: 5661.50, settlement: 5669.75, tickSize: 0.25, tickValue: 12.50, decimals: 2 },
  { symbol: "NQ", name: "Nasdaq 100 E-mini", exchange: "CME", lastPrice: 19_824.50, change: 78.25, changePct: 0.40, volume: 892_450, openInterest: 1_124_300, high: 19_901.00, low: 19_718.75, settlement: 19_746.25, tickSize: 0.25, tickValue: 5.00, decimals: 2 },
  { symbol: "YM", name: "Dow E-mini", exchange: "CBOT", lastPrice: 42_156, change: -84, changePct: -0.20, volume: 312_400, openInterest: 445_200, high: 42_310, low: 42_048, settlement: 42_240, tickSize: 1, tickValue: 5.00, decimals: 0 },
  { symbol: "RTY", name: "Russell 2000", exchange: "CME", lastPrice: 2_078.40, change: -6.30, changePct: -0.30, volume: 245_100, openInterest: 512_800, high: 2_092.10, low: 2_068.20, settlement: 2_084.70, tickSize: 0.10, tickValue: 5.00, decimals: 2 },
  { symbol: "CL", name: "Crude Oil", exchange: "NYMEX", lastPrice: 68.42, change: 0.87, changePct: 1.29, volume: 1_124_500, openInterest: 1_845_200, high: 68.95, low: 67.18, settlement: 67.55, tickSize: 0.01, tickValue: 10.00, decimals: 2 },
  { symbol: "GC", name: "Gold", exchange: "COMEX", lastPrice: 2_682.30, change: 14.60, changePct: 0.55, volume: 412_800, openInterest: 524_100, high: 2_694.80, low: 2_662.50, settlement: 2_667.70, tickSize: 0.10, tickValue: 10.00, decimals: 2 },
  { symbol: "SI", name: "Silver", exchange: "COMEX", lastPrice: 31.285, change: -0.195, changePct: -0.62, volume: 128_400, openInterest: 215_600, high: 31.640, low: 31.085, settlement: 31.480, tickSize: 0.005, tickValue: 25.00, decimals: 3 },
  { symbol: "ZB", name: "30yr Treasury", exchange: "CBOT", lastPrice: 118.15625, change: 0.21875, changePct: 0.19, volume: 524_300, openInterest: 1_215_400, high: 118.46875, low: 117.84375, settlement: 117.9375, tickSize: 0.03125, tickValue: 31.25, decimals: 5 },
  { symbol: "ZN", name: "10yr Note", exchange: "CBOT", lastPrice: 110.578125, change: 0.109375, changePct: 0.10, volume: 1_845_200, openInterest: 3_412_500, high: 110.75, low: 110.40625, settlement: 110.46875, tickSize: 0.015625, tickValue: 15.625, decimals: 6 },
  { symbol: "6E", name: "Euro FX", exchange: "CME", lastPrice: 1.08425, change: -0.00185, changePct: -0.17, volume: 312_800, openInterest: 645_200, high: 1.08720, low: 1.08215, settlement: 1.08610, tickSize: 0.00005, tickValue: 6.25, decimals: 5 },
];

const SESSIONS_SEED: SessionInfo[] = [
  { name: "New York", city: "New York", tz: "America/New_York", openHourET: 8, closeHourET: 17, high: 5696.50, low: 5665.00 },
  { name: "London", city: "London", tz: "Europe/London", openHourET: 3, closeHourET: 12, high: 5691.25, low: 5668.75 },
  { name: "Asia / Tokyo", city: "Tokyo", tz: "Asia/Tokyo", openHourET: 19, closeHourET: 4, high: 5678.50, low: 5660.25 },
];

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function getETHour(): number {
  const now = new Date();
  const etStr = now.toLocaleString("en-US", { timeZone: "America/New_York", hour: "2-digit", hour12: false });
  return parseInt(etStr, 10);
}

function isSessionLive(s: SessionInfo): boolean {
  const h = getETHour();
  if (s.openHourET < s.closeHourET) {
    return h >= s.openHourET && h < s.closeHourET;
  }
  // overnight session (Asia)
  return h >= s.openHourET || h < s.closeHourET;
}

function getCurrentTimeInTz(tz: string): string {
  return new Date().toLocaleTimeString("en-US", { timeZone: tz, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: true });
}

function fmtNum(n: number, decimals: number): string {
  return n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtVol(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

function drift(base: number, amplitude: number, seed: number, t: number): number {
  return base + amplitude * Math.sin(t * 0.001 + seed) + amplitude * 0.3 * Math.sin(t * 0.0037 + seed * 2.1);
}

function generateBook(mid: number, tickSize: number, decimals: number): { bids: BookLevel[]; asks: BookLevel[] } {
  const bids: BookLevel[] = [];
  const asks: BookLevel[] = [];
  let cumBid = 0;
  let cumAsk = 0;
  for (let i = 1; i <= 5; i++) {
    const bSize = Math.floor(80 + Math.random() * 400);
    const aSize = Math.floor(80 + Math.random() * 400);
    cumBid += bSize;
    cumAsk += aSize;
    bids.push({ price: parseFloat((mid - i * tickSize).toFixed(decimals)), size: bSize, cumulative: cumBid });
    asks.push({ price: parseFloat((mid + i * tickSize).toFixed(decimals)), size: aSize, cumulative: cumAsk });
  }
  return { bids, asks };
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function FuturesPage() {
  const [tick, setTick] = useState(0);
  const [selected, setSelected] = useState("ES");
  const [showAllContracts, setShowAllContracts] = useState(true);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1_200);
    return () => clearInterval(id);
  }, []);

  /* live-drifting contracts */
  const contracts = useMemo(() => {
    const t = Date.now();
    return CONTRACTS_SEED.map((c, idx) => {
      const d = drift(0, c.lastPrice * 0.0003, idx * 7.3, t);
      const last = parseFloat((c.lastPrice + d).toFixed(c.decimals));
      const change = parseFloat((last - c.settlement).toFixed(c.decimals));
      const changePct = parseFloat(((change / c.settlement) * 100).toFixed(2));
      const high = Math.max(c.high, last);
      const low = Math.min(c.low, last);
      const volume = c.volume + Math.floor(Math.random() * 200);
      return { ...c, lastPrice: last, change, changePct, high, low, volume };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick]);

  const activeContract = contracts.find((c) => c.symbol === selected) ?? contracts[0];

  const book = useMemo(
    () => generateBook(activeContract.lastPrice, activeContract.tickSize, activeContract.decimals),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [tick, selected]
  );

  /* Session analysis for selected contract */
  const sessionAnalysis = useMemo(() => {
    const p = activeContract.lastPrice;
    const dayRange = activeContract.high - activeContract.low;
    return {
      overnightHigh: parseFloat((activeContract.settlement + dayRange * 0.6).toFixed(activeContract.decimals)),
      overnightLow: parseFloat((activeContract.settlement - dayRange * 0.4).toFixed(activeContract.decimals)),
      ibHigh: parseFloat((p + dayRange * 0.15).toFixed(activeContract.decimals)),
      ibLow: parseFloat((p - dayRange * 0.15).toFixed(activeContract.decimals)),
      vpoc: parseFloat((p - dayRange * 0.02).toFixed(activeContract.decimals)),
      vah: parseFloat((p + dayRange * 0.12).toFixed(activeContract.decimals)),
      val: parseFloat((p - dayRange * 0.14).toFixed(activeContract.decimals)),
      delta: Math.floor((Math.random() - 0.4) * 28000),
    };
  }, [activeContract]);

  /* Key levels for selected contract */
  const keyLevels: KeyLevel[] = useMemo(() => {
    const p = activeContract.lastPrice;
    const range = activeContract.high - activeContract.low;
    const pivot = parseFloat(((activeContract.high + activeContract.low + activeContract.settlement) / 3).toFixed(activeContract.decimals));
    return [
      { label: "Prev High", value: activeContract.high },
      { label: "Prev Low", value: activeContract.low },
      { label: "Prev Close", value: activeContract.settlement },
      { label: "Weekly High", value: parseFloat((p + range * 1.4).toFixed(activeContract.decimals)) },
      { label: "Weekly Low", value: parseFloat((p - range * 1.6).toFixed(activeContract.decimals)) },
      { label: "Pivot", value: pivot },
      { label: "R1", value: parseFloat((2 * pivot - activeContract.low).toFixed(activeContract.decimals)) },
      { label: "R2", value: parseFloat((pivot + range).toFixed(activeContract.decimals)) },
      { label: "S1", value: parseFloat((2 * pivot - activeContract.high).toFixed(activeContract.decimals)) },
      { label: "S2", value: parseFloat((pivot - range).toFixed(activeContract.decimals)) },
    ];
  }, [activeContract]);

  /* Spread */
  const spread = book.asks.length && book.bids.length ? parseFloat((book.asks[0].price - book.bids[0].price).toFixed(activeContract.decimals)) : 0;

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* ---- Session Tracker Banner ---- */}
      <div className="border-b border-border bg-bg-card">
        <div className="max-w-[1800px] mx-auto px-4 py-3">
          <div className="flex items-center gap-2 mb-3">
            <Globe className="w-4 h-4 text-text-secondary" />
            <span className="text-xs font-heading text-text-secondary uppercase tracking-wider">Global Trading Sessions</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {SESSIONS_SEED.map((session) => {
              const live = isSessionLive(session);
              return (
                <div key={session.name} className="flex items-center justify-between bg-bg-elevated rounded-card px-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="relative">
                      <div className={`w-2.5 h-2.5 rounded-full ${live ? "bg-profit" : "bg-text-tertiary"}`} />
                      {live && <div className="absolute inset-0 w-2.5 h-2.5 rounded-full bg-profit animate-ping opacity-75" />}
                    </div>
                    <div>
                      <div className="text-sm font-heading text-text-primary">{session.name}</div>
                      <div className="text-xs text-text-tertiary">{live ? "LIVE" : "CLOSED"}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-6 text-xs">
                    <div className="text-right">
                      <div className="text-text-tertiary">High</div>
                      <div className="text-text-primary font-mono">{fmtNum(session.high, 2)}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-text-tertiary">Low</div>
                      <div className="text-text-primary font-mono">{fmtNum(session.low, 2)}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-text-tertiary">Time</div>
                      <div className="text-text-primary font-mono">{getCurrentTimeInTz(session.tz)}</div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="max-w-[1800px] mx-auto px-4 py-6 space-y-6">
        {/* ---- Page Header ---- */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-heading text-text-primary">Futures</h1>
            <p className="text-sm text-text-secondary mt-1">Real-time futures contracts across indices, energy, metals &amp; fixed income</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAllContracts(!showAllContracts)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-button bg-bg-elevated border border-border text-xs text-text-secondary hover:text-text-primary transition-colors"
            >
              <Layers className="w-3.5 h-3.5" />
              {showAllContracts ? "Compact" : "Expand"}
            </button>
          </div>
        </div>

        {/* ---- Futures Contracts Grid ---- */}
        <div className={`grid gap-3 ${showAllContracts ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5" : "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 xl:grid-cols-10"}`}>
          {contracts.map((c) => {
            const up = c.change >= 0;
            const isSelected = c.symbol === selected;
            return (
              <Card
                key={c.symbol}
                padding={showAllContracts ? "md" : "sm"}
                className={`cursor-pointer transition-all ${isSelected ? "ring-1 ring-text-secondary" : "hover:border-text-tertiary"}`}
                onClick={() => setSelected(c.symbol)}
              >
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="text-sm font-heading text-text-primary">{c.symbol}</div>
                    {showAllContracts && <div className="text-xs text-text-tertiary">{c.name}</div>}
                  </div>
                  <span className="text-[10px] text-text-tertiary bg-bg-elevated px-1.5 py-0.5 rounded-chip font-mono">{c.exchange}</span>
                </div>

                <div className="font-mono text-lg text-text-primary mb-1">{fmtNum(c.lastPrice, c.decimals)}</div>

                <div className="flex items-center gap-2 mb-2">
                  <span className={`text-xs font-mono ${up ? "text-profit" : "text-loss"}`}>
                    {up ? "+" : ""}{fmtNum(c.change, c.decimals)}
                  </span>
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded-chip ${up ? "bg-profit/10 text-profit" : "bg-loss/10 text-loss"}`}>
                    {up ? "+" : ""}{c.changePct.toFixed(2)}%
                  </span>
                </div>

                {showAllContracts && (
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs border-t border-border pt-2 mt-2">
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">Vol</span>
                      <span className="text-text-secondary font-mono">{fmtVol(c.volume)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">OI</span>
                      <span className="text-text-secondary font-mono">{fmtVol(c.openInterest)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">High</span>
                      <span className="text-text-secondary font-mono">{fmtNum(c.high, c.decimals)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-text-tertiary">Low</span>
                      <span className="text-text-secondary font-mono">{fmtNum(c.low, c.decimals)}</span>
                    </div>
                    <div className="flex justify-between col-span-2">
                      <span className="text-text-tertiary">Settle</span>
                      <span className="text-text-secondary font-mono">{fmtNum(c.settlement, c.decimals)}</span>
                    </div>
                  </div>
                )}
              </Card>
            );
          })}
        </div>

        {/* ---- Detail panels ---- */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ---- Market Depth / Level 2 ---- */}
          <Card padding="none" className="lg:col-span-1">
            <div className="px-5 py-4 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-text-secondary" />
                <span className="text-sm font-heading text-text-primary">Market Depth</span>
              </div>
              <span className="text-xs text-text-tertiary font-mono">{activeContract.symbol}</span>
            </div>

            <div className="px-5 py-3 border-b border-border flex items-center justify-between text-xs">
              <span className="text-text-secondary">Spread</span>
              <span className="text-text-primary font-mono">{fmtNum(spread, activeContract.decimals)} ({(spread / activeContract.tickSize).toFixed(0)} tick{(spread / activeContract.tickSize) !== 1 ? "s" : ""})</span>
            </div>

            {/* Header */}
            <div className="grid grid-cols-7 gap-1 px-5 py-2 text-[10px] text-text-tertiary uppercase tracking-wider border-b border-border">
              <div className="col-span-1 text-right">Cum</div>
              <div className="col-span-1 text-right">Size</div>
              <div className="col-span-1 text-right text-profit">Bid</div>
              <div className="col-span-1 text-center">—</div>
              <div className="col-span-1 text-left text-loss">Ask</div>
              <div className="col-span-1 text-left">Size</div>
              <div className="col-span-1 text-left">Cum</div>
            </div>

            {/* Rows */}
            <div className="divide-y divide-border/50">
              {Array.from({ length: 5 }).map((_, i) => {
                const bid = book.bids[i];
                const ask = book.asks[i];
                const maxCum = Math.max(book.bids[4]?.cumulative ?? 1, book.asks[4]?.cumulative ?? 1);
                const bidPct = ((bid?.cumulative ?? 0) / maxCum) * 100;
                const askPct = ((ask?.cumulative ?? 0) / maxCum) * 100;
                return (
                  <div key={i} className="relative grid grid-cols-7 gap-1 px-5 py-1.5 text-xs font-mono">
                    {/* bid depth bar */}
                    <div className="absolute left-0 top-0 bottom-0 bg-profit/5" style={{ width: `${bidPct / 2}%` }} />
                    {/* ask depth bar */}
                    <div className="absolute right-0 top-0 bottom-0 bg-loss/5" style={{ width: `${askPct / 2}%` }} />

                    <div className="col-span-1 text-right text-text-tertiary relative z-10">{bid?.cumulative}</div>
                    <div className="col-span-1 text-right text-text-secondary relative z-10">{bid?.size}</div>
                    <div className="col-span-1 text-right text-profit relative z-10">{bid ? fmtNum(bid.price, activeContract.decimals) : ""}</div>
                    <div className="col-span-1 text-center text-text-tertiary relative z-10"><Minus className="w-3 h-3 inline" /></div>
                    <div className="col-span-1 text-left text-loss relative z-10">{ask ? fmtNum(ask.price, activeContract.decimals) : ""}</div>
                    <div className="col-span-1 text-left text-text-secondary relative z-10">{ask?.size}</div>
                    <div className="col-span-1 text-left text-text-tertiary relative z-10">{ask?.cumulative}</div>
                  </div>
                );
              })}
            </div>
          </Card>

          {/* ---- Session Analysis Panel ---- */}
          <Card padding="none" className="lg:col-span-1">
            <div className="px-5 py-4 border-b border-border flex items-center gap-2">
              <Activity className="w-4 h-4 text-text-secondary" />
              <span className="text-sm font-heading text-text-primary">Session Analysis</span>
            </div>
            <div className="divide-y divide-border/50">
              {[
                { label: "Overnight High (Globex)", value: sessionAnalysis.overnightHigh },
                { label: "Overnight Low (Globex)", value: sessionAnalysis.overnightLow },
                { label: "Initial Balance High", value: sessionAnalysis.ibHigh },
                { label: "Initial Balance Low", value: sessionAnalysis.ibLow },
                { label: "VPOC", value: sessionAnalysis.vpoc },
                { label: "Value Area High", value: sessionAnalysis.vah },
                { label: "Value Area Low", value: sessionAnalysis.val },
              ].map((row) => (
                <div key={row.label} className="flex items-center justify-between px-5 py-2.5">
                  <span className="text-xs text-text-secondary">{row.label}</span>
                  <span className="text-xs font-mono text-text-primary">{fmtNum(row.value, activeContract.decimals)}</span>
                </div>
              ))}
              <div className="flex items-center justify-between px-5 py-2.5">
                <span className="text-xs text-text-secondary">Delta (Buy - Sell Vol)</span>
                <span className={`text-xs font-mono ${sessionAnalysis.delta >= 0 ? "text-profit" : "text-loss"}`}>
                  {sessionAnalysis.delta >= 0 ? "+" : ""}{sessionAnalysis.delta.toLocaleString()}
                </span>
              </div>
            </div>
          </Card>

          {/* ---- Key Levels ---- */}
          <Card padding="none" className="lg:col-span-1">
            <div className="px-5 py-4 border-b border-border flex items-center gap-2">
              <Target className="w-4 h-4 text-text-secondary" />
              <span className="text-sm font-heading text-text-primary">Key Levels</span>
            </div>
            <div className="divide-y divide-border/50">
              {keyLevels.map((lvl) => {
                const diff = lvl.value - activeContract.lastPrice;
                const diffPct = (diff / activeContract.lastPrice) * 100;
                const above = diff > 0;
                return (
                  <div key={lvl.label} className="flex items-center justify-between px-5 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded-chip ${
                        lvl.label.startsWith("R") ? "bg-profit/10 text-profit" :
                        lvl.label.startsWith("S") ? "bg-loss/10 text-loss" :
                        "bg-bg-elevated text-text-secondary"
                      }`}>{lvl.label}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-xs font-mono text-text-primary">{fmtNum(lvl.value, activeContract.decimals)}</span>
                      <span className={`text-[10px] font-mono ${above ? "text-profit" : "text-loss"}`}>
                        {above ? "+" : ""}{diffPct.toFixed(2)}%
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
