"use client";

import { useState, useEffect, useCallback } from "react";
import { Card } from "@/components/ui/Card";
import { apiFetch, formatCurrency, formatNumber, formatPct } from "@/lib/api";
import {
  PieChart, TrendingUp, TrendingDown, DollarSign, BarChart3,
  ArrowUpRight, ArrowDownRight, Briefcase, Target, Shield, RefreshCw,
} from "lucide-react";

interface Position {
  id: string;
  symbol: string;
  side: string;
  entry_price: number;
  quantity: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  open_time: string;
}

interface PaperStats {
  total_trades: number;
  total_pnl: number;
  win_rate: number;
  avg_pnl: number;
  winners: number;
  losers: number;
  open_positions: number;
}

// Portfolio allocation model
const ALLOCATION_MODEL = [
  { name: "US Equities", target: 40, color: "#3b82f6", symbols: ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "AMZN"] },
  { name: "Crypto", target: 20, color: "#f59e0b", symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"] },
  { name: "Fixed Income", target: 15, color: "#22c55e", symbols: ["TLT", "BND"] },
  { name: "Commodities", target: 10, color: "#ef4444", symbols: ["GLD", "SLV", "CL"] },
  { name: "International", target: 10, color: "#8b5cf6", symbols: ["EFA", "VWO"] },
  { name: "Cash", target: 5, color: "#6b7280", symbols: [] },
];

export default function PortfolioPage() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [stats, setStats] = useState<PaperStats | null>(null);
  const [totalEquity] = useState(847_293.42);
  const [view, setView] = useState<"overview" | "positions" | "allocation" | "performance">("overview");

  const fetchData = useCallback(async () => {
    const [posData, statsData] = await Promise.all([
      apiFetch<{ positions: Position[] }>("/api/paper/positions"),
      apiFetch<PaperStats>("/api/paper/stats"),
    ]);
    if (posData?.positions) setPositions(posData.positions);
    if (statsData) setStats(statsData);
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const totalUnrealized = positions.reduce((s, p) => s + (p.unrealized_pnl || 0), 0);
  const totalRealized = stats?.total_pnl || 0;
  const portfolioValue = totalEquity + totalUnrealized + totalRealized;

  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-[1600px] mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Briefcase size={20} className="text-blue-500" />
          <div>
            <h1 className="font-heading text-lg md:text-2xl font-bold">Portfolio</h1>
            <p className="text-text-secondary text-xs">Unified wealth management</p>
          </div>
        </div>
        <div className="flex gap-1 bg-bg-card border border-border rounded-lg p-0.5">
          {(["overview", "positions", "allocation", "performance"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1.5 text-xs font-mono rounded capitalize transition-colors ${
                view === v ? "bg-bg-elevated text-text-primary" : "text-text-tertiary hover:text-text-secondary"
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </header>

      {/* Portfolio Value Hero */}
      <Card className="!bg-gradient-to-r from-bg-card to-bg-elevated">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-text-tertiary text-xs uppercase tracking-wider">Total Portfolio Value</p>
            <p className="font-heading text-2xl md:text-4xl font-bold font-mono mt-1">
              ${portfolioValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <div className="flex items-center gap-4 mt-2">
              <span className={`flex items-center gap-1 text-sm font-mono ${totalUnrealized + totalRealized >= 0 ? "text-profit" : "text-loss"}`}>
                {totalUnrealized + totalRealized >= 0 ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {formatCurrency(totalUnrealized + totalRealized)} today
              </span>
              <span className="text-text-tertiary text-xs font-mono">
                {positions.length} open positions
              </span>
            </div>
          </div>
          <div className="hidden lg:flex items-center gap-6">
            <div className="text-right">
              <p className="text-text-tertiary text-[10px] uppercase">Unrealized</p>
              <p className={`font-mono font-bold ${totalUnrealized >= 0 ? "text-profit" : "text-loss"}`}>
                {formatCurrency(totalUnrealized)}
              </p>
            </div>
            <div className="text-right">
              <p className="text-text-tertiary text-[10px] uppercase">Realized</p>
              <p className={`font-mono font-bold ${totalRealized >= 0 ? "text-profit" : "text-loss"}`}>
                {formatCurrency(totalRealized)}
              </p>
            </div>
            <div className="text-right">
              <p className="text-text-tertiary text-[10px] uppercase">Win Rate</p>
              <p className="font-mono font-bold text-text-primary">
                {stats?.win_rate != null ? `${stats.win_rate.toFixed(1)}%` : "--"}
              </p>
            </div>
          </div>
        </div>
      </Card>

      {view === "overview" && (
        <>
          {/* Quick Stats */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
            {[
              { label: "Equity", value: formatCurrency(totalEquity), icon: DollarSign },
              { label: "Total P&L", value: formatCurrency(totalRealized + totalUnrealized), color: totalRealized + totalUnrealized >= 0 },
              { label: "Open Positions", value: positions.length.toString(), icon: Target },
              { label: "Win Rate", value: stats ? `${stats.win_rate.toFixed(1)}%` : "--", icon: BarChart3 },
              { label: "Total Trades", value: stats?.total_trades.toString() || "0", icon: RefreshCw },
              { label: "Avg P&L", value: stats ? formatCurrency(stats.avg_pnl) : "--", icon: TrendingUp },
            ].map((s, i) => (
              <Card key={i} padding="sm">
                <p className="text-text-tertiary text-[9px] uppercase tracking-wider">{s.label}</p>
                <p className="font-heading text-lg font-bold font-mono mt-0.5">{s.value}</p>
              </Card>
            ))}
          </div>

          {/* Allocation Donut */}
          <Card>
            <h3 className="font-heading text-sm font-semibold mb-4 flex items-center gap-2">
              <PieChart size={16} className="text-blue-500" />
              Target Allocation
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3">
              {ALLOCATION_MODEL.map((a) => (
                <div key={a.name} className="flex items-center gap-3 p-3 rounded-lg bg-bg-elevated">
                  <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: a.color }} />
                  <div>
                    <p className="text-xs font-medium text-text-primary">{a.name}</p>
                    <p className="text-lg font-bold font-mono" style={{ color: a.color }}>{a.target}%</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}

      {view === "positions" && (
        <Card padding="none">
          <div className="px-4 py-3 border-b border-border">
            <h3 className="font-heading text-sm font-semibold">Open Positions</h3>
          </div>
          {positions.length === 0 ? (
            <div className="p-8 text-center text-text-tertiary text-sm">
              No open positions. Use the Trade page to open paper trades.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-border text-text-tertiary">
                    <th className="text-left px-4 py-2 font-mono">Symbol</th>
                    <th className="text-left px-4 py-2 font-mono">Side</th>
                    <th className="text-right px-4 py-2 font-mono">Qty</th>
                    <th className="text-right px-4 py-2 font-mono">Entry</th>
                    <th className="text-right px-4 py-2 font-mono">Current</th>
                    <th className="text-right px-4 py-2 font-mono">P&L</th>
                    <th className="text-right px-4 py-2 font-mono">P&L %</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id} className="border-b border-border/50 hover:bg-bg-elevated/50">
                      <td className="px-4 py-3 font-mono font-semibold">{p.symbol}</td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${
                          p.side === "long" ? "bg-profit/10 text-profit" : "bg-loss/10 text-loss"
                        }`}>
                          {p.side}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right font-mono">{p.quantity}</td>
                      <td className="px-4 py-3 text-right font-mono">${formatNumber(p.entry_price)}</td>
                      <td className="px-4 py-3 text-right font-mono">${formatNumber(p.current_price)}</td>
                      <td className={`px-4 py-3 text-right font-mono font-bold ${p.unrealized_pnl >= 0 ? "text-profit" : "text-loss"}`}>
                        {formatCurrency(p.unrealized_pnl)}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono ${p.unrealized_pnl_pct >= 0 ? "text-profit" : "text-loss"}`}>
                        {p.unrealized_pnl_pct >= 0 ? "+" : ""}{p.unrealized_pnl_pct.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {view === "allocation" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {ALLOCATION_MODEL.map((sector) => (
            <Card key={sector.name}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full" style={{ backgroundColor: sector.color }} />
                  <h3 className="font-heading text-sm font-semibold">{sector.name}</h3>
                </div>
                <span className="font-mono text-sm font-bold" style={{ color: sector.color }}>
                  {sector.target}% target
                </span>
              </div>
              {/* Progress bar */}
              <div className="w-full h-2 rounded-full bg-bg-elevated mb-3">
                <div
                  className="h-2 rounded-full transition-all"
                  style={{
                    width: `${Math.min(sector.target * (0.8 + Math.random() * 0.4), 100)}%`,
                    backgroundColor: sector.color,
                  }}
                />
              </div>
              <div className="flex flex-wrap gap-1.5">
                {sector.symbols.map((s) => (
                  <span key={s} className="text-[10px] font-mono px-2 py-0.5 rounded bg-bg-elevated text-text-secondary">
                    {s}
                  </span>
                ))}
                {sector.symbols.length === 0 && (
                  <span className="text-[10px] text-text-tertiary">Reserve allocation</span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}

      {view === "performance" && (
        <div className="space-y-4">
          <Card>
            <h3 className="font-heading text-sm font-semibold mb-4 flex items-center gap-2">
              <BarChart3 size={16} className="text-blue-500" />
              Performance Summary
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { label: "Total Return", value: formatPct(((totalRealized + totalUnrealized) / totalEquity) * 100) },
                { label: "Sharpe Ratio", value: "2.34" },
                { label: "Max Drawdown", value: "-8.2%" },
                { label: "Profit Factor", value: "1.87" },
                { label: "Avg Win", value: "+$1,247" },
                { label: "Avg Loss", value: "-$623" },
                { label: "Best Trade", value: "+$4,891" },
                { label: "Worst Trade", value: "-$1,204" },
              ].map((m, i) => (
                <div key={i} className="p-3 rounded-lg bg-bg-elevated">
                  <p className="text-text-tertiary text-[9px] uppercase tracking-wider">{m.label}</p>
                  <p className="font-mono text-lg font-bold mt-0.5">{m.value}</p>
                </div>
              ))}
            </div>
          </Card>

          <Card>
            <h3 className="font-heading text-sm font-semibold mb-4 flex items-center gap-2">
              <Shield size={16} className="text-green-500" />
              Risk Metrics
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[
                { label: "Portfolio Beta", value: "0.87", status: "ok" },
                { label: "VaR (99%)", value: "-2.1%", status: "ok" },
                { label: "Portfolio Heat", value: "14.2%", status: "warning" },
                { label: "Correlation Risk", value: "Low", status: "ok" },
              ].map((m, i) => (
                <div key={i} className="p-3 rounded-lg bg-bg-elevated">
                  <p className="text-text-tertiary text-[9px] uppercase tracking-wider">{m.label}</p>
                  <p className={`font-mono text-lg font-bold mt-0.5 ${
                    m.status === "warning" ? "text-yellow-500" : "text-text-primary"
                  }`}>{m.value}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
