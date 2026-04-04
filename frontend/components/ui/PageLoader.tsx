"use client";

import { clsx } from "clsx";

interface PageLoaderProps {
  variant?: "dashboard" | "table" | "chart" | "minimal";
}

function Shimmer({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        "relative overflow-hidden rounded-chip bg-bg-elevated",
        className
      )}
    >
      <div className="absolute inset-0 shimmer-effect" />
    </div>
  );
}

function HeaderSkeleton() {
  return (
    <div className="flex items-center justify-between mb-8">
      <div>
        <Shimmer className="h-8 w-48 mb-2" />
        <Shimmer className="h-4 w-72" />
      </div>
      <div className="flex gap-3">
        <Shimmer className="h-9 w-24 rounded-button" />
        <Shimmer className="h-9 w-32 rounded-button" />
      </div>
    </div>
  );
}

function MetricCardSkeleton() {
  return (
    <div className="bg-bg-card border border-border rounded-card p-5">
      <Shimmer className="h-3.5 w-24 mb-3" />
      <Shimmer className="h-7 w-32 mb-2" />
      <Shimmer className="h-3.5 w-16" />
    </div>
  );
}

function TableSkeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="bg-bg-card border border-border rounded-card overflow-hidden">
      {/* Table header */}
      <div className="flex items-center gap-4 px-5 py-3.5 border-b border-border">
        <Shimmer className="h-3.5 w-32" />
        <Shimmer className="h-3.5 w-20 ml-auto" />
        <Shimmer className="h-3.5 w-20" />
        <Shimmer className="h-3.5 w-24" />
        <Shimmer className="h-3.5 w-16" />
      </div>
      {/* Table rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="flex items-center gap-4 px-5 py-3.5 border-b border-border last:border-b-0"
        >
          <Shimmer className="h-4 w-28" />
          <Shimmer className="h-4 w-16 ml-auto" />
          <Shimmer className="h-4 w-20" />
          <Shimmer className="h-4 w-20" />
          <Shimmer className="h-4 w-14" />
        </div>
      ))}
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="bg-bg-card border border-border rounded-card p-5">
      <div className="flex items-center justify-between mb-6">
        <Shimmer className="h-5 w-36" />
        <div className="flex gap-2">
          <Shimmer className="h-7 w-12 rounded-button" />
          <Shimmer className="h-7 w-12 rounded-button" />
          <Shimmer className="h-7 w-12 rounded-button" />
        </div>
      </div>
      <Shimmer className="h-64 w-full rounded-chip" />
    </div>
  );
}

export function PageLoader({ variant = "dashboard" }: PageLoaderProps) {
  if (variant === "minimal") {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-10 h-10 rounded-full border-2 border-border border-t-text-secondary animate-spin" />
          <p className="text-sm text-text-tertiary">Loading...</p>
        </div>
      </div>
    );
  }

  if (variant === "chart") {
    return (
      <div className="p-6 lg:p-8 animate-fade-in">
        <HeaderSkeleton />
        <ChartSkeleton />
      </div>
    );
  }

  if (variant === "table") {
    return (
      <div className="p-6 lg:p-8 animate-fade-in">
        <HeaderSkeleton />
        <TableSkeleton rows={10} />
      </div>
    );
  }

  // Default: dashboard variant
  return (
    <div className="p-6 lg:p-8 animate-fade-in">
      <HeaderSkeleton />

      {/* Metric cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {Array.from({ length: 4 }).map((_, i) => (
          <MetricCardSkeleton key={i} />
        ))}
      </div>

      {/* Chart + Table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <ChartSkeleton />
        <ChartSkeleton />
      </div>

      <TableSkeleton />
    </div>
  );
}
