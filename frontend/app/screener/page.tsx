"use client";

import { useState, useMemo } from "react";
import { Card } from "@/components/ui/Card";
import {
  Search,
  SlidersHorizontal,
  X,
  ChevronDown,
  ChevronUp,
  Zap,
  TrendingUp,
  BarChart3,
  Activity,
  DollarSign,
  ArrowUpDown,
  Filter,
  Layers,
} from "lucide-react";
import { ExportMenu } from "@/components/ui/ExportMenu";

/* ------------------------------------------------------------------ */
/*  TYPES                                                              */
/* ------------------------------------------------------------------ */

interface Stock {
  symbol: string;
  name: string;
  sector: string;
  price: number;
  change1D: number;
  change1W: number;
  change1M: number;
  change3M: number;
  changeYTD: number;
  volume: number;
  avgVolume: number;
  relVolume: number;
  rsi: number;
  ma20: number;
  ma50: number;
  ma200: number;
  macdSignal: "bullish" | "bearish" | "neutral";
  high52w: number;
  low52w: number;
  marketCap: number;
  floatShares: number;
  shortFloat: number;
  pe: number | null;
  epsGrowth: number | null;
  divYield: number | null;
  gapPct: number;
}

interface Filters {
  minPrice: string;
  maxPrice: string;
  minVolume: string;
  minRelVolume: string;
  rsiBelow: string;
  rsiAbove: string;
  aboveMA: "" | "20" | "50" | "200";
  belowMA: "" | "20" | "50" | "200";
  macdSignal: "" | "bullish" | "bearish";
  near52wHigh: string;
  near52wLow: string;
  minMarketCap: string;
  maxMarketCap: string;
  minPE: string;
  maxPE: string;
  minEpsGrowth: string;
  minDivYield: string;
  sector: string;
  minChange1D: string;
  maxChange1D: string;
  minChange1W: string;
  minChange1M: string;
  minChange3M: string;
  minChangeYTD: string;
  minGap: string;
  maxGap: string;
  minShortFloat: string;
  maxShortFloat: string;
}

type SortKey = keyof Stock;
type SortDir = "asc" | "desc";

interface PresetScan {
  label: string;
  icon: React.ReactNode;
  filters: Partial<Filters>;
}

/* ------------------------------------------------------------------ */
/*  MOCK DATA — 65 stocks across all sectors                          */
/* ------------------------------------------------------------------ */

const SECTORS = [
  "Technology",
  "Healthcare",
  "Financials",
  "Consumer Discretionary",
  "Industrials",
  "Energy",
  "Materials",
  "Utilities",
  "Real Estate",
  "Communication Services",
  "Consumer Staples",
];

function r(min: number, max: number, dec = 2) {
  return +(min + Math.random() * (max - min)).toFixed(dec);
}

function makeStock(
  symbol: string,
  name: string,
  sector: string,
  price: number,
  mcap: number,
  pe: number | null,
  divYield: number | null
): Stock {
  const vol = r(500_000, 80_000_000, 0);
  const avgVol = r(vol * 0.5, vol * 1.5, 0);
  const ma20 = price * r(0.93, 1.07);
  const ma50 = price * r(0.88, 1.12);
  const ma200 = price * r(0.78, 1.22);
  const high52 = price * r(1.02, 1.55);
  const low52 = price * r(0.45, 0.96);
  const rsi = r(15, 88, 1);
  const macdOpts: ("bullish" | "bearish" | "neutral")[] = ["bullish", "bearish", "neutral"];
  return {
    symbol,
    name,
    sector,
    price,
    change1D: r(-6, 8),
    change1W: r(-12, 15),
    change1M: r(-18, 25),
    change3M: r(-25, 40),
    changeYTD: r(-30, 60),
    volume: vol,
    avgVolume: avgVol,
    relVolume: +(vol / avgVol).toFixed(2),
    rsi,
    ma20,
    ma50,
    ma200,
    macdSignal: macdOpts[Math.floor(Math.random() * 3)],
    high52w: high52,
    low52w: low52,
    marketCap: mcap,
    pe,
    floatShares: r(mcap / price * 0.6, mcap / price * 0.95, 0),
    shortFloat: r(0.5, 25, 1),
    epsGrowth: pe ? r(-20, 80) : null,
    divYield,
    gapPct: r(-5, 8),
  };
}

const MOCK_STOCKS: Stock[] = [
  makeStock("AAPL", "Apple Inc.", "Technology", 189.84, 2.95e12, 31.2, 0.52),
  makeStock("MSFT", "Microsoft Corp.", "Technology", 415.60, 3.09e12, 36.8, 0.72),
  makeStock("NVDA", "NVIDIA Corp.", "Technology", 878.35, 2.16e12, 68.4, 0.02),
  makeStock("GOOGL", "Alphabet Inc.", "Communication Services", 153.51, 1.92e12, 25.1, null),
  makeStock("AMZN", "Amazon.com Inc.", "Consumer Discretionary", 185.07, 1.91e12, 58.3, null),
  makeStock("META", "Meta Platforms", "Communication Services", 503.28, 1.28e12, 27.6, 0.37),
  makeStock("TSLA", "Tesla Inc.", "Consumer Discretionary", 177.48, 5.65e11, 42.1, null),
  makeStock("BRK.B", "Berkshire Hathaway", "Financials", 412.35, 8.84e11, 10.8, null),
  makeStock("LLY", "Eli Lilly & Co.", "Healthcare", 782.10, 7.43e11, 118.5, 0.72),
  makeStock("V", "Visa Inc.", "Financials", 281.42, 5.78e11, 31.4, 0.76),
  makeStock("UNH", "UnitedHealth Group", "Healthcare", 527.68, 4.87e11, 22.1, 1.38),
  makeStock("JPM", "JPMorgan Chase", "Financials", 198.47, 5.71e11, 11.8, 2.24),
  makeStock("XOM", "Exxon Mobil", "Energy", 104.71, 4.28e11, 12.5, 3.35),
  makeStock("MA", "Mastercard Inc.", "Financials", 458.92, 4.26e11, 35.7, 0.55),
  makeStock("JNJ", "Johnson & Johnson", "Healthcare", 156.74, 3.78e11, 11.2, 3.02),
  makeStock("PG", "Procter & Gamble", "Consumer Staples", 162.15, 3.82e11, 26.4, 2.38),
  makeStock("HD", "Home Depot", "Consumer Discretionary", 362.80, 3.60e11, 24.1, 2.28),
  makeStock("AVGO", "Broadcom Inc.", "Technology", 1328.45, 6.12e11, 52.3, 1.62),
  makeStock("COST", "Costco Wholesale", "Consumer Staples", 728.60, 3.23e11, 50.2, 0.58),
  makeStock("ABBV", "AbbVie Inc.", "Healthcare", 171.82, 3.03e11, 44.7, 3.68),
  makeStock("CRM", "Salesforce Inc.", "Technology", 272.35, 2.64e11, 48.2, null),
  makeStock("AMD", "Advanced Micro Devices", "Technology", 164.22, 2.65e11, 245.0, null),
  makeStock("NFLX", "Netflix Inc.", "Communication Services", 628.15, 2.72e11, 44.8, null),
  makeStock("WMT", "Walmart Inc.", "Consumer Staples", 168.42, 4.54e11, 27.8, 1.34),
  makeStock("PFE", "Pfizer Inc.", "Healthcare", 27.18, 1.52e11, 44.2, 5.82),
  makeStock("TMO", "Thermo Fisher", "Healthcare", 572.30, 2.22e11, 34.8, 0.22),
  makeStock("MRK", "Merck & Co.", "Healthcare", 126.84, 3.21e11, 35.1, 2.52),
  makeStock("ORCL", "Oracle Corp.", "Technology", 125.18, 3.42e11, 34.6, 1.18),
  makeStock("ACN", "Accenture plc", "Technology", 342.65, 2.15e11, 29.8, 1.62),
  makeStock("BAC", "Bank of America", "Financials", 34.72, 2.72e11, 11.2, 2.68),
  makeStock("DIS", "Walt Disney Co.", "Communication Services", 112.48, 2.06e11, 68.4, null),
  makeStock("CSCO", "Cisco Systems", "Technology", 50.28, 2.04e11, 14.8, 2.92),
  makeStock("CVX", "Chevron Corp.", "Energy", 155.42, 2.88e11, 11.6, 4.02),
  makeStock("COP", "ConocoPhillips", "Energy", 114.35, 1.38e11, 12.2, 1.95),
  makeStock("NEE", "NextEra Energy", "Utilities", 62.48, 1.28e11, 20.8, 2.82),
  makeStock("SO", "Southern Company", "Utilities", 72.35, 7.88e10, 21.2, 3.72),
  makeStock("DUK", "Duke Energy", "Utilities", 98.15, 7.56e10, 18.6, 3.95),
  makeStock("SHW", "Sherwin-Williams", "Materials", 325.48, 8.28e10, 32.4, 0.88),
  makeStock("ECL", "Ecolab Inc.", "Materials", 202.15, 5.68e10, 42.8, 1.02),
  makeStock("NEM", "Newmont Corp.", "Materials", 42.18, 3.35e10, 18.2, 2.15),
  makeStock("FCX", "Freeport-McMoRan", "Materials", 42.85, 6.12e10, 28.4, 0.72),
  makeStock("PLD", "Prologis Inc.", "Real Estate", 128.42, 1.18e11, 52.1, 2.62),
  makeStock("AMT", "American Tower", "Real Estate", 202.35, 9.42e10, 48.4, 3.15),
  makeStock("SPG", "Simon Property", "Real Estate", 148.62, 4.85e10, 18.2, 5.12),
  makeStock("UNP", "Union Pacific", "Industrials", 248.32, 1.52e11, 22.8, 2.12),
  makeStock("HON", "Honeywell Intl.", "Industrials", 202.15, 1.32e11, 24.2, 2.02),
  makeStock("CAT", "Caterpillar Inc.", "Industrials", 322.48, 1.58e11, 16.8, 1.68),
  makeStock("GE", "GE Aerospace", "Industrials", 158.35, 1.72e11, 34.2, 0.62),
  makeStock("RTX", "RTX Corp.", "Industrials", 92.15, 1.28e11, 42.8, 2.35),
  makeStock("LMT", "Lockheed Martin", "Industrials", 448.62, 1.08e11, 16.4, 2.72),
  makeStock("DE", "Deere & Company", "Industrials", 402.80, 1.15e11, 13.2, 1.38),
  makeStock("LOW", "Lowe's Companies", "Consumer Discretionary", 228.42, 1.32e11, 18.8, 1.82),
  makeStock("SBUX", "Starbucks Corp.", "Consumer Discretionary", 92.65, 1.06e11, 24.6, 2.15),
  makeStock("NKE", "Nike Inc.", "Consumer Discretionary", 98.35, 1.50e11, 28.2, 1.32),
  makeStock("MCD", "McDonald's Corp.", "Consumer Discretionary", 292.15, 2.12e11, 25.8, 2.08),
  makeStock("KO", "Coca-Cola Co.", "Consumer Staples", 60.28, 2.60e11, 24.2, 3.02),
  makeStock("PEP", "PepsiCo Inc.", "Consumer Staples", 168.42, 2.32e11, 26.8, 2.72),
  makeStock("PM", "Philip Morris Intl.", "Consumer Staples", 95.85, 1.49e11, 18.2, 5.28),
  makeStock("GILD", "Gilead Sciences", "Healthcare", 82.48, 1.03e11, 12.8, 3.42),
  makeStock("INTC", "Intel Corp.", "Technology", 42.85, 1.80e11, 108.0, 1.08),
  makeStock("COIN", "Coinbase Global", "Financials", 228.15, 5.52e10, null, null),
  makeStock("PLTR", "Palantir Tech.", "Technology", 22.48, 4.88e10, 225.0, null),
  makeStock("RIVN", "Rivian Automotive", "Consumer Discretionary", 16.82, 1.68e10, null, null),
  makeStock("SOFI", "SoFi Technologies", "Financials", 8.42, 8.12e9, null, null),
  makeStock("SMCI", "Super Micro Comp.", "Technology", 782.35, 4.58e10, 22.8, null),
];

/* ------------------------------------------------------------------ */
/*  PRESET SCANS                                                       */
/* ------------------------------------------------------------------ */

const PRESET_SCANS: PresetScan[] = [
  {
    label: "Oversold Bounce",
    icon: <Activity className="w-3.5 h-3.5" />,
    filters: { rsiBelow: "30", minChange1D: "1", minRelVolume: "1.5" },
  },
  {
    label: "Momentum Breakout",
    icon: <TrendingUp className="w-3.5 h-3.5" />,
    filters: { rsiAbove: "60", aboveMA: "20", macdSignal: "bullish", minChange1W: "5" },
  },
  {
    label: "High Volume Surge",
    icon: <BarChart3 className="w-3.5 h-3.5" />,
    filters: { minRelVolume: "2.5", minChange1D: "2" },
  },
  {
    label: "Dividend Aristocrats",
    icon: <DollarSign className="w-3.5 h-3.5" />,
    filters: { minDivYield: "2.5", minMarketCap: "10000000000", maxPE: "30" },
  },
  {
    label: "Earnings Gap Up",
    icon: <Zap className="w-3.5 h-3.5" />,
    filters: { minGap: "3", minRelVolume: "2", minEpsGrowth: "15" },
  },
  {
    label: "Golden Cross",
    icon: <Layers className="w-3.5 h-3.5" />,
    filters: { aboveMA: "50", macdSignal: "bullish", minChange1M: "5" },
  },
];

/* ------------------------------------------------------------------ */
/*  DEFAULT FILTERS                                                    */
/* ------------------------------------------------------------------ */

const DEFAULT_FILTERS: Filters = {
  minPrice: "",
  maxPrice: "",
  minVolume: "",
  minRelVolume: "",
  rsiBelow: "",
  rsiAbove: "",
  aboveMA: "",
  belowMA: "",
  macdSignal: "",
  near52wHigh: "",
  near52wLow: "",
  minMarketCap: "",
  maxMarketCap: "",
  minPE: "",
  maxPE: "",
  minEpsGrowth: "",
  minDivYield: "",
  sector: "",
  minChange1D: "",
  maxChange1D: "",
  minChange1W: "",
  minChange1M: "",
  minChange3M: "",
  minChangeYTD: "",
  minGap: "",
  maxGap: "",
  minShortFloat: "",
  maxShortFloat: "",
};

/* ------------------------------------------------------------------ */
/*  HELPERS                                                            */
/* ------------------------------------------------------------------ */

function fmtNum(n: number | null, dec = 2): string {
  if (n == null) return "--";
  return n.toFixed(dec);
}

function fmtVol(n: number): string {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toString();
}

function fmtMcap(n: number): string {
  if (n >= 1e12) return "$" + (n / 1e12).toFixed(2) + "T";
  if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return "$" + (n / 1e6).toFixed(0) + "M";
  return "$" + n.toLocaleString();
}

function pn(v: number) {
  return v >= 0 ? "text-profit" : "text-loss";
}

const FILTER_LABELS: Record<string, string> = {
  minPrice: "Min Price",
  maxPrice: "Max Price",
  minVolume: "Min Volume",
  minRelVolume: "Rel Volume >",
  rsiBelow: "RSI <",
  rsiAbove: "RSI >",
  aboveMA: "Above MA",
  belowMA: "Below MA",
  macdSignal: "MACD",
  near52wHigh: "Near 52W High %",
  near52wLow: "Near 52W Low %",
  minMarketCap: "Min MCap",
  maxMarketCap: "Max MCap",
  minPE: "Min P/E",
  maxPE: "Max P/E",
  minEpsGrowth: "EPS Growth >",
  minDivYield: "Div Yield >",
  sector: "Sector",
  minChange1D: "1D Change >",
  maxChange1D: "1D Change <",
  minChange1W: "1W Change >",
  minChange1M: "1M Change >",
  minChange3M: "3M Change >",
  minChangeYTD: "YTD Change >",
  minGap: "Gap Up >",
  maxGap: "Gap Down <",
};

/* ------------------------------------------------------------------ */
/*  FILTER SECTION COMPONENT                                           */
/* ------------------------------------------------------------------ */

function FilterSection({
  title,
  icon,
  open,
  toggle,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  open: boolean;
  toggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={toggle}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-bg-elevated/50 transition-colors"
      >
        <span className="flex items-center gap-2 text-sm font-medium text-text-primary">
          {icon}
          {title}
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-text-tertiary" />
        ) : (
          <ChevronDown className="w-4 h-4 text-text-tertiary" />
        )}
      </button>
      {open && <div className="px-4 pb-4 grid grid-cols-2 gap-3">{children}</div>}
    </div>
  );
}

function FilterInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <label className="text-[11px] text-text-tertiary uppercase tracking-wider mb-1 block">
        {label}
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder ?? "Any"}
        className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-1.5 text-xs font-mono text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-text-tertiary transition-colors"
      />
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <label className="text-[11px] text-text-tertiary uppercase tracking-wider mb-1 block">
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-bg-elevated border border-border rounded-chip px-3 py-1.5 text-xs text-text-primary focus:outline-none focus:border-text-tertiary transition-colors appearance-none"
      >
        <option value="">Any</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  MAIN PAGE                                                          */
/* ------------------------------------------------------------------ */

export default function ScreenerPage() {
  const [filters, setFilters] = useState<Filters>({ ...DEFAULT_FILTERS });
  const [sortKey, setSortKey] = useState<SortKey>("marketCap");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [searchQuery, setSearchQuery] = useState("");
  const [openSections, setOpenSections] = useState({
    priceVol: true,
    technical: false,
    fundamental: false,
    momentum: false,
  });
  const [presetsOpen, setPresetsOpen] = useState(false);

  const set = (key: keyof Filters, val: string) =>
    setFilters((p) => ({ ...p, [key]: val }));

  const toggleSection = (s: keyof typeof openSections) =>
    setOpenSections((p) => ({ ...p, [s]: !p[s] }));

  const activeFilters = Object.entries(filters).filter(([, v]) => v !== "");

  const clearFilter = (key: string) => setFilters((p) => ({ ...p, [key]: "" }));
  const clearAll = () => setFilters({ ...DEFAULT_FILTERS });

  const applyPreset = (scan: PresetScan) => {
    const next = { ...DEFAULT_FILTERS, ...scan.filters } as Filters;
    setFilters(next);
    setPresetsOpen(false);
    setOpenSections({ priceVol: true, technical: true, fundamental: true, momentum: true });
  };

  const handleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  /* apply filters */
  const results = useMemo(() => {
    let data = [...MOCK_STOCKS];

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      data = data.filter(
        (s) =>
          s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
      );
    }

    const f = filters;
    if (f.minPrice) data = data.filter((s) => s.price >= +f.minPrice);
    if (f.maxPrice) data = data.filter((s) => s.price <= +f.maxPrice);
    if (f.minVolume) data = data.filter((s) => s.volume >= +f.minVolume);
    if (f.minRelVolume) data = data.filter((s) => s.relVolume >= +f.minRelVolume);
    if (f.rsiBelow) data = data.filter((s) => s.rsi <= +f.rsiBelow);
    if (f.rsiAbove) data = data.filter((s) => s.rsi >= +f.rsiAbove);
    if (f.aboveMA === "20") data = data.filter((s) => s.price > s.ma20);
    if (f.aboveMA === "50") data = data.filter((s) => s.price > s.ma50);
    if (f.aboveMA === "200") data = data.filter((s) => s.price > s.ma200);
    if (f.belowMA === "20") data = data.filter((s) => s.price < s.ma20);
    if (f.belowMA === "50") data = data.filter((s) => s.price < s.ma50);
    if (f.belowMA === "200") data = data.filter((s) => s.price < s.ma200);
    if (f.macdSignal) data = data.filter((s) => s.macdSignal === f.macdSignal);
    if (f.near52wHigh)
      data = data.filter((s) => ((s.high52w - s.price) / s.high52w) * 100 <= +f.near52wHigh);
    if (f.near52wLow)
      data = data.filter((s) => ((s.price - s.low52w) / s.low52w) * 100 <= +f.near52wLow);
    if (f.minMarketCap) data = data.filter((s) => s.marketCap >= +f.minMarketCap);
    if (f.maxMarketCap) data = data.filter((s) => s.marketCap <= +f.maxMarketCap);
    if (f.minPE) data = data.filter((s) => s.pe != null && s.pe >= +f.minPE);
    if (f.maxPE) data = data.filter((s) => s.pe != null && s.pe <= +f.maxPE);
    if (f.minEpsGrowth) data = data.filter((s) => s.epsGrowth != null && s.epsGrowth >= +f.minEpsGrowth);
    if (f.minDivYield) data = data.filter((s) => s.divYield != null && s.divYield >= +f.minDivYield);
    if (f.sector) data = data.filter((s) => s.sector === f.sector);
    if (f.minChange1D) data = data.filter((s) => s.change1D >= +f.minChange1D);
    if (f.maxChange1D) data = data.filter((s) => s.change1D <= +f.maxChange1D);
    if (f.minChange1W) data = data.filter((s) => s.change1W >= +f.minChange1W);
    if (f.minChange1M) data = data.filter((s) => s.change1M >= +f.minChange1M);
    if (f.minChange3M) data = data.filter((s) => s.change3M >= +f.minChange3M);
    if (f.minChangeYTD) data = data.filter((s) => s.changeYTD >= +f.minChangeYTD);
    if (f.minGap) data = data.filter((s) => s.gapPct >= +f.minGap);
    if (f.maxGap) data = data.filter((s) => s.gapPct <= +f.maxGap);

    data.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === "string" && typeof bv === "string")
        return sortDir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      return sortDir === "asc" ? +av - +bv : +bv - +av;
    });

    return data;
  }, [filters, sortKey, sortDir, searchQuery]);

  const SortHeader = ({
    label,
    k,
    className,
  }: {
    label: string;
    k: SortKey;
    className?: string;
  }) => (
    <th
      onClick={() => handleSort(k)}
      className={`px-3 py-2.5 text-left text-[11px] uppercase tracking-wider text-text-tertiary font-medium cursor-pointer hover:text-text-secondary select-none whitespace-nowrap ${className ?? ""}`}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {sortKey === k && (
          <ArrowUpDown className="w-3 h-3 text-text-secondary" />
        )}
      </span>
    </th>
  );

  return (
    <div className="min-h-screen bg-bg-primary p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-heading font-bold text-text-primary tracking-tight">
            Stock Screener
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Multi-factor screening across {MOCK_STOCKS.length} equities
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Results badge */}
          <div className="flex items-center gap-2 bg-bg-card border border-border rounded-chip px-3 py-1.5">
            <Filter className="w-3.5 h-3.5 text-text-tertiary" />
            <span className="text-xs font-mono text-text-secondary">
              <span className="text-text-primary font-semibold">{results.length}</span> results
            </span>
          </div>
          {/* Export */}
          <ExportMenu
            data={results as unknown as Record<string, unknown>[]}
            filename="lumare_screener_results"
            title="Stock Screener Results"
            columns={[
              { key: "symbol", label: "Symbol" },
              { key: "name", label: "Name" },
              { key: "sector", label: "Sector" },
              { key: "price", label: "Price" },
              { key: "change1D", label: "Chg % 1D" },
              { key: "volume", label: "Volume" },
              { key: "relVolume", label: "Rel Vol" },
              { key: "rsi", label: "RSI" },
              { key: "marketCap", label: "Mkt Cap" },
              { key: "pe", label: "P/E" },
              { key: "divYield", label: "Div %" },
            ]}
          />
        </div>
      </div>

      <div className="flex gap-6">
        {/* ---- LEFT PANEL: FILTERS ---- */}
        <div className="w-72 flex-shrink-0 space-y-4">
          {/* Search */}
          <Card padding="none" className="overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
              <Search className="w-4 h-4 text-text-tertiary" />
              <input
                type="text"
                placeholder="Search symbol or name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-transparent text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none flex-1"
              />
            </div>
          </Card>

          {/* Presets */}
          <Card padding="none" className="overflow-hidden">
            <button
              onClick={() => setPresetsOpen(!presetsOpen)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-bg-elevated/50 transition-colors"
            >
              <span className="flex items-center gap-2 text-sm font-medium text-text-primary">
                <SlidersHorizontal className="w-4 h-4 text-text-tertiary" />
                Pre-built Scans
              </span>
              <ChevronDown
                className={`w-4 h-4 text-text-tertiary transition-transform ${presetsOpen ? "rotate-180" : ""}`}
              />
            </button>
            {presetsOpen && (
              <div className="px-3 pb-3 grid gap-1.5">
                {PRESET_SCANS.map((scan) => (
                  <button
                    key={scan.label}
                    onClick={() => applyPreset(scan)}
                    className="flex items-center gap-2 w-full px-3 py-2 rounded-chip text-xs text-text-secondary hover:bg-bg-elevated hover:text-text-primary transition-colors text-left"
                  >
                    {scan.icon}
                    {scan.label}
                  </button>
                ))}
              </div>
            )}
          </Card>

          {/* Filter Sections */}
          <Card padding="none" className="overflow-hidden">
            <FilterSection
              title="Price & Volume"
              icon={<DollarSign className="w-4 h-4 text-text-tertiary" />}
              open={openSections.priceVol}
              toggle={() => toggleSection("priceVol")}
            >
              <FilterInput label="Min Price" value={filters.minPrice} onChange={(v) => set("minPrice", v)} placeholder="$0" />
              <FilterInput label="Max Price" value={filters.maxPrice} onChange={(v) => set("maxPrice", v)} placeholder="$999" />
              <FilterInput label="Min Avg Volume" value={filters.minVolume} onChange={(v) => set("minVolume", v)} placeholder="e.g. 1000000" />
              <FilterInput label="Rel Volume >" value={filters.minRelVolume} onChange={(v) => set("minRelVolume", v)} placeholder="e.g. 1.5" />
            </FilterSection>

            <FilterSection
              title="Technical"
              icon={<Activity className="w-4 h-4 text-text-tertiary" />}
              open={openSections.technical}
              toggle={() => toggleSection("technical")}
            >
              <FilterInput label="RSI Below" value={filters.rsiBelow} onChange={(v) => set("rsiBelow", v)} placeholder="e.g. 30" />
              <FilterInput label="RSI Above" value={filters.rsiAbove} onChange={(v) => set("rsiAbove", v)} placeholder="e.g. 70" />
              <FilterSelect
                label="Above MA"
                value={filters.aboveMA}
                onChange={(v) => set("aboveMA", v)}
                options={[
                  { value: "20", label: "MA 20" },
                  { value: "50", label: "MA 50" },
                  { value: "200", label: "MA 200" },
                ]}
              />
              <FilterSelect
                label="Below MA"
                value={filters.belowMA}
                onChange={(v) => set("belowMA", v)}
                options={[
                  { value: "20", label: "MA 20" },
                  { value: "50", label: "MA 50" },
                  { value: "200", label: "MA 200" },
                ]}
              />
              <FilterSelect
                label="MACD Signal"
                value={filters.macdSignal}
                onChange={(v) => set("macdSignal", v)}
                options={[
                  { value: "bullish", label: "Bullish" },
                  { value: "bearish", label: "Bearish" },
                ]}
              />
              <FilterInput label="Near 52W High %" value={filters.near52wHigh} onChange={(v) => set("near52wHigh", v)} placeholder="e.g. 5" />
              <FilterInput label="Near 52W Low %" value={filters.near52wLow} onChange={(v) => set("near52wLow", v)} placeholder="e.g. 10" />
            </FilterSection>

            <FilterSection
              title="Fundamental"
              icon={<BarChart3 className="w-4 h-4 text-text-tertiary" />}
              open={openSections.fundamental}
              toggle={() => toggleSection("fundamental")}
            >
              <FilterInput label="Min Market Cap" value={filters.minMarketCap} onChange={(v) => set("minMarketCap", v)} placeholder="e.g. 1e9" />
              <FilterInput label="Max Market Cap" value={filters.maxMarketCap} onChange={(v) => set("maxMarketCap", v)} placeholder="e.g. 1e12" />
              <FilterInput label="Min P/E" value={filters.minPE} onChange={(v) => set("minPE", v)} placeholder="e.g. 5" />
              <FilterInput label="Max P/E" value={filters.maxPE} onChange={(v) => set("maxPE", v)} placeholder="e.g. 30" />
              <FilterInput label="EPS Growth >" value={filters.minEpsGrowth} onChange={(v) => set("minEpsGrowth", v)} placeholder="e.g. 15" />
              <FilterInput label="Div Yield >" value={filters.minDivYield} onChange={(v) => set("minDivYield", v)} placeholder="e.g. 2" />
              <FilterSelect
                label="Sector"
                value={filters.sector}
                onChange={(v) => set("sector", v)}
                options={SECTORS.map((s) => ({ value: s, label: s }))}
              />
            </FilterSection>

            <FilterSection
              title="Momentum"
              icon={<TrendingUp className="w-4 h-4 text-text-tertiary" />}
              open={openSections.momentum}
              toggle={() => toggleSection("momentum")}
            >
              <FilterInput label="1D Change >" value={filters.minChange1D} onChange={(v) => set("minChange1D", v)} placeholder="%" />
              <FilterInput label="1D Change <" value={filters.maxChange1D} onChange={(v) => set("maxChange1D", v)} placeholder="%" />
              <FilterInput label="1W Change >" value={filters.minChange1W} onChange={(v) => set("minChange1W", v)} placeholder="%" />
              <FilterInput label="1M Change >" value={filters.minChange1M} onChange={(v) => set("minChange1M", v)} placeholder="%" />
              <FilterInput label="3M Change >" value={filters.minChange3M} onChange={(v) => set("minChange3M", v)} placeholder="%" />
              <FilterInput label="YTD Change >" value={filters.minChangeYTD} onChange={(v) => set("minChangeYTD", v)} placeholder="%" />
              <FilterInput label="Gap Up >" value={filters.minGap} onChange={(v) => set("minGap", v)} placeholder="%" />
              <FilterInput label="Gap Down <" value={filters.maxGap} onChange={(v) => set("maxGap", v)} placeholder="%" />
            </FilterSection>
          </Card>
        </div>

        {/* ---- RIGHT PANEL: ACTIVE FILTERS + TABLE ---- */}
        <div className="flex-1 min-w-0 space-y-4">
          {/* Active filter pills */}
          {activeFilters.length > 0 && (
            <div className="flex items-center flex-wrap gap-2">
              {activeFilters.map(([key, val]) => (
                <span
                  key={key}
                  className="inline-flex items-center gap-1.5 bg-accent/10 text-text-secondary rounded-full px-3 py-1 text-xs"
                >
                  <span className="text-text-tertiary">{FILTER_LABELS[key] || key}:</span>
                  <span className="text-text-primary font-mono">{val}</span>
                  <button
                    onClick={() => clearFilter(key)}
                    className="ml-0.5 hover:text-loss transition-colors"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              <button
                onClick={clearAll}
                className="text-xs text-text-tertiary hover:text-loss transition-colors px-2 py-1"
              >
                Clear all
              </button>
            </div>
          )}

          {/* Results Table */}
          <Card padding="none" className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-bg-elevated/30">
                    <SortHeader label="Symbol" k="symbol" />
                    <SortHeader label="Name" k="name" />
                    <SortHeader label="Sector" k="sector" />
                    <SortHeader label="Price" k="price" />
                    <SortHeader label="Chg %" k="change1D" />
                    <SortHeader label="Volume" k="volume" />
                    <SortHeader label="Rel Vol" k="relVolume" />
                    <SortHeader label="RSI" k="rsi" />
                    <SortHeader label="Mkt Cap" k="marketCap" />
                    <SortHeader label="Float" k="floatShares" />
                    <SortHeader label="SI %" k="shortFloat" />
                    <SortHeader label="P/E" k="pe" />
                    <SortHeader label="Div %" k="divYield" />
                  </tr>
                </thead>
                <tbody>
                  {results.length === 0 ? (
                    <tr>
                      <td colSpan={13} className="text-center py-16 text-text-tertiary text-sm">
                        No stocks match current filters. Try adjusting your criteria.
                      </td>
                    </tr>
                  ) : (
                    results.map((s) => (
                      <tr
                        key={s.symbol}
                        className="border-b border-border/50 hover:bg-bg-elevated/40 transition-colors"
                      >
                        <td className="px-3 py-2.5 font-mono font-semibold text-text-primary whitespace-nowrap">
                          {s.symbol}
                        </td>
                        <td className="px-3 py-2.5 text-text-secondary whitespace-nowrap max-w-[160px] truncate">
                          {s.name}
                        </td>
                        <td className="px-3 py-2.5 text-text-tertiary text-xs whitespace-nowrap">
                          {s.sector}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-text-primary whitespace-nowrap">
                          ${fmtNum(s.price)}
                        </td>
                        <td className={`px-3 py-2.5 font-mono whitespace-nowrap ${pn(s.change1D)}`}>
                          {s.change1D >= 0 ? "+" : ""}
                          {fmtNum(s.change1D)}%
                        </td>
                        <td className="px-3 py-2.5 font-mono text-text-secondary whitespace-nowrap">
                          {fmtVol(s.volume)}
                        </td>
                        <td
                          className={`px-3 py-2.5 font-mono whitespace-nowrap ${
                            s.relVolume >= 2 ? "text-profit" : "text-text-secondary"
                          }`}
                        >
                          {fmtNum(s.relVolume, 1)}x
                        </td>
                        <td
                          className={`px-3 py-2.5 font-mono whitespace-nowrap ${
                            s.rsi <= 30
                              ? "text-profit"
                              : s.rsi >= 70
                                ? "text-loss"
                                : "text-text-secondary"
                          }`}
                        >
                          {fmtNum(s.rsi, 1)}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-text-secondary whitespace-nowrap">
                          {fmtMcap(s.marketCap)}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-text-secondary whitespace-nowrap">
                          {fmtVol(s.floatShares)}
                        </td>
                        <td className={`px-3 py-2.5 font-mono whitespace-nowrap ${
                          s.shortFloat >= 20 ? "text-loss" : s.shortFloat >= 10 ? "text-yellow-400" : "text-text-secondary"
                        }`}>
                          {fmtNum(s.shortFloat, 1)}%
                        </td>
                        <td className="px-3 py-2.5 font-mono text-text-secondary whitespace-nowrap">
                          {fmtNum(s.pe, 1)}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-text-secondary whitespace-nowrap">
                          {s.divYield != null ? fmtNum(s.divYield) + "%" : "--"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
