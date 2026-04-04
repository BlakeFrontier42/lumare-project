"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import { usePriceStream } from "@/hooks/usePriceStream";
import {
  apiFetch,
  formatCurrency,
  formatNumber,
  formatVolume,
  type PortfolioSummary,
} from "@/lib/api";
import {
  TrendingUp,
  TrendingDown,
  Activity,
  BarChart3,
  Shield,
  Globe,
  Zap,
  Landmark,
  Users,
  Store,
  Target,
  Wallet,
  Wifi,
  WifiOff,
  Grid3X3,
  Filter,
  List,
  Newspaper,
  BookOpen,
  Calendar,
  Bell,
  LayoutGrid,
  Database,
  CandlestickChart,
  Layers,
  Bot,
  Search,
  FileBarChart,
  Radio,
  ArrowRightLeft,
  AlertTriangle,
  CheckCircle,
  XCircle,
  DollarSign,
  Percent,
} from "lucide-react";

// ─── Pillar Cards ────────────────────────────────────────────

const PILLARS = [
  { name: "Intel", description: "CMT-grade technical analysis with ICT, Wyckoff, Elliott Wave", icon: BarChart3, href: "/intel", accent: "#3b82f6" },
  { name: "Macro", description: "Regime detection, FOMC calendar, yield curve analysis", icon: Globe, href: "/macro", accent: "#8b5cf6" },
  { name: "Trade", description: "Paper and live execution with autonomous signals and SL/TP", icon: Zap, href: "/trade", accent: "#22c55e" },
  { name: "Bot", description: "Autonomous trading bot — momentum, mean reversion, breakout strategies", icon: Activity, href: "/bot", accent: "#f59e0b" },
  { name: "Portfolio", description: "Unified wealth management with positions, allocation, performance", icon: Wallet, href: "/portfolio", accent: "#06b6d4" },
  { name: "Taxes", description: "Capital gains tracking, wash sale detection, tax loss harvesting", icon: Landmark, href: "/taxes", accent: "#ef4444" },
  { name: "Real Estate", description: "Property portfolio with cap rates, cashflow, appreciation", icon: Target, href: "/realestate", accent: "#f97316" },
  { name: "Risk", description: "War Room mode with VaR, stress tests, correlation matrix", icon: Shield, href: "/risk", accent: "#10b981" },
  { name: "Correlations", description: "Cross-sector correlation matrix, sector rotation, event simulator", icon: Database, href: "/correlations", accent: "#8b5cf6" },
  { name: "Alpha", description: "Congressional disclosures, insider Form 4, institutional 13F", icon: Store, href: "/alpha", accent: "#ef4444" },
  { name: "Copy", description: "Leaderboard and strategy mirroring from top performers", icon: Users, href: "/copy", accent: "#f59e0b" },
  { name: "Plan", description: "Financial planning suite with projection modeling", icon: Target, href: "/plan", accent: "#06b6d4" },
];

// ─── Page ────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter();
  const { prices, connected } = usePriceStream();
  const [portfolio, setPortfolio] = useState<PortfolioSummary | null>(null);
  const [apiStatus, setApiStatus] = useState<"connected" | "disconnected">("disconnected");

  useEffect(() => {
    async function fetchData() {
      const [portfolioData, healthData] = await Promise.all([
        apiFetch<PortfolioSummary>("/api/portfolio/summary"),
        apiFetch<{ status: string }>("/api/health"),
      ]);
      if (portfolioData) setPortfolio(portfolioData);
      setApiStatus(healthData ? "connected" : "disconnected");
    }
    fetchData();
    const interval = setInterval(fetchData, 10_000);
    return () => clearInterval(interval);
  }, []);

  const isLive = connected || apiStatus === "connected";
  const totalPnl = portfolio?.total_pnl ?? null;
  const pnlPositive = totalPnl != null && totalPnl >= 0;

  return (
    <div className="p-4 lg:p-8 space-y-8 max-w-7xl mx-auto animate-fade-in">
      {/* Header */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="font-heading text-2xl lg:text-3xl font-bold tracking-tight">
            Dashboard
          </h1>
          <p className="text-text-secondary text-sm mt-1">
            Capital Intelligence Overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          {connected && (
            <span className="text-[10px] text-profit font-mono bg-profit/10 px-2 py-0.5 rounded">
              WS STREAMING
            </span>
          )}
          <div className="flex items-center gap-1.5">
            <span
              className={`w-2 h-2 rounded-full ${
                isLive ? "bg-profit pulse-live" : "bg-loss"
              }`}
            />
            <span className="text-xs text-text-tertiary font-mono">
              {isLive ? "LIVE" : "OFFLINE"}
            </span>
          </div>
        </div>
      </header>

      {/* Portfolio Summary */}
      <section className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className={pnlPositive ? "glow-profit" : totalPnl != null ? "glow-loss" : ""}>
          <div className="space-y-1">
            <p className="text-text-secondary text-xs uppercase tracking-wider">Net Worth</p>
            <p className="font-heading text-2xl font-bold">
              {formatCurrency(portfolio?.total_equity)}
            </p>
          </div>
        </Card>
        <Card>
          <div className="space-y-1">
            <p className="text-text-secondary text-xs uppercase tracking-wider">Total P&L</p>
            <PriceDisplay value={totalPnl} format="currency" className="text-2xl font-heading font-bold" />
          </div>
        </Card>
        <Card>
          <div className="space-y-1">
            <p className="text-text-secondary text-xs uppercase tracking-wider">Open Positions</p>
            <p className="font-heading text-2xl font-bold font-mono">
              {portfolio?.open_positions ?? "--"}
            </p>
          </div>
        </Card>
        <Card>
          <div className="space-y-1">
            <p className="text-text-secondary text-xs uppercase tracking-wider">Drawdown</p>
            <p className="font-heading text-2xl font-bold font-mono text-loss">
              {portfolio?.drawdown_pct != null ? `${(portfolio.drawdown_pct * 100).toFixed(1)}%` : "--"}
            </p>
          </div>
        </Card>
      </section>

      {/* Market Prices — now streaming via WebSocket */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-heading text-lg font-semibold">Markets</h2>
          {connected && (
            <span className="text-[10px] text-text-tertiary font-mono flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-profit animate-pulse" />
              Real-time
            </span>
          )}
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {prices.length > 0 ? (
            prices.map((p) => (
              <Card
                key={p.symbol}
                className="hover:border-profit/40 transition-colors cursor-pointer group"
                onClick={() => router.push(`/trade?symbol=${p.symbol}`)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <p className="font-mono text-sm text-text-secondary group-hover:text-text-primary transition-colors">{p.symbol}</p>
                      {p.asset_class && (
                        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded ${
                          p.asset_class === "crypto" ? "bg-purple-500/10 text-purple-400" : "bg-blue-500/10 text-blue-400"
                        }`}>
                          {p.asset_class === "crypto" ? "CRYPTO" : "EQUITY"}
                        </span>
                      )}
                    </div>
                    <p className="font-heading text-xl font-bold font-mono mt-0.5">
                      ${formatNumber(p.price)}
                    </p>
                  </div>
                  <div className="text-right">
                    <PriceDisplay value={p.change_24h} format="percent" className="text-sm font-mono" />
                    <p className="text-xs text-text-tertiary mt-1">
                      Vol {formatVolume(p.volume_24h)}
                    </p>
                  </div>
                </div>
              </Card>
            ))
          ) : (
            <Card className="col-span-full">
              <div className="text-center py-8 text-text-tertiary text-sm">
                <Activity size={24} className="mx-auto mb-2 opacity-50" />
                <p>Connecting to market data feeds...</p>
                <p className="text-xs mt-1 font-mono">Start the API: uvicorn backend.api.app:app --port 8000</p>
              </div>
            </Card>
          )}
        </div>
      </section>

      {/* 8 Pillars */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Pillars</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {PILLARS.map((pillar, i) => {
            const Icon = pillar.icon;
            return (
              <a key={pillar.name} href={pillar.href} className="group" style={{ animationDelay: `${i * 50}ms` }}>
                <Card className="h-full hover:border-accent-hover transition-all group-hover:translate-y-[-2px]">
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ backgroundColor: `${pillar.accent}15` }}>
                        <Icon size={18} style={{ color: pillar.accent }} />
                      </div>
                      <h3 className="font-heading font-semibold">{pillar.name}</h3>
                    </div>
                    <p className="text-text-secondary text-xs leading-relaxed">{pillar.description}</p>
                  </div>
                </Card>
              </a>
            );
          })}
        </div>
      </section>

      {/* Quick Actions */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Quick Actions</h2>
        <div className="flex flex-wrap gap-3">
          {[
            { label: "New Trade", icon: Zap, href: "/trade", accent: "#22c55e" },
            { label: "Scan Screener", icon: Search, href: "/screener", accent: "#3b82f6" },
            { label: "Check Signals", icon: Radio, href: "/intel", accent: "#f59e0b" },
            { label: "Risk Report", icon: Shield, href: "/risk", accent: "#ef4444" },
            { label: "Bot Status", icon: Bot, href: "/bot", accent: "#8b5cf6" },
          ].map((action) => {
            const Icon = action.icon;
            return (
              <a
                key={action.label}
                href={action.href}
                className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg border border-border hover:border-accent-hover bg-bg-card hover:bg-bg-elevated transition-all group"
              >
                <div
                  className="w-8 h-8 rounded-md flex items-center justify-center"
                  style={{ backgroundColor: `${action.accent}15` }}
                >
                  <Icon size={16} style={{ color: action.accent }} />
                </div>
                <span className="text-sm font-medium text-text-secondary group-hover:text-text-primary transition-colors">
                  {action.label}
                </span>
              </a>
            );
          })}
        </div>
      </section>

      {/* Account Summary */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Account Summary</h2>
        <Card>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-6">
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <DollarSign size={12} className="text-text-tertiary" />
                <p className="text-text-secondary text-xs uppercase tracking-wider">Account Value</p>
              </div>
              <p className="font-heading text-xl font-bold font-mono">$125,000.00</p>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <Wallet size={12} className="text-text-tertiary" />
                <p className="text-text-secondary text-xs uppercase tracking-wider">Buying Power</p>
              </div>
              <p className="font-heading text-xl font-bold font-mono">$87,500.00</p>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <Percent size={12} className="text-text-tertiary" />
                <p className="text-text-secondary text-xs uppercase tracking-wider">Margin Used</p>
              </div>
              <p className="font-heading text-xl font-bold font-mono text-yellow-400">30%</p>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <TrendingUp size={12} className="text-text-tertiary" />
                <p className="text-text-secondary text-xs uppercase tracking-wider">Daily P/L</p>
              </div>
              <p className="font-heading text-xl font-bold font-mono text-profit">+$1,250.00</p>
            </div>
          </div>
        </Card>
      </section>

      {/* Recent Activity */}
      <section>
        <h2 className="font-heading text-lg font-semibold mb-4">Recent Activity</h2>
        <Card>
          <div className="space-y-0">
            {[
              { icon: CheckCircle, color: "text-profit", label: "Trade Executed", detail: "LONG NVDA 50 shares @ $878.32", time: "2 min ago" },
              { icon: Radio, color: "text-yellow-400", label: "Signal Fired", detail: "BTCUSDT bullish breakout — composite 78/100", time: "8 min ago" },
              { icon: XCircle, color: "text-loss", label: "Position Closed", detail: "SHORT TSLA 100 shares — P/L -$312.50", time: "23 min ago" },
              { icon: AlertTriangle, color: "text-yellow-400", label: "Alert Triggered", detail: "SPY drawdown exceeds -1.5% intraday threshold", time: "41 min ago" },
              { icon: CheckCircle, color: "text-profit", label: "Trade Executed", detail: "LONG ETH 2.5 units @ $3,521.45", time: "1h ago" },
              { icon: Bot, color: "text-purple-400", label: "Bot Cycle Complete", detail: "Momentum strategy scanned 142 symbols, 3 setups found", time: "1h 15m ago" },
              { icon: ArrowRightLeft, color: "text-blue-400", label: "Rebalance Triggered", detail: "Portfolio drift exceeded 5% threshold — rebalance queued", time: "2h ago" },
              { icon: CheckCircle, color: "text-profit", label: "Take Profit Hit", detail: "LONG AMZN 25 shares — P/L +$487.25 (2.1R)", time: "3h ago" },
            ].map((event, i) => {
              const Icon = event.icon;
              return (
                <div
                  key={i}
                  className={`flex items-center gap-3 px-1 py-3 ${i > 0 ? "border-t border-border/50" : ""}`}
                >
                  <Icon size={16} className={event.color} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-text-primary">{event.label}</span>
                    </div>
                    <p className="text-xs text-text-secondary truncate">{event.detail}</p>
                  </div>
                  <span className="text-[10px] text-text-tertiary font-mono whitespace-nowrap">{event.time}</span>
                </div>
              );
            })}
          </div>
        </Card>
      </section>

      <footer className="text-center text-text-tertiary text-xs py-8 border-t border-border-subtle">
        Lumare Capital Intelligence Platform
      </footer>
    </div>
  );
}
