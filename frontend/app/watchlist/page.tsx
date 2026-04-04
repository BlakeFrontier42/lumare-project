"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Card } from "@/components/ui/Card";
import {
  Star, Plus, X, Search, ChevronUp, ChevronDown, GripVertical,
  List, LayoutGrid, Pencil, Trash2, Check, FolderPlus, Eye,
} from "lucide-react";
import { ExportMenu } from "@/components/ui/ExportMenu";

// ─── Symbol Pool ────────────────────────────────────────────────────────────
const SYMBOL_POOL: SymbolData[] = [
  { symbol: "AAPL", name: "Apple Inc.", sector: "Tech", basePrice: 189.45, mcap: "2.94T", floatShares: "15.2B", shortFloat: 0.7 },
  { symbol: "MSFT", name: "Microsoft Corp.", sector: "Tech", basePrice: 417.88, mcap: "3.11T", floatShares: "7.43B", shortFloat: 0.5 },
  { symbol: "NVDA", name: "NVIDIA Corp.", sector: "Tech", basePrice: 875.32, mcap: "2.15T", floatShares: "2.45B", shortFloat: 1.2 },
  { symbol: "GOOGL", name: "Alphabet Inc.", sector: "Tech", basePrice: 155.72, mcap: "1.93T", floatShares: "5.87B", shortFloat: 0.8 },
  { symbol: "AMZN", name: "Amazon.com Inc.", sector: "Tech", basePrice: 186.13, mcap: "1.94T", floatShares: "10.3B", shortFloat: 0.9 },
  { symbol: "META", name: "Meta Platforms", sector: "Tech", basePrice: 505.95, mcap: "1.29T", floatShares: "2.25B", shortFloat: 0.6 },
  { symbol: "TSLA", name: "Tesla Inc.", sector: "Auto", basePrice: 175.21, mcap: "558B", floatShares: "2.84B", shortFloat: 3.1 },
  { symbol: "TSM", name: "Taiwan Semi.", sector: "Tech", basePrice: 152.30, mcap: "789B", floatShares: "5.18B", shortFloat: 0.4 },
  { symbol: "AVGO", name: "Broadcom Inc.", sector: "Tech", basePrice: 1320.55, mcap: "612B", floatShares: "464M", shortFloat: 1.1 },
  { symbol: "ORCL", name: "Oracle Corp.", sector: "Tech", basePrice: 127.40, mcap: "351B", floatShares: "2.72B", shortFloat: 1.3 },
  { symbol: "BTC", name: "Bitcoin", sector: "Crypto", basePrice: 67842.00, mcap: "1.33T", floatShares: "19.6M", shortFloat: 0 },
  { symbol: "ETH", name: "Ethereum", sector: "Crypto", basePrice: 3521.45, mcap: "423B", floatShares: "120M", shortFloat: 0 },
  { symbol: "SOL", name: "Solana", sector: "Crypto", basePrice: 142.80, mcap: "63.2B", floatShares: "442M", shortFloat: 0 },
  { symbol: "BNB", name: "BNB", sector: "Crypto", basePrice: 598.30, mcap: "89.5B", floatShares: "150M", shortFloat: 0 },
  { symbol: "XRP", name: "Ripple", sector: "Crypto", basePrice: 0.5234, mcap: "28.6B", floatShares: "54.6B", shortFloat: 0 },
  { symbol: "ADA", name: "Cardano", sector: "Crypto", basePrice: 0.4521, mcap: "16.1B", floatShares: "35.6B", shortFloat: 0 },
  { symbol: "DOGE", name: "Dogecoin", sector: "Crypto", basePrice: 0.0823, mcap: "11.7B", floatShares: "142B", shortFloat: 0 },
  { symbol: "LINK", name: "Chainlink", sector: "Crypto", basePrice: 14.52, mcap: "8.5B", floatShares: "587M", shortFloat: 0 },
  { symbol: "JPM", name: "JPMorgan Chase", sector: "Finance", basePrice: 198.72, mcap: "571B", floatShares: "2.87B", shortFloat: 0.8 },
  { symbol: "V", name: "Visa Inc.", sector: "Finance", basePrice: 279.33, mcap: "573B", floatShares: "1.65B", shortFloat: 0.6 },
  { symbol: "MA", name: "Mastercard Inc.", sector: "Finance", basePrice: 458.90, mcap: "428B", floatShares: "928M", shortFloat: 0.5 },
  { symbol: "BAC", name: "Bank of America", sector: "Finance", basePrice: 37.42, mcap: "296B", floatShares: "7.92B", shortFloat: 1.1 },
  { symbol: "GS", name: "Goldman Sachs", sector: "Finance", basePrice: 412.50, mcap: "137B", floatShares: "332M", shortFloat: 1.4 },
  { symbol: "JNJ", name: "Johnson & Johnson", sector: "Health", basePrice: 156.82, mcap: "378B", floatShares: "2.41B", shortFloat: 0.7 },
  { symbol: "UNH", name: "UnitedHealth Group", sector: "Health", basePrice: 527.15, mcap: "487B", floatShares: "921M", shortFloat: 0.6 },
  { symbol: "PFE", name: "Pfizer Inc.", sector: "Health", basePrice: 27.35, mcap: "153B", floatShares: "5.61B", shortFloat: 2.3 },
  { symbol: "LLY", name: "Eli Lilly", sector: "Health", basePrice: 792.40, mcap: "752B", floatShares: "949M", shortFloat: 0.5 },
  { symbol: "ABBV", name: "AbbVie Inc.", sector: "Health", basePrice: 171.23, mcap: "302B", floatShares: "1.77B", shortFloat: 0.8 },
  { symbol: "WMT", name: "Walmart Inc.", sector: "Retail", basePrice: 168.50, mcap: "454B", floatShares: "2.69B", shortFloat: 0.4 },
  { symbol: "COST", name: "Costco Wholesale", sector: "Retail", basePrice: 728.90, mcap: "323B", floatShares: "443M", shortFloat: 0.7 },
  { symbol: "HD", name: "Home Depot", sector: "Retail", basePrice: 362.18, mcap: "360B", floatShares: "992M", shortFloat: 0.9 },
  { symbol: "DIS", name: "Walt Disney Co.", sector: "Media", basePrice: 112.45, mcap: "205B", floatShares: "1.82B", shortFloat: 1.5 },
  { symbol: "NFLX", name: "Netflix Inc.", sector: "Media", basePrice: 628.30, mcap: "272B", floatShares: "432M", shortFloat: 1.8 },
  { symbol: "CRM", name: "Salesforce Inc.", sector: "Tech", basePrice: 272.15, mcap: "264B", floatShares: "970M", shortFloat: 1.0 },
  { symbol: "AMD", name: "AMD Inc.", sector: "Tech", basePrice: 178.92, mcap: "289B", floatShares: "1.62B", shortFloat: 3.5 },
  { symbol: "INTC", name: "Intel Corp.", sector: "Tech", basePrice: 43.28, mcap: "183B", floatShares: "4.23B", shortFloat: 2.8 },
  { symbol: "QCOM", name: "Qualcomm Inc.", sector: "Tech", basePrice: 168.75, mcap: "188B", floatShares: "1.11B", shortFloat: 1.2 },
  { symbol: "BA", name: "Boeing Co.", sector: "Industrial", basePrice: 195.60, mcap: "118B", floatShares: "601M", shortFloat: 4.2 },
  { symbol: "CAT", name: "Caterpillar Inc.", sector: "Industrial", basePrice: 352.44, mcap: "172B", floatShares: "487M", shortFloat: 0.9 },
  { symbol: "XOM", name: "Exxon Mobil", sector: "Energy", basePrice: 108.32, mcap: "432B", floatShares: "3.99B", shortFloat: 0.5 },
  { symbol: "CVX", name: "Chevron Corp.", sector: "Energy", basePrice: 156.80, mcap: "291B", floatShares: "1.85B", shortFloat: 0.6 },
  { symbol: "COP", name: "ConocoPhillips", sector: "Energy", basePrice: 118.45, mcap: "139B", floatShares: "1.17B", shortFloat: 1.3 },
];

const SYMBOL_MAP = new Map(SYMBOL_POOL.map((s) => [s.symbol, s]));

// ─── Types ──────────────────────────────────────────────────────────────────
interface SymbolData {
  symbol: string;
  name: string;
  sector: string;
  basePrice: number;
  mcap: string;
  floatShares: string;
  shortFloat: number;
}

interface WatchlistItem {
  symbol: string;
  addedAt: number;
}

interface Watchlist {
  id: string;
  name: string;
  items: WatchlistItem[];
}

interface LivePrice {
  price: number;
  change: number;
  changePct: number;
  volume: number;
  high52w: number;
  low52w: number;
  sparkline: number[];
  prevPrice: number;
}

type SortKey = "symbol" | "name" | "price" | "changePct" | "volume" | "mcap" | "high52w" | "low52w" | "floatShares" | "shortFloat";
type SortDir = "asc" | "desc";

// ─── Default Watchlists ─────────────────────────────────────────────────────
const DEFAULT_WATCHLISTS: Watchlist[] = [
  {
    id: "favorites",
    name: "Favorites",
    items: ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "BTC", "ETH"].map((s) => ({ symbol: s, addedAt: Date.now() })),
  },
  {
    id: "tech-mega",
    name: "Tech Mega Caps",
    items: ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSM", "AVGO", "CRM", "AMD"].map((s) => ({ symbol: s, addedAt: Date.now() })),
  },
  {
    id: "crypto",
    name: "Crypto",
    items: ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "DOGE", "LINK"].map((s) => ({ symbol: s, addedAt: Date.now() })),
  },
  {
    id: "earnings",
    name: "Earnings Watch",
    items: ["NFLX", "GOOGL", "META", "JPM", "GS", "UNH", "LLY"].map((s) => ({ symbol: s, addedAt: Date.now() })),
  },
];

// ─── Price Simulation ───────────────────────────────────────────────────────
function generateSparkline(base: number, t: number): number[] {
  const points: number[] = [];
  for (let i = 0; i < 20; i++) {
    const noise = Math.sin((t + i) * 0.3) * 0.015 + Math.sin((t + i) * 0.7) * 0.008 + Math.cos((t + i) * 1.1) * 0.005;
    points.push(base * (1 + noise));
  }
  return points;
}

function simulatePrice(base: number, t: number): LivePrice {
  const drift = Math.sin(t * 0.05) * 0.03 + Math.sin(t * 0.13) * 0.015 + Math.cos(t * 0.21) * 0.008;
  const price = base * (1 + drift);
  const prevDrift = Math.sin((t - 1) * 0.05) * 0.03 + Math.sin((t - 1) * 0.13) * 0.015 + Math.cos((t - 1) * 0.21) * 0.008;
  const prevPrice = base * (1 + prevDrift);
  const change = price - base;
  const changePct = (change / base) * 100;
  const volume = Math.round(base * 1000 * (20 + Math.abs(Math.sin(t * 0.3) * 80)));
  const high52w = base * 1.35;
  const low52w = base * 0.72;
  const sparkline = generateSparkline(base, t);
  return { price, change, changePct, volume, high52w, low52w, sparkline, prevPrice };
}

// ─── Sparkline Component ────────────────────────────────────────────────────
function Sparkline({ data, positive }: { data: number[]; positive: boolean }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const w = 80;
  const h = 24;
  const points = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`).join(" ");
  const color = positive ? "#22c55e" : "#e05252";
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="inline-block">
      <polyline fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" points={points} />
    </svg>
  );
}

// ─── Helpers ────────────────────────────────────────────────────────────────
function fmtPrice(n: number): string {
  if (n >= 10000) return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(4);
}

function fmtVolume(n: number): string {
  if (n >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toString();
}

function parseMcap(s: string): number {
  const m = s.match(/([\d.]+)([TBMK])/);
  if (!m) return 0;
  const v = parseFloat(m[1]);
  return m[2] === "T" ? v * 1e12 : m[2] === "B" ? v * 1e9 : m[2] === "M" ? v * 1e6 : v * 1e3;
}

// ─── Main Component ─────────────────────────────────────────────────────────
export default function WatchlistPage() {
  const router = useRouter();
  const [watchlists, setWatchlists] = useState<Watchlist[]>(DEFAULT_WATCHLISTS);
  const [activeId, setActiveId] = useState("favorites");
  const [tick, setTick] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>("symbol");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [compact, setCompact] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [flash, setFlash] = useState<Record<string, "up" | "down" | null>>({});
  const searchRef = useRef<HTMLDivElement>(null);
  const prevPricesRef = useRef<Record<string, number>>({});

  const activeList = watchlists.find((w) => w.id === activeId) || watchlists[0];

  // Price tick every 2s
  useEffect(() => {
    const iv = setInterval(() => setTick((t) => t + 1), 2000);
    return () => clearInterval(iv);
  }, []);

  // Compute live prices
  const livePrices = useMemo(() => {
    const map: Record<string, LivePrice> = {};
    SYMBOL_POOL.forEach((s) => {
      map[s.symbol] = simulatePrice(s.basePrice, tick);
    });
    return map;
  }, [tick]);

  // Flash on price change
  useEffect(() => {
    const newFlash: Record<string, "up" | "down" | null> = {};
    const prev = prevPricesRef.current;
    Object.entries(livePrices).forEach(([sym, lp]) => {
      if (prev[sym] !== undefined && prev[sym] !== lp.price) {
        newFlash[sym] = lp.price > prev[sym] ? "up" : "down";
      }
    });
    setFlash(newFlash);
    const to = setTimeout(() => setFlash({}), 600);
    const newPrev: Record<string, number> = {};
    Object.entries(livePrices).forEach(([sym, lp]) => { newPrev[sym] = lp.price; });
    prevPricesRef.current = newPrev;
    return () => clearTimeout(to);
  }, [livePrices]);

  // Close search dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) setSearchOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Search autocomplete
  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const q = searchQuery.toLowerCase();
    const inList = new Set(activeList.items.map((i) => i.symbol));
    return SYMBOL_POOL.filter(
      (s) => !inList.has(s.symbol) && (s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q))
    ).slice(0, 8);
  }, [searchQuery, activeList.items]);

  // Sorted rows
  const sortedItems = useMemo(() => {
    const items = [...activeList.items];
    items.sort((a, b) => {
      const sa = SYMBOL_MAP.get(a.symbol);
      const sb = SYMBOL_MAP.get(b.symbol);
      if (!sa || !sb) return 0;
      const la = livePrices[a.symbol];
      const lb = livePrices[b.symbol];
      let cmp = 0;
      switch (sortKey) {
        case "symbol": cmp = a.symbol.localeCompare(b.symbol); break;
        case "name": cmp = sa.name.localeCompare(sb.name); break;
        case "price": cmp = (la?.price || 0) - (lb?.price || 0); break;
        case "changePct": cmp = (la?.changePct || 0) - (lb?.changePct || 0); break;
        case "volume": cmp = (la?.volume || 0) - (lb?.volume || 0); break;
        case "mcap": cmp = parseMcap(sa.mcap) - parseMcap(sb.mcap); break;
        case "high52w": cmp = (la?.high52w || 0) - (lb?.high52w || 0); break;
        case "low52w": cmp = (la?.low52w || 0) - (lb?.low52w || 0); break;
        case "floatShares": cmp = parseMcap(sa.floatShares) - parseMcap(sb.floatShares); break;
        case "shortFloat": cmp = sa.shortFloat - sb.shortFloat; break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return items;
  }, [activeList.items, sortKey, sortDir, livePrices]);

  // Actions
  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("asc"); }
  };

  const addSymbol = useCallback((symbol: string) => {
    setWatchlists((prev) =>
      prev.map((w) =>
        w.id === activeId && !w.items.find((i) => i.symbol === symbol)
          ? { ...w, items: [...w.items, { symbol, addedAt: Date.now() }] }
          : w
      )
    );
    setSearchQuery("");
    setSearchOpen(false);
  }, [activeId]);

  const removeSymbol = useCallback((symbol: string) => {
    setWatchlists((prev) =>
      prev.map((w) => (w.id === activeId ? { ...w, items: w.items.filter((i) => i.symbol !== symbol) } : w))
    );
  }, [activeId]);

  const createWatchlist = () => {
    const id = `wl-${Date.now()}`;
    setWatchlists((prev) => [...prev, { id, name: "New Watchlist", items: [] }]);
    setActiveId(id);
    setEditingId(id);
    setEditName("New Watchlist");
  };

  const deleteWatchlist = (id: string) => {
    setWatchlists((prev) => prev.filter((w) => w.id !== id));
    if (activeId === id) setActiveId(watchlists[0]?.id || "favorites");
  };

  const confirmRename = () => {
    if (!editingId || !editName.trim()) return;
    setWatchlists((prev) => prev.map((w) => (w.id === editingId ? { ...w, name: editName.trim() } : w)));
    setEditingId(null);
  };

  const SortIcon = ({ col }: { col: SortKey }) => {
    if (sortKey !== col) return <ChevronUp className="w-3 h-3 text-text-tertiary opacity-0 group-hover:opacity-50" />;
    return sortDir === "asc" ? (
      <ChevronUp className="w-3 h-3 text-white" />
    ) : (
      <ChevronDown className="w-3 h-3 text-white" />
    );
  };

  const TH = ({ col, label, align = "left" }: { col: SortKey; label: string; align?: string }) => (
    <th
      onClick={() => toggleSort(col)}
      className={`group cursor-pointer px-3 ${compact ? "py-1.5" : "py-2.5"} text-xs font-medium text-text-secondary uppercase tracking-wider select-none whitespace-nowrap ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <SortIcon col={col} />
      </span>
    </th>
  );

  return (
    <div className="min-h-screen bg-bg-primary p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Eye className="w-6 h-6 text-text-secondary" />
          <h1 className="font-heading text-2xl font-bold text-white">Watchlists</h1>
          <span className="text-xs text-text-tertiary font-mono bg-bg-elevated px-2 py-0.5 rounded-chip">
            {activeList.items.length} symbols
          </span>
        </div>
        <div className="flex items-center gap-2">
          <ExportMenu
            data={sortedItems.map((item) => {
              const d = SYMBOL_MAP.get(item.symbol);
              const lp = livePrices[item.symbol];
              return {
                symbol: item.symbol,
                name: d?.name ?? "",
                sector: d?.sector ?? "",
                price: lp ? +lp.price.toFixed(2) : 0,
                changePct: lp ? +lp.changePct.toFixed(2) : 0,
                volume: lp?.volume ?? 0,
                mcap: d?.mcap ?? "",
                high52w: lp ? +lp.high52w.toFixed(2) : 0,
                low52w: lp ? +lp.low52w.toFixed(2) : 0,
              } as Record<string, unknown>;
            })}
            filename={`lumare_watchlist_${activeList.name.toLowerCase().replace(/\s+/g, "_")}`}
            title={`Watchlist — ${activeList.name}`}
            columns={[
              { key: "symbol", label: "Symbol" },
              { key: "name", label: "Name" },
              { key: "sector", label: "Sector" },
              { key: "price", label: "Price" },
              { key: "changePct", label: "Change %" },
              { key: "volume", label: "Volume" },
              { key: "mcap", label: "Mkt Cap" },
              { key: "high52w", label: "52W High" },
              { key: "low52w", label: "52W Low" },
            ]}
          />
          <button
            onClick={() => setCompact(!compact)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-secondary border border-border rounded-button hover:bg-bg-elevated transition-colors"
          >
            {compact ? <LayoutGrid className="w-3.5 h-3.5" /> : <List className="w-3.5 h-3.5" />}
            {compact ? "Expanded" : "Compact"}
          </button>
        </div>
      </div>

      {/* Watchlist Tabs */}
      <div className="flex items-center gap-2 mb-4 overflow-x-auto pb-1">
        {watchlists.map((wl) => (
          <div
            key={wl.id}
            className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-button text-sm cursor-pointer transition-all whitespace-nowrap ${
              activeId === wl.id
                ? "bg-bg-elevated text-white border border-border"
                : "text-text-secondary hover:text-text-primary hover:bg-bg-card border border-transparent"
            }`}
            onClick={() => setActiveId(wl.id)}
          >
            {wl.id === "favorites" && <Star className="w-3.5 h-3.5 text-yellow-500" />}
            {editingId === wl.id ? (
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <input
                  autoFocus
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && confirmRename()}
                  className="bg-transparent border-b border-text-secondary text-white text-sm w-28 outline-none"
                />
                <button onClick={confirmRename} className="text-profit hover:text-green-400">
                  <Check className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <span>{wl.name}</span>
            )}
            {activeId === wl.id && editingId !== wl.id && (
              <div className="flex items-center gap-0.5 ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  onClick={(e) => { e.stopPropagation(); setEditingId(wl.id); setEditName(wl.name); }}
                  className="p-0.5 hover:text-white text-text-tertiary"
                >
                  <Pencil className="w-3 h-3" />
                </button>
                {wl.id !== "favorites" && (
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteWatchlist(wl.id); }}
                    className="p-0.5 hover:text-loss text-text-tertiary"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
        <button
          onClick={createWatchlist}
          className="flex items-center gap-1 px-3 py-1.5 text-sm text-text-tertiary hover:text-text-primary border border-dashed border-border rounded-button hover:border-text-tertiary transition-colors"
        >
          <FolderPlus className="w-3.5 h-3.5" />
          New
        </button>
      </div>

      {/* Search + Table */}
      <Card padding="none" className="overflow-hidden">
        {/* Search Bar */}
        <div className="p-3 border-b border-border" ref={searchRef}>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-tertiary" />
            <input
              type="text"
              placeholder="Search symbols to add..."
              value={searchQuery}
              onChange={(e) => { setSearchQuery(e.target.value); setSearchOpen(true); }}
              onFocus={() => setSearchOpen(true)}
              className="w-full bg-bg-primary border border-border rounded-button pl-9 pr-4 py-2 text-sm text-white placeholder-text-tertiary outline-none focus:border-text-secondary transition-colors"
            />
            {searchOpen && searchResults.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-bg-card border border-border rounded-card z-50 max-h-64 overflow-y-auto shadow-2xl">
                {searchResults.map((s) => (
                  <button
                    key={s.symbol}
                    onClick={() => addSymbol(s.symbol)}
                    className="w-full flex items-center justify-between px-4 py-2.5 hover:bg-bg-elevated transition-colors text-left"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-mono font-semibold text-white">{s.symbol}</span>
                      <span className="text-xs text-text-secondary">{s.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] text-text-tertiary bg-bg-elevated px-1.5 py-0.5 rounded-chip">{s.sector}</span>
                      <Plus className="w-3.5 h-3.5 text-text-tertiary" />
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Table */}
        {activeList.items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-text-tertiary">
            <Eye className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm">No symbols in this watchlist</p>
            <p className="text-xs mt-1">Use the search above to add symbols</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-border bg-bg-primary/50">
                <tr>
                  <th className={`w-8 ${compact ? "py-1.5" : "py-2.5"}`} />
                  <TH col="symbol" label="Symbol" />
                  <TH col="name" label="Name" />
                  <TH col="price" label="Price" align="right" />
                  <TH col="changePct" label="Change %" align="right" />
                  <TH col="volume" label="Volume" align="right" />
                  <TH col="mcap" label="Mkt Cap" align="right" />
                  <TH col="floatShares" label="Float" align="right" />
                  <TH col="shortFloat" label="SI %" align="right" />
                  <TH col="high52w" label="52W High" align="right" />
                  <TH col="low52w" label="52W Low" align="right" />
                  <th className={`px-3 ${compact ? "py-1.5" : "py-2.5"} text-xs font-medium text-text-secondary uppercase tracking-wider text-center`}>
                    Trend
                  </th>
                  <th className={`w-8 ${compact ? "py-1.5" : "py-2.5"}`} />
                </tr>
              </thead>
              <tbody>
                {sortedItems.map((item) => {
                  const data = SYMBOL_MAP.get(item.symbol);
                  const lp = livePrices[item.symbol];
                  if (!data || !lp) return null;
                  const pos = lp.changePct >= 0;
                  const flashState = flash[item.symbol];
                  return (
                    <tr
                      key={item.symbol}
                      onClick={() => router.push(`/trade?symbol=${item.symbol}`)}
                      className={`border-b border-border/50 hover:bg-bg-elevated cursor-pointer transition-colors ${
                        flashState === "up"
                          ? "animate-flash-green"
                          : flashState === "down"
                          ? "animate-flash-red"
                          : ""
                      }`}
                    >
                      {/* Drag handle */}
                      <td className={`pl-2 ${compact ? "py-1" : "py-2.5"}`}>
                        <GripVertical className="w-3.5 h-3.5 text-text-tertiary/40 hover:text-text-secondary cursor-grab" />
                      </td>
                      {/* Symbol */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"}`}>
                        <span className="font-mono text-sm font-semibold text-white">{item.symbol}</span>
                      </td>
                      {/* Name */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"}`}>
                        <span className={`text-text-secondary ${compact ? "text-xs" : "text-sm"}`}>{data.name}</span>
                      </td>
                      {/* Price */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className="font-mono text-sm text-white">${fmtPrice(lp.price)}</span>
                      </td>
                      {/* Change % */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className={`font-mono text-sm ${pos ? "text-profit" : "text-loss"}`}>
                          {pos ? "+" : ""}{lp.changePct.toFixed(2)}%
                        </span>
                      </td>
                      {/* Volume */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className="font-mono text-xs text-text-secondary">{fmtVolume(lp.volume)}</span>
                      </td>
                      {/* Market Cap */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className="font-mono text-xs text-text-secondary">{data.mcap}</span>
                      </td>
                      {/* Float */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className="font-mono text-xs text-text-secondary">{data.floatShares}</span>
                      </td>
                      {/* Short Interest */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className={`font-mono text-xs ${data.shortFloat >= 10 ? "text-loss" : data.shortFloat >= 3 ? "text-yellow-400" : "text-text-secondary"}`}>
                          {data.shortFloat > 0 ? data.shortFloat.toFixed(1) + "%" : "—"}
                        </span>
                      </td>
                      {/* 52W High */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className="font-mono text-xs text-text-secondary">${fmtPrice(lp.high52w)}</span>
                      </td>
                      {/* 52W Low */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-right`}>
                        <span className="font-mono text-xs text-text-secondary">${fmtPrice(lp.low52w)}</span>
                      </td>
                      {/* Sparkline */}
                      <td className={`px-3 ${compact ? "py-1" : "py-2.5"} text-center`}>
                        <Sparkline data={lp.sparkline} positive={pos} />
                      </td>
                      {/* Remove */}
                      <td className={`pr-2 ${compact ? "py-1" : "py-2.5"}`}>
                        <button
                          onClick={(e) => { e.stopPropagation(); removeSymbol(item.symbol); }}
                          className="p-1 text-text-tertiary/40 hover:text-loss transition-colors rounded"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Flash Animations */}
      <style jsx global>{`
        @keyframes flash-green {
          0% { background-color: rgba(34, 197, 94, 0.15); }
          100% { background-color: transparent; }
        }
        @keyframes flash-red {
          0% { background-color: rgba(224, 82, 82, 0.15); }
          100% { background-color: transparent; }
        }
        .animate-flash-green { animation: flash-green 0.6s ease-out; }
        .animate-flash-red { animation: flash-red 0.6s ease-out; }
      `}</style>
    </div>
  );
}
