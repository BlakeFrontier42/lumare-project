"use client";

import { useState, useMemo, useCallback, useEffect } from "react";
import { Card } from "@/components/ui/Card";
import {
  LayoutGrid,
  Search,
  X,
  TrendingUp,
  TrendingDown,
  BarChart3,
  Volume2,
  Calendar,
  DollarSign,
  Activity,
  Layers,
} from "lucide-react";

/* ─── types ─── */
interface Stock {
  ticker: string;
  name: string;
  sector: string;
  marketCap: number; // billions
  price: number;
  dailyChange: number;
  weeklyChange: number;
  monthlyChange: number;
  ytdChange: number;
  volume: number; // millions
  high52w: number;
  low52w: number;
}

type TimeFrame = "daily" | "weekly" | "monthly" | "ytd";
type ViewMode = "sector" | "marketcap";

/* ─── mock data generator ─── */
function generateStocks(): Stock[] {
  const sectors: Record<string, { ticker: string; name: string; cap: number; price: number }[]> = {
    Technology: [
      { ticker: "AAPL", name: "Apple Inc.", cap: 3420, price: 234.56 },
      { ticker: "MSFT", name: "Microsoft Corp.", cap: 3180, price: 468.12 },
      { ticker: "NVDA", name: "NVIDIA Corp.", cap: 2890, price: 142.33 },
      { ticker: "GOOGL", name: "Alphabet Inc.", cap: 2150, price: 178.45 },
      { ticker: "META", name: "Meta Platforms", cap: 1580, price: 612.78 },
      { ticker: "AVGO", name: "Broadcom Inc.", cap: 820, price: 186.92 },
      { ticker: "ADBE", name: "Adobe Inc.", cap: 248, price: 542.18 },
      { ticker: "CRM", name: "Salesforce Inc.", cap: 272, price: 278.45 },
      { ticker: "AMD", name: "AMD Inc.", cap: 268, price: 165.89 },
      { ticker: "INTC", name: "Intel Corp.", cap: 112, price: 26.34 },
    ],
    Healthcare: [
      { ticker: "UNH", name: "UnitedHealth Group", cap: 548, price: 592.34 },
      { ticker: "JNJ", name: "Johnson & Johnson", cap: 398, price: 164.89 },
      { ticker: "LLY", name: "Eli Lilly & Co.", cap: 842, price: 892.45 },
      { ticker: "PFE", name: "Pfizer Inc.", cap: 156, price: 27.56 },
      { ticker: "ABBV", name: "AbbVie Inc.", cap: 312, price: 176.23 },
      { ticker: "MRK", name: "Merck & Co.", cap: 298, price: 118.67 },
      { ticker: "TMO", name: "Thermo Fisher", cap: 218, price: 568.12 },
      { ticker: "ABT", name: "Abbott Labs", cap: 198, price: 114.56 },
    ],
    Finance: [
      { ticker: "BRK.B", name: "Berkshire Hathaway", cap: 892, price: 456.78 },
      { ticker: "JPM", name: "JPMorgan Chase", cap: 628, price: 218.34 },
      { ticker: "V", name: "Visa Inc.", cap: 578, price: 298.56 },
      { ticker: "MA", name: "Mastercard Inc.", cap: 428, price: 468.23 },
      { ticker: "BAC", name: "Bank of America", cap: 312, price: 39.45 },
      { ticker: "GS", name: "Goldman Sachs", cap: 168, price: 486.78 },
      { ticker: "MS", name: "Morgan Stanley", cap: 158, price: 98.34 },
      { ticker: "BLK", name: "BlackRock Inc.", cap: 142, price: 928.45 },
    ],
    Energy: [
      { ticker: "XOM", name: "Exxon Mobil", cap: 468, price: 108.23 },
      { ticker: "CVX", name: "Chevron Corp.", cap: 298, price: 158.67 },
      { ticker: "COP", name: "ConocoPhillips", cap: 142, price: 112.34 },
      { ticker: "SLB", name: "Schlumberger", cap: 78, price: 54.12 },
      { ticker: "EOG", name: "EOG Resources", cap: 72, price: 124.56 },
      { ticker: "MPC", name: "Marathon Petroleum", cap: 62, price: 168.23 },
    ],
    Consumer: [
      { ticker: "AMZN", name: "Amazon.com Inc.", cap: 2120, price: 198.45 },
      { ticker: "TSLA", name: "Tesla Inc.", cap: 812, price: 254.67 },
      { ticker: "WMT", name: "Walmart Inc.", cap: 578, price: 172.34 },
      { ticker: "HD", name: "Home Depot", cap: 378, price: 378.12 },
      { ticker: "PG", name: "Procter & Gamble", cap: 368, price: 158.45 },
      { ticker: "COST", name: "Costco Wholesale", cap: 358, price: 812.34 },
      { ticker: "KO", name: "Coca-Cola Co.", cap: 268, price: 62.12 },
      { ticker: "NKE", name: "Nike Inc.", cap: 148, price: 96.78 },
    ],
    Industrials: [
      { ticker: "GE", name: "GE Aerospace", cap: 198, price: 182.34 },
      { ticker: "CAT", name: "Caterpillar Inc.", cap: 178, price: 368.12 },
      { ticker: "RTX", name: "RTX Corp.", cap: 158, price: 118.45 },
      { ticker: "UNP", name: "Union Pacific", cap: 148, price: 242.67 },
      { ticker: "HON", name: "Honeywell Intl.", cap: 138, price: 212.34 },
      { ticker: "BA", name: "Boeing Co.", cap: 128, price: 178.56 },
      { ticker: "DE", name: "Deere & Co.", cap: 118, price: 412.78 },
    ],
    Communications: [
      { ticker: "NFLX", name: "Netflix Inc.", cap: 378, price: 878.45 },
      { ticker: "DIS", name: "Walt Disney Co.", cap: 198, price: 108.34 },
      { ticker: "CMCSA", name: "Comcast Corp.", cap: 168, price: 42.56 },
      { ticker: "TMUS", name: "T-Mobile US", cap: 248, price: 212.34 },
      { ticker: "VZ", name: "Verizon Comm.", cap: 172, price: 42.12 },
      { ticker: "ATVI", name: "Activision Bliz.", cap: 78, price: 94.56 },
    ],
    Utilities: [
      { ticker: "NEE", name: "NextEra Energy", cap: 158, price: 78.34 },
      { ticker: "SO", name: "Southern Co.", cap: 92, price: 84.56 },
      { ticker: "DUK", name: "Duke Energy", cap: 88, price: 112.34 },
      { ticker: "AEP", name: "American Electric", cap: 52, price: 98.67 },
      { ticker: "D", name: "Dominion Energy", cap: 48, price: 56.78 },
      { ticker: "EXC", name: "Exelon Corp.", cap: 44, price: 42.12 },
    ],
    "Real Estate": [
      { ticker: "PLD", name: "Prologis Inc.", cap: 118, price: 128.45 },
      { ticker: "AMT", name: "American Tower", cap: 98, price: 212.34 },
      { ticker: "EQIX", name: "Equinix Inc.", cap: 82, price: 842.12 },
      { ticker: "CCI", name: "Crown Castle", cap: 48, price: 112.56 },
      { ticker: "SPG", name: "Simon Property", cap: 52, price: 156.78 },
      { ticker: "O", name: "Realty Income", cap: 48, price: 58.34 },
    ],
    Materials: [
      { ticker: "LIN", name: "Linde PLC", cap: 218, price: 468.12 },
      { ticker: "APD", name: "Air Products", cap: 68, price: 298.45 },
      { ticker: "SHW", name: "Sherwin-Williams", cap: 88, price: 348.56 },
      { ticker: "FCX", name: "Freeport-McMoRan", cap: 62, price: 42.34 },
      { ticker: "NEM", name: "Newmont Corp.", cap: 52, price: 42.78 },
      { ticker: "ECL", name: "Ecolab Inc.", cap: 58, price: 232.12 },
    ],
  };

  const stocks: Stock[] = [];
  Object.entries(sectors).forEach(([sector, items]) => {
    items.forEach((s, i) => {
      const seed = hashCode(s.ticker);
      const daily = seededChange(seed, 0, 6.5);
      const weekly = seededChange(seed, 1, 12);
      const monthly = seededChange(seed, 2, 20);
      const ytd = seededChange(seed, 3, 35);
      stocks.push({
        ticker: s.ticker,
        name: s.name,
        sector,
        marketCap: s.cap,
        price: s.price,
        dailyChange: daily,
        weeklyChange: weekly,
        monthlyChange: monthly,
        ytdChange: ytd,
        volume: Math.round(10 + Math.abs(seed % 200) + i * 3),
        high52w: s.price * (1 + Math.abs(ytd / 100) + 0.15),
        low52w: s.price * (1 - Math.abs(ytd / 100) * 0.6 - 0.08),
      });
    });
  });
  return stocks;
}

function hashCode(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  return h;
}

function seededChange(seed: number, offset: number, range: number): number {
  const t = Date.now() / 86400000;
  const v = Math.sin(seed * 0.001 + offset * 2.71 + t * 0.01) * range;
  const drift = Math.cos(seed * 0.0037 + offset * 1.41) * range * 0.4;
  return Math.round((v + drift) * 100) / 100;
}

/* ─── color helpers ─── */
function changeColor(pct: number): string {
  if (pct <= -5) return "rgb(220, 38, 38)";
  if (pct <= -3) return "rgb(239, 68, 68)";
  if (pct <= -1.5) return "rgb(249, 115, 22)";
  if (pct <= -0.3) return "rgb(156, 100, 72)";
  if (pct < 0.3) return "rgb(82, 82, 82)";
  if (pct < 1.5) return "rgb(72, 140, 88)";
  if (pct < 3) return "rgb(34, 197, 94)";
  if (pct < 5) return "rgb(22, 163, 74)";
  return "rgb(21, 128, 61)";
}

function changeBg(pct: number, alpha = 0.55): string {
  if (pct <= -5) return `rgba(220, 38, 38, ${alpha})`;
  if (pct <= -3) return `rgba(239, 68, 68, ${alpha * 0.85})`;
  if (pct <= -1.5) return `rgba(249, 115, 22, ${alpha * 0.65})`;
  if (pct <= -0.3) return `rgba(156, 100, 72, ${alpha * 0.4})`;
  if (pct < 0.3) return `rgba(82, 82, 82, ${alpha * 0.35})`;
  if (pct < 1.5) return `rgba(34, 197, 94, ${alpha * 0.45})`;
  if (pct < 3) return `rgba(34, 197, 94, ${alpha * 0.65})`;
  if (pct < 5) return `rgba(22, 163, 74, ${alpha * 0.8})`;
  return `rgba(21, 128, 61, ${alpha})`;
}

function changeTextClass(pct: number): string {
  if (pct < -0.3) return "text-loss";
  if (pct > 0.3) return "text-profit";
  return "text-text-secondary";
}

function formatCap(b: number): string {
  if (b >= 1000) return `$${(b / 1000).toFixed(1)}T`;
  return `$${b.toFixed(0)}B`;
}

function formatVol(m: number): string {
  return `${m.toFixed(1)}M`;
}

function formatPrice(p: number): string {
  return `$${p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/* ─── timeframe labels ─── */
const TF_LABELS: Record<TimeFrame, string> = {
  daily: "1D",
  weekly: "1W",
  monthly: "1M",
  ytd: "YTD",
};

const TF_FULL: Record<TimeFrame, string> = {
  daily: "Daily Change",
  weekly: "Weekly Change",
  monthly: "Monthly Change",
  ytd: "Year to Date",
};

/* ─── market cap tiers ─── */
const CAP_TIERS = [
  { label: "Mega Cap", min: 1000 },
  { label: "Large Cap", min: 200 },
  { label: "Mid Cap", min: 50 },
  { label: "Small Cap", min: 0 },
];

/* ─── component ─── */
export default function HeatmapPage() {
  const [timeframe, setTimeframe] = useState<TimeFrame>("daily");
  const [viewMode, setViewMode] = useState<ViewMode>("sector");
  const [search, setSearch] = useState("");
  const [selectedStock, setSelectedStock] = useState<Stock | null>(null);
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    setStocks(generateStocks());
  }, []);

  // Slight drift every 4s for realism
  useEffect(() => {
    const iv = setInterval(() => {
      setStocks(generateStocks());
      setTick((t) => t + 1);
    }, 4000);
    return () => clearInterval(iv);
  }, []);

  const getChange = useCallback(
    (s: Stock) => {
      switch (timeframe) {
        case "weekly": return s.weeklyChange;
        case "monthly": return s.monthlyChange;
        case "ytd": return s.ytdChange;
        default: return s.dailyChange;
      }
    },
    [timeframe]
  );

  const searchLower = search.toLowerCase();
  const highlighted = useCallback(
    (s: Stock) =>
      !search ||
      s.ticker.toLowerCase().includes(searchLower) ||
      s.name.toLowerCase().includes(searchLower),
    [search, searchLower]
  );

  /* group stocks */
  const grouped = useMemo(() => {
    if (viewMode === "sector") {
      const map = new Map<string, Stock[]>();
      stocks.forEach((s) => {
        if (!map.has(s.sector)) map.set(s.sector, []);
        map.get(s.sector)!.push(s);
      });
      // Sort sectors by total market cap
      return Array.from(map.entries())
        .map(([label, items]) => ({
          label,
          stocks: items.sort((a, b) => b.marketCap - a.marketCap),
          totalCap: items.reduce((sum, s) => sum + s.marketCap, 0),
        }))
        .sort((a, b) => b.totalCap - a.totalCap);
    } else {
      return CAP_TIERS.map((tier, i) => {
        const next = CAP_TIERS[i + 1];
        const items = stocks
          .filter((s) => s.marketCap >= tier.min && (!next || s.marketCap < (CAP_TIERS[i - 1]?.min ?? Infinity)))
          .sort((a, b) => b.marketCap - a.marketCap);
        // Simpler: just filter by tier boundaries
        return { label: tier.label, stocks: [] as Stock[], totalCap: 0 };
      });
    }
  }, [stocks, viewMode]);

  // Better market cap grouping
  const groupedFinal = useMemo(() => {
    if (viewMode === "sector") return grouped;
    const mega = stocks.filter((s) => s.marketCap >= 1000).sort((a, b) => b.marketCap - a.marketCap);
    const large = stocks.filter((s) => s.marketCap >= 200 && s.marketCap < 1000).sort((a, b) => b.marketCap - a.marketCap);
    const mid = stocks.filter((s) => s.marketCap >= 50 && s.marketCap < 200).sort((a, b) => b.marketCap - a.marketCap);
    const small = stocks.filter((s) => s.marketCap < 50).sort((a, b) => b.marketCap - a.marketCap);
    return [
      { label: "Mega Cap (>$1T)", stocks: mega, totalCap: mega.reduce((s, x) => s + x.marketCap, 0) },
      { label: "Large Cap ($200B-$1T)", stocks: large, totalCap: large.reduce((s, x) => s + x.marketCap, 0) },
      { label: "Mid Cap ($50B-$200B)", stocks: mid, totalCap: mid.reduce((s, x) => s + x.marketCap, 0) },
      { label: "Small Cap (<$50B)", stocks: small, totalCap: small.reduce((s, x) => s + x.marketCap, 0) },
    ].filter((g) => g.stocks.length > 0);
  }, [stocks, viewMode, grouped]);

  /* summary stats */
  const summary = useMemo(() => {
    const changes = stocks.map(getChange);
    const gainers = changes.filter((c) => c > 0).length;
    const losers = changes.filter((c) => c < 0).length;
    const avg = changes.reduce((s, c) => s + c, 0) / (changes.length || 1);
    return { gainers, losers, avg };
  }, [stocks, getChange]);

  return (
    <div className="min-h-screen bg-bg-primary p-4 md:p-6 lg:p-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <LayoutGrid className="w-7 h-7 text-text-secondary" />
          <h1 className="font-heading text-2xl font-bold text-text-primary">
            Market Heatmap
          </h1>
        </div>
        <p className="text-text-tertiary text-sm ml-10">
          Real-time sector performance across {stocks.length} equities
        </p>
      </div>

      {/* Controls Row */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        {/* Timeframe Selector */}
        <div className="flex bg-bg-card border border-border rounded-lg p-0.5">
          {(Object.keys(TF_LABELS) as TimeFrame[]).map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3 py-1.5 text-xs font-mono font-medium rounded-md transition-all duration-200 ${
                timeframe === tf
                  ? "bg-white/10 text-text-primary"
                  : "text-text-tertiary hover:text-text-secondary"
              }`}
            >
              {TF_LABELS[tf]}
            </button>
          ))}
        </div>

        {/* View Mode */}
        <div className="flex bg-bg-card border border-border rounded-lg p-0.5">
          <button
            onClick={() => setViewMode("sector")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
              viewMode === "sector"
                ? "bg-white/10 text-text-primary"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            Sector
          </button>
          <button
            onClick={() => setViewMode("marketcap")}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-200 ${
              viewMode === "marketcap"
                ? "bg-white/10 text-text-primary"
                : "text-text-tertiary hover:text-text-secondary"
            }`}
          >
            <BarChart3 className="w-3.5 h-3.5" />
            Market Cap
          </button>
        </div>

        {/* Search */}
        <div className="relative flex-1 min-w-[200px] max-w-xs ml-auto">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-tertiary" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search ticker or name..."
            className="w-full bg-bg-card border border-border rounded-lg pl-9 pr-8 py-2 text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-text-tertiary transition-colors"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-tertiary hover:text-text-secondary"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Summary Bar */}
      <Card className="mb-5 !py-3 !px-5">
        <div className="flex flex-wrap items-center gap-6 text-xs">
          <div className="flex items-center gap-2">
            <Activity className="w-3.5 h-3.5 text-text-tertiary" />
            <span className="text-text-secondary">{TF_FULL[timeframe]}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <TrendingUp className="w-3.5 h-3.5 text-profit" />
            <span className="text-profit font-mono font-medium">{summary.gainers}</span>
            <span className="text-text-tertiary">gainers</span>
          </div>
          <div className="flex items-center gap-1.5">
            <TrendingDown className="w-3.5 h-3.5 text-loss" />
            <span className="text-loss font-mono font-medium">{summary.losers}</span>
            <span className="text-text-tertiary">losers</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="text-text-tertiary">Avg:</span>
            <span className={`font-mono font-medium ${changeTextClass(summary.avg)}`}>
              {summary.avg >= 0 ? "+" : ""}
              {summary.avg.toFixed(2)}%
            </span>
          </div>
          {/* Color Legend */}
          <div className="flex items-center gap-1 ml-auto">
            <span className="text-text-tertiary text-[10px] mr-1">-5%</span>
            {[-5, -3, -1.5, 0, 1.5, 3, 5].map((v) => (
              <div
                key={v}
                className="w-5 h-2.5 rounded-sm"
                style={{ backgroundColor: changeBg(v, 0.85) }}
              />
            ))}
            <span className="text-text-tertiary text-[10px] ml-1">+5%</span>
          </div>
        </div>
      </Card>

      {/* Heatmap Grid */}
      <div className="space-y-4">
        {groupedFinal.map((group) => (
          <Card key={group.label} padding="none" className="overflow-hidden">
            {/* Sector/Group Header */}
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-heading font-semibold text-text-primary">
                  {group.label}
                </h2>
                <span className="text-[10px] text-text-tertiary font-mono">
                  {group.stocks.length} stocks
                </span>
              </div>
              <span className="text-[10px] text-text-tertiary font-mono">
                {formatCap(group.totalCap)} total
              </span>
            </div>

            {/* Treemap Tiles */}
            <div className="p-2">
              <div
                className="grid gap-1"
                style={{
                  gridTemplateColumns: `repeat(auto-fill, minmax(${
                    group.stocks.length > 6 ? "100px" : "130px"
                  }, 1fr))`,
                }}
              >
                {group.stocks.map((stock) => {
                  const change = getChange(stock);
                  const isHighlighted = highlighted(stock);
                  const sizeClass = stock.marketCap >= 1000
                    ? "min-h-[100px]"
                    : stock.marketCap >= 200
                    ? "min-h-[80px]"
                    : "min-h-[64px]";

                  return (
                    <button
                      key={stock.ticker}
                      onClick={() => setSelectedStock(stock)}
                      className={`
                        relative group rounded-lg p-2.5 text-left transition-all duration-300 ease-out
                        border border-transparent
                        hover:border-white/20 hover:scale-[1.03] hover:z-10 hover:shadow-lg hover:shadow-black/40
                        active:scale-[0.98]
                        ${sizeClass}
                        ${!isHighlighted && search ? "opacity-20" : "opacity-100"}
                      `}
                      style={{
                        backgroundColor: changeBg(change, 0.45),
                        gridColumn:
                          stock.marketCap >= 2000
                            ? "span 2"
                            : stock.marketCap >= 800
                            ? "span 2"
                            : undefined,
                      }}
                    >
                      {/* Hover Glow */}
                      <div
                        className="absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                        style={{
                          background: `radial-gradient(ellipse at center, ${changeBg(change, 0.2)}, transparent 70%)`,
                        }}
                      />

                      {/* Content */}
                      <div className="relative z-10 flex flex-col h-full justify-between">
                        <div>
                          <div className="font-heading font-bold text-text-primary text-sm leading-tight tracking-wide">
                            {stock.ticker}
                          </div>
                          {stock.marketCap >= 200 && (
                            <div className="text-[10px] text-white/40 mt-0.5 truncate">
                              {stock.name}
                            </div>
                          )}
                        </div>
                        <div className="mt-auto">
                          <div className="font-mono text-xs font-semibold" style={{ color: changeColor(change) }}>
                            {change >= 0 ? "+" : ""}
                            {change.toFixed(2)}%
                          </div>
                          {stock.marketCap >= 200 && (
                            <div className="font-mono text-[10px] text-white/35">
                              {formatPrice(stock.price)}
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Detail Popup Modal */}
      {selectedStock && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedStock(null)}
        >
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />

          {/* Modal */}
          <Card
            className="relative z-10 w-full max-w-md !bg-bg-card border-border"
            padding="none"
            onClick={() => {}}
          >
            <div onClick={(e) => e.stopPropagation()}>
              {/* Modal Header */}
              <div
                className="px-5 py-4 border-b border-border"
                style={{ backgroundColor: changeBg(getChange(selectedStock), 0.15) }}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-heading text-lg font-bold text-text-primary">
                        {selectedStock.ticker}
                      </h3>
                      <span
                        className="text-xs font-mono font-semibold px-2 py-0.5 rounded-full"
                        style={{
                          backgroundColor: changeBg(getChange(selectedStock), 0.3),
                          color: changeColor(getChange(selectedStock)),
                        }}
                      >
                        {getChange(selectedStock) >= 0 ? "+" : ""}
                        {getChange(selectedStock).toFixed(2)}%
                      </span>
                    </div>
                    <p className="text-text-secondary text-sm mt-0.5">{selectedStock.name}</p>
                    <p className="text-text-tertiary text-xs mt-0.5">{selectedStock.sector}</p>
                  </div>
                  <button
                    onClick={() => setSelectedStock(null)}
                    className="text-text-tertiary hover:text-text-primary transition-colors p-1"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="p-5 space-y-4">
                {/* Price */}
                <div className="text-center">
                  <div className="font-mono text-3xl font-bold text-text-primary">
                    {formatPrice(selectedStock.price)}
                  </div>
                </div>

                {/* All Timeframe Changes */}
                <div className="grid grid-cols-4 gap-2">
                  {(["daily", "weekly", "monthly", "ytd"] as TimeFrame[]).map((tf) => {
                    const val =
                      tf === "daily"
                        ? selectedStock.dailyChange
                        : tf === "weekly"
                        ? selectedStock.weeklyChange
                        : tf === "monthly"
                        ? selectedStock.monthlyChange
                        : selectedStock.ytdChange;
                    return (
                      <div
                        key={tf}
                        className="bg-bg-primary rounded-lg p-2.5 text-center border border-border"
                      >
                        <div className="text-[10px] text-text-tertiary uppercase mb-1">
                          {TF_LABELS[tf]}
                        </div>
                        <div
                          className={`font-mono text-sm font-semibold ${changeTextClass(val)}`}
                        >
                          {val >= 0 ? "+" : ""}
                          {val.toFixed(2)}%
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Stats Grid */}
                <div className="grid grid-cols-2 gap-3">
                  <StatRow
                    icon={<DollarSign className="w-3.5 h-3.5" />}
                    label="Market Cap"
                    value={formatCap(selectedStock.marketCap)}
                  />
                  <StatRow
                    icon={<BarChart3 className="w-3.5 h-3.5" />}
                    label="Volume"
                    value={formatVol(selectedStock.volume)}
                  />
                  <StatRow
                    icon={<TrendingUp className="w-3.5 h-3.5" />}
                    label="52W High"
                    value={formatPrice(selectedStock.high52w)}
                  />
                  <StatRow
                    icon={<TrendingDown className="w-3.5 h-3.5" />}
                    label="52W Low"
                    value={formatPrice(selectedStock.low52w)}
                  />
                </div>

                {/* 52W Range Bar */}
                <div>
                  <div className="flex justify-between text-[10px] text-text-tertiary mb-1.5">
                    <span>52W Range</span>
                    <span className="font-mono">
                      {formatPrice(selectedStock.low52w)} — {formatPrice(selectedStock.high52w)}
                    </span>
                  </div>
                  <div className="relative h-2 bg-bg-primary rounded-full border border-border overflow-hidden">
                    <div
                      className="absolute inset-y-0 left-0 rounded-full"
                      style={{
                        width: `${Math.min(
                          100,
                          Math.max(
                            5,
                            ((selectedStock.price - selectedStock.low52w) /
                              (selectedStock.high52w - selectedStock.low52w)) *
                              100
                          )
                        )}%`,
                        background: `linear-gradient(90deg, ${changeColor(
                          getChange(selectedStock)
                        )}66, ${changeColor(getChange(selectedStock))})`,
                      }}
                    />
                    <div
                      className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white border-2 shadow-md"
                      style={{
                        left: `${Math.min(
                          97,
                          Math.max(
                            2,
                            ((selectedStock.price - selectedStock.low52w) /
                              (selectedStock.high52w - selectedStock.low52w)) *
                              100
                          )
                        )}%`,
                        borderColor: changeColor(getChange(selectedStock)),
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

/* ─── stat row helper ─── */
function StatRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 bg-bg-primary rounded-lg px-3 py-2 border border-border">
      <span className="text-text-tertiary">{icon}</span>
      <div>
        <div className="text-[10px] text-text-tertiary">{label}</div>
        <div className="font-mono text-sm text-text-primary font-medium">{value}</div>
      </div>
    </div>
  );
}
