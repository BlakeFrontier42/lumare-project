"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Users,
  Trophy,
  TrendingUp,
  TrendingDown,
  Copy,
  Star,
  Shield,
  BarChart3,
  Target,
  Clock,
  DollarSign,
  Search,
  Filter,
  ChevronDown,
  CheckCircle,
  XCircle,
  Activity,
  Zap,
  Eye,
  Pause,
  Play,
} from "lucide-react";

// ── Types ────────────────────────────────────────────────

interface Leader {
  rank: number;
  name: string;
  avatar: string;
  return_pct: number;
  return_30d: number;
  sharpe: number;
  dd: number;
  followers: number;
  strategy: string;
  tags: string[];
  win_rate: number;
  total_trades: number;
  avg_holding: string;
  verified: boolean;
}

interface CopyPosition {
  id: string;
  leader: string;
  symbol: string;
  side: "Long" | "Short";
  entry: number;
  current: number;
  pnl: number;
  pnl_pct: number;
  time: string;
}

type Tab = "leaderboard" | "active" | "history";
type SortKey = "return" | "sharpe" | "followers" | "win_rate";
type TimeFilter = "7d" | "30d" | "90d" | "1y" | "all";

// ── Mock Data ────────────────────────────────────────────

const LEADERS: Leader[] = [
  { rank: 1, name: "QuantAlpha", avatar: "QA", return_pct: 147.2, return_30d: 12.3, sharpe: 3.1, dd: 8.2, followers: 1243, strategy: "Momentum + ICT", tags: ["Crypto", "Equities"], win_rate: 72, total_trades: 847, avg_holding: "4.2h", verified: true },
  { rank: 2, name: "MacroHunter", avatar: "MH", return_pct: 98.9, return_30d: 8.1, sharpe: 2.8, dd: 11.5, followers: 891, strategy: "Macro Regime", tags: ["Macro", "Bonds"], win_rate: 68, total_trades: 342, avg_holding: "2.1d", verified: true },
  { rank: 3, name: "StructureTrader", avatar: "ST", return_pct: 82.1, return_30d: 6.4, sharpe: 2.5, dd: 9.8, followers: 654, strategy: "Wyckoff + Volume Profile", tags: ["Equities"], win_rate: 65, total_trades: 523, avg_holding: "6h", verified: true },
  { rank: 4, name: "FlowReader", avatar: "FR", return_pct: 68.7, return_30d: 5.2, sharpe: 2.2, dd: 13.1, followers: 432, strategy: "Dark Pool + Options Flow", tags: ["Options", "Flow"], win_rate: 61, total_trades: 1205, avg_holding: "45m", verified: true },
  { rank: 5, name: "TrendFollower", avatar: "TF", return_pct: 54.3, return_30d: 3.8, sharpe: 2.0, dd: 14.2, followers: 321, strategy: "Trend + Elliott Wave", tags: ["Crypto"], win_rate: 58, total_trades: 189, avg_holding: "3.5d", verified: false },
  { rank: 6, name: "ScalpKing", avatar: "SK", return_pct: 42.8, return_30d: 9.7, sharpe: 1.9, dd: 6.3, followers: 567, strategy: "Order Flow Scalping", tags: ["Crypto", "Futures"], win_rate: 74, total_trades: 3420, avg_holding: "8m", verified: true },
  { rank: 7, name: "ValueSeeker", avatar: "VS", return_pct: 38.1, return_30d: 2.1, sharpe: 2.4, dd: 7.8, followers: 234, strategy: "Deep Value + Catalyst", tags: ["Equities"], win_rate: 63, total_trades: 87, avg_holding: "14d", verified: false },
  { rank: 8, name: "VolTrader", avatar: "VT", return_pct: 35.6, return_30d: 4.5, sharpe: 1.7, dd: 15.9, followers: 178, strategy: "Volatility Arbitrage", tags: ["Options", "VIX"], win_rate: 59, total_trades: 654, avg_holding: "1.2d", verified: true },
];

const MOCK_COPIES: CopyPosition[] = [
  { id: "1", leader: "QuantAlpha", symbol: "BTC", side: "Long", entry: 67200, current: 68450, pnl: 1250, pnl_pct: 1.86, time: "2h ago" },
  { id: "2", leader: "MacroHunter", symbol: "TLT", side: "Short", entry: 92.30, current: 91.80, pnl: 50, pnl_pct: 0.54, time: "5h ago" },
  { id: "3", leader: "ScalpKing", symbol: "ETH", side: "Long", entry: 3780, current: 3812, pnl: 32, pnl_pct: 0.85, time: "15m ago" },
];

// ── Component ────────────────────────────────────────────

export default function CopyPage() {
  const [tab, setTab] = useState<Tab>("leaderboard");
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("return");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [following, setFollowing] = useState<Set<string>>(new Set());
  const [selectedLeader, setSelectedLeader] = useState<Leader | null>(null);
  const [copies, setCopies] = useState<CopyPosition[]>(MOCK_COPIES);
  const [totalPnl, setTotalPnl] = useState(0);

  useEffect(() => {
    setTotalPnl(copies.reduce((sum, c) => sum + c.pnl, 0));
  }, [copies]);

  const filteredLeaders = LEADERS
    .filter((l) => !search || l.name.toLowerCase().includes(search.toLowerCase()) || l.strategy.toLowerCase().includes(search.toLowerCase()))
    .sort((a, b) => {
      switch (sortBy) {
        case "return": return b.return_pct - a.return_pct;
        case "sharpe": return b.sharpe - a.sharpe;
        case "followers": return b.followers - a.followers;
        case "win_rate": return b.win_rate - a.win_rate;
        default: return 0;
      }
    });

  const toggleFollow = (name: string) => {
    setFollowing((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  return (
    <div className="min-h-screen bg-[#080808] text-white pb-24">
      {/* Header */}
      <div className="p-4 md:p-6 border-b border-[#1a1a1a]">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-amber-500/20">
              <Users className="w-6 h-6 text-amber-400" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-bold tracking-tight">Copy Trading</h1>
              <p className="text-sm text-gray-500">Mirror verified traders automatically</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right">
              <p className="text-xs text-gray-500">Active Copies P&L</p>
              <p className={`text-lg font-bold font-mono ${totalPnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                {totalPnl >= 0 ? "+" : ""}${totalPnl.toLocaleString()}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-2 mx-4 md:mx-6 mt-4 bg-[#0a0a0a] rounded-lg w-fit">
        {([
          { key: "leaderboard" as Tab, label: "Leaderboard", icon: Trophy },
          { key: "active" as Tab, label: `Active (${copies.length})`, icon: Activity },
          { key: "history" as Tab, label: "History", icon: Clock },
        ]).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              tab === t.key ? "bg-[#1a1a1a] text-white" : "text-gray-500 hover:text-gray-300"
            }`}
          >
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      <div className="p-4 md:p-6">
        {/* Leaderboard Tab */}
        {tab === "leaderboard" && (
          <div className="space-y-4">
            {/* Search + Sort */}
            <div className="flex items-center gap-3 flex-wrap">
              <div className="relative flex-1 min-w-[200px] max-w-md">
                <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search traders or strategies..."
                  className="w-full bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg pl-9 pr-3 py-2 text-sm placeholder:text-gray-600 focus:outline-none focus:border-blue-500/50"
                />
              </div>
              <div className="flex gap-1 bg-[#0a0a0a] border border-[#1a1a1a] rounded-lg p-0.5">
                {(["return", "sharpe", "followers", "win_rate"] as SortKey[]).map((s) => (
                  <button
                    key={s}
                    onClick={() => setSortBy(s)}
                    className={`px-2.5 py-1 rounded text-xs transition-colors capitalize ${
                      sortBy === s ? "bg-[#1a1a1a] text-white" : "text-gray-500 hover:text-gray-300"
                    }`}
                  >
                    {s.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            {/* Leaders */}
            <div className="space-y-3">
              {filteredLeaders.map((leader) => (
                <div
                  key={leader.rank}
                  className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4 hover:border-[#333] transition-colors cursor-pointer"
                  onClick={() => setSelectedLeader(selectedLeader?.name === leader.name ? null : leader)}
                >
                  <div className="flex items-center gap-4">
                    {/* Rank */}
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                      leader.rank <= 3 ? "bg-amber-500/20 text-amber-400" : "bg-[#1a1a1a] text-gray-500"
                    }`}>
                      {leader.rank}
                    </div>

                    {/* Avatar + Name */}
                    <div className="flex items-center gap-3 min-w-[140px]">
                      <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500/30 to-purple-500/30 flex items-center justify-center text-xs font-bold font-mono">
                        {leader.avatar}
                      </div>
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-sm">{leader.name}</span>
                          {leader.verified && <CheckCircle className="w-3.5 h-3.5 text-blue-400" />}
                        </div>
                        <p className="text-xs text-gray-600">{leader.strategy}</p>
                      </div>
                    </div>

                    {/* Stats */}
                    <div className="hidden md:flex items-center gap-6 flex-1">
                      <div className="text-center">
                        <p className="text-xs text-gray-500">Return</p>
                        <p className="text-sm font-bold font-mono text-green-400">+{leader.return_pct}%</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-gray-500">30d</p>
                        <p className={`text-sm font-mono ${leader.return_30d >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {leader.return_30d >= 0 ? "+" : ""}{leader.return_30d}%
                        </p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-gray-500">Sharpe</p>
                        <p className="text-sm font-mono">{leader.sharpe}</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-gray-500">Win Rate</p>
                        <p className="text-sm font-mono">{leader.win_rate}%</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-gray-500">Max DD</p>
                        <p className="text-sm font-mono text-red-400/70">{leader.dd}%</p>
                      </div>
                      <div className="text-center">
                        <p className="text-xs text-gray-500">Followers</p>
                        <p className="text-sm font-mono">{leader.followers.toLocaleString()}</p>
                      </div>
                    </div>

                    {/* Tags */}
                    <div className="hidden lg:flex gap-1">
                      {leader.tags.map((tag) => (
                        <span key={tag} className="px-2 py-0.5 rounded text-[10px] bg-[#1a1a1a] text-gray-400">
                          {tag}
                        </span>
                      ))}
                    </div>

                    {/* Action */}
                    <button
                      onClick={(e) => { e.stopPropagation(); toggleFollow(leader.name); }}
                      className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors flex-shrink-0 ${
                        following.has(leader.name)
                          ? "bg-green-500/20 text-green-400"
                          : "bg-blue-500/20 text-blue-400 hover:bg-blue-500/30"
                      }`}
                    >
                      {following.has(leader.name) ? (
                        <>
                          <CheckCircle className="w-3.5 h-3.5" />
                          Following
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          Copy
                        </>
                      )}
                    </button>
                  </div>

                  {/* Expanded Detail */}
                  {selectedLeader?.name === leader.name && (
                    <div className="mt-4 pt-4 border-t border-[#1a1a1a] grid grid-cols-2 md:grid-cols-4 gap-4">
                      <div className="p-3 rounded-lg bg-[#111]">
                        <p className="text-[10px] text-gray-500 uppercase">Total Trades</p>
                        <p className="text-lg font-bold font-mono">{leader.total_trades.toLocaleString()}</p>
                      </div>
                      <div className="p-3 rounded-lg bg-[#111]">
                        <p className="text-[10px] text-gray-500 uppercase">Avg Holding</p>
                        <p className="text-lg font-bold font-mono">{leader.avg_holding}</p>
                      </div>
                      <div className="p-3 rounded-lg bg-[#111]">
                        <p className="text-[10px] text-gray-500 uppercase">Profit Factor</p>
                        <p className="text-lg font-bold font-mono text-green-400">{(leader.sharpe * 0.8).toFixed(1)}</p>
                      </div>
                      <div className="p-3 rounded-lg bg-[#111]">
                        <p className="text-[10px] text-gray-500 uppercase">Risk Score</p>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex-1 h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${leader.dd < 10 ? "bg-green-500" : leader.dd < 15 ? "bg-amber-500" : "bg-red-500"}`}
                              style={{ width: `${Math.min(100, leader.dd * 5)}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono">{leader.dd < 10 ? "Low" : leader.dd < 15 ? "Med" : "High"}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Active Copies Tab */}
        {tab === "active" && (
          <div className="space-y-4">
            {copies.length === 0 ? (
              <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-12 text-center">
                <Copy className="w-10 h-10 text-gray-600 mx-auto mb-2" />
                <p className="text-gray-400">No active copy trades</p>
                <p className="text-xs text-gray-600 mt-1">Follow a trader from the leaderboard to start</p>
              </div>
            ) : (
              <div className="space-y-3">
                {copies.map((pos) => (
                  <div key={pos.id} className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className={`px-2 py-0.5 rounded text-xs font-semibold ${
                          pos.side === "Long" ? "bg-green-500/20 text-green-400" : "bg-red-500/20 text-red-400"
                        }`}>
                          {pos.side}
                        </div>
                        <span className="font-mono font-medium">{pos.symbol}</span>
                        <span className="text-xs text-gray-500">via {pos.leader}</span>
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <p className={`text-sm font-bold font-mono ${pos.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {pos.pnl >= 0 ? "+" : ""}${pos.pnl.toLocaleString()}
                          </p>
                          <p className={`text-xs font-mono ${pos.pnl_pct >= 0 ? "text-green-400/70" : "text-red-400/70"}`}>
                            {pos.pnl_pct >= 0 ? "+" : ""}{pos.pnl_pct}%
                          </p>
                        </div>
                        <button className="p-1.5 rounded-lg bg-[#1a1a1a] hover:bg-red-500/20 text-gray-500 hover:text-red-400 transition-colors">
                          <XCircle className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                      <span>Entry: ${pos.entry.toLocaleString()}</span>
                      <span>Current: ${pos.current.toLocaleString()}</span>
                      <span>{pos.time}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* History Tab */}
        {tab === "history" && (
          <div className="rounded-xl bg-[#0a0a0a] border border-[#1a1a1a] p-12 text-center">
            <Clock className="w-10 h-10 text-gray-600 mx-auto mb-2" />
            <p className="text-gray-400">No copy trade history yet</p>
            <p className="text-xs text-gray-600 mt-1">Completed copy trades will appear here</p>
          </div>
        )}
      </div>

      {/* How It Works */}
      <div className="px-4 md:px-6 pb-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { step: "1", title: "Browse & Analyze", desc: "Filter traders by return, risk metrics, strategy, and track record", icon: Search },
            { step: "2", title: "Set Allocation", desc: "Define your copy amount, risk limits, and max drawdown per trader", icon: Shield },
            { step: "3", title: "Auto-Execute", desc: "Trades mirror proportionally in paper mode with your custom SL/TP", icon: Zap },
          ].map((item) => (
            <div key={item.step} className="flex items-start gap-3 p-4 rounded-xl bg-[#0a0a0a] border border-[#1a1a1a]">
              <div className="w-8 h-8 rounded-full bg-amber-500/10 text-amber-400 flex items-center justify-center text-xs font-bold flex-shrink-0">
                {item.step}
              </div>
              <div>
                <h3 className="font-semibold text-sm">{item.title}</h3>
                <p className="text-xs text-gray-600 mt-1">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
