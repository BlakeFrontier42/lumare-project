/**
 * Lumare API client — shared utilities for all frontend pages.
 * Centralizes the API base URL, fetch helpers, and WebSocket connection.
 */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "";

export const WS_BASE =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

// ─── Typed Fetch ──────────────────────────────────────────

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T | null> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

// ─── Format Helpers ───────────────────────────────────────

export function formatCurrency(val: number | null | undefined): string {
  if (val == null) return "--";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(val);
}

export function formatNumber(
  val: number | null | undefined,
  decimals = 2
): string {
  if (val == null) return "--";
  return new Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(val);
}

export function formatVolume(val: number | null | undefined): string {
  if (val == null) return "--";
  if (val >= 1_000_000_000) return `${(val / 1_000_000_000).toFixed(1)}B`;
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `${(val / 1_000).toFixed(1)}K`;
  return val.toFixed(0);
}

export function formatPct(val: number | null | undefined, decimals = 2): string {
  if (val == null) return "--";
  const sign = val >= 0 ? "+" : "";
  return `${sign}${val.toFixed(decimals)}%`;
}

// ─── Types ────────────────────────────────────────────────

export interface PriceData {
  symbol: string;
  price: number;
  change_24h: number | null;
  volume_24h: number | null;
  high_24h: number | null;
  low_24h: number | null;
  bid?: number | null;
  ask?: number | null;
  asset_class?: string;
}

export interface PortfolioSummary {
  total_equity: number | null;
  cash: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number | null;
  total_pnl: number | null;
  portfolio_heat: number | null;
  open_positions: number;
  drawdown_pct: number | null;
  peak_equity: number | null;
  positions: PositionData[];
  timestamp: string | null;
}

export interface PositionData {
  symbol: string;
  direction: string | null;
  entry_price: number | null;
  current_price: number | null;
  quantity: number | null;
  unrealized_pnl: number | null;
  stop_loss: number | null;
  take_profit: number | null;
}

export interface TradeRecord {
  trade_id: string | null;
  symbol: string;
  side: string | null;
  entry_time: string | null;
  exit_time: string | null;
  entry_price: number | null;
  exit_price: number | null;
  quantity: number | null;
  pnl: number | null;
  pnl_pct: number | null;
  r_multiple: number | null;
  fees: number | null;
  status: string | null;
  signal_score: number | null;
  regime: string | null;
}

export interface SignalScore {
  symbol: string;
  timestamp: string | null;
  composite_score: number;
  trend_score: number | null;
  momentum_score: number | null;
  structure_score: number | null;
  flow_score: number | null;
  macro_score: number | null;
  direction: string | null;
  regime: string | null;
}

export interface MacroIndicator {
  key: string;
  label: string;
  value: number | null;
  unit: string;
  category: string;
  source?: string;
}

export interface RiskMetric {
  name: string;
  value: number | null;
  unit: string;
  limit: number | null;
  status: string;
}

export interface StressTestResult {
  scenario: string;
  market_impact: string;
  portfolio_impact: number | null;
  portfolio_impact_pct: number | null;
  description: string;
  survives: boolean;
}

// ─── Orchestrator API ────────────────────────────────────

export async function orchestratorQuery(params: {
  query: string;
  user_id?: string;
  symbol?: string;
  symbols?: string[];
  context?: Record<string, unknown>;
  session_id?: string;
  category_hint?: string;
}) {
  return apiFetch<{
    request_id: string;
    routing: { category: string; confidence: number; adapters_used: string[]; slm_handled: boolean };
    policy: { allowed: boolean; reason: string | null; severity: string };
    blocks: Array<{ type: string; title: string | null; data: Record<string, unknown>; severity?: string; source?: string }>;
    latency_ms: number;
    timestamp: string;
  }>("/api/orchestrator/query", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function getUserProfile(userId = "default") {
  return apiFetch<{
    user_id: string;
    preferences: Record<string, unknown>;
    signal_stats: { total_signals: number; wins: number; losses: number; win_rate: number };
    risk_tolerance: string;
    experience_level: string;
    favorite_symbols: string[];
  }>(`/api/orchestrator/memory/profile?user_id=${userId}`);
}

export async function setUserPreference(key: string, value: unknown, userId = "default") {
  return apiFetch("/api/orchestrator/memory/preferences", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, key, value }),
  });
}

export async function getAuditLog(userId = "default", limit = 50) {
  return apiFetch<{ decisions: Array<Record<string, unknown>> }>(
    `/api/orchestrator/audit?user_id=${userId}&limit=${limit}`
  );
}
