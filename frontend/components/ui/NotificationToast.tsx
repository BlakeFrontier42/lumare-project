"use client";

import { useEffect, useCallback } from "react";
import { clsx } from "clsx";
import {
  useNotifications,
  type Notification,
  type NotificationType,
  type ConnectionStatus,
} from "@/lib/websocket";

// ─── Constants ───────────────────────────────────────────

const AUTO_DISMISS_MS = 5_000;
const MAX_VISIBLE = 5;

// ─── Color / icon mapping ────────────────────────────────

function toastStyles(type: NotificationType): {
  border: string;
  bg: string;
  icon: string;
  iconColor: string;
} {
  switch (type) {
    case "sl_hit":
      return {
        border: "border-[var(--color-loss)]",
        bg: "bg-[#e0525210]",
        icon: "\u25BC",  // down triangle
        iconColor: "text-[var(--color-loss)]",
      };
    case "tp_hit":
      return {
        border: "border-[var(--color-profit)]",
        bg: "bg-[#22c55e10]",
        icon: "\u25B2",  // up triangle
        iconColor: "text-[var(--color-profit)]",
      };
    case "position_closed":
      return {
        border: "border-[var(--color-text-tertiary)]",
        bg: "bg-[var(--color-bg-elevated)]",
        icon: "\u2716",  // cross
        iconColor: "text-[var(--color-text-secondary)]",
      };
    case "signal_triggered":
      return {
        border: "border-blue-500",
        bg: "bg-blue-500/10",
        icon: "\u26A1",  // lightning
        iconColor: "text-blue-400",
      };
    case "price_alert":
      return {
        border: "border-amber-500",
        bg: "bg-amber-500/10",
        icon: "\u25C6",  // diamond
        iconColor: "text-amber-400",
      };
    case "system":
    default:
      return {
        border: "border-[var(--color-border)]",
        bg: "bg-[var(--color-bg-card)]",
        icon: "\u2139",  // info
        iconColor: "text-[var(--color-text-secondary)]",
      };
  }
}

// Decide if the notification represents a profit-like event
function isProfitNotification(n: Notification): boolean | null {
  if (n.type === "tp_hit") return true;
  if (n.type === "sl_hit") return false;
  if (n.type === "position_closed" && n.data) {
    const pnl = n.data.pnl as number | undefined;
    if (pnl !== undefined) return pnl >= 0;
  }
  return null; // neutral / not applicable
}

// Override border color for position_closed based on P&L
function resolveClosedBorder(n: Notification): string {
  if (n.type !== "position_closed") return "";
  const profit = isProfitNotification(n);
  if (profit === true) return "border-[var(--color-profit)]";
  if (profit === false) return "border-[var(--color-loss)]";
  return "";
}

// ─── Single toast ────────────────────────────────────────

function Toast({
  notification,
  onDismiss,
}: {
  notification: Notification;
  onDismiss: (id: string) => void;
}) {
  const styles = toastStyles(notification.type);
  const closedBorder = resolveClosedBorder(notification);

  // Auto-dismiss timer
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(notification.id), AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [notification.id, onDismiss]);

  // Relative time
  const time = new Date(notification.timestamp);
  const seconds = Math.round((Date.now() - time.getTime()) / 1000);
  const timeLabel = seconds < 5 ? "just now" : `${seconds}s ago`;

  return (
    <div
      className={clsx(
        "pointer-events-auto w-full sm:w-80 rounded-md border px-4 py-3 shadow-lg backdrop-blur-sm",
        "animate-[slideIn_0.3s_ease-out]",
        styles.bg,
        closedBorder || styles.border,
      )}
      role="alert"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={clsx("text-base flex-shrink-0", styles.iconColor)}>
            {styles.icon}
          </span>
          <span className="text-sm font-semibold text-[var(--color-text-primary)] truncate">
            {notification.title}
          </span>
        </div>
        <button
          onClick={() => onDismiss(notification.id)}
          className="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] transition-colors text-xs flex-shrink-0"
          aria-label="Dismiss notification"
        >
          \u2715
        </button>
      </div>
      {/* Body */}
      <p className="mt-1 text-xs text-[var(--color-text-secondary)] leading-relaxed">
        {notification.message}
      </p>
      {/* Timestamp */}
      <p className="mt-1.5 text-[10px] text-[var(--color-text-tertiary)]">
        {timeLabel}
      </p>
    </div>
  );
}

// ─── Status dot ──────────────────────────────────────────

function StatusDot({ status }: { status: ConnectionStatus }) {
  const color =
    status === "connected"
      ? "bg-[var(--color-profit)]"
      : status === "connecting"
      ? "bg-amber-400"
      : "bg-[var(--color-loss)]";

  return (
    <span
      className={clsx("inline-block h-1.5 w-1.5 rounded-full", color)}
      title={`Notifications: ${status}`}
    />
  );
}

// ─── Container ───────────────────────────────────────────

export function NotificationToast() {
  const { notifications, status, dismiss } = useNotifications();

  const handleDismiss = useCallback(
    (id: string) => dismiss(id),
    [dismiss],
  );

  // Only show un-dismissed, up to MAX_VISIBLE
  const visible = notifications
    .filter((n) => !n.dismissed && n.type !== "system")
    .slice(0, MAX_VISIBLE);

  return (
    <>
      {/* Inject slide-in keyframe once */}
      <style jsx global>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(24px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
      `}</style>

      {/* Toast stack — top-right, above everything */}
      <div className="fixed top-4 left-4 right-4 sm:left-auto z-[9999] flex flex-col gap-2 pointer-events-none">
        {visible.map((n) => (
          <Toast key={n.id} notification={n} onDismiss={handleDismiss} />
        ))}
      </div>

      {/* Tiny connection indicator — bottom-right */}
      <div className="fixed bottom-3 right-3 z-[9998]">
        <StatusDot status={status} />
      </div>
    </>
  );
}
