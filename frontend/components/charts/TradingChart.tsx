"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type LineData,
  type HistogramData,
  ColorType,
  CrosshairMode,
  LineStyle,
} from "lightweight-charts";

type ChartType = "candles" | "line" | "area" | "bars";

interface TradingChartProps {
  symbol: string;
  initialTimeframe?: string;
  height?: number;
  className?: string;
  showTimeframes?: boolean;
  showVolume?: boolean;
}

interface CandleRaw {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

const TIMEFRAMES = ["1M", "5M", "15M", "1H", "4H", "1D"] as const;

const CHART_TYPES: { key: ChartType; label: string }[] = [
  { key: "candles", label: "Candles" },
  { key: "line", label: "Line" },
  { key: "area", label: "Area" },
  { key: "bars", label: "Bars" },
];

// ─── Mock candle generator ────────────────────────────────────
const BASE_PRICES: Record<string, number> = {
  BTCUSDT: 87500, ETHUSDT: 2050, SOLUSDT: 140, XRPUSDT: 2.45, ADAUSDT: 0.72,
  AVAXUSDT: 22, DOGEUSDT: 0.18, LINKUSDT: 15.5, DOTUSDT: 4.3, MATICUSDT: 0.38,
  SPY: 572, QQQ: 490, AAPL: 218, TSLA: 275, NVDA: 118, AMZN: 205,
  MSFT: 390, GOOG: 160, META: 590, AMD: 105, JPM: 250, V: 320,
  NFLX: 960, DIS: 110, BA: 175, WMT: 92,
};

function generateMockCandles(symbol: string, tf: string, count: number = 300): CandleRaw[] {
  const base = BASE_PRICES[symbol] ?? 100;
  const now = Date.now();
  const tfMs: Record<string, number> = {
    "1M": 60_000, "5M": 300_000, "15M": 900_000,
    "1H": 3_600_000, "4H": 14_400_000, "1D": 86_400_000,
  };
  const interval = tfMs[tf] || 3_600_000;
  const candles: CandleRaw[] = [];
  let price = base * (0.95 + Math.random() * 0.1);
  const volatility = base * 0.008;

  for (let i = count; i >= 0; i--) {
    const ts = now - i * interval;
    const drift = Math.sin(i / 40) * volatility * 0.5;
    const open = price + drift;
    const move = (Math.random() - 0.48) * volatility * 2;
    const close = open + move;
    const high = Math.max(open, close) + Math.random() * volatility * 0.7;
    const low = Math.min(open, close) - Math.random() * volatility * 0.7;
    const volume = base * (500 + Math.random() * 2000);

    candles.push({
      timestamp: new Date(ts).toISOString(),
      open: +open.toFixed(6),
      high: +high.toFixed(6),
      low: +low.toFixed(6),
      close: +close.toFixed(6),
      volume: +volume.toFixed(0),
    });

    price = close;
  }

  return candles;
}

export function TradingChart({
  symbol,
  initialTimeframe = "1H",
  height = 500,
  className = "",
  showTimeframes = true,
  showVolume = true,
}: TradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const mainSeriesRef = useRef<ISeriesApi<any> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTimeframe, setActiveTimeframe] = useState(initialTimeframe);
  const [chartType, setChartType] = useState<ChartType>("candles");
  const [currentPrice, setCurrentPrice] = useState<number | null>(null);
  const [dataSource, setDataSource] = useState<"live" | "mock">("live");

  // Build chart + series whenever symbol, timeframe, or chart type changes
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Clean up previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      mainSeriesRef.current = null;
      volumeSeriesRef.current = null;
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#080808" },
        textColor: "#888888",
        fontFamily: "'Space Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#151515" },
        horzLines: { color: "#151515" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#333", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#222" },
        horzLine: { color: "#333", width: 1, style: LineStyle.Dashed, labelBackgroundColor: "#222" },
      },
      rightPriceScale: {
        borderColor: "#1a1a1a",
        scaleMargins: { top: 0.1, bottom: showVolume ? 0.25 : 0.1 },
      },
      timeScale: {
        borderColor: "#1a1a1a",
        timeVisible: true,
        secondsVisible: false,
      },
    });

    chartRef.current = chart;

    // Create main series based on chart type
    let mainSeries: ISeriesApi<any>;
    switch (chartType) {
      case "line":
        mainSeries = chart.addLineSeries({
          color: "#3b82f6",
          lineWidth: 2,
          crosshairMarkerRadius: 4,
        });
        break;
      case "area":
        mainSeries = chart.addAreaSeries({
          topColor: "rgba(59,130,246,0.4)",
          bottomColor: "rgba(59,130,246,0.02)",
          lineColor: "#3b82f6",
          lineWidth: 2,
        });
        break;
      case "bars":
        mainSeries = chart.addBarSeries({
          upColor: "#22c55e",
          downColor: "#e05252",
        });
        break;
      default: // candles
        mainSeries = chart.addCandlestickSeries({
          upColor: "#22c55e",
          downColor: "#e05252",
          borderUpColor: "#22c55e",
          borderDownColor: "#e05252",
          wickUpColor: "#22c55e",
          wickDownColor: "#e05252",
        });
    }
    mainSeriesRef.current = mainSeries;

    // Volume
    let volumeSeries: ISeriesApi<"Histogram"> | null = null;
    if (showVolume) {
      volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "",
      });
      volumeSeries.priceScale().applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      volumeSeriesRef.current = volumeSeries;
    }

    // Fetch data then set it
    let cancelled = false;

    async function loadData() {
      setLoading(true);
      setError(null);

      let rawCandles: CandleRaw[] = [];
      let source: "live" | "mock" = "mock";

      try {
        const res = await fetch(
          `${API_BASE}/api/markets/candles/${symbol}?timeframe=${activeTimeframe}&limit=500`,
          { signal: AbortSignal.timeout(4000) }
        );
        if (res.ok) {
          const data = await res.json();
          if (data.candles && data.candles.length > 0) {
            rawCandles = data.candles;
            source = "live";
          }
        }
      } catch {
        // API not available — use mock
      }

      // Fallback to mock data
      if (rawCandles.length === 0) {
        rawCandles = generateMockCandles(symbol, activeTimeframe);
        source = "mock";
      }

      if (cancelled) return;

      const candles: CandlestickData[] = rawCandles.map((c) => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as any,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }));

      const lineData: LineData[] = rawCandles.map((c) => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as any,
        value: c.close,
      }));

      const volumes: HistogramData[] = rawCandles.map((c) => ({
        time: Math.floor(new Date(c.timestamp).getTime() / 1000) as any,
        value: c.volume,
        color: c.close >= c.open ? "rgba(34,197,94,0.15)" : "rgba(224,82,82,0.15)",
      }));

      if (chartType === "line" || chartType === "area") {
        mainSeries.setData(lineData as any);
      } else {
        mainSeries.setData(candles as any);
      }

      if (volumeSeries && showVolume) {
        volumeSeries.setData(volumes);
      }

      const last = candles[candles.length - 1];
      if (last) {
        setCurrentPrice(last.close);
        // Live price line
        mainSeries.createPriceLine({
          price: last.close,
          color: last.close >= last.open ? "#22c55e" : "#e05252",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: "",
        });
      }

      setDataSource(source);
      chart.timeScale().fitContent();
      setLoading(false);
    }

    loadData();

    // Resize observer
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(container);

    return () => {
      cancelled = true;
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      mainSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [symbol, activeTimeframe, chartType, height, showVolume]);

  return (
    <div
      className={`relative ${className}`}
      style={{ fontFamily: "'Space Mono', monospace" }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-wrap gap-2"
        style={{ borderBottom: "1px solid #1a1a1a" }}
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold" style={{ color: "#e0e0e0" }}>
            {symbol}
          </span>
          {currentPrice !== null && (
            <span className="text-sm" style={{ color: "#22c55e" }}>
              {currentPrice.toLocaleString(undefined, {
                minimumFractionDigits: 2,
                maximumFractionDigits: currentPrice < 1 ? 6 : 2,
              })}
            </span>
          )}
          {dataSource === "mock" && !loading && (
            <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-yellow-500/10 text-yellow-500">
              SIMULATED
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Chart type selector */}
          <div className="flex items-center gap-0.5 bg-[#0d0d0d] rounded-md p-0.5">
            {CHART_TYPES.map((ct) => (
              <button
                key={ct.key}
                onClick={() => setChartType(ct.key)}
                className="px-2 py-1 text-[10px] rounded transition-all"
                style={{
                  background: chartType === ct.key ? "#1a1a1a" : "transparent",
                  color: chartType === ct.key ? "#e0e0e0" : "#666",
                  border: chartType === ct.key ? "1px solid #333" : "1px solid transparent",
                  cursor: "pointer",
                }}
              >
                {ct.label}
              </button>
            ))}
          </div>

          {/* Timeframe selector */}
          {showTimeframes && (
            <div className="flex items-center gap-0.5 bg-[#0d0d0d] rounded-md p-0.5">
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setActiveTimeframe(tf)}
                  className="px-2.5 py-1 text-xs rounded transition-all"
                  style={{
                    background: activeTimeframe === tf ? "#1a1a1a" : "transparent",
                    color: activeTimeframe === tf ? "#e0e0e0" : "#666",
                    border: activeTimeframe === tf ? "1px solid #333" : "1px solid transparent",
                    cursor: "pointer",
                  }}
                >
                  {tf}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Chart container — ALWAYS visible so lightweight-charts gets proper dimensions */}
      <div ref={containerRef} className="w-full" style={{ height }} />

      {/* Loading overlay — sits on top of the chart */}
      {loading && (
        <div
          className="absolute inset-0 flex items-center justify-center z-10"
          style={{ background: "rgba(8,8,8,0.85)", top: 52 }}
        >
          <div className="flex items-center gap-2 text-sm" style={{ color: "#888" }}>
            <div className="w-4 h-4 border-2 border-t-transparent border-blue-500 rounded-full animate-spin" />
            Loading chart...
          </div>
        </div>
      )}

      {/* Error overlay */}
      {error && !loading && (
        <div
          className="absolute inset-0 flex items-center justify-center z-10"
          style={{ background: "rgba(8,8,8,0.85)", top: 52 }}
        >
          <div className="text-center space-y-2">
            <p className="text-sm" style={{ color: "#aaa" }}>{error}</p>
            <p className="text-xs" style={{ color: "#666" }}>
              Using simulated data — start API for live feed
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
