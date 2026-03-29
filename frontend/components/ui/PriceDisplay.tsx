"use client";

import { clsx } from "clsx";

interface PriceDisplayProps {
  value: number | null | undefined;
  format?: "currency" | "percent" | "number";
  showSign?: boolean;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

const sizeMap = {
  sm: "text-sm",
  md: "text-base",
  lg: "text-xl",
  xl: "text-3xl",
};

function formatValue(value: number, format: string, showSign: boolean): string {
  const sign = showSign && value > 0 ? "+" : "";

  switch (format) {
    case "currency":
      return `${sign}$${Math.abs(value).toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;
    case "percent":
      return `${sign}${value.toFixed(2)}%`;
    case "number":
    default:
      return `${sign}${value.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`;
  }
}

export function PriceDisplay({
  value,
  format = "currency",
  showSign = false,
  size = "md",
  className,
}: PriceDisplayProps) {
  if (value == null) {
    return <span className={clsx("font-numbers tabular-nums", sizeMap[size], "text-text-tertiary", className)}>--</span>;
  }

  const isPositive = value > 0;
  const isNegative = value < 0;
  const isNeutral = value === 0;

  return (
    <span
      className={clsx(
        "font-numbers tabular-nums",
        sizeMap[size],
        isPositive && "text-profit",
        isNegative && "text-loss",
        isNeutral && "text-text-secondary",
        className
      )}
    >
      {formatValue(value, format, showSign || true)}
    </span>
  );
}
