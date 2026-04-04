"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import { TradingViewChart } from "@/components/charts/TradingViewChart";
import { SessionTracker } from "@/components/ui/SessionTracker";
import { usePriceStream } from "@/hooks/usePriceStream";
import {
  API_BASE,
  apiFetch,
  formatCurrency,
  formatNumber,
  type PortfolioSummary,
  type TradeRecord,
  type SignalScore,
} from "@/lib/api";
import {
  Zap,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
  Shield,
  ChevronDown,
  TrendingUp,
  TrendingDown,
  Activity,
  Layers,
  Target,
  Crosshair,
  Globe,
  X,
  Loader2,
  CheckCircle,
  AlertCircle,
  DollarSign,
} from "lucide-react";

const CRYPTO_SYMBOLS = [
  { value: "BTCUSDT", label: "BTC/USDT", type: "crypto" },
  { value: "ETHUSDT", label: "ETH/USDT", type: "crypto" },
  { value: "SOLUSDT", label: "SOL/USDT", type: "crypto" },
  { value: "XRPUSDT", label: "XRP/USDT", type: "crypto" },
  { value: "ADAUSDT", label: "ADA/USDT", type: "crypto" },
  { value: "AVAXUSDT", label: "AVAX/USDT", type: "crypto" },
];

const EQUITY_SYMBOLS = [
  { value: "SPY", label: "SPY", type: "equity" },
  { value: "QQQ", label: "QQQ", type: "equity" },
  { value: "AAPL", label: "AAPL", type: "equity" },
  { value: "TSLA", label: "TSLA", type: "equity" },
  { value: "NVDA", label: "NVDA", type: "equity" },
  { value: "AMZN", label: "AMZN", type: "equity" },
  { value: "MSFT", label: "MSFT", type: "equity" },
  { value: "META", label: "META", type: "equity" },
  { value: "AMD", label: "AMD", type: "equity" },
  { value: "GOOGL", label: "GOOGL", type: "equity" },
];

const ALL_SYMBOLS = [...CRYPTO_SYMBOLS, ...EQUITY_SYMBOLS];

// Quick stats mock data per symbol
const SYMBOL_STATS: Record<string, { volume24h: string; marketCap: string; high52w: string; low52w: string; avgVolume: string; float: string | null }> = {
  BTCUSDT: { volume24h: "38.2B", marketCap: "1.33T", high52w: "73,750", low52w: "25,200", avgVolume: "31.5B", float: null },
  ETHUSDT: { volume24h: "14.8B", marketCap: "423B", high52w: "4,092", low52w: "1,520", avgVolume: "12.1B", float: null },
  SOLUSDT: { volume24h: "2.4B", marketCap: "63.2B", high52w: "210.18", low52w: "18.50", avgVolume: "1.9B", float: null },
  XRPUSDT: { volume24h: "1.1B", marketCap: "28.6B", high52w: "0.94", low52w: "0.38", avgVolume: "850M", float: null },
  ADAUSDT: { volume24h: "420M", marketCap: "16.1B", high52w: "0.81", low52w: "0.24", avgVolume: "380M", float: null },
  AVAXUSDT: { volume24h: "680M", marketCap: "12.8B", high52w: "65.40", low52w: "8.90", avgVolume: "520M", float: null },
  SPY: { volume24h: "82.5M", marketCap: "512B", high52w: "524.61", low52w: "410.68", avgVolume: "76.3M", float: "889M" },
  QQQ: { volume24h: "54.2M", marketCap: "215B", high52w: "449.34", low52w: "342.10", avgVolume: "48.8M", float: "398M" },
  AAPL: { volume24h: "58.3M", marketCap: "2.94T", high52w: "199.62", low52w: "164.08", avgVolume: "52.1M", float: "15.2B" },
  TSLA: { volume24h: "112.8M", marketCap: "558B", high52w: "299.29", low52w: "138.80", avgVolume: "98.4M", float: "2.84B" },
  NVDA: { volume24h: "45.6M", marketCap: "2.15T", high52w: "974.00", low52w: "392.30", avgVolume: "41.2M", float: "2.45B" },
  AMZN: { volume24h: "47.1M", marketCap: "1.94T", high52w: "201.20", low52w: "118.35", avgVolume: "42.8M", float: "10.3B" },
  MSFT: { volume24h: "22.4M", marketCap: "3.11T", high52w: "430.82", low52w: "309.45", avgVolume: "19.8M", float: "7.43B" },
  META: { volume24h: "18.7M", marketCap: "1.29T", high52w: "542.81", low52w: "274.38", avgVolume: "16.2M", float: "2.25B" },
  AMD: { volume24h: "62.3M", marketCap: "289B", high52w: "227.30", low52w: "93.12", avgVolume: "55.8M", float: "1.62B" },
  GOOGL: { volume24h: "28.9M", marketCap: "1.93T", high52w: "174.72", low52w: "120.21", avgVolume: "25.1M", float: "5.87B" },
};

export default function TradePage() {
  return (
    <Suspense fallback={<div className="p-8 text-text-secondary">Loading...</div>}>
      <TradePageInner />
    </Suspense>
  );
}

function TradePageInner() {
  const searchParams = useSearchParams();
  const initialSymbol = searchParams.get("symbol") || "BTCUSDT";

  const [mode, setMode] = useState<"paper" | "live">("paper");
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [symbol, setSymbol] = useState(initialSymbol);
  const [signal, setSignal] = useState<SignalScore | null>(null);
  const { priceMap, connected } = usePriceStream();

  // Paper trading state
  const [orderQty, setOrderQty] = useState<string>("1");
  const [orderSL, setOrderSL] = useState<string>("");
  const [orderTP, setOrderTP] = useState<string>("");
  const [orderLoading, setOrderLoading] = useState<"long" | "short" | null>(null);
  const [orderFeedback, setOrderFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  interface PaperPosition {
    position_id: string;
    symbol: string;
    side: string;
    entry_price: number;
    current_price: number | null;
    quantity: number;
    unrealized_pnl: number | null;
    stop_loss: number | null;
    take_profit: number | null;
    opened_at: string | null;
  }
  interface PaperStats {
    total_pnl: number | null;
    win_rate: number | null;
    total_trades: number;
    open_positions: number;
  }
  const [paperPositions, setPaperPositions] = useState<PaperPosition[]>([]);
  const [paperStats, setPaperStats] = useState<PaperStats | null>(null);
  const [closingId, setClosingId] = useState<string | null>(null);

  const currentPrice = priceMap.get(symbol)?.price;
  const priceData = priceMap.get(symbol);
  const symbolInfo = ALL_SYMBOLS.find((s) => s.value === symbol);

  // Fetch paper positions + stats
  const fetchPaperData = useCallback(async () => {
    const [posData, statsData] = await Promise.all([
      apiFetch<{ positions: PaperPosition[] }>("/api/paper/positions"),
      apiFetch<PaperStats>("/api/paper/stats"),
    ]);
    if (posData?.positions) setPaperPositions(posData.positions);
    if (statsData) setPaperStats(statsData);
  }, []);

  useEffect(() => {
    fetchPaperData();
    const interval = setInterval(fetchPaperData, 5_000);
    return () => clearInterval(interval);
  }, [fetchPaperData]);

  // Clear order feedback after 4s
  useEffect(() => {
    if (!orderFeedback) return;
    const t = setTimeout(() => setOrderFeedback(null), 4000);
    return () => clearTimeout(t);
  }, [orderFeedback]);

  const submitOrder = async (side: "long" | "short") => {
    if (!currentPrice) return;
    setOrderLoading(side);
    setOrderFeedback(null);
    try {
      const body: Record<string, unknown> = {
        symbol,
        side,
        quantity: parseFloat(orderQty) || 1,
        entry_price: currentPrice,
      };
      if (orderSL) body.stop_loss = parseFloat(orderSL);
      if (orderTP) body.take_profit = parseFloat(orderTP);

      const res = await fetch(`${API_BASE}/api/paper/order`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Order failed (${res.status})`);
      }
      setOrderFeedback({ type: "success", msg: `${side.toUpperCase()} order filled @ $${formatNumber(currentPrice)}` });
      fetchPaperData();
    } catch (e: unknown) {
      setOrderFeedback({ type: "error", msg: e instanceof Error ? e.message : "Order failed" });
    } finally {
      setOrderLoading(null);
    }
  };

  const closePosition = async (positionId: string) => {
    setClosingId(positionId);
    try {
      const res = await fetch(`${API_BASE}/api/paper/close/${positionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) throw new Error("Close failed");
      fetchPaperData();
    } catch {
      setOrderFeedback({ type: "error", msg: "Failed to close position" });
    } finally {
      setClosingId(null);
    }
  };

  const fetchData = useCallback(async () => {
    const [portData, tradeData, signalData] = await Promise.all([
      apiFetch<PortfolioSummary>("/api/portfolio/summary"),
      apiFetch<{ trades: TradeRecord[] }>("/api/portfolio/trades?days=30"),
      apiFetch<{ signal: SignalScore | null }>(`/api/scoring/compute/${symbol}?direction=long`),
    ]);
    if (portData) setPortfolio(portData);
    if (tradeData) setTrades(tradeData.trades || []);
    if (signalData?.signal) setSignal(signalData.signal);
  }, [symbol]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10_000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const composite = signal?.composite_score ?? 0;
  const signalColor = composite >= 70 ? "#22c55e" : composite >= 50 ? "#f59e0b" : "#ef4444";
  const direction = signal?.direction ?? "neutral";

  const winningTrades = trades.filter((t) => (t.pnl ?? 0) > 0);
  const winRate = trades.length > 0 ? ((winningTrades.length / trades.length) * 100).toFixed(1) : "--";

  return (
    <div className="p-4 lg:p-8 space-y-4 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Zap size={20} className="text-green-500" />
          <div>
            <h1 className="font-heading text-lg md:text-2xl font-bold">Trade</h1>
            <p className="text-text-secondary text-xs">Autonomous execution engine</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Symbol Selector */}
          <div className="relative">
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="appearance-none bg-bg-card border border-border rounded-lg px-3 py-2 pr-8 text-xs font-mono focus:outline-none focus:border-profit"
            >
              <optgroup label="Crypto">
                {CRYPTO_SYMBOLS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </optgroup>
              <optgroup label="Equities">
                {EQUITY_SYMBOLS.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </optgroup>
            </select>
            <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-tertiary pointer-events-none" />
          </div>

          {/* Mode Toggle */}
          <div className="flex bg-bg-card border border-border rounded-lg overflow-hidden">
            {(["paper", "live"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-4 py-2 text-xs font-mono uppercase transition-colors ${
                  mode === m
                    ? m === "live" ? "bg-loss/20 text-loss" : "bg-accent text-text-primary"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {m === "live" && <Shield size={12} className="inline mr-1" />}
                {m}
              </button>
            ))}
          </div>

          {/* Connection */}
          <div className="flex items-center gap-1.5">
            <span className={`w-2 h-2 rounded-full ${connected ? "bg-profit animate-pulse" : "bg-loss"}`} />
            <span className="text-[10px] text-text-tertiary font-mono">{connected ? "LIVE" : "OFFLINE"}</span>
          </div>
        </div>
      </header>

      {/* Chart — full width, immediately after header */}
      <Card padding="none" className="overflow-hidden min-h-[300px] md:min-h-[500px]">
        <TradingViewChart symbol={symbol} height={480} interval="60" />
      </Card>

      {/* Symbol Quick Stats */}
      {(() => {
        const qs = SYMBOL_STATS[symbol];
        if (!qs) return null;
        const stats = [
          { label: "24h Volume", value: qs.volume24h },
          { label: "Market Cap", value: qs.marketCap },
          { label: "52W High", value: `$${qs.high52w}` },
          { label: "52W Low", value: `$${qs.low52w}` },
          { label: "Avg Volume", value: qs.avgVolume },
          ...(qs.float ? [{ label: "Float", value: qs.float }] : []),
        ];
        return (
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 px-3 py-2 rounded-lg bg-bg-card border border-border">
            {stats.map((s) => (
              <div key={s.label} className="flex items-center gap-1.5">
                <span className="text-[10px] text-text-tertiary uppercase tracking-wider">{s.label}</span>
                <span className="text-xs font-mono font-medium text-text-primary">{s.value}</span>
              </div>
            ))}
          </div>
        );
      })()}

      {/* Compact stats strip: session tracker + key portfolio stats */}
      <div className="flex flex-col lg:flex-row gap-3 items-stretch">
        <div className="lg:flex-1 min-w-0">
          <SessionTracker compact />
        </div>
        <div className="flex flex-wrap gap-3">
          <Card padding="sm" className="min-w-[120px]">
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Equity</p>
            <p className="font-heading text-sm font-bold font-mono mt-0.5">{formatCurrency(portfolio?.total_equity)}</p>
          </Card>
          <Card padding="sm" className="min-w-[120px]">
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Realized P&L</p>
            <PriceDisplay value={portfolio?.realized_pnl ?? null} format="currency" className="text-sm font-heading font-bold mt-0.5" />
          </Card>
          <Card padding="sm" className="min-w-[100px]">
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Win Rate</p>
            <p className="font-heading text-sm font-bold font-mono mt-0.5">{winRate}{winRate !== "--" ? "%" : ""}</p>
          </Card>
          <Card padding="sm" className="min-w-[100px]">
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Trades (30d)</p>
            <p className="font-heading text-sm font-bold font-mono mt-0.5">{trades.length}</p>
          </Card>
          <Card padding="sm" className="min-w-[100px]">
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Drawdown</p>
            <p className="font-heading text-sm font-bold font-mono text-loss mt-0.5">
              {portfolio?.drawdown_pct != null ? `${(portfolio.drawdown_pct * 100).toFixed(1)}%` : "--"}
            </p>
          </Card>
        </div>
      </div>

      {/* Signal panel + Live Price + Trade buttons side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Signal Score — spans 5 cols */}
        <div className="lg:col-span-5">
          <Card>
            <div className="flex items-center justify-between mb-2">
              <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Signal Score</p>
              {direction !== "neutral" && (
                <span className={`text-[9px] font-mono px-2 py-0.5 rounded-chip ${
                  direction === "bullish" ? "bg-profit/10 text-profit" :
                  direction === "bearish" ? "bg-loss/10 text-loss" :
                  "bg-bg-elevated text-text-secondary"
                }`}>
                  {direction.toUpperCase()}
                </span>
              )}
            </div>

            <div className="flex items-baseline gap-2">
              <span className="font-mono text-3xl font-bold" style={{ color: signalColor }}>
                {composite.toFixed(0)}
              </span>
              <span className="text-xs text-text-tertiary">/100</span>
            </div>
            <div className="h-2 bg-bg-elevated rounded-full overflow-hidden mt-2">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{ width: `${composite}%`, backgroundColor: signalColor }}
              />
            </div>

            {/* Engine breakdown */}
            {signal && (
              <div className="space-y-2 mt-4 pt-3 border-t border-border">
                {[
                  { label: "Trend", value: signal.trend_score, icon: TrendingUp },
                  { label: "Momentum", value: signal.momentum_score, icon: Activity },
                  { label: "Structure", value: signal.structure_score, icon: Layers },
                  { label: "Flow", value: signal.flow_score, icon: BarChart3 },
                  { label: "Macro", value: signal.macro_score, icon: Globe },
                ].map((s) => {
                  const Icon = s.icon;
                  const val = s.value ?? 0;
                  const pct = (val / 20) * 100;
                  return (
                    <div key={s.label}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <div className="flex items-center gap-1.5">
                          <Icon size={10} className="text-text-tertiary" />
                          <span className="text-text-secondary">{s.label}</span>
                        </div>
                        <span className="font-mono font-bold">{val.toFixed(1)}<span className="text-text-tertiary font-normal">/20</span></span>
                      </div>
                      <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all" style={{
                          width: `${pct}%`,
                          backgroundColor: pct >= 70 ? "#22c55e" : pct >= 40 ? "#f59e0b" : "#e05252"
                        }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {signal?.regime && (
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-[10px] text-text-tertiary uppercase">Regime</p>
                <p className="font-mono text-sm font-bold">{signal.regime}</p>
              </div>
            )}
          </Card>
        </div>

        {/* Live Price + Quick Actions — spans 7 cols */}
        <div className="lg:col-span-7 space-y-4">
          {/* Live Price Card */}
          <Card>
            <div className="flex items-center justify-between mb-3">
              <div>
                <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Live Price</p>
                <p className="font-mono text-2xl font-bold mt-0.5">
                  {currentPrice ? `$${formatNumber(currentPrice)}` : "--"}
                </p>
              </div>
              <div className="text-right">
                {priceData?.change_24h != null && (
                  <div className={`flex items-center gap-1 ${priceData.change_24h >= 0 ? "text-profit" : "text-loss"}`}>
                    {priceData.change_24h >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                    <span className="font-mono text-sm font-bold">
                      {priceData.change_24h >= 0 ? "+" : ""}{priceData.change_24h.toFixed(2)}%
                    </span>
                  </div>
                )}
                {connected && <span className="text-[9px] text-profit font-mono">streaming</span>}
              </div>
            </div>

            {/* Price details */}
            {priceData && (
              <div className="grid grid-cols-3 lg:grid-cols-6 gap-2 text-xs border-t border-border pt-3">
                <div>
                  <p className="text-text-tertiary text-[9px]">24h High</p>
                  <p className="font-mono font-medium">{priceData.high_24h ? `$${formatNumber(priceData.high_24h)}` : "--"}</p>
                </div>
                <div>
                  <p className="text-text-tertiary text-[9px]">24h Low</p>
                  <p className="font-mono font-medium">{priceData.low_24h ? `$${formatNumber(priceData.low_24h)}` : "--"}</p>
                </div>
                <div>
                  <p className="text-text-tertiary text-[9px]">Bid</p>
                  <p className="font-mono font-medium text-profit">{priceData.bid ? `$${formatNumber(priceData.bid)}` : "--"}</p>
                </div>
                <div>
                  <p className="text-text-tertiary text-[9px]">Ask</p>
                  <p className="font-mono font-medium text-loss">{priceData.ask ? `$${formatNumber(priceData.ask)}` : "--"}</p>
                </div>
                <div className="col-span-2">
                  <p className="text-text-tertiary text-[9px]">24h Volume</p>
                  <p className="font-mono font-medium">
                    {priceData.volume_24h ? `$${(priceData.volume_24h / 1e6).toFixed(1)}M` : "--"}
                  </p>
                </div>
              </div>
            )}
          </Card>

          {/* Trade Entry Panel */}
          <Card>
            <div className="flex items-center justify-between mb-3">
              <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Place Order</p>
              <span className="text-[9px] font-mono px-2 py-0.5 rounded-chip bg-accent text-text-primary">PAPER</span>
            </div>

            {/* Entry price display */}
            <div className="mb-3 p-2 rounded-lg bg-bg-elevated">
              <p className="text-text-tertiary text-[9px] uppercase">Entry Price</p>
              <p className="font-mono text-lg font-bold">
                {currentPrice ? `$${formatNumber(currentPrice)}` : "Waiting for price..."}
              </p>
            </div>

            {/* Quantity */}
            <div className="mb-3">
              <label className="text-text-tertiary text-[9px] uppercase tracking-wider block mb-1">Quantity</label>
              <input
                type="number"
                min="0.001"
                step="any"
                value={orderQty}
                onChange={(e) => setOrderQty(e.target.value)}
                className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:border-profit placeholder-text-tertiary"
                placeholder="1"
              />
            </div>

            {/* SL / TP row */}
            <div className="grid grid-cols-2 gap-2 mb-4">
              <div>
                <label className="text-text-tertiary text-[9px] uppercase tracking-wider block mb-1">Stop Loss</label>
                <input
                  type="number"
                  step="any"
                  value={orderSL}
                  onChange={(e) => setOrderSL(e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:border-loss placeholder-text-tertiary"
                  placeholder="Optional"
                />
              </div>
              <div>
                <label className="text-text-tertiary text-[9px] uppercase tracking-wider block mb-1">Take Profit</label>
                <input
                  type="number"
                  step="any"
                  value={orderTP}
                  onChange={(e) => setOrderTP(e.target.value)}
                  className="w-full bg-bg-elevated border border-border rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:border-profit placeholder-text-tertiary"
                  placeholder="Optional"
                />
              </div>
            </div>

            {/* Long / Short buttons */}
            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => submitOrder("long")}
                disabled={!currentPrice || orderLoading !== null}
                className="py-3 rounded-button bg-profit/15 text-profit text-sm font-heading font-bold hover:bg-profit/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1.5"
              >
                {orderLoading === "long" ? <Loader2 size={14} className="animate-spin" /> : <ArrowUpRight size={14} />}
                Long
              </button>
              <button
                onClick={() => submitOrder("short")}
                disabled={!currentPrice || orderLoading !== null}
                className="py-3 rounded-button bg-loss/15 text-loss text-sm font-heading font-bold hover:bg-loss/25 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1.5"
              >
                {orderLoading === "short" ? <Loader2 size={14} className="animate-spin" /> : <ArrowDownRight size={14} />}
                Short
              </button>
            </div>

            {/* Feedback toast */}
            {orderFeedback && (
              <div className={`mt-3 flex items-center gap-2 text-xs font-mono px-3 py-2 rounded-lg ${
                orderFeedback.type === "success" ? "bg-profit/10 text-profit" : "bg-loss/10 text-loss"
              }`}>
                {orderFeedback.type === "success" ? <CheckCircle size={12} /> : <AlertCircle size={12} />}
                {orderFeedback.msg}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Paper Trading Stats Strip */}
      <div className="flex flex-wrap gap-3">
        <Card padding="sm" className="min-w-[140px] flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <DollarSign size={10} className="text-text-tertiary" />
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Paper P&L</p>
          </div>
          <PriceDisplay value={paperStats?.total_pnl ?? null} format="currency" className="text-sm font-heading font-bold font-mono" />
        </Card>
        <Card padding="sm" className="min-w-[120px] flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <Target size={10} className="text-text-tertiary" />
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Win Rate</p>
          </div>
          <p className="font-heading text-sm font-bold font-mono">
            {paperStats?.win_rate != null ? `${(paperStats.win_rate * 100).toFixed(1)}%` : "--"}
          </p>
        </Card>
        <Card padding="sm" className="min-w-[120px] flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <BarChart3 size={10} className="text-text-tertiary" />
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Total Trades</p>
          </div>
          <p className="font-heading text-sm font-bold font-mono">{paperStats?.total_trades ?? 0}</p>
        </Card>
        <Card padding="sm" className="min-w-[120px] flex-1">
          <div className="flex items-center gap-1.5 mb-1">
            <Layers size={10} className="text-text-tertiary" />
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Open Positions</p>
          </div>
          <p className="font-heading text-sm font-bold font-mono">{paperStats?.open_positions ?? 0}</p>
        </Card>
      </div>

      {/* Open Positions Table */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-lg font-semibold">Open Positions</h2>
          <span className="text-xs text-text-tertiary font-mono">{paperPositions.length} open</span>
        </div>
        <Card>
          {paperPositions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-tertiary text-[10px] uppercase border-b border-border">
                    <th className="text-left py-2 pr-4">Symbol</th>
                    <th className="text-left py-2 pr-4">Side</th>
                    <th className="text-right py-2 pr-4">Qty</th>
                    <th className="text-right py-2 pr-4">Entry</th>
                    <th className="text-right py-2 pr-4">Current</th>
                    <th className="text-right py-2 pr-4">Unrealized P&L</th>
                    <th className="text-right py-2 pr-4">SL</th>
                    <th className="text-right py-2 pr-4">TP</th>
                    <th className="text-center py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {paperPositions.map((pos) => {
                    const livePx = priceMap.get(pos.symbol)?.price ?? pos.current_price;
                    const pnl = pos.unrealized_pnl ?? (livePx != null
                      ? (pos.side === "long" ? (livePx - pos.entry_price) : (pos.entry_price - livePx)) * pos.quantity
                      : null);
                    return (
                      <tr key={pos.position_id} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
                        <td className="py-2.5 pr-4 font-mono text-xs">{pos.symbol}</td>
                        <td className="py-2.5 pr-4">
                          <span className={`flex items-center gap-1 text-xs ${pos.side === "long" ? "text-profit" : "text-loss"}`}>
                            {pos.side === "long" ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                            {pos.side.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">{pos.quantity}</td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">${formatNumber(pos.entry_price)}</td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">
                          {livePx != null ? `$${formatNumber(livePx)}` : "--"}
                        </td>
                        <td className="py-2.5 pr-4 text-right">
                          <PriceDisplay value={pnl} format="currency" className="text-xs font-mono" />
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs text-text-secondary">
                          {pos.stop_loss != null ? `$${formatNumber(pos.stop_loss)}` : "--"}
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs text-text-secondary">
                          {pos.take_profit != null ? `$${formatNumber(pos.take_profit)}` : "--"}
                        </td>
                        <td className="py-2.5 text-center">
                          <button
                            onClick={() => closePosition(pos.position_id)}
                            disabled={closingId === pos.position_id}
                            className="inline-flex items-center gap-1 px-2 py-1 rounded bg-loss/10 text-loss text-[10px] font-mono hover:bg-loss/20 disabled:opacity-40 transition-colors"
                          >
                            {closingId === pos.position_id ? <Loader2 size={10} className="animate-spin" /> : <X size={10} />}
                            Close
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-text-tertiary text-sm">
              <Crosshair size={20} className="mx-auto mb-2 opacity-50" />
              <p>No open positions. Place an order above to get started.</p>
            </div>
          )}
        </Card>
      </section>

      {/* Recent Trades */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-heading text-lg font-semibold">Recent Trades</h2>
          <span className="text-xs text-text-tertiary font-mono">{trades.length} trades (30d)</span>
        </div>
        <Card>
          {trades.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-text-tertiary text-[10px] uppercase border-b border-border">
                    <th className="text-left py-2 pr-4">Symbol</th>
                    <th className="text-left py-2 pr-4">Side</th>
                    <th className="text-right py-2 pr-4">Entry</th>
                    <th className="text-right py-2 pr-4">Exit</th>
                    <th className="text-right py-2 pr-4">P&L</th>
                    <th className="text-right py-2 pr-4">R</th>
                    <th className="text-center py-2 pr-4">Score</th>
                    <th className="text-left py-2">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.slice(0, 25).map((t, i) => (
                    <tr key={i} className="border-b border-border/50 hover:bg-bg-elevated/50 transition-colors">
                      <td className="py-2.5 pr-4 font-mono text-xs">{t.symbol}</td>
                      <td className="py-2.5 pr-4">
                        <span className={`flex items-center gap-1 text-xs ${t.side === "long" ? "text-profit" : "text-loss"}`}>
                          {t.side === "long" ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                          {t.side?.toUpperCase()}
                        </span>
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono text-xs">
                        {t.entry_price != null ? `$${t.entry_price.toLocaleString()}` : "--"}
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono text-xs">
                        {t.exit_price != null ? `$${t.exit_price.toLocaleString()}` : "--"}
                      </td>
                      <td className="py-2.5 pr-4 text-right">
                        <PriceDisplay value={t.pnl} format="currency" className="text-xs font-mono" />
                      </td>
                      <td className="py-2.5 pr-4 text-right font-mono text-xs text-text-secondary">
                        {t.r_multiple != null ? `${t.r_multiple.toFixed(1)}R` : "--"}
                      </td>
                      <td className="py-2.5 pr-4 text-center font-mono text-xs text-text-secondary">
                        {t.signal_score ?? "--"}
                      </td>
                      <td className="py-2.5 text-xs text-text-secondary">
                        {t.entry_time ? new Date(t.entry_time).toLocaleDateString() : "--"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-12 text-text-tertiary text-sm">
              <Clock size={24} className="mx-auto mb-2 opacity-50" />
              <p>No trades yet. Start the engine to begin paper trading.</p>
            </div>
          )}
        </Card>
      </section>
    </div>
  );
}
