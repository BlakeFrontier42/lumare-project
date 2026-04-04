"use client";

import { useState, useMemo } from "react";
import {
  Store,
  Zap,
  Lock,
  Star,
  Filter,
  ArrowRight,
  Search,
  Users,
  TrendingUp,
  BarChart3,
  Shield,
  CheckCircle,
  Crown,
  Eye,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────

interface SignalStream {
  id: string;
  name: string;
  author: string;
  verified: boolean;
  price: number;
  rating: number;
  subscribers: number;
  description: string;
  winRate: number;
  avgReturn: number;
  totalSignals: number;
  category: string;
  tier: "free" | "pro" | "elite";
  tags: string[];
}

type Category = "All" | "Crypto" | "Equities" | "Macro" | "Options" | "Quant";
type SortKey = "popular" | "rating" | "winRate" | "price";

// ── Data ─────────────────────────────────────────────────

const STREAMS: SignalStream[] = [
  { id: "1", name: "ICT Order Flow Signals", author: "SmartMoneyLab", verified: true, price: 99, rating: 4.8, subscribers: 1342, description: "Fair value gaps, order blocks, and liquidity sweep signals across 12 crypto + equity pairs. Avg 4-6 signals/day.", winRate: 68, avgReturn: 2.3, totalSignals: 4823, category: "Crypto", tier: "pro", tags: ["ICT", "Order Flow", "SMC"] },
  { id: "2", name: "Macro Regime Alpha", author: "MacroQuant", verified: true, price: 149, rating: 4.6, subscribers: 687, description: "FOMC-aware signals with yield curve analysis, liquidity regime detection, and cross-asset momentum.", winRate: 72, avgReturn: 1.8, totalSignals: 1247, category: "Macro", tier: "elite", tags: ["FOMC", "Yield Curve", "Regime"] },
  { id: "3", name: "Congressional Edge", author: "PoliticalAlpha", verified: true, price: 49, rating: 4.3, subscribers: 2891, description: "Real-time alerts on congressional trades with sector clustering and historical hit-rate analysis.", winRate: 61, avgReturn: 3.1, totalSignals: 892, category: "Equities", tier: "pro", tags: ["Congress", "Insider", "Politics"] },
  { id: "4", name: "Low Float Momentum", author: "FloatHunter", verified: false, price: 79, rating: 4.5, subscribers: 534, description: "Squeeze potential scanner with volume confirmation on sub-10M float stocks. Pre-market + RTH.", winRate: 58, avgReturn: 5.7, totalSignals: 2341, category: "Equities", tier: "pro", tags: ["Small Cap", "Squeeze", "Momentum"] },
  { id: "5", name: "Options Flow Intelligence", author: "FlowAlpha", verified: true, price: 129, rating: 4.7, subscribers: 876, description: "Unusual options activity scanner. Tracks dark pool prints, sweep orders, and block trades in real-time.", winRate: 64, avgReturn: 4.2, totalSignals: 3456, category: "Options", tier: "elite", tags: ["Dark Pool", "Sweeps", "Block"] },
  { id: "6", name: "Quant Factor Signals", author: "AlphaLab", verified: true, price: 199, rating: 4.9, subscribers: 342, description: "Multi-factor model combining momentum, value, quality, and low-vol factors. Weekly rebalance signals.", winRate: 71, avgReturn: 1.4, totalSignals: 456, category: "Quant", tier: "elite", tags: ["Factor", "Quant", "Long-Term"] },
  { id: "7", name: "Crypto Scalp Alerts", author: "ScalpMaster", verified: false, price: 0, rating: 4.1, subscribers: 4231, description: "Free BTC/ETH/SOL scalp signals with entry, SL, and TP. 15m-1H timeframe focused.", winRate: 55, avgReturn: 1.2, totalSignals: 8934, category: "Crypto", tier: "free", tags: ["Scalping", "Free", "Crypto"] },
  { id: "8", name: "Volatility Edge", author: "VolTrader", verified: true, price: 169, rating: 4.4, subscribers: 298, description: "VIX regime-based signals. Straddle/strangle entries on earnings, FOMC, and high-vol events.", winRate: 66, avgReturn: 3.8, totalSignals: 743, category: "Options", tier: "elite", tags: ["VIX", "Earnings", "Volatility"] },
];

// ── Component ────────────────────────────────────────────

export default function MarketplacePage() {
  const [category, setCategory] = useState<Category>("All");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("popular");
  const [subscribedIds, setSubscribedIds] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    let results = STREAMS.filter((s) => {
      if (category !== "All" && s.category !== category) return false;
      if (search && !s.name.toLowerCase().includes(search.toLowerCase()) && !s.author.toLowerCase().includes(search.toLowerCase()) && !s.tags.some(t => t.toLowerCase().includes(search.toLowerCase()))) return false;
      return true;
    });
    results.sort((a, b) => {
      switch (sortBy) {
        case "popular": return b.subscribers - a.subscribers;
        case "rating": return b.rating - a.rating;
        case "winRate": return b.winRate - a.winRate;
        case "price": return a.price - b.price;
        default: return 0;
      }
    });
    return results;
  }, [category, search, sortBy]);

  const toggleSubscribe = (id: string) => {
    setSubscribedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const tierColors: Record<string, string> = {
    free: "bg-green-500/20 text-green-400",
    pro: "bg-blue-500/20 text-blue-400",
    elite: "bg-purple-500/20 text-purple-400",
  };

  return (
    <div className="min-h-screen bg-[#080808] text-white pb-24">
      {/* Header */}
      <div className="p-4 md:p-6 border-b border-[#1a1a1a]">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-cyan-500/20">
              <Store className="w-6 h-6 text-cyan-400" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-bold tracking-tight">Signal Marketplace</h1>
              <p className="text-sm text-gray-500">Subscribe to curated signals from verified providers</p>
            </div>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-500">{STREAMS.length} providers</span>
            <span className="text-gray-700">•</span>
            <span className="text-gray-500">{STREAMS.reduce((s, st) => s + st.subscribers, 0).toLocaleString()} subscribers</span>
          </div>
        </div>
      </div>

      <div className="p-4 md:p-6 space-y-4">
        {/* Filters */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search signals, providers, tags..."
              className="w-full bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg pl-9 pr-3 py-2 text-sm placeholder:text-gray-600 focus:outline-none focus:border-blue-500/50"
            />
          </div>
          <div className="flex gap-0.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-0.5">
            {(["All", "Crypto", "Equities", "Macro", "Options", "Quant"] as Category[]).map((cat) => (
              <button
                key={cat}
                onClick={() => setCategory(cat)}
                className={`px-2.5 py-1.5 rounded text-xs transition-colors ${
                  category === cat ? "bg-[#1a1a1a] text-white" : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>
          <div className="flex gap-0.5 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-0.5">
            {(["popular", "rating", "winRate", "price"] as SortKey[]).map((s) => (
              <button
                key={s}
                onClick={() => setSortBy(s)}
                className={`px-2.5 py-1.5 rounded text-xs transition-colors capitalize ${
                  sortBy === s ? "bg-[#1a1a1a] text-white" : "text-gray-500 hover:text-gray-300"
                }`}
              >
                {s === "winRate" ? "Win Rate" : s}
              </button>
            ))}
          </div>
        </div>

        {/* Stream Cards */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {filtered.map((stream) => (
            <div
              key={stream.id}
              className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4 hover:border-[#333] transition-colors"
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <h3 className="font-semibold text-sm truncate">{stream.name}</h3>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${tierColors[stream.tier]}`}>
                      {stream.tier}
                    </span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-gray-500">
                    <span>by {stream.author}</span>
                    {stream.verified && <CheckCircle className="w-3 h-3 text-blue-400" />}
                  </div>
                </div>
                <div className="text-right flex-shrink-0 ml-3">
                  {stream.price === 0 ? (
                    <span className="text-green-400 font-bold text-lg">FREE</span>
                  ) : (
                    <>
                      <span className="font-mono text-lg font-bold">${stream.price}</span>
                      <span className="text-gray-600 text-xs">/mo</span>
                    </>
                  )}
                </div>
              </div>

              <p className="text-xs text-gray-400 leading-relaxed mb-3">{stream.description}</p>

              {/* Stats */}
              <div className="flex items-center gap-4 text-xs mb-3">
                <span className="flex items-center gap-1 text-amber-400">
                  <Star className="w-3 h-3" fill="currentColor" />
                  {stream.rating}
                </span>
                <span className="flex items-center gap-1 text-gray-500">
                  <Users className="w-3 h-3" />
                  {stream.subscribers.toLocaleString()}
                </span>
                <span className="text-green-400 font-mono">{stream.winRate}% WR</span>
                <span className="text-gray-400 font-mono">+{stream.avgReturn}% avg</span>
                <span className="text-gray-600">{stream.totalSignals.toLocaleString()} signals</span>
              </div>

              {/* Tags */}
              <div className="flex items-center justify-between">
                <div className="flex gap-1">
                  {stream.tags.map((tag) => (
                    <span key={tag} className="px-2 py-0.5 rounded text-[10px] bg-[#1a1a1a] text-gray-500">
                      {tag}
                    </span>
                  ))}
                </div>
                <button
                  onClick={() => toggleSubscribe(stream.id)}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    subscribedIds.has(stream.id)
                      ? "bg-green-500/20 text-green-400"
                      : "bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30"
                  }`}
                >
                  {subscribedIds.has(stream.id) ? (
                    <>
                      <CheckCircle className="w-3.5 h-3.5" />
                      Subscribed
                    </>
                  ) : (
                    <>
                      <ArrowRight className="w-3.5 h-3.5" />
                      Subscribe
                    </>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-12 text-center">
            <Search className="w-10 h-10 text-gray-600 mx-auto mb-2" />
            <p className="text-gray-400">No signal streams match your filters</p>
          </div>
        )}

        {/* Become a Provider */}
        <div className="rounded-xl bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border border-[#1a1a1a] p-8 text-center">
          <Crown className="w-8 h-8 text-cyan-400 mx-auto mb-3" />
          <h3 className="font-bold text-lg mb-1">Become a Signal Provider</h3>
          <p className="text-sm text-gray-400 max-w-md mx-auto mb-4">
            Monetize your trading strategy. Publish signals, build subscribers, and earn 80% of subscription revenue.
          </p>
          <div className="flex items-center justify-center gap-6 text-xs text-gray-500 mb-4">
            <span className="flex items-center gap-1"><Shield className="w-3.5 h-3.5 text-green-400" /> Verified track record</span>
            <span className="flex items-center gap-1"><BarChart3 className="w-3.5 h-3.5 text-blue-400" /> Real-time analytics</span>
            <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5 text-purple-400" /> Built-in audience</span>
          </div>
          <button className="bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 px-6 py-2.5 rounded-lg text-sm font-medium transition-colors">
            Apply Now
          </button>
        </div>
      </div>
    </div>
  );
}
