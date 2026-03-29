"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { PriceDisplay } from "@/components/ui/PriceDisplay";
import {
  Landmark,
  UserCheck,
  BarChart2,
  AlertTriangle,
  TrendingUp,
  Search,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
}

type Tab = "congressional" | "insider" | "float";

function formatShares(val: number | null): string {
  if (val == null) return "--";
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  return val.toFixed(0);
}

export default function AlphaPage() {
  const [tab, setTab] = useState<Tab>("congressional");
  const [congressTrades, setCongressTrades] = useState<CongressionalTrade[]>([]);
  const [insiderTxns, setInsiderTxns] = useState<InsiderTransaction[]>([]);
  const [floatProfiles, setFloatProfiles] = useState<FloatProfile[]>([]);
  const [floatQuery, setFloatQuery] = useState("AAPL,TSLA,GME,AMC,NVDA,META");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchData();
  }, [tab]);

  async function fetchData() {
    setLoading(true);
    try {
      if (tab === "congressional") {
        const res = await fetch(`${API_BASE}/api/alpha/congressional?days=90`);
        if (res.ok) {
          const data = await res.json();
          setCongressTrades(data.trades || []);
        }
      } else if (tab === "insider") {
        const res = await fetch(`${API_BASE}/api/alpha/insider?days=30`);
        if (res.ok) {
          const data = await res.json();
          setInsiderTxns(data.transactions || []);
        }
      } else if (tab === "float") {
        const res = await fetch(
          `${API_BASE}/api/float/summary?symbols=${encodeURIComponent(floatQuery)}`
        );
        if (res.ok) {
          const data = await res.json();
          setFloatProfiles(data.profiles || []);
        }
      }
    } catch {
      // API not available
    } finally {
      setLoading(false);
    }
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
                      <th className="text-right py-2">Amount</th>
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
                        <td className="py-2.5 text-right text-xs text-text-secondary">
                          {t.amount_range || "--"}
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
                      <th className="text-left py-2">Date</th>
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
                        <td className="py-2.5 text-xs text-text-secondary">
                          {t.date || "--"}
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

      {/* Float Analysis */}
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

          {/* Float profiles table */}
          <Card>
            {floatProfiles.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-text-tertiary text-xs border-b border-border">
                      <th className="text-left py-2 pr-4">Symbol</th>
                      <th className="text-right py-2 pr-4">Float</th>
                      <th className="text-center py-2 pr-4">Category</th>
                      <th className="text-right py-2 pr-4">SI % Float</th>
                      <th className="text-right py-2 pr-4">Squeeze</th>
                      <th className="text-right py-2 pr-4">Liquidity</th>
                      <th className="text-right py-2 pr-4">Vol Mult</th>
                      <th className="text-right py-2">Mkt Cap</th>
                    </tr>
                  </thead>
                  <tbody>
                    {floatProfiles.map((p) => (
                      <tr
                        key={p.symbol}
                        className="border-b border-border-subtle hover:bg-bg-elevated"
                      >
                        <td className="py-2.5 pr-4 font-mono font-semibold text-xs">
                          {p.symbol}
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">
                          {formatShares(p.float_shares)}
                        </td>
                        <td className="py-2.5 pr-4 text-center">
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                              p.float_category === "NANO" || p.float_category === "LOW"
                                ? "bg-loss/10 text-loss"
                                : p.float_category === "MID"
                                ? "bg-warning/10 text-warning"
                                : "bg-profit/10 text-profit"
                            }`}
                          >
                            {p.float_category || "--"}
                          </span>
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">
                          {p.short_pct_of_float != null
                            ? `${p.short_pct_of_float.toFixed(1)}%`
                            : "--"}
                        </td>
                        <td className="py-2.5 pr-4 text-right">
                          {p.squeeze_potential != null ? (
                            <span
                              className={`font-mono text-xs ${
                                p.squeeze_potential >= 70
                                  ? "text-loss"
                                  : p.squeeze_potential >= 40
                                  ? "text-warning"
                                  : "text-text-secondary"
                              }`}
                            >
                              {p.squeeze_potential.toFixed(0)}
                            </span>
                          ) : (
                            "--"
                          )}
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs text-text-secondary">
                          {p.liquidity_score != null
                            ? p.liquidity_score.toFixed(0)
                            : "--"}
                        </td>
                        <td className="py-2.5 pr-4 text-right font-mono text-xs">
                          {p.volatility_multiplier != null
                            ? `${p.volatility_multiplier.toFixed(1)}x`
                            : "--"}
                        </td>
                        <td className="py-2.5 text-right font-mono text-xs text-text-secondary">
                          {p.market_cap != null
                            ? `$${formatShares(p.market_cap)}`
                            : "--"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-12 text-text-tertiary text-sm">
                {loading
                  ? "Analyzing float data..."
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
