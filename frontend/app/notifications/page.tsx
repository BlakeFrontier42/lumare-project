"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import {
  useNotifications,
  type Notification,
  type NotificationType,
} from "@/lib/websocket";
import { API_BASE } from "@/lib/api";
import {
  Bell,
  BellOff,
  Filter,
  Check,
  X,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Info,
  ChevronDown,
  Zap,
  Target,
  Loader2,
} from "lucide-react";

// ─── Filter categories ──────────────────────────────────

type FilterCategory = "all" | "signals" | "sltp" | "price_alerts" | "system";

const FILTER_OPTIONS: { value: FilterCategory; label: string }[] = [
  { value: "all", label: "All" },
  { value: "signals", label: "Signals" },
  { value: "sltp", label: "SL/TP" },
  { value: "price_alerts", label: "Price Alerts" },
  { value: "system", label: "System" },
];

function matchesFilter(
  type: NotificationType,
  filter: FilterCategory
): boolean {
  if (filter === "all") return true;
  if (filter === "signals")
    return type === "signal_triggered" || type === "position_closed";
  if (filter === "sltp") return type === "sl_hit" || type === "tp_hit";
  if (filter === "price_alerts") return type === "price_alert";
  if (filter === "system") return type === "system";
  return true;
}

// ─── Type icon/color mapping ────────────────────────────

function typeIcon(type: NotificationType) {
  switch (type) {
    case "signal_triggered":
      return <Zap className="w-4 h-4 text-blue-400" />;
    case "sl_hit":
      return <TrendingDown className="w-4 h-4 text-red-400" />;
    case "tp_hit":
      return <TrendingUp className="w-4 h-4 text-green-400" />;
    case "position_closed":
      return <Target className="w-4 h-4 text-zinc-400" />;
    case "price_alert":
      return <AlertTriangle className="w-4 h-4 text-amber-400" />;
    case "system":
    default:
      return <Info className="w-4 h-4 text-zinc-500" />;
  }
}

function typeBadgeBg(type: NotificationType): string {
  switch (type) {
    case "signal_triggered":
      return "bg-blue-500/10";
    case "sl_hit":
      return "bg-red-500/10";
    case "tp_hit":
      return "bg-green-500/10";
    case "position_closed":
      return "bg-zinc-500/10";
    case "price_alert":
      return "bg-amber-500/10";
    case "system":
    default:
      return "bg-zinc-800";
  }
}

// ─── Relative time ──────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const days = Math.floor(hr / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

// ─── Date grouping ──────────────────────────────────────

function dateGroup(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86_400_000);
  const weekAgo = new Date(today.getTime() - 7 * 86_400_000);

  if (d >= today) return "Today";
  if (d >= yesterday) return "Yesterday";
  if (d >= weekAgo) return "This Week";
  return "Older";
}

// ─── Merged notification type (WS live + API history) ───

interface MergedNotification {
  id: string;
  type: NotificationType;
  title: string;
  message: string;
  timestamp: string;
  data?: Record<string, unknown>;
  read: boolean;
  dismissed?: boolean;
}

// ─── Main Page ──────────────────────────────────────────

export default function NotificationsPage() {
  const { notifications: wsNotifications, status, dismiss, clearAll } = useNotifications();
  const [historyNotifications, setHistoryNotifications] = useState<MergedNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterCategory>("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [readIds, setReadIds] = useState<Set<string>>(new Set());

  // Fetch historical notifications from API
  useEffect(() => {
    let cancelled = false;
    async function fetchHistory() {
      try {
        const res = await fetch(`${API_BASE}/api/notifications/history?limit=200&offset=0`);
        if (!res.ok) throw new Error("Failed to fetch");
        const json = await res.json();
        if (!cancelled && json.notifications) {
          setHistoryNotifications(
            json.notifications.map((n: Record<string, unknown>) => ({
              id: (n.id as string) || `hist-${Math.random().toString(36).slice(2)}`,
              type: (n.type as NotificationType) || "system",
              title: (n.title as string) || "",
              message: (n.message as string) || "",
              timestamp: (n.timestamp as string) || new Date().toISOString(),
              data: n.data as Record<string, unknown> | undefined,
              read: (n.read as boolean) ?? true,
            }))
          );
        }
      } catch {
        // Silently fail — history unavailable
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchHistory();
    return () => {
      cancelled = true;
    };
  }, []);

  // Merge WS live + history, deduplicate by id
  const merged = useMemo<MergedNotification[]>(() => {
    const map = new Map<string, MergedNotification>();
    // Add history first (older)
    for (const h of historyNotifications) {
      map.set(h.id, h);
    }
    // WS notifications override (newer)
    for (const n of wsNotifications) {
      map.set(n.id, {
        id: n.id,
        type: n.type,
        title: n.title,
        message: n.message,
        timestamp: n.timestamp,
        data: n.data,
        read: readIds.has(n.id),
        dismissed: n.dismissed,
      });
    }
    return Array.from(map.values())
      .filter((n) => !n.dismissed)
      .sort(
        (a, b) =>
          new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
      );
  }, [wsNotifications, historyNotifications, readIds]);

  // Apply filter
  const filtered = useMemo(
    () => merged.filter((n) => matchesFilter(n.type, filter)),
    [merged, filter]
  );

  // Group by date
  const grouped = useMemo(() => {
    const groups: { label: string; items: MergedNotification[] }[] = [];
    const groupMap = new Map<string, MergedNotification[]>();
    const order: string[] = [];
    for (const n of filtered) {
      const g = dateGroup(n.timestamp);
      if (!groupMap.has(g)) {
        groupMap.set(g, []);
        order.push(g);
      }
      groupMap.get(g)!.push(n);
    }
    for (const label of order) {
      groups.push({ label, items: groupMap.get(label)! });
    }
    return groups;
  }, [filtered]);

  const unreadCount = merged.filter((n) => !n.read).length;

  const markAllRead = useCallback(() => {
    setReadIds((prev) => {
      const next = new Set(prev);
      for (const n of merged) next.add(n.id);
      return next;
    });
    setHistoryNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }, [merged]);

  const handleDismiss = useCallback(
    (id: string) => {
      dismiss(id);
      setHistoryNotifications((prev) => prev.filter((n) => n.id !== id));
    },
    [dismiss]
  );

  const handleExpand = useCallback(
    (id: string) => {
      setExpandedId((prev) => (prev === id ? null : id));
      // Mark as read on expand
      setReadIds((prev) => new Set(prev).add(id));
      setHistoryNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read: true } : n))
      );
    },
    []
  );

  return (
    <div className="min-h-screen bg-[#080808]">
      {/* ── Header ────────────────────────────────── */}
      <div className="sticky top-0 z-30 bg-[#080808]/95 backdrop-blur-md border-b border-[#1a1a1a]">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="relative">
              <Bell className="w-5 h-5 text-zinc-300" />
              {unreadCount > 0 && (
                <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full bg-[#3b82f6] text-[10px] font-bold text-white px-1">
                  {unreadCount > 99 ? "99+" : unreadCount}
                </span>
              )}
            </div>
            <h1 className="text-lg font-semibold text-white tracking-tight">
              Notifications
            </h1>
            {/* Connection status */}
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${
                status === "connected"
                  ? "bg-[#22c55e]"
                  : status === "connecting"
                  ? "bg-amber-400"
                  : "bg-[#ef4444]"
              }`}
              title={`WS: ${status}`}
            />
          </div>

          <div className="flex items-center gap-2">
            {/* Mark all read */}
            <button
              onClick={markAllRead}
              disabled={unreadCount === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                         border border-[#1a1a1a] text-zinc-400 hover:text-white hover:border-[#333]
                         disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <Check className="w-3.5 h-3.5" />
              Mark all read
            </button>

            {/* Filter dropdown */}
            <div className="relative">
              <button
                onClick={() => setFilterOpen(!filterOpen)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors
                           border border-[#1a1a1a] text-zinc-400 hover:text-white hover:border-[#333]"
              >
                <Filter className="w-3.5 h-3.5" />
                {FILTER_OPTIONS.find((f) => f.value === filter)?.label}
                <ChevronDown className="w-3 h-3" />
              </button>
              {filterOpen && (
                <div className="absolute right-0 mt-1 w-40 bg-[#0a0a0a] border border-[#1a1a1a] rounded-md shadow-xl overflow-hidden z-40">
                  {FILTER_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => {
                        setFilter(opt.value);
                        setFilterOpen(false);
                      }}
                      className={`w-full text-left px-3 py-2 text-xs transition-colors hover:bg-[#1a1a1a]
                                  ${
                                    filter === opt.value
                                      ? "text-[#3b82f6] font-medium"
                                      : "text-zinc-400"
                                  }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Content ───────────────────────────────── */}
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-6">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-32 text-zinc-500">
            <Loader2 className="w-6 h-6 animate-spin mb-3" />
            <p className="text-sm">Loading notifications...</p>
          </div>
        ) : filtered.length === 0 ? (
          /* ── Empty state ─────────────────────────── */
          <div className="flex flex-col items-center justify-center py-32 text-zinc-500">
            <div className="w-16 h-16 rounded-full bg-[#0a0a0a] border border-[#1a1a1a] flex items-center justify-center mb-4">
              <BellOff className="w-7 h-7 text-zinc-600" />
            </div>
            <p className="text-sm font-medium text-zinc-400">
              No notifications
            </p>
            <p className="text-xs text-zinc-600 mt-1">
              {filter !== "all"
                ? "Try changing the filter to see more."
                : "New alerts will appear here in real time."}
            </p>
          </div>
        ) : (
          /* ── Grouped list ────────────────────────── */
          <div className="space-y-6">
            {grouped.map((group) => (
              <div key={group.label}>
                <h2 className="text-[11px] font-semibold uppercase tracking-wider text-zinc-600 mb-2 px-1">
                  {group.label}
                </h2>
                <div className="space-y-1">
                  {group.items.map((n) => (
                    <NotificationCard
                      key={n.id}
                      notification={n}
                      expanded={expandedId === n.id}
                      onExpand={() => handleExpand(n.id)}
                      onDismiss={() => handleDismiss(n.id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Close filter dropdown on outside click */}
      {filterOpen && (
        <div
          className="fixed inset-0 z-20"
          onClick={() => setFilterOpen(false)}
        />
      )}
    </div>
  );
}

// ─── Notification Card ──────────────────────────────────

function NotificationCard({
  notification,
  expanded,
  onExpand,
  onDismiss,
}: {
  notification: MergedNotification;
  expanded: boolean;
  onExpand: () => void;
  onDismiss: () => void;
}) {
  const n = notification;

  return (
    <div
      className={`group relative rounded-lg border transition-all cursor-pointer
                  ${
                    n.read
                      ? "bg-[#0a0a0a] border-[#1a1a1a]"
                      : "bg-[#0a0a0a] border-[#1a1a1a] ring-1 ring-[#3b82f6]/20"
                  }
                  hover:border-[#333]`}
    >
      <div
        className="flex items-start gap-3 px-4 py-3"
        onClick={onExpand}
      >
        {/* Unread dot */}
        <div className="pt-0.5 w-2 flex-shrink-0">
          {!n.read && (
            <span className="block h-2 w-2 rounded-full bg-[#3b82f6]" />
          )}
        </div>

        {/* Type icon */}
        <div
          className={`flex-shrink-0 w-8 h-8 rounded-md flex items-center justify-center ${typeBadgeBg(
            n.type
          )}`}
        >
          {typeIcon(n.type)}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white truncate">
              {n.title}
            </span>
            <span className="text-[10px] text-zinc-600 flex-shrink-0">
              {relativeTime(n.timestamp)}
            </span>
          </div>
          <p className="text-xs text-zinc-500 mt-0.5 leading-relaxed line-clamp-2">
            {n.message}
          </p>
        </div>

        {/* Dismiss button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDismiss();
          }}
          className="flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-[#1a1a1a] text-zinc-600 hover:text-zinc-300"
          aria-label="Dismiss"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Expanded details */}
      {expanded && n.data && Object.keys(n.data).length > 0 && (
        <div className="px-4 pb-3 pt-0 ml-[52px]">
          <div className="rounded-md bg-[#080808] border border-[#1a1a1a] p-3 text-xs font-mono text-zinc-500 space-y-1">
            {Object.entries(n.data).map(([key, value]) => (
              <div key={key} className="flex gap-2">
                <span className="text-zinc-600">{key}:</span>
                <span className="text-zinc-400">
                  {typeof value === "object"
                    ? JSON.stringify(value)
                    : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
