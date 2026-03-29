"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import { TradingChart } from "@/components/charts/TradingChart";
import { SessionTracker } from "@/components/ui/SessionTracker";
import { usePriceStream } from "@/hooks/usePriceStream";
import {
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

  const currentPrice = priceMap.get(symbol)?.price;
  const priceData = priceMap.get(symbol);
  const symbolInfo = ALL_SYMBOLS.find((s) => s.value === symbol);

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
            <h1 className="font-heading text-2xl font-bold">Trade</h1>
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

      {/* Session Tracker */}
      <SessionTracker compact />

      {/* Portfolio Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card padding="sm">
          <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Equity</p>
          <p className="font-heading text-lg font-bold font-mono mt-0.5">{formatCurrency(portfolio?.total_equity)}</p>
        </Card>
        <Card padding="sm">
          <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Realized P&L</p>
          <PriceDisplay value={portfolio?.realized_pnl ?? null} format="currency" className="text-lg font-heading font-bold mt-0.5" />
        </Card>
        <Card padding="sm">
          <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Win Rate</p>
          <p className="font-heading text-lg font-bold font-mono mt-0.5">{winRate}{winRate !== "--" ? "%" : ""}</p>
        </Card>
        <Card padding="sm">
          <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Trades (30d)</p>
          <p className="font-heading text-lg font-bold font-mono mt-0.5">{trades.length}</p>
        </Card>
        <Card padding="sm">
          <p className="text-text-tertiary text-[10px] uppercase tracking-wider">Drawdown</p>
          <p className="font-heading text-lg font-bold font-mono text-loss mt-0.5">
            {portfolio?.drawdown_pct != null ? `${(portfolio.drawdown_pct * 100).toFixed(1)}%` : "--"}
          </p>
        </Card>
      </div>

      {/* Main Content: Chart + Panels */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Chart — spans 9 cols */}
        <div className="lg:col-span-9">
          <Card padding="none" className="overflow-hidden">
            <TradingChart symbol={symbol} initialTimeframe="1H" height={520} showTimeframes showVolume />
          </Card>
        </div>

        {/* Right Panel — spans 3 cols */}
        <div className="lg:col-span-3 space-y-4">
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
              <div className="grid grid-cols-2 gap-2 text-xs border-t border-border pt-3">
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

          {/* Signal Score */}
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

          {/* Quick Actions */}
          <Card>
            <p className="text-text-tertiary text-[10px] uppercase tracking-wider mb-3">Quick Actions</p>
            <div className="grid grid-cols-2 gap-2">
              <button className="py-2.5 rounded-button bg-profit/10 text-profit text-xs font-heading font-semibold hover:bg-profit/20 transition-colors flex items-center justify-center gap-1.5">
                <ArrowUpRight size={14} />
                Long
              </button>
              <button className="py-2.5 rounded-button bg-loss/10 text-loss text-xs font-heading font-semibold hover:bg-loss/20 transition-colors flex items-center justify-center gap-1.5">
                <ArrowDownRight size={14} />
                Short
              </button>
            </div>
          </Card>
        </div>
      </div>

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
