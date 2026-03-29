import { create } from "zustand";

// ── Types ──────────────────────────────────────────────────────────────────

export interface Position {
  ticker: string;
  shares: number;
  avgCost: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
}

export interface AssetAllocation {
  label: string;
  value: number;
  percentage: number;
}

export interface WatchlistItem {
  ticker: string;
  name: string;
  price: number;
  change: number;
  changePct: number;
}

export type MarketRegime = "risk-on" | "risk-off" | "transitional";

// ── App Store ──────────────────────────────────────────────────────────────

interface AppState {
  // Sidebar
  sidebarExpanded: boolean;
  setSidebarExpanded: (expanded: boolean) => void;
  toggleSidebar: () => void;

  // Portfolio
  netWorth: number;
  netWorthChange: number;
  netWorthChangePct: number;
  positions: Position[];
  allocations: AssetAllocation[];

  // Watchlist
  watchlist: WatchlistItem[];

  // Macro
  marketRegime: MarketRegime;

  // UI state
  activeAsset: string | null;
  setActiveAsset: (ticker: string | null) => void;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Sidebar
  sidebarExpanded: false,
  setSidebarExpanded: (expanded) => set({ sidebarExpanded: expanded }),
  toggleSidebar: () =>
    set((state) => ({ sidebarExpanded: !state.sidebarExpanded })),

  // Portfolio — placeholder data
  netWorth: 847_293.42,
  netWorthChange: 12_847.31,
  netWorthChangePct: 1.54,
  positions: [],
  allocations: [
    { label: "Equities", value: 412_000, percentage: 48.6 },
    { label: "Real Estate", value: 185_000, percentage: 21.8 },
    { label: "Crypto", value: 94_000, percentage: 11.1 },
    { label: "Cash", value: 78_293, percentage: 9.2 },
    { label: "Bonds", value: 52_000, percentage: 6.1 },
    { label: "Alternatives", value: 26_000, percentage: 3.1 },
  ],

  // Watchlist — placeholder data
  watchlist: [
    { ticker: "SPY", name: "S&P 500 ETF", price: 521.43, change: 3.21, changePct: 0.62 },
    { ticker: "QQQ", name: "Nasdaq 100 ETF", price: 448.17, change: -1.84, changePct: -0.41 },
    { ticker: "NVDA", name: "NVIDIA Corp", price: 878.35, change: 12.47, changePct: 1.44 },
    { ticker: "AAPL", name: "Apple Inc", price: 178.72, change: -0.93, changePct: -0.52 },
    { ticker: "MSFT", name: "Microsoft Corp", price: 425.18, change: 5.63, changePct: 1.34 },
  ],

  // Macro
  marketRegime: "risk-on",

  // UI state
  activeAsset: null,
  setActiveAsset: (ticker) => set({ activeAsset: ticker }),
  searchQuery: "",
  setSearchQuery: (query) => set({ searchQuery: query }),
}));
