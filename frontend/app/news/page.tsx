"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import { useRouter } from "next/navigation";
import {
  Newspaper,
  TrendingUp,
  TrendingDown,
  Minus,
  Search,
  Zap,
  Clock,
  Filter,
  BarChart3,
  ArrowUpRight,
  RefreshCw,
  ChevronRight,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Sentiment = "Bullish" | "Bearish" | "Neutral";
type Category =
  | "Market News"
  | "Earnings"
  | "M&A"
  | "Fed/Macro"
  | "Crypto"
  | "Sector Rotation";

interface NewsItem {
  id: string;
  headline: string;
  source: string;
  timestamp: Date;
  tickers: string[];
  sentiment: Sentiment;
  sentimentScore: number; // -1 to 1
  category: Category;
  breaking: boolean;
}

// ---------------------------------------------------------------------------
// Sentiment config
// ---------------------------------------------------------------------------
const SENTIMENT_COLOR: Record<Sentiment, string> = {
  Bullish: "#22c55e",
  Bearish: "#e05252",
  Neutral: "#888888",
};

const SENTIMENT_ICON: Record<Sentiment, typeof TrendingUp> = {
  Bullish: TrendingUp,
  Bearish: TrendingDown,
  Neutral: Minus,
};

const CATEGORIES: Category[] = [
  "Market News",
  "Earnings",
  "M&A",
  "Fed/Macro",
  "Crypto",
  "Sector Rotation",
];

// ---------------------------------------------------------------------------
// Mock data — 45 realistic financial headlines
// ---------------------------------------------------------------------------
const MOCK_HEADLINES: Omit<NewsItem, "id" | "timestamp" | "breaking">[] = [
  { headline: "S&P 500 rallies to fresh all-time high on strong jobs data", source: "Reuters", tickers: ["SPY", "SPX"], sentiment: "Bullish", sentimentScore: 0.82, category: "Market News" },
  { headline: "Fed holds rates steady, signals potential cut in September", source: "Bloomberg", tickers: ["TLT", "SPY"], sentiment: "Bullish", sentimentScore: 0.75, category: "Fed/Macro" },
  { headline: "NVIDIA beats Q4 estimates, data center revenue surges 409%", source: "CNBC", tickers: ["NVDA", "SMH"], sentiment: "Bullish", sentimentScore: 0.95, category: "Earnings" },
  { headline: "Tesla recalls 2.2 million vehicles over warning light issue", source: "WSJ", tickers: ["TSLA"], sentiment: "Bearish", sentimentScore: -0.68, category: "Market News" },
  { headline: "Bitcoin breaks above $100K for first time, ETF inflows surge", source: "CoinDesk", tickers: ["BTC", "IBIT", "COIN"], sentiment: "Bullish", sentimentScore: 0.91, category: "Crypto" },
  { headline: "Apple acquires AI startup for $2B to bolster Siri capabilities", source: "Bloomberg", tickers: ["AAPL"], sentiment: "Bullish", sentimentScore: 0.63, category: "M&A" },
  { headline: "Regional bank index drops 4% amid renewed deposit concerns", source: "Reuters", tickers: ["KRE", "PACW", "WAL"], sentiment: "Bearish", sentimentScore: -0.77, category: "Sector Rotation" },
  { headline: "Amazon Web Services announces 30% price cuts for GPU instances", source: "TechCrunch", tickers: ["AMZN", "MSFT", "GOOG"], sentiment: "Neutral", sentimentScore: 0.12, category: "Market News" },
  { headline: "Oil prices tumble 5% as OPEC+ signals production increase", source: "Reuters", tickers: ["USO", "XOM", "CVX"], sentiment: "Bearish", sentimentScore: -0.71, category: "Market News" },
  { headline: "Microsoft Azure revenue growth accelerates to 31% YoY", source: "CNBC", tickers: ["MSFT"], sentiment: "Bullish", sentimentScore: 0.78, category: "Earnings" },
  { headline: "China PMI contracts for third straight month, stimulus expected", source: "Bloomberg", tickers: ["FXI", "EEM", "BABA"], sentiment: "Bearish", sentimentScore: -0.55, category: "Fed/Macro" },
  { headline: "Broadcom surges 12% after announcing 10-for-1 stock split", source: "MarketWatch", tickers: ["AVGO"], sentiment: "Bullish", sentimentScore: 0.84, category: "Market News" },
  { headline: "Ethereum ETF applications under SEC review, decision pending", source: "CoinDesk", tickers: ["ETH", "ETHA"], sentiment: "Neutral", sentimentScore: 0.22, category: "Crypto" },
  { headline: "JPMorgan raises S&P 500 year-end target to 5,800", source: "Bloomberg", tickers: ["SPY", "JPM"], sentiment: "Bullish", sentimentScore: 0.67, category: "Market News" },
  { headline: "Boeing faces new quality probe after mid-flight door incident", source: "WSJ", tickers: ["BA"], sentiment: "Bearish", sentimentScore: -0.82, category: "Market News" },
  { headline: "Palantir wins $480M Army contract for AI battlefield systems", source: "Reuters", tickers: ["PLTR"], sentiment: "Bullish", sentimentScore: 0.72, category: "Market News" },
  { headline: "CPI comes in hot at 3.5%, rate cut expectations pushed back", source: "CNBC", tickers: ["TLT", "SPY", "QQQ"], sentiment: "Bearish", sentimentScore: -0.65, category: "Fed/Macro" },
  { headline: "Meta reports record ad revenue, user growth beats estimates", source: "Bloomberg", tickers: ["META"], sentiment: "Bullish", sentimentScore: 0.88, category: "Earnings" },
  { headline: "Pfizer cuts full-year guidance amid slowing vaccine demand", source: "Reuters", tickers: ["PFE", "XBI"], sentiment: "Bearish", sentimentScore: -0.58, category: "Earnings" },
  { headline: "Gold surges to $2,800 as geopolitical tensions escalate", source: "Bloomberg", tickers: ["GLD", "GDX", "NEM"], sentiment: "Bullish", sentimentScore: 0.61, category: "Market News" },
  { headline: "Uber and Lyft rally on California gig worker ruling victory", source: "CNBC", tickers: ["UBER", "LYFT"], sentiment: "Bullish", sentimentScore: 0.69, category: "Market News" },
  { headline: "Dollar index hits 6-month low on dovish Fed commentary", source: "Reuters", tickers: ["UUP", "EEM", "GLD"], sentiment: "Neutral", sentimentScore: -0.15, category: "Fed/Macro" },
  { headline: "Costco misses same-store sales estimates for first time in 8 quarters", source: "WSJ", tickers: ["COST"], sentiment: "Bearish", sentimentScore: -0.52, category: "Earnings" },
  { headline: "Semiconductor sector rotates higher, SOX index up 3.2%", source: "MarketWatch", tickers: ["SMH", "NVDA", "AMD", "INTC"], sentiment: "Bullish", sentimentScore: 0.74, category: "Sector Rotation" },
  { headline: "Rivian secures $5B Volkswagen investment for joint EV platform", source: "Bloomberg", tickers: ["RIVN", "VWAGY"], sentiment: "Bullish", sentimentScore: 0.79, category: "M&A" },
  { headline: "Treasury yields invert further, 2s10s spread hits -45bps", source: "Reuters", tickers: ["TLT", "SHY"], sentiment: "Bearish", sentimentScore: -0.61, category: "Fed/Macro" },
  { headline: "Solana network processes 65K TPS, surpasses Visa throughput", source: "CoinDesk", tickers: ["SOL"], sentiment: "Bullish", sentimentScore: 0.66, category: "Crypto" },
  { headline: "Disney+ subscriber growth stalls, streaming losses widen", source: "CNBC", tickers: ["DIS"], sentiment: "Bearish", sentimentScore: -0.59, category: "Earnings" },
  { headline: "AMD unveils MI400 AI chip to challenge NVIDIA dominance", source: "TechCrunch", tickers: ["AMD", "NVDA"], sentiment: "Neutral", sentimentScore: 0.31, category: "Market News" },
  { headline: "European Central Bank cuts rates by 25bps, euro weakens", source: "Bloomberg", tickers: ["FXE", "EWG", "VGK"], sentiment: "Neutral", sentimentScore: -0.08, category: "Fed/Macro" },
  { headline: "Eli Lilly weight-loss drug shows 25% body mass reduction in trials", source: "Reuters", tickers: ["LLY", "NVO"], sentiment: "Bullish", sentimentScore: 0.87, category: "Market News" },
  { headline: "Commercial real estate defaults surge to 2008 levels", source: "WSJ", tickers: ["VNQ", "XLRE", "SPG"], sentiment: "Bearish", sentimentScore: -0.73, category: "Sector Rotation" },
  { headline: "Alphabet announces $70B buyback, largest in tech history", source: "Bloomberg", tickers: ["GOOG", "GOOGL"], sentiment: "Bullish", sentimentScore: 0.81, category: "Market News" },
  { headline: "Natural gas spikes 18% on unexpected cold weather forecast", source: "Reuters", tickers: ["UNG", "AR", "EQT"], sentiment: "Bullish", sentimentScore: 0.55, category: "Market News" },
  { headline: "Stripe confidentially files S-1 for anticipated IPO", source: "Bloomberg", tickers: [], sentiment: "Neutral", sentimentScore: 0.35, category: "Market News" },
  { headline: "VIX surges above 25 as Middle East tensions escalate", source: "CNBC", tickers: ["VIX", "UVXY", "SPY"], sentiment: "Bearish", sentimentScore: -0.69, category: "Market News" },
  { headline: "Cathie Wood's ARKK buys $200M in Tesla on dip below $150", source: "MarketWatch", tickers: ["TSLA", "ARKK"], sentiment: "Neutral", sentimentScore: 0.18, category: "Market News" },
  { headline: "Reddit IPO prices above range at $34, valued at $8B", source: "WSJ", tickers: ["RDDT"], sentiment: "Bullish", sentimentScore: 0.58, category: "Market News" },
  { headline: "Micron Technology guides above consensus on AI memory demand", source: "Bloomberg", tickers: ["MU", "SMH"], sentiment: "Bullish", sentimentScore: 0.76, category: "Earnings" },
  { headline: "XRP surges 40% after favorable Ripple court ruling", source: "CoinDesk", tickers: ["XRP"], sentiment: "Bullish", sentimentScore: 0.83, category: "Crypto" },
  { headline: "UnitedHealth drops 8% after DOJ opens Medicare fraud probe", source: "Reuters", tickers: ["UNH", "XLV"], sentiment: "Bearish", sentimentScore: -0.84, category: "Market News" },
  { headline: "Snowflake acquires Neeva AI for $1.5B to enhance data analytics", source: "TechCrunch", tickers: ["SNOW"], sentiment: "Bullish", sentimentScore: 0.54, category: "M&A" },
  { headline: "Japanese yen hits 160 vs dollar, intervention speculation rises", source: "Bloomberg", tickers: ["FXY", "EWJ"], sentiment: "Bearish", sentimentScore: -0.42, category: "Fed/Macro" },
  { headline: "Retail sector underperforms as consumer confidence drops to 14-month low", source: "CNBC", tickers: ["XRT", "WMT", "TGT"], sentiment: "Bearish", sentimentScore: -0.56, category: "Sector Rotation" },
  { headline: "CrowdStrike raises guidance after record net-new ARR quarter", source: "Bloomberg", tickers: ["CRWD", "HACK"], sentiment: "Bullish", sentimentScore: 0.71, category: "Earnings" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function generateId(): string {
  return Math.random().toString(36).substring(2, 10);
}

function minutesAgo(n: number): Date {
  return new Date(Date.now() - n * 60_000);
}

function formatTimestamp(date: Date): string {
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHrs = Math.floor(diffMin / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function buildInitialFeed(): NewsItem[] {
  return MOCK_HEADLINES.map((item, i) => ({
    ...item,
    id: generateId(),
    timestamp: minutesAgo(i * 3 + Math.floor(Math.random() * 5)),
    breaking: i < 3,
  }));
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------

function SentimentDistributionBar({
  items,
}: {
  items: NewsItem[];
}) {
  const total = items.length || 1;
  const bullish = items.filter((n) => n.sentiment === "Bullish").length;
  const bearish = items.filter((n) => n.sentiment === "Bearish").length;
  const neutral = items.filter((n) => n.sentiment === "Neutral").length;
  const bPct = Math.round((bullish / total) * 100);
  const bearPct = Math.round((bearish / total) * 100);
  const nPct = 100 - bPct - bearPct;

  return (
    <Card className="mb-6">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <BarChart3 size={16} className="text-text-secondary" />
          <span className="text-sm font-semibold text-text-primary">
            Sentiment Distribution
          </span>
        </div>
        <span className="text-xs text-text-tertiary font-mono">
          {items.length} headlines today
        </span>
      </div>

      {/* Bar */}
      <div className="flex h-4 rounded-full overflow-hidden bg-[#1a1a1a]">
        {bPct > 0 && (
          <div
            className="h-full transition-all duration-700"
            style={{ width: `${bPct}%`, backgroundColor: "#22c55e" }}
          />
        )}
        {nPct > 0 && (
          <div
            className="h-full transition-all duration-700"
            style={{ width: `${nPct}%`, backgroundColor: "#888888" }}
          />
        )}
        {bearPct > 0 && (
          <div
            className="h-full transition-all duration-700"
            style={{ width: `${bearPct}%`, backgroundColor: "#e05252" }}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 mt-3">
        {[
          { label: "Bullish", count: bullish, pct: bPct, color: "#22c55e" },
          { label: "Neutral", count: neutral, pct: nPct, color: "#888888" },
          { label: "Bearish", count: bearish, pct: bearPct, color: "#e05252" },
        ].map((s) => (
          <div key={s.label} className="flex items-center gap-2">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="text-xs text-text-secondary">
              {s.label}{" "}
              <span className="font-mono font-bold" style={{ color: s.color }}>
                {s.pct}%
              </span>{" "}
              <span className="text-text-tertiary">({s.count})</span>
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  const Icon = SENTIMENT_ICON[sentiment];
  const color = SENTIMENT_COLOR[sentiment];
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold"
      style={{
        color,
        backgroundColor: `${color}15`,
        border: `1px solid ${color}30`,
      }}
    >
      <Icon size={12} />
      {sentiment}
    </span>
  );
}

function BreakingBadge() {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold text-red-400 bg-red-500/10 border border-red-500/20 animate-pulse">
      <Zap size={11} />
      BREAKING
    </span>
  );
}

function NewsItemRow({
  item,
  onTickerClick,
}: {
  item: NewsItem;
  onTickerClick: (ticker: string) => void;
}) {
  const borderColor = SENTIMENT_COLOR[item.sentiment];
  const router = useRouter();

  return (
    <div
      className="group flex items-start gap-4 px-4 py-3 rounded-lg transition-all duration-200 hover:bg-[#111111]"
      style={{ borderLeft: `3px solid ${borderColor}` }}
    >
      {/* Timestamp */}
      <div className="flex-shrink-0 w-16 pt-0.5">
        <span className="text-text-tertiary text-xs font-mono">
          {formatTimestamp(item.timestamp)}
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          {item.breaking && <BreakingBadge />}
          <SentimentBadge sentiment={item.sentiment} />
          <span className="text-xs text-text-tertiary px-1.5 py-0.5 rounded bg-[#1a1a1a]">
            {item.category}
          </span>
        </div>

        <p className="text-sm text-text-primary leading-snug mb-1.5 group-hover:text-white transition-colors">
          {item.headline}
        </p>

        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-text-secondary text-xs">{item.source}</span>
          {item.tickers.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              {item.tickers.map((ticker) => (
                <button
                  key={ticker}
                  onClick={() => {
                    onTickerClick(ticker);
                    router.push(`/trade?symbol=${ticker}`);
                  }}
                  className="inline-flex items-center gap-0.5 bg-blue-500/10 text-blue-400 rounded px-2 py-0.5 text-xs font-mono hover:bg-blue-500/20 transition-colors cursor-pointer"
                >
                  {ticker}
                  <ArrowUpRight size={10} />
                </button>
              ))}
            </div>
          )}
          <span className="text-text-tertiary text-xs font-mono ml-auto">
            Score: {item.sentimentScore > 0 ? "+" : ""}
            {item.sentimentScore.toFixed(2)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function NewsPage() {
  const [feed, setFeed] = useState<NewsItem[]>([]);
  const [sentimentFilter, setSentimentFilter] = useState<
    "All" | Sentiment
  >("All");
  const [categoryFilter, setCategoryFilter] = useState<"All" | Category>(
    "All"
  );
  const [tickerSearch, setTickerSearch] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const [newCount, setNewCount] = useState(0);
  const feedRef = useRef<HTMLDivElement>(null);
  const headlineIndexRef = useRef(0);

  // Initialize feed
  useEffect(() => {
    setFeed(buildInitialFeed());
  }, []);

  // Auto-add new headlines every 5-8 seconds
  useEffect(() => {
    if (!autoScroll) return;

    const interval = setInterval(
      () => {
        setFeed((prev) => {
          const idx = headlineIndexRef.current % MOCK_HEADLINES.length;
          headlineIndexRef.current += 1;
          const base = MOCK_HEADLINES[idx];
          const newItem: NewsItem = {
            ...base,
            id: generateId(),
            timestamp: new Date(),
            breaking: true,
          };
          // Unmark old breaking items
          const updated = prev.map((item) =>
            item.breaking ? { ...item, breaking: false } : item
          );
          return [newItem, ...updated];
        });
        setNewCount((c) => c + 1);
      },
      5000 + Math.random() * 3000
    );

    return () => clearInterval(interval);
  }, [autoScroll]);

  // Reset new count on interaction
  useEffect(() => {
    if (newCount > 0) {
      const timeout = setTimeout(() => setNewCount(0), 3000);
      return () => clearTimeout(timeout);
    }
  }, [newCount]);

  // Filter logic
  const filtered = useMemo(() => {
    let items = feed;
    if (sentimentFilter !== "All") {
      items = items.filter((n) => n.sentiment === sentimentFilter);
    }
    if (categoryFilter !== "All") {
      items = items.filter((n) => n.category === categoryFilter);
    }
    if (tickerSearch.trim()) {
      const q = tickerSearch.trim().toUpperCase();
      items = items.filter((n) =>
        n.tickers.some((t) => t.includes(q))
      );
    }
    return items;
  }, [feed, sentimentFilter, categoryFilter, tickerSearch]);

  const handleTickerClick = (ticker: string) => {
    // Could also set search filter, but navigation is primary
  };

  return (
    <div className="min-h-screen p-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
            <Newspaper size={20} className="text-blue-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-text-primary">
              Market News Feed
            </h1>
            <p className="text-xs text-text-tertiary">
              Real-time headlines with AI sentiment scoring
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {newCount > 0 && (
            <span className="text-xs font-mono text-blue-400 bg-blue-500/10 px-2.5 py-1 rounded animate-pulse">
              +{newCount} new
            </span>
          )}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border transition-colors ${
              autoScroll
                ? "border-green-500/30 text-green-400 bg-green-500/10"
                : "border-[#1a1a1a] text-text-tertiary bg-[#0d0d0d]"
            }`}
          >
            <RefreshCw
              size={12}
              className={autoScroll ? "animate-spin" : ""}
              style={autoScroll ? { animationDuration: "3s" } : {}}
            />
            {autoScroll ? "Live" : "Paused"}
          </button>
        </div>
      </div>

      {/* Sentiment distribution */}
      <SentimentDistributionBar items={feed} />

      {/* Filters */}
      <Card className="mb-4" padding="sm">
        <div className="flex flex-col gap-3">
          {/* Row 1: Sentiment filter + ticker search */}
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5">
              <Filter size={14} className="text-text-tertiary" />
              <span className="text-xs text-text-secondary font-medium">
                Sentiment:
              </span>
            </div>
            {(["All", "Bullish", "Bearish", "Neutral"] as const).map((s) => {
              const active = sentimentFilter === s;
              const color =
                s === "All" ? "#3b82f6" : SENTIMENT_COLOR[s as Sentiment];
              return (
                <button
                  key={s}
                  onClick={() =>
                    setSentimentFilter(s === "All" ? "All" : (s as Sentiment))
                  }
                  className="text-xs px-2.5 py-1 rounded border transition-all"
                  style={{
                    borderColor: active ? `${color}50` : "#1a1a1a",
                    backgroundColor: active ? `${color}15` : "transparent",
                    color: active ? color : "#888",
                  }}
                >
                  {s}
                </button>
              );
            })}

            <div className="ml-auto relative">
              <Search
                size={14}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary"
              />
              <input
                type="text"
                placeholder="Search ticker..."
                value={tickerSearch}
                onChange={(e) => setTickerSearch(e.target.value)}
                className="bg-[#0d0d0d] border border-[#1a1a1a] rounded px-3 py-1.5 pl-8 text-xs text-text-primary placeholder-text-tertiary w-40 focus:outline-none focus:border-blue-500/50 transition-colors font-mono"
              />
            </div>
          </div>

          {/* Row 2: Category tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto">
            <span className="text-xs text-text-secondary font-medium mr-1">
              Category:
            </span>
            {(["All", ...CATEGORIES] as const).map((cat) => {
              const active = categoryFilter === cat;
              return (
                <button
                  key={cat}
                  onClick={() =>
                    setCategoryFilter(
                      cat === "All" ? "All" : (cat as Category)
                    )
                  }
                  className={`text-xs px-2.5 py-1 rounded whitespace-nowrap transition-all ${
                    active
                      ? "bg-blue-500/15 text-blue-400 border border-blue-500/30"
                      : "text-text-tertiary hover:text-text-secondary border border-transparent hover:border-[#1a1a1a]"
                  }`}
                >
                  {cat}
                </button>
              );
            })}
          </div>
        </div>
      </Card>

      {/* Feed count */}
      <div className="flex items-center justify-between mb-3 px-1">
        <span className="text-xs text-text-tertiary">
          Showing {filtered.length} of {feed.length} headlines
        </span>
        <div className="flex items-center gap-1 text-text-tertiary">
          <Clock size={12} />
          <span className="text-xs font-mono">
            {new Date().toLocaleTimeString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
              hour12: true,
            })}
          </span>
        </div>
      </div>

      {/* News feed */}
      <Card padding="none" className="overflow-hidden">
        <div ref={feedRef} className="divide-y divide-[#1a1a1a]">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-text-tertiary">
              <Search size={32} className="mb-3 opacity-40" />
              <p className="text-sm">No headlines match your filters</p>
              <p className="text-xs mt-1">
                Try adjusting sentiment, category, or ticker search
              </p>
            </div>
          ) : (
            filtered.map((item) => (
              <NewsItemRow
                key={item.id}
                item={item}
                onTickerClick={handleTickerClick}
              />
            ))
          )}
        </div>
      </Card>

      {/* Footer */}
      <div className="flex items-center justify-center mt-4 gap-2 text-text-tertiary">
        <ChevronRight size={12} />
        <span className="text-xs">
          Powered by Lumare AI Sentiment Engine
        </span>
      </div>
    </div>
  );
}
