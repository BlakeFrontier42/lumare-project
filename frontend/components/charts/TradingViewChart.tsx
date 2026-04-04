"use client";

import { useEffect, useRef, memo, useState } from "react";

const SYMBOL_MAP: Record<string, string> = {
  // Crypto
  BTCUSDT: "BINANCE:BTCUSDT",
  ETHUSDT: "BINANCE:ETHUSDT",
  SOLUSDT: "BINANCE:SOLUSDT",
  XRPUSDT: "BINANCE:XRPUSDT",
  ADAUSDT: "BINANCE:ADAUSDT",
  AVAXUSDT: "BINANCE:AVAXUSDT",
  BTC: "BINANCE:BTCUSDT",
  ETH: "BINANCE:ETHUSDT",
  SOL: "BINANCE:SOLUSDT",
  XRP: "BINANCE:XRPUSDT",
  ADA: "BINANCE:ADAUSDT",
  AVAX: "BINANCE:AVAXUSDT",
  DOT: "BINANCE:DOTUSDT",
  LINK: "BINANCE:LINKUSDT",
  // Equities
  SPY: "AMEX:SPY",
  QQQ: "NASDAQ:QQQ",
  AAPL: "NASDAQ:AAPL",
  TSLA: "NASDAQ:TSLA",
  NVDA: "NASDAQ:NVDA",
  AMZN: "NASDAQ:AMZN",
  MSFT: "NASDAQ:MSFT",
  META: "NASDAQ:META",
  GOOGL: "NASDAQ:GOOGL",
  AMD: "NASDAQ:AMD",
  INTC: "NASDAQ:INTC",
  NFLX: "NASDAQ:NFLX",
  PLTR: "NASDAQ:PLTR",
  // Futures
  ES: "CME_MINI:ES1!",
  NQ: "CME_MINI:NQ1!",
  GC: "COMEX:GC1!",
  CL: "NYMEX:CL1!",
};

function mapSymbol(symbol: string): string {
  // Try direct match first
  if (SYMBOL_MAP[symbol]) return SYMBOL_MAP[symbol];
  // Try uppercase
  if (SYMBOL_MAP[symbol.toUpperCase()]) return SYMBOL_MAP[symbol.toUpperCase()];
  // If it already has exchange prefix (e.g. "NASDAQ:AAPL"), use as-is
  if (symbol.includes(":")) return symbol;
  // Default: assume NASDAQ equity
  return `NASDAQ:${symbol.toUpperCase()}`;
}

interface TradingViewChartProps {
  symbol: string;
  height?: number;
  theme?: "dark";
  interval?: string;
  className?: string;
}

function TradingViewChartInner({
  symbol,
  height = 500,
  theme = "dark",
  interval = "60",
  className = "",
}: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    setLoaded(false);

    // Clear previous
    container.innerHTML = "";

    const mappedSymbol = mapSymbol(symbol);

    // Create widget container div
    const widgetContainer = document.createElement("div");
    widgetContainer.className = "tradingview-widget-container";
    widgetContainer.style.height = `${height}px`;
    widgetContainer.style.width = "100%";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    widgetDiv.style.height = "calc(100% - 32px)";
    widgetDiv.style.width = "100%";
    widgetContainer.appendChild(widgetDiv);

    // Copyright div (required by TradingView TOS)
    const copyright = document.createElement("div");
    copyright.className = "tradingview-widget-copyright";
    copyright.innerHTML = `<a href="https://www.tradingview.com/" rel="noopener nofollow" target="_blank"><span class="blue-text" style="font-size:10px;color:#555;">TradingView</span></a>`;
    widgetContainer.appendChild(copyright);

    container.appendChild(widgetContainer);

    // Inject the widget script
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.async = true;
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";

    const config = {
      autosize: true,
      symbol: mappedSymbol,
      interval: interval,
      timezone: "America/New_York",
      theme: "dark",
      style: "1",
      locale: "en",
      backgroundColor: "rgba(8, 8, 8, 1)",
      gridColor: "rgba(21, 21, 21, 1)",
      allow_symbol_change: true,
      hide_volume: false,
      calendar: false,
      support_host: "https://www.tradingview.com",
    };

    script.textContent = JSON.stringify(config);

    script.onload = () => setLoaded(true);
    // Give it a moment then mark loaded anyway (the widget renders before onload fires)
    const timer = setTimeout(() => setLoaded(true), 2000);

    widgetContainer.appendChild(script);

    return () => {
      clearTimeout(timer);
      if (container) container.innerHTML = "";
    };
  }, [symbol, height, theme, interval]);

  return (
    <div className={`relative ${className}`} style={{ height: `${height}px`, width: "100%" }}>
      <div
        ref={containerRef}
        style={{ height: `${height}px`, width: "100%", background: "#080808" }}
      />
      {!loaded && (
        <div
          className="absolute inset-0 flex items-center justify-center"
          style={{ background: "#080808" }}
        >
          <div className="text-center">
            <div
              className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin mx-auto mb-2"
              style={{ borderColor: "#333", borderTopColor: "transparent" }}
            />
            <span className="text-xs font-mono" style={{ color: "#555" }}>
              Loading {mapSymbol(symbol)}...
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

export const TradingViewChart = memo(TradingViewChartInner);
