"use client";

import { Card } from "@/components/ui/Card";
import { Store, Zap, Lock, Star, Filter, ArrowRight } from "lucide-react";

const SIGNAL_STREAMS = [
  {
    name: "ICT Order Flow Signals",
    author: "SmartMoneyLab",
    price: 99,
    rating: 4.8,
    subscribers: 342,
    description: "Fair value gaps, order blocks, and liquidity sweep signals across 12 pairs",
    winRate: 68,
    avgReturn: 2.3,
  },
  {
    name: "Macro Regime Alpha",
    author: "MacroQuant",
    price: 149,
    rating: 4.6,
    subscribers: 187,
    description: "FOMC-aware signals with yield curve and liquidity regime analysis",
    winRate: 72,
    avgReturn: 1.8,
  },
  {
    name: "Congressional Edge",
    author: "PoliticalAlpha",
    price: 49,
    rating: 4.3,
    subscribers: 891,
    description: "Real-time alerts on congressional trades with sector clustering",
    winRate: 61,
    avgReturn: 3.1,
  },
  {
    name: "Low Float Momentum",
    author: "FloatHunter",
    price: 79,
    rating: 4.5,
    subscribers: 234,
    description: "Squeeze potential scanner with volume confirmation on sub-10M float stocks",
    winRate: 58,
    avgReturn: 5.7,
  },
];

export default function MarketplacePage() {
  return (
    <div className="p-4 lg:p-8 space-y-6 max-w-7xl mx-auto">
      <header>
        <div className="flex items-center gap-3 mb-1">
          <Store size={20} className="text-cyan-500" />
          <h1 className="font-heading text-2xl font-bold">Marketplace</h1>
        </div>
        <p className="text-text-secondary text-sm">
          Subscribe to curated signal streams and strategy signals from verified providers
        </p>
      </header>

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex bg-bg-card border border-border rounded-lg overflow-hidden">
          {["All", "Crypto", "Equities", "Macro", "Options"].map((cat) => (
            <button
              key={cat}
              className={`px-3 py-2 text-xs transition-colors ${
                cat === "All"
                  ? "bg-accent text-text-primary"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
        <button className="flex items-center gap-1.5 bg-bg-card border border-border rounded-lg px-3 py-2 text-xs text-text-secondary hover:text-text-primary">
          <Filter size={12} />
          Filters
        </button>
      </div>

      {/* Signal Streams */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {SIGNAL_STREAMS.map((stream) => (
          <Card key={stream.name} className="hover:border-accent-hover transition-colors">
            <div className="space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-heading font-semibold">{stream.name}</h3>
                  <p className="text-text-tertiary text-xs">by {stream.author}</p>
                </div>
                <div className="text-right">
                  <span className="font-mono text-lg font-bold">${stream.price}</span>
                  <span className="text-text-tertiary text-xs">/mo</span>
                </div>
              </div>

              <p className="text-text-secondary text-xs leading-relaxed">
                {stream.description}
              </p>

              <div className="flex items-center gap-4 text-xs">
                <span className="flex items-center gap-1 text-yellow-500">
                  <Star size={12} fill="currentColor" />
                  {stream.rating}
                </span>
                <span className="text-text-secondary">
                  {stream.subscribers} subscribers
                </span>
                <span className="text-profit font-mono">
                  {stream.winRate}% WR
                </span>
                <span className="text-text-secondary font-mono">
                  +{stream.avgReturn}% avg
                </span>
              </div>

              <button className="w-full bg-accent hover:bg-accent-hover rounded-lg py-2 text-xs font-medium transition-colors flex items-center justify-center gap-2">
                Subscribe
                <ArrowRight size={12} />
              </button>
            </div>
          </Card>
        ))}
      </div>

      {/* Become a Provider */}
      <Card>
        <div className="text-center py-8 space-y-3">
          <Zap size={24} className="mx-auto text-cyan-500" />
          <h3 className="font-heading font-semibold">Become a Signal Provider</h3>
          <p className="text-text-secondary text-xs max-w-md mx-auto">
            Monetize your trading strategy. Publish signals, build subscribers, and earn 80% of subscription revenue.
          </p>
          <button className="bg-cyan-500/10 text-cyan-500 hover:bg-cyan-500/20 px-6 py-2 rounded-lg text-xs font-medium transition-colors">
            Apply Now
          </button>
        </div>
      </Card>
    </div>
  );
}
