/**
 * Orchestrator Types — TypeScript + Zod schemas
 *
 * Mirrors backend/orchestrator/schemas.py exactly.
 * Frontend uses these to render any orchestrator response.
 */

import { z } from "zod";

// ─── Enums ───────────────────────────────────────────────

export const BlockType = z.enum([
  "text",
  "chart",
  "table",
  "metric",
  "metrics_group",
  "signal",
  "trade_plan",
  "portfolio",
  "risk_alert",
  "citation",
  "code",
  "action",
  "error",
]);
export type BlockType = z.infer<typeof BlockType>;

export const IntentCategory = z.enum([
  "research",
  "trade",
  "portfolio",
  "macro",
  "memory",
  "risk",
  "general",
  "quant",
]);
export type IntentCategory = z.infer<typeof IntentCategory>;

export const Severity = z.enum(["info", "warning", "critical", "blocked"]);
export type Severity = z.infer<typeof Severity>;

// ─── Response Blocks ─────────────────────────────────────

export const ResponseBlock = z.object({
  type: BlockType,
  title: z.string().nullable().optional(),
  data: z.record(z.string(), z.any()).default({}),
  severity: Severity.nullable().optional(),
  source: z.string().nullable().optional(),
});
export type ResponseBlock = z.infer<typeof ResponseBlock>;

export const PolicyDecision = z.object({
  allowed: z.boolean().default(true),
  reason: z.string().nullable().optional(),
  severity: Severity.default("info"),
  checks_run: z.array(z.string()).default([]),
  blocked_by: z.string().nullable().optional(),
});
export type PolicyDecision = z.infer<typeof PolicyDecision>;

export const RoutingDecision = z.object({
  category: IntentCategory,
  confidence: z.number().min(0).max(1),
  adapters_used: z.array(z.string()).default([]),
  slm_handled: z.boolean().default(false),
  reasoning: z.string().nullable().optional(),
});
export type RoutingDecision = z.infer<typeof RoutingDecision>;

// ─── Unified Response ────────────────────────────────────

export const OrchestratorResponse = z.object({
  request_id: z.string(),
  user_id: z.string().default("default"),
  routing: RoutingDecision,
  policy: PolicyDecision,
  blocks: z.array(ResponseBlock).default([]),
  memory_writes: z.array(z.record(z.string(), z.any())).default([]),
  latency_ms: z.number().nullable().optional(),
  timestamp: z.string(),
});
export type OrchestratorResponse = z.infer<typeof OrchestratorResponse>;

// ─── Request ─────────────────────────────────────────────

export const OrchestratorRequest = z.object({
  query: z.string(),
  user_id: z.string().default("default"),
  symbol: z.string().optional(),
  symbols: z.array(z.string()).default([]),
  context: z.record(z.string(), z.any()).default({}),
  session_id: z.string().optional(),
  category_hint: IntentCategory.optional(),
});
export type OrchestratorRequest = z.infer<typeof OrchestratorRequest>;

// ─── Memory Types ────────────────────────────────────────

export const UserProfile = z.object({
  user_id: z.string(),
  preferences: z.record(z.string(), z.any()).default({}),
  signal_stats: z.object({
    total_signals: z.number().default(0),
    wins: z.number().default(0),
    losses: z.number().default(0),
    win_rate: z.number().default(0),
    avg_pnl_pct: z.number().default(0),
    acted_on: z.number().default(0),
  }).default({
    total_signals: 0, wins: 0, losses: 0,
    win_rate: 0, avg_pnl_pct: 0, acted_on: 0,
  }),
  risk_tolerance: z.string().default("moderate"),
  experience_level: z.string().default("intermediate"),
  favorite_symbols: z.array(z.string()).default([]),
  preferred_timeframes: z.array(z.string()).default(["4H", "1D"]),
});
export type UserProfile = z.infer<typeof UserProfile>;

export const SignalOutcome = z.object({
  id: z.number(),
  signal_id: z.string(),
  symbol: z.string(),
  direction: z.string().nullable(),
  score: z.number().nullable(),
  entry_price: z.number().nullable(),
  outcome: z.string(),
  pnl: z.number().nullable(),
  pnl_pct: z.number().nullable(),
  acted_on: z.boolean(),
  created_at: z.string(),
  resolved_at: z.string().nullable(),
});
export type SignalOutcome = z.infer<typeof SignalOutcome>;

export const AuditEntry = z.object({
  id: z.number(),
  request_id: z.string(),
  user_id: z.string(),
  query: z.string(),
  category: z.string(),
  confidence: z.number().nullable(),
  adapters: z.string().nullable(),
  policy_ok: z.boolean(),
  policy_reason: z.string().nullable(),
  response_summary: z.string().nullable(),
  latency_ms: z.number().nullable(),
  created_at: z.string(),
});
export type AuditEntry = z.infer<typeof AuditEntry>;
